import dataclasses
import logging
import re
import typing

import asyncpg
import discord

from bot.config import config
from bot.services.context import CommandContextProtocol
from bot.services.results import OperationResult
from bot.utils import converter, exceptions
from bot.utils.exceptions import ForbiddenTask


@dataclasses.dataclass
class PartyMemberCount:
    name: str
    count: int


@dataclasses.dataclass
class PartyRoleResolution:
    role: discord.Role
    created: bool


@dataclasses.dataclass
class PartyJoinRequest:
    request_id: int
    party: converter.PoliticalParty
    member: discord.Member
    leaders: typing.Sequence[typing.Union[discord.Member, discord.User]]


@dataclasses.dataclass
class PartyJoinResult:
    message: str
    request: typing.Optional[PartyJoinRequest] = None


class PartyService:
    def __init__(self, bot):
        self.bot = bot
        self.discord_invite_pattern = re.compile(
            r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?"
        )

    def normalize_invite(self, value: str) -> typing.Optional[str]:
        value = (value or "").strip()
        if value and self.discord_invite_pattern.fullmatch(value):
            return value
        return None

    async def collect_parties_and_members(
        self, *, clean_missing: bool = True
    ) -> typing.List[PartyMemberCount]:
        parties_and_members = []
        error_string = []

        for record in await self.bot.db.fetch("SELECT id FROM party"):
            party_id = record["id"]
            role = self.bot.dciv.get_role(party_id)

            if role is None:
                if clean_missing:
                    await self.bot.db.execute(
                        "DELETE FROM party WHERE id = $1", party_id
                    )
                    error_string.append(str(party_id))
                continue

            parties_and_members.append(
                PartyMemberCount(name=role.name, count=len(role.members))
            )

        if error_string:
            errored = ", ".join(error_string)
            logging.warning(
                "The following ids were added as a party but have no role on the "
                f"Democraciv guild. Records were deleted: {errored}"
            )

        parties_and_members.sort(key=lambda party: party.count, reverse=True)
        return parties_and_members

    async def find_or_create_role(
        self,
        ctx: CommandContextProtocol,
        name: str,
    ) -> PartyRoleResolution:
        role_name = (name or "").strip()
        if not role_name:
            raise exceptions.DemocracivBotException(
                f"{config.NO} The party name cannot be empty."
            )

        role = discord.utils.find(
            lambda candidate: candidate.name.lower() == role_name.lower(),
            self.bot.dciv.roles,
        )
        if role is not None:
            return PartyRoleResolution(role=role, created=False)

        try:
            role = await self.bot.dciv.create_role(name=role_name)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.CREATE_ROLE, role_name
            )

        return PartyRoleResolution(role=role, created=True)

    async def create_party(
        self,
        ctx: CommandContextProtocol,
        *,
        role: discord.Role,
        leader_ids: typing.Sequence[int],
        invite: typing.Optional[str],
        join_mode: str,
        merge: bool = False,
    ) -> converter.PoliticalParty:
        try:
            existing = await converter.PoliticalParty.convert(ctx, role.id)
        except exceptions.NotFoundError:
            existing = None

        if merge and existing is not None:
            return existing

        if not merge and existing is not None:
            raise exceptions.DemocracivBotException(
                f"{config.NO} `{role.name}` already is a political party."
            )

        leader_ids = list(leader_ids) or [0]
        invite = self.normalize_invite(invite)

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute(
                        "INSERT INTO party (id, discord_invite, join_mode) VALUES ($1, $2, $3)"
                        "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, join_mode = $3 WHERE party.id = $1",
                        role.id,
                        invite,
                        join_mode,
                    )
                except asyncpg.UniqueViolationError:
                    raise exceptions.DemocracivBotException(
                        f"{config.NO} `{role.name}` already is a political party."
                    )

                await connection.execute(
                    "INSERT INTO party_alias (party_id, alias) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    role.id,
                    role.name.lower(),
                )

                for leader_id in leader_ids:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        role.id,
                        leader_id,
                    )

        return await converter.PoliticalParty.convert(ctx, role.id)

    async def edit_party(
        self,
        ctx: CommandContextProtocol,
        *,
        party: converter.PoliticalParty,
        new_name: str,
        leader_ids: typing.Sequence[int],
        invite: typing.Optional[str],
        join_mode: str,
    ) -> OperationResult:
        if party.is_independent:
            raise exceptions.DemocracivBotException(
                f"{config.NO} You can't change the Independent party."
            )

        new_name = (new_name or "").strip()
        if not new_name:
            raise exceptions.DemocracivBotException(
                f"{config.NO} Party names cannot be empty."
            )

        if party.role.name != new_name:
            try:
                other = await converter.PoliticalParty.convert(ctx, new_name)
            except exceptions.NotFoundError:
                other = None

            if other is not None and other._id != party._id:
                raise exceptions.DemocracivBotException(
                    f"{config.NO} Another political party is already named `{new_name}`."
                )

            old_name = party.role.name
            await party.role.edit(name=new_name)
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM party_alias WHERE alias = $1",
                        old_name.lower(),
                    )
                    await connection.execute(
                        "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        new_name.lower(),
                        party.role.id,
                    )

        leader_ids = list(leader_ids) or [0]
        invite = self.normalize_invite(invite)

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE party SET discord_invite = $2, join_mode = $3 WHERE id = $1",
                    party.role.id,
                    invite,
                    join_mode,
                )
                await connection.execute(
                    "DELETE FROM party_leader WHERE party_id = $1",
                    party.role.id,
                )
                for leader_id in leader_ids:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        party.role.id,
                        leader_id,
                    )

        return OperationResult(
            message=(
                f"{config.YES} `{new_name}` was edited."
                f"\n{config.HINT} Remember to update https://reddit.com/r/democraciv/wiki accordingly."
            )
        )

    async def delete_party(
        self,
        *,
        party: converter.PoliticalParty,
        delete_role_too: bool,
    ) -> OperationResult:
        name = party.role.name

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM party_alias WHERE party_id = $1", party.role.id
                )
                await connection.execute(
                    "DELETE FROM party_leader WHERE party_id = $1", party.role.id
                )
                await connection.execute(
                    "DELETE FROM party WHERE id = $1", party.role.id
                )

        if delete_role_too and party.role:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.DELETE_ROLE, detail=party.role.name
                )

        return OperationResult(
            message=(
                f"{config.YES} `{name}` and all its aliases were deleted."
                f"\n{config.HINT} Remember to update https://reddit.com/r/democraciv/wiki accordingly."
            )
        )

    async def add_alias(
        self,
        *,
        party: converter.PoliticalParty,
        alias: str,
    ) -> OperationResult:
        alias = (alias or "").lower().strip()
        if not alias:
            raise exceptions.DemocracivBotException(
                f"{config.NO} The alias cannot be empty."
            )

        try:
            await self.bot.db.execute(
                "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                alias,
                party.role.id,
            )
        except asyncpg.UniqueViolationError:
            raise exceptions.DemocracivBotException(
                f"{config.NO} `{alias}` is already an alias for `{party.role.name}`."
            )

        return OperationResult(
            message=(
                f"{config.YES} Alias `{alias}` for party `{party.role.name}` was added."
            )
        )

    async def remove_alias(
        self,
        ctx: CommandContextProtocol,
        *,
        alias: str,
    ) -> OperationResult:
        alias = (alias or "").lower().strip()

        try:
            await converter.PoliticalParty.convert(ctx, alias)
        except exceptions.NotFoundError:
            raise exceptions.DemocracivBotException(
                f"{config.NO} `{alias}` is not an alias of any party."
            )

        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias)
        return OperationResult(
            message=(
                f"{config.YES} Alias `{alias}` was deleted.\n{config.HINT} If you "
                f"want to delete all aliases of a party, consider using the "
                f"`{config.BOT_PREFIX}party clearalias` command instead."
            )
        )

    async def clear_aliases(
        self, *, party: converter.PoliticalParty
    ) -> OperationResult:
        for alias in party.aliases:
            if alias == party.role.name.lower():
                continue
            await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias)

        return OperationResult(
            message=f"{config.YES} All aliases of `{party.role.name}` were deleted."
        )

    async def leave_party(
        self,
        ctx: CommandContextProtocol,
        *,
        party: converter.PoliticalParty,
    ) -> OperationResult:
        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            raise exceptions.DemocracivBotException(
                f"{config.NO} You're not in the {self.bot.dciv.name} server."
            )

        if party.role not in person_in_dciv.roles:
            raise exceptions.DemocracivBotException(
                f"{config.NO} You are not part of {party.role.name}."
            )

        try:
            await person_in_dciv.remove_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                ForbiddenTask.REMOVE_ROLE, detail=party.role.name
            )

        if party.role.name == "Independent":
            msg = f"{config.YES} You are no longer an {party.role.name}."
        else:
            msg = f"{config.YES} You left {party.role.name}."

        return OperationResult(message=msg)

    async def join_party(
        self,
        ctx: CommandContextProtocol,
        *,
        party: converter.PoliticalParty,
    ) -> PartyJoinResult:
        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            raise exceptions.DemocracivBotException(
                f"{config.NO} You're not in the {self.bot.dciv.name} server."
            )

        if party.role in person_in_dciv.roles:
            raise exceptions.DemocracivBotException(
                f"{config.NO} You're already part of `{party.role.name}`."
            )

        if party.join_mode is converter.PoliticalPartyJoinMode.PRIVATE:
            if person_in_dciv in party.leaders:
                await self._add_party_role(person_in_dciv, party)
                return PartyJoinResult(
                    message=(
                        f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                        "*As you're a leader of this party, you ignored this "
                        "party's join mode of `Private`.*"
                    )
                )

            raise exceptions.DemocracivBotException(
                f"{config.NO} {party.role.name} is a private party. Contact the party leaders for further information."
            )

        if party.join_mode is converter.PoliticalPartyJoinMode.REQUEST:
            if person_in_dciv in party.leaders:
                await self._add_party_role(person_in_dciv, party)
                return PartyJoinResult(
                    message=(
                        f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                        "*As you're a leader of this party, you skipped the request step.*"
                    )
                )

            existing_request = await self.bot.db.fetchrow(
                "SELECT * FROM party_join_request WHERE party_id = $1 AND requesting_member = $2",
                party.role.id,
                ctx.author.id,
            )
            if existing_request:
                raise exceptions.DemocracivBotException(
                    f"{config.NO} You already requested to join `{party.role.name}`. "
                    "Once the leaders accept or deny your request, I will notify you."
                )

            if not party.leaders:
                raise exceptions.DemocracivBotException(
                    f"{config.NO} I was not told who `{party.role.name}`'s leaders are, so "
                    f"I can't send your join request to anyone. Please tell {self.bot.dciv.name} "
                    f"Moderation to add the leaders with `{config.BOT_PREFIX}party edit "
                    f"{party.role.name}`, then try again."
                )

            request_id = await self.bot.db.fetchval(
                "INSERT INTO party_join_request (party_id, requesting_member) VALUES ($1, $2) RETURNING id",
                party.role.id,
                ctx.author.id,
            )
            leaders_fmt = ", ".join(f"`{leader}`" for leader in party.leaders)
            return PartyJoinResult(
                message=(
                    f"{config.YES} Your request to join `{party.role.name}` was sent to "
                    f"their leaders ({leaders_fmt}). Once they accept or deny your "
                    "request, I'll notify you."
                ),
                request=PartyJoinRequest(
                    request_id=request_id,
                    party=party,
                    member=person_in_dciv,
                    leaders=party.leaders,
                ),
            )

        await self._add_party_role(person_in_dciv, party)

        if party.role.name == "Independent":
            return PartyJoinResult(
                message=f"{config.YES} You are now an {party.role.name}."
            )

        message = f"{config.YES} You've joined {party.role.name}."
        if party.discord_invite:
            message = (
                f"{message} Now head to their Discord Server and introduce yourself: "
                f"{party.discord_invite}"
            )

        return PartyJoinResult(message=message)

    async def record_join_request_message(self, *, request_id: int, message_id: int):
        await self.bot.db.execute(
            "INSERT INTO party_join_request_message (request_id, message_id) VALUES ($1, $2)",
            request_id,
            message_id,
        )

    async def _add_party_role(
        self,
        member: discord.Member,
        party: converter.PoliticalParty,
    ):
        try:
            await member.add_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

    async def finish_merge(
        self,
        *,
        new_party: converter.PoliticalParty,
        old_parties: typing.Sequence[converter.PoliticalParty],
    ) -> OperationResult:
        members_to_merge = set()
        for party in old_parties:
            if party.role is not None:
                members_to_merge.update(party.role.members)

        for member in members_to_merge:
            try:
                await member.add_roles(new_party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.ADD_ROLE,
                    new_party.role.name,
                )

        for party in old_parties:
            if party.role.id == new_party.role.id:
                continue

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM party WHERE id = $1", party.role.id
                    )
                    await connection.execute(
                        "DELETE FROM party_alias WHERE party_id = $1",
                        party.role.id,
                    )
                    await connection.execute(
                        "DELETE FROM party_leader WHERE party_id = $1",
                        party.role.id,
                    )

            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.DELETE_ROLE,
                    detail=party.role.name,
                )

        return OperationResult(
            message=(
                f"{config.YES} The old parties were deleted and all their members "
                f"now have the role of `{new_party.role.name}`."
            )
        )
