import asyncio
import typing
import discord

from discord.ext import commands

from bot.config import config
from bot.presenters import parties as party_presenter, party_forms
from bot.services.parties import PartyService
from bot.utils import exceptions, checks, converter, context, text
from bot.utils.converter import (
    PoliticalParty,
    Fuzzy,
)
from bot.utils.context import MockContext


def _split_lines(value: str) -> typing.List[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class Party(context.CustomCog, name="Political Parties"):
    """Interact with the political parties of {NATION_NAME}."""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = PartyService(bot)
        self._party_lock = asyncio.Lock()

    async def collect_parties_and_members(self):
        """Returns all parties with a role on the Democraciv server and their amount of members for -members."""
        return await self.service.collect_parties_and_members()

    @commands.group(
        name="party", aliases=["p"], case_insensitive=True, invoke_without_command=True
    )
    async def party(self, ctx, *, party: Fuzzy[PoliticalParty] = None):
        """Detailed information about a single political party"""

        if party is None:
            return await ctx.invoke(self.bot.get_command("parties"))

        embed = await party_presenter.build_party_embed(ctx, party)
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def party_join_request_listener(
        self, payload: discord.RawReactionActionEvent
    ):
        if payload.guild_id:  # only ever happens in DMs
            return

        query = """SELECT party_join_request.id, party_join_request.party_id, party_join_request.requesting_member
                   FROM party_join_request, party_join_request_message
                   WHERE party_join_request_message.request_id = party_join_request.id
                   AND party_join_request_message.message_id = $1"""

        async with self._party_lock:
            request_match = await self.bot.db.fetchrow(query, payload.message_id)

            if not request_match:
                return

            yes_emoji = config.YES
            no_emoji = config.NO

            reactor = self.bot.get_user(payload.user_id)

            try:
                party = await PoliticalParty.convert(
                    MockContext(self.bot), request_match["party_id"]
                )
            except commands.BadArgument:
                return

            member = self.bot.dciv.get_member(request_match["requesting_member"])

            if not party or not party.role or not member:
                return

            if payload.user_id not in [leader.id for leader in party.leaders]:
                return

            if str(payload.emoji) == yes_emoji:
                try:
                    await member.add_roles(party.role)
                except discord.Forbidden:
                    return await reactor.send(
                        f"{config.NO} I don't have `Manage Roles` permissions "
                        f"on the {self.bot.dciv.name} server, so unfortunately I cannot give "
                        f"`{member}` your party's role. Please contact Moderation."
                    )

                message = (
                    f"{config.HINT}  {member.display_name}'s request to join {party.role.name} was "
                    f"accepted by {reactor.display_name}."
                )

                if party.discord_invite:
                    invite_fmt = f"\n\nGo ahead and join their Discord server if you haven't already: {party.discord_invite}"
                else:
                    invite_fmt = ""

                member_embed = text.SafeEmbed(
                    title=f"{yes_emoji}  Party Join Request Accepted",
                    description=f"Your request to join **{party.role.name}** was accepted by "
                    f"{reactor}.{invite_fmt}",
                )

            elif str(payload.emoji) == no_emoji:
                message = (
                    f"{config.HINT}  {member.display_name}'s request to join {party.role.name} was "
                    f"denied by {reactor.display_name}."
                )

                member_embed = text.SafeEmbed(
                    title=f"{no_emoji}  Party Join Request Denied",
                    description=f"Your request to join **{party.role.name}** was denied by {reactor}.",
                )

            else:
                return

            await self.bot.db.execute(
                "DELETE FROM party_join_request WHERE id = $1", request_match["id"]
            )
            await member.send(embed=member_embed)

            leaders_without_reactor = [
                l.id for l in party.leaders if l.id != reactor.id
            ]

            for leader in leaders_without_reactor:
                try:
                    leader_obj = self.bot.get_user(leader)

                    if leader_obj:
                        await leader_obj.send(embed=text.SafeEmbed(title=message))
                except discord.Forbidden:
                    continue

    @commands.Cog.listener(name="on_member_update")
    async def party_join_leave_notification(self, before, after):
        if before.guild.id != self.bot.dciv.id or before.roles == after.roles:
            return

        possible_party = None
        message = ""

        if len(before.roles) < len(after.roles):
            # joined party
            for role in after.roles:
                if role not in before.roles:
                    possible_party = role
                    message = f"{config.JOIN}  {before.display_name} just joined your political party **{role.name}**."
                    break

        else:
            # left party
            for role in before.roles:
                if role not in after.roles:
                    possible_party = role
                    message = f"{config.LEAVE}  {before.display_name} just left your political party **{role.name}**."
                    break

        if not possible_party or not message:
            return

        try:
            party = await PoliticalParty.convert(
                MockContext(self.bot), possible_party.id
            )
        except exceptions.NotFoundError:
            return

        embed = text.SafeEmbed(description=message)
        embed.set_author(name=before, icon_url=before.display_avatar.url)

        for leader in party.leaders:
            if leader.id == before.id:
                continue

            await self.bot.safe_send_dm(
                target=leader, embed=embed, reason="party_join_leave"
            )

    @party.command(name="join", hidden=True)
    @checks.is_citizen_if_multiciv()
    async def _join_alias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Join a political party"""
        return await ctx.invoke(self.bot.get_command("join"), party=party)

    @commands.command(name="join")
    @checks.is_citizen_if_multiciv()
    async def join(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Join a political party"""

        result = await self.service.join_party(ctx, party=party)
        await ctx.send(result.message)

        if result.request:
            for leader in result.request.leaders:
                try:
                    embed = party_presenter.build_join_request_embed(
                        ctx, result.request, leader
                    )
                    message = await leader.send(embed=embed)
                    await message.add_reaction(config.YES)
                    await message.add_reaction(config.NO)

                except discord.Forbidden:
                    continue

                await self.service.record_join_request_message(
                    request_id=result.request.request_id,
                    message_id=message.id,
                )

    @party.command(name="leave", hidden=True)
    @checks.is_citizen_if_multiciv()
    async def _leave_alias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Leave a political party"""
        return await ctx.invoke(self.bot.get_command("leave"), party=party)

    @commands.command(name="leave")
    @checks.is_citizen_if_multiciv()
    async def leave(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Leave a political party"""

        result = await self.service.leave_party(ctx, party=party)
        await ctx.send(result.message)

    @commands.command(
        name="parties",
        aliases=["rank", "ranks", "members", "member", "rankings", "ranking"],
    )
    async def parties(self, ctx, *, party: Fuzzy[PoliticalParty] = None):
        """Ranking of political parties by their amount of members"""

        if party:
            return await ctx.invoke(self.bot.get_command("party"), party=party)

        sorted_parties_and_members = await self.collect_parties_and_members()
        embed = party_presenter.build_party_list_embed(ctx, sorted_parties_and_members)
        await ctx.send(embed=embed)

    async def _prompt_party_form(
        self,
        ctx: context.CustomContext,
        *,
        modal_factory: typing.Callable[[], party_forms.PartyModal],
        button_label: str,
        prompt: str,
    ) -> typing.Optional[party_forms.PartyFormResult]:
        view = text.ModalPromptView(
            ctx,
            modal_factory=modal_factory,
            button_label=button_label,
            timeout=300,
        )
        return await view.prompt_message(prompt)

    async def _resolve_leader_ids(
        self,
        ctx: context.CustomContext,
        leaders_text: str,
    ) -> typing.List[int]:
        leaders = []
        conv = Fuzzy[converter.CaseInsensitiveMember]

        for line in _split_lines(leaders_text):
            try:
                converted = await conv.convert(ctx, line)
            except commands.BadArgument:
                continue

            if not converted.bot:
                leaders.append(converted.id)

        return leaders or [0]

    async def _resolve_parties(
        self,
        ctx: context.CustomContext,
        parties_text: str,
    ) -> typing.List[PoliticalParty]:
        parties = {}
        conv = Fuzzy[PoliticalParty]

        for line in _split_lines(parties_text):
            try:
                party = await conv.convert(ctx, line)
            except (exceptions.DemocracivBotException, commands.BadArgument) as error:
                message = getattr(error, "message", str(error))
                raise exceptions.DemocracivBotException(message)

            parties[party._id] = party

        return list(parties.values())

    async def _create_party_from_form(
        self,
        ctx: context.CustomContext,
        form: party_forms.PartyFormResult,
        *,
        merge: bool = False,
    ) -> PoliticalParty:
        resolution = await self.service.find_or_create_role(ctx, form.role_name)

        if resolution.created:
            await ctx.send(
                f"{config.YES} I will **create a new role** on this server named `{resolution.role.name}`"
                " for the new party."
            )
        elif merge:
            try:
                existing_party = await PoliticalParty.convert(ctx, resolution.role.id)
            except exceptions.NotFoundError:
                existing_party = None

            if existing_party is not None:
                await ctx.send(
                    f"{config.YES} I'll use the **already existing** party `{resolution.role.name}` "
                    "to merge the others into."
                )
                return existing_party

            await ctx.send(
                f"{config.YES} I'll use the **pre-existing role** `{resolution.role.name}` for the new party."
            )

        else:
            await ctx.send(
                f"{config.YES} I'll use the **pre-existing role** `{resolution.role.name}` for the new party."
            )

        leaders = await self._resolve_leader_ids(ctx, form.leaders_text)
        return await self.service.create_party(
            ctx,
            role=resolution.role,
            leader_ids=leaders,
            invite=form.invite,
            join_mode=form.join_mode,
            merge=merge,
        )

    @party.command(name="add", aliases=["create", "make"])
    @checks.moderation_or_nation_leader()
    async def addparty(self, ctx):
        """Add a new political party"""

        if "alias" in ctx.message.content.lower():
            return await ctx.send(
                f"{config.HINT} Did you mean the `{config.BOT_PREFIX}party addalias` command?"
            )

        form = await self._prompt_party_form(
            ctx,
            modal_factory=party_forms.PartyCreateModal,
            button_label="Create Party",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Fill out the party details in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        party = await self._create_party_from_form(ctx, form)
        await ctx.send(
            f"{config.YES} `{party.role.name}` was added as a new Political Party."
            f"\n{config.HINT} Add abbreviations, acronyms and different spellings for **easier typing** with: `{config.BOT_PREFIX}party addalias {party.role.name}`"
            f"\n{config.HINT} Remember to update <https://reddit.com/r/democraciv/wiki> accordingly."
        )

    @party.command(name="edit", aliases=["change"])
    @checks.moderation_or_nation_leader()
    async def changeparty(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Edit an existing political party

        **Example**
            `{PREFIX}{COMMAND} Ecological Democratic Union`
            `{PREFIX}{COMMAND} scp`
            `{PREFIX}{COMMAND} progressive union`"""

        if party.is_independent:
            return await ctx.send(
                f"{config.NO} You can't change the Independent party."
            )

        form = await self._prompt_party_form(
            ctx,
            modal_factory=lambda: party_forms.PartyEditModal(party=party),
            button_label="Edit Party",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Update `{party.role.name}` in the form. "
                "Leave pre-filled values unchanged to keep them."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        leaders = await self._resolve_leader_ids(ctx, form.leaders_text)

        result = await self.service.edit_party(
            ctx,
            party=party,
            new_name=form.role_name,
            leader_ids=leaders,
            invite=form.invite,
            join_mode=form.join_mode,
        )
        await ctx.send(result.message)

    @party.command(name="delete", aliases=["remove"])
    @checks.moderation_or_nation_leader()
    async def deleteparty(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Delete a political party

        **Usage**
         `{PREFIX}{COMMAND} <party>`
        """

        if "alias" in ctx.message.content.lower():
            return await ctx.send(
                f"{config.HINT} Did you mean the `{config.BOT_PREFIX}party deletealias` command?"
            )

        delete_role_too = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} I will remove `{party.role.name}` from the list of "
            f"parties. Should I delete their Discord role too?"
        )

        result = await self.service.delete_party(
            party=party, delete_role_too=delete_role_too
        )
        await ctx.send(result.message)

    @party.command(name="addalias", aliases=["alias"])
    @checks.moderation_or_nation_leader()
    async def addalias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Add a new alias to a political party"""

        form = await self._prompt_party_form(
            ctx,
            modal_factory=lambda: party_forms.PartyAliasModal(party=party),
            button_label="Add Alias",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Add an alias for `{party.role.name}` in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        alias = form.alias
        if not alias:
            return

        result = await self.service.add_alias(party=party, alias=alias)
        await ctx.send(result.message)

    @party.command(name="deletealias", aliases=["removealias"])
    @checks.moderation_or_nation_leader()
    async def deletealias(self, ctx, *, alias: str):
        """Delete a party's alias"""
        result = await self.service.remove_alias(ctx, alias=alias)
        await ctx.send(result.message)

    @party.command(name="clearalias")
    @checks.moderation_or_nation_leader()
    async def clearalias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Delete all aliases of a party"""

        sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to "
            f"delete all aliases of `{party.role.name}`?"
        )

        if not sure:
            return await ctx.send("Cancelled.")

        result = await self.service.clear_aliases(party=party)
        await ctx.send(result.message)

    @party.command(name="merge")
    @checks.moderation_or_nation_leader()
    async def mergeparties(self, ctx, amount_of_parties: int = None):
        """Merge multiple parties into a single, new party"""

        form = await self._prompt_party_form(
            ctx,
            modal_factory=party_forms.PartyMergeModal,
            button_label="Merge Parties",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Fill out the merge details in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        to_be_merged = await self._resolve_parties(ctx, form.parties_text)
        pretty_parties = [f"`{party.role.name}`" for party in to_be_merged]

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to merge"
            f" {', '.join(pretty_parties)} into one, new party?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        if len(to_be_merged) < 2:
            return await ctx.send(
                f"{config.NO} You have to merge at least 2 parties, you can't merge just one."
            )

        try:
            new_party = await self._create_party_from_form(ctx, form, merge=True)
        except exceptions.DemocracivBotException as e:
            return await ctx.send(
                f"{e.message}\n{config.NO} Party creation failed, old parties were not deleted."
            )

        if new_party is None or new_party.role is None:
            return await ctx.send(
                f"{config.NO} Party creation failed, old parties were not deleted."
            )

        async with ctx.typing():
            result = await self.service.finish_merge(
                new_party=new_party,
                old_parties=to_be_merged,
            )

        await ctx.send(
            f"{result.message}\n{config.HINT} Remember to update <https://reddit.com/r/democraciv/wiki> accordingly."
        )


async def setup(bot):
    await bot.add_cog(Party(bot))
