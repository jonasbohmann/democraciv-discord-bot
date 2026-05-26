import dataclasses
import typing

import asyncpg
import discord

from bot.config import config
from bot.services.context import CommandContextProtocol
from bot.utils import exceptions


@dataclasses.dataclass
class NPCWriteResult:
    message: str
    record: typing.Optional[typing.Mapping] = None


class NPCService:
    def __init__(self, bot):
        self.bot = bot

    @property
    def legacy_cog(self):
        return self.bot.get_cog("NPC")

    def validate_name(self, name: str) -> str:
        name = (name or "").strip()

        if not name:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} The name cannot be empty."
            )

        if name.lower() == self.bot.user.name.lower():
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You can't have an NPC that is named after me."
            )

        if len(name) > 80:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} The name cannot be longer than 80 characters."
            )

        return name

    def validate_trigger_phrase(self, trigger_phrase: str) -> str:
        trigger_phrase = (trigger_phrase or "").strip().lower()
        bot_prefixes = tuple(config.BOT_ADDITIONAL_PREFIXES)

        if trigger_phrase == "text":
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to surround the word `text` with a prefix and/or suffix."
            )

        if trigger_phrase.startswith(bot_prefixes):
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Your trigger phrase can't have any of my bot prefixes at the beginning."
            )

        if "text" not in trigger_phrase:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to include the word `text` in your trigger phrase."
            )

        prefix, suffix = trigger_phrase.split("text", maxsplit=1)
        if not prefix and not suffix:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to surround the word `text` with a prefix and/or suffix."
            )

        return trigger_phrase

    def normalize_avatar_url(self, avatar_url: str) -> typing.Optional[str]:
        avatar_url = (avatar_url or "").strip()
        if avatar_url.lower().startswith("http"):
            return avatar_url
        return None

    def _cache_npc(self, record):
        if self.legacy_cog is None:
            return

        self.legacy_cog._npc_cache[record["id"]] = dict(record)
        self.legacy_cog._npc_access_cache[record["owner_id"]].add(record["id"])

    async def refresh_caches(self):
        if self.legacy_cog is None:
            return

        await self.legacy_cog._load_npc_cache()
        await self.legacy_cog._load_automatic_trigger_cache()

    def list_accessible_records(self, member) -> typing.List[typing.Mapping]:
        if self.legacy_cog is None:
            return []

        records = []
        for npc_id in self.legacy_cog._npc_access_cache[member.id]:
            try:
                records.append(self.legacy_cog._npc_cache[npc_id])
            except KeyError:
                continue

        records.sort(key=lambda record: record["id"])
        return records

    def has_access(self, member, npc) -> bool:
        if self.legacy_cog is None:
            return False

        return npc.id in self.legacy_cog._npc_access_cache[member.id]

    async def get_allowed_people(
        self, npc
    ) -> typing.List[typing.Union[discord.Member, discord.User]]:
        records = await self.bot.db.fetch(
            "SELECT user_id FROM npc_allowed_user WHERE npc_id = $1",
            npc.id,
        )
        people = []

        for record in records:
            user = self.bot.dciv.get_member(record["user_id"]) or self.bot.get_user(
                record["user_id"]
            )
            if user:
                people.append(user)

        return people

    async def get_automatic_channels(self, ctx: CommandContextProtocol, npc):
        if ctx.guild is None:
            return []

        records = await self.bot.db.fetch(
            "SELECT channel_id FROM npc_automatic_mode WHERE user_id = $1 AND guild_id = $2 AND npc_id = $3",
            ctx.author.id,
            ctx.guild.id,
            npc.id,
        )
        channels = []

        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel:
                channels.append(channel)

        return channels

    async def get_automatic_overview_records(self, ctx: CommandContextProtocol):
        return await self.bot.db.fetch(
            "SELECT npc_automatic_mode.npc_id, npc_automatic_mode.channel_id FROM npc_automatic_mode "
            "WHERE npc_automatic_mode.user_id = $1 "
            "AND npc_automatic_mode.guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )

    async def create_npc(
        self,
        ctx: CommandContextProtocol,
        *,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ) -> NPCWriteResult:
        name = self.validate_name(name)
        avatar_url = self.normalize_avatar_url(avatar_url)
        trigger_phrase = self.validate_trigger_phrase(trigger_phrase)

        try:
            npc_record = await self.bot.db.fetchrow(
                "INSERT INTO npc (name, avatar_url, owner_id, trigger_phrase) VALUES ($1, $2, $3, $4) RETURNING *",
                name,
                avatar_url,
                ctx.author.id,
                trigger_phrase,
            )
        except asyncpg.UniqueViolationError:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You already have an NPC with either that same name, or that same trigger phrase."
            )

        self._cache_npc(npc_record)
        example = trigger_phrase.replace("text", "Hello!")
        return NPCWriteResult(
            message=(
                f"{config.YES} The NPC #{npc_record['id']} `{name}` was created. "
                f"Try speaking as them with `{example}`."
            ),
            record=npc_record,
        )

    async def edit_npc(
        self,
        *,
        npc,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ) -> NPCWriteResult:
        name = self.validate_name(name)
        avatar_url = self.normalize_avatar_url(avatar_url)
        trigger_phrase = self.validate_trigger_phrase(trigger_phrase)

        try:
            new_npc = await self.bot.db.fetchrow(
                "UPDATE npc SET name = $1, avatar_url = $2, trigger_phrase = $3 WHERE id = $4 RETURNING *",
                name,
                avatar_url,
                trigger_phrase,
                npc.id,
            )
        except asyncpg.UniqueViolationError:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You already have a different NPC with either that same new name, or that same new trigger phrase."
            )

        if self.legacy_cog is not None:
            self.legacy_cog._npc_cache[npc.id] = dict(new_npc)

        return NPCWriteResult(
            message=f"{config.YES} Your NPC was edited.", record=new_npc
        )

    async def delete_npc(self, ctx: CommandContextProtocol, *, npc) -> NPCWriteResult:
        await self.bot.db.execute(
            "DELETE FROM npc WHERE id = $1 AND owner_id = $2",
            npc.id,
            ctx.author.id,
        )
        await self.refresh_caches()
        return NPCWriteResult(message=f"{config.YES} `{npc.name}` was deleted.")

    async def update_access(
        self,
        *,
        npc,
        people: typing.Sequence[discord.Member],
        add: bool,
    ) -> NPCWriteResult:
        people = [
            person
            for person in people
            if not getattr(person, "bot", False) and person.id != npc.owner_id
        ]

        if not people:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} No valid people were specified."
            )

        for person in people:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO npc_allowed_user (npc_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    npc.id,
                    person.id,
                )
                if self.legacy_cog is not None:
                    self.legacy_cog._npc_access_cache[person.id].add(npc.id)
            else:
                await self.bot.db.execute(
                    "DELETE FROM npc_allowed_user WHERE npc_id = $1 AND user_id = $2",
                    npc.id,
                    person.id,
                )
                if self.legacy_cog is not None:
                    self.legacy_cog._npc_access_cache[person.id].discard(npc.id)

        message = (
            f"{config.YES} Those people can now speak as your NPC `{npc.name}`."
            if add
            else f"{config.YES} Those people can no longer speak as your NPC `{npc.name}`."
        )
        return NPCWriteResult(message=message)

    async def update_automatic(
        self,
        ctx: CommandContextProtocol,
        *,
        npc,
        channels: typing.Sequence[
            typing.Union[discord.TextChannel, discord.CategoryChannel]
        ],
        add: bool,
    ) -> NPCWriteResult:
        if not channels:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Something went wrong, you didn't specify anything."
            )

        for channel in channels:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO npc_automatic_mode (npc_id, user_id, channel_id, guild_id) "
                    "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                    npc.id,
                    ctx.author.id,
                    channel.id,
                    ctx.guild.id,
                )
                if self.legacy_cog is not None:
                    self.legacy_cog._automatic_npc_cache[ctx.author.id][
                        channel.id
                    ] = npc.id
            else:
                await self.bot.db.execute(
                    "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND channel_id = $3",
                    npc.id,
                    ctx.author.id,
                    channel.id,
                )
                if self.legacy_cog is not None:
                    self.legacy_cog._automatic_npc_cache[ctx.author.id].pop(
                        channel.id,
                        None,
                    )

        message = (
            f"{config.YES} You will now automatically speak as your NPC `{npc.name}` in those channels or categories."
            if add
            else f"{config.YES} You will no longer automatically speak as your NPC `{npc.name}` in those channels or categories."
        )
        return NPCWriteResult(message=message)

    async def clear_automatic(
        self,
        ctx: CommandContextProtocol,
        *,
        npc,
    ) -> NPCWriteResult:
        channels = await self.bot.db.fetch(
            "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND guild_id = $3 RETURNING channel_id",
            npc.id,
            ctx.author.id,
            ctx.guild.id,
        )

        if self.legacy_cog is not None:
            for record in channels:
                self.legacy_cog._automatic_npc_cache[ctx.author.id].pop(
                    record["channel_id"],
                    None,
                )

        return NPCWriteResult(
            message=(
                f"{config.YES} You will no longer automatically speak as your NPC "
                f"`{npc.name}` in any channel on this server."
            )
        )
