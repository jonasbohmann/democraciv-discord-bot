import asyncio
import collections
import logging
import re
import typing
import asyncpg
import discord

from discord.ext import commands, menus
from discord.utils import escape_markdown

from bot.config import config
from bot.utils import exceptions, checks, converter, context, text
from bot.utils.context import CustomContext
from bot.utils.converter import (
    PoliticalParty,
    PoliticalPartyJoinMode,
    Fuzzy,
)
from bot.utils.context import MockContext
from bot.utils.exceptions import ForbiddenTask


class SelectJoinModeView(text.PromptView):
    @discord.ui.select(
        options=[
            discord.SelectOption(
                label="Public",
                value="Public",
                description="Everyone can join",
                emoji="\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467",
            ),
            discord.SelectOption(
                label="Request",
                value="Request",
                description="Everyone can ask to join & leaders can accept/deny",
                emoji="\U0001f4e9",
            ),
            discord.SelectOption(
                label="Private",
                value="Private",
                description="No one can join & moderation has to give role out",
                emoji="\U0001f575",
            ),
        ]
    )
    async def select(self, component, interaction):
        self.result = component.values[0]
        self.stop()


class Party(context.CustomCog, name="Political Parties"):
    """Interact with the political parties of {NATION_NAME}."""

    def __init__(self, bot):
        super().__init__(bot)
        self._party_lock = asyncio.Lock()
        self.discord_invite_pattern = re.compile(
            r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?"
        )

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv server and their amount of members for -members."""
        parties_and_members = []

        parties = await self.bot.db.fetch("SELECT id FROM party")
        error_string = []

        for record in parties:
            party_id = record["id"]
            role = self.bot.dciv.get_role(party_id)

            if role is None:
                await self.bot.db.execute("DELETE FROM party WHERE id = $1", party_id)
                error_string.append(str(party_id))
                continue

            parties_and_members.append((role.name, len(role.members)))

        if error_string:
            errored = ", ".join(error_string)
            logging.warning(
                f"The following ids were added as a party but have no role on the Democraciv guild. "
                f"Records were deleted: {errored}"
            )

        parties_and_members.sort(key=lambda x: x[1], reverse=True)
        return parties_and_members

    @commands.group(
        name="party", aliases=["p"], case_insensitive=True, invoke_without_command=True
    )
    async def party(self, ctx, *, party: Fuzzy[PoliticalParty] = None):
        """Detailed information about a single political party"""

        if party is None:
            return await ctx.invoke(self.bot.get_command("parties"))

        embed = text.SafeEmbed()
        logo = await party.get_logo()
        embed.set_author(
            name=party.role.name, icon_url=logo or self.bot.mk.NATION_ICON_URL
        )

        if not party.is_independent:
            embed.description = (
                f"[Platform and Description]({self.bot.mk.POLITICAL_PARTIES})\nJoin this party with "
                f"`{config.BOT_PREFIX}join {min(party.aliases, key=len)}`."
            )
            members_name = "Members"

            if logo:
                embed.set_thumbnail(url=logo)

            invite_value = party.discord_invite if party.discord_invite else "*N/A*"
            embed.add_field(name="Server", value=invite_value)
            embed.add_field(name="Join Setting", value=party.join_mode.value)

            aliases = party.aliases

            try:
                aliases.remove(party.role.name.lower())
            except ValueError:
                pass

            embed.add_field(
                name="Aliases",
                value=", ".join([f"`{alias}`" for alias in aliases]) or "-",
                inline=False,
            )
        else:
            embed.description = (
                f"These people have decided to remain Independent and to not join any "
                f"political party. Become an Independent with "
                f"`{config.BOT_PREFIX}join {party.role.name}`."
                f"\n\n[Overview of existing Political Parties]({self.bot.mk.POLITICAL_PARTIES})"
            )

            members_name = "Independents"

        party_members = [
            f"{member.mention} {escape_markdown(str(member))}"
            for member in party.role.members
            if member.id not in party.leader_ids
        ]

        for i, leader in enumerate(party.leaders):
            if leader in party.role.members:
                party_members.insert(
                    i, f"{leader.mention} **{escape_markdown(str(leader))} (Leader)**"
                )

        embed.add_field(
            name=f"{members_name} ({len(party.role.members)})",
            value="\n".join(party_members or ["-"]),
            inline=False,
        )

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

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(
                f"{config.NO} You're not in the {self.bot.dciv.name} server."
            )

        if party.role in person_in_dciv.roles:
            return await ctx.send(
                f"{config.NO} You're already part of `{party.role.name}`."
            )

        if party.join_mode is PoliticalPartyJoinMode.PRIVATE:
            if person_in_dciv in party.leaders:

                try:
                    await person_in_dciv.add_roles(party.role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(
                        ForbiddenTask.ADD_ROLE, party.role.name
                    )

                return await ctx.send(
                    f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                    f"*As you're a leader of this party, you ignored this party's join mode of `Private`.*\n"
                )

            return await ctx.send(
                f"{config.NO} {party.role.name} is a private party. Contact the party leaders for further information."
            )

        elif party.join_mode is PoliticalPartyJoinMode.REQUEST:
            if person_in_dciv in party.leaders:

                try:
                    await person_in_dciv.add_roles(party.role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(
                        ForbiddenTask.ADD_ROLE, party.role.name
                    )

                return await ctx.send(
                    f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                    f"*As you're a leader of this party, you skipped the request step.*\n"
                )

            query = """SELECT * FROM party_join_request WHERE party_id = $1 AND requesting_member = $2"""
            existing_request = await self.bot.db.fetchrow(
                query, party.role.id, ctx.author.id
            )

            if existing_request:
                return await ctx.send(
                    f"{config.NO} You already requested to join `{party.role.name}`. Once the leaders "
                    f"accept or deny your request, I will notify you."
                )

            if not party.leaders:
                return await ctx.send(
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

            fmt_leader = ", ".join([f"`{leader}`" for leader in party.leaders])

            await ctx.send(
                f"{config.YES} Your request to join `{party.role.name}` was sent to their leaders ({fmt_leader}). "
                f"Once they accept or deny your request, I'll notify you."
            )

            for leader in party.leaders:
                try:
                    other_leaders = party.leaders
                    other_leaders.remove(leader)

                    if other_leaders:
                        other_leaders_fmt = ", ".join(
                            [f"`{le}`" for le in other_leaders]
                        )
                        other_help = (
                            f"\nThe other party leaders, {other_leaders_fmt}, also received this message. "
                            f"Once any of you either accept or deny, that is the final decision."
                        )

                    else:
                        other_help = ""

                    embed = text.SafeEmbed(
                        title=f"Request to join {party.role.name}",
                        description=f"{ctx.author.display_name} wants to join your political "
                        f"party **{party.role.name}**. Do you want to accept "
                        f"their request?\n\n{config.HINT} This has no timeout, so "
                        f"you don't have to decide immediately.{other_help}",
                    )

                    embed.set_author(name=ctx.author, icon_url=ctx.author_icon)

                    message = await leader.send(embed=embed)
                    await message.add_reaction(config.YES)
                    await message.add_reaction(config.NO)

                except discord.Forbidden:
                    continue

                await self.bot.db.execute(
                    "INSERT INTO party_join_request_message (request_id, message_id) VALUES ($1, $2)",
                    request_id,
                    message.id,
                )

            return

        elif party.join_mode is PoliticalPartyJoinMode.PUBLIC:
            try:
                await person_in_dciv.add_roles(party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

            if party.role.name == "Independent":
                return await ctx.send(f"{config.YES} You are now an {party.role.name}.")

            message = f"{config.YES} You've joined {party.role.name}."

            if party.discord_invite:
                message = f"{message} Now head to their Discord Server and introduce yourself: {party.discord_invite}"

            await ctx.send(message)

    @party.command(name="leave", hidden=True)
    @checks.is_citizen_if_multiciv()
    async def _leave_alias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Leave a political party"""
        return await ctx.invoke(self.bot.get_command("leave"), party=party)

    @commands.command(name="leave")
    @checks.is_citizen_if_multiciv()
    async def leave(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Leave a political party"""

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(
                f"{config.NO} You're not in the {self.bot.dciv.name} server."
            )

        if party.role not in person_in_dciv.roles:
            return await ctx.send(f"{config.NO} You are not part of {party.role.name}.")

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

        await ctx.send(msg)

    @commands.command(
        name="parties",
        aliases=["rank", "ranks", "members", "member", "rankings", "ranking"],
    )
    async def parties(self, ctx, *, party: Fuzzy[PoliticalParty] = None):
        """Ranking of political parties by their amount of members"""

        if party:
            return await ctx.invoke(self.bot.get_command("party"), party=party)

        party_list_embed_content = []
        sorted_parties_and_members = await self.collect_parties_and_members()

        for party in sorted_parties_and_members:
            if party[0] == "Independent":
                continue
            if party[1] == 1:
                party_list_embed_content.append(f"**{party[0]}**\n{party[1]} member")
            else:
                party_list_embed_content.append(f"**{party[0]}**\n{party[1]} members")

        # Append Independents to message
        independent_role = discord.utils.get(self.bot.dciv.roles, name="Independent")
        embed = text.SafeEmbed()

        if not party_list_embed_content:
            party_list_embed_content = ["There are no political parties yet."]

        base_description = (
            f"Check out the [party platforms & descriptions on our Wiki]"
            f"({self.bot.mk.POLITICAL_PARTIES}).\nFor more information about a single "
            f"party, use `{config.BOT_PREFIX}party <party>`."
        )

        if len(party_list_embed_content) > 5:
            # split in half
            first_half = party_list_embed_content[: len(party_list_embed_content) // 2]
            second_half = party_list_embed_content[len(party_list_embed_content) // 2 :]

            if len(second_half) > len(first_half):
                elem = second_half.pop(0)
                first_half.append(elem)

            if independent_role:
                inds = len(independent_role.members)
                embed.description = (
                    f"{base_description}\nThere {'is' if inds == 1 else 'are'} {inds} "
                    f"Independent{'s' if inds != 1 else ''}."
                )

            else:
                embed.description = base_description

            embed.add_field(name="\u200b", value="\n\n".join(first_half))
            embed.add_field(name="\u200b", value="\n\n".join(second_half))

        else:
            if sorted_parties_and_members and independent_role:
                party_list_embed_content.append(
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n{len(independent_role.members)}"
                    f" citizen"
                )
            fmt = "\n\n".join(party_list_embed_content)
            embed.description = f"{base_description}\n\n{fmt}"

        embed.set_author(
            name=f"Ranking of Political Parties in {self.bot.mk.NATION_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        await ctx.send(embed=embed)

    async def create_new_party(
        self,
        ctx: CustomContext,
        *,
        role=True,
        leaders=True,
        invite=True,
        join_mode=True,
        commit=True,
        merge=False,
    ) -> typing.Union[typing.Dict, PoliticalParty]:

        result = {"role": None, "invite": None, "leaders": [], "join_mode": None}

        if role:
            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the new party you want to create."
            )

            role_name = await ctx.converted_input(
                converter=converter.CaseInsensitiveRole
            )

            if isinstance(role_name, str):
                await ctx.send(
                    f"{config.YES} I will **create a new role** on this server named `{role_name}`"
                    f" for the new party."
                )
                try:
                    discord_role = await ctx.guild.create_role(name=role_name)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(
                        exceptions.ForbiddenTask.CREATE_ROLE, role_name
                    )

            else:
                discord_role = role_name

                try:
                    match = await PoliticalParty.convert(ctx, role_name)

                    if match and merge:
                        await ctx.send(
                            f"{config.YES} I'll use the **already existing** party `{discord_role.name}` to merge "
                            f"the others into."
                        )
                        return match

                except exceptions.NotFoundError:
                    pass

                await ctx.send(
                    f"{config.YES} I'll use the **pre-existing role** `{discord_role.name}` for the new party."
                )

            result["role"] = discord_role

        if leaders:
            img = await self.bot.make_file_from_image_link(
                "https://cdn.discordapp.com/attachments/499669824847478785/784584955921301554/partyjoin.PNG"
            )

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the party's leaders or "
                f"representatives. If this party has multiple leaders, separate them with a newline, like in the "
                f"image below.\n\n "
                f"{config.HINT} *Party leaders get DM notifications by me when someone joins or leaves their "
                f"party, and they are the ones that can accept and deny join requests if the party's join mode "
                f"is request-based.*",
                file=img,
            )

            leaders_text = (await ctx.input()).splitlines()

            leaders = []

            conv = Fuzzy[converter.CaseInsensitiveMember]

            for leader in leaders_text:
                try:
                    converted = await conv.convert(ctx, leader.strip())

                    if not converted.bot:
                        leaders.append(converted.id)

                except commands.BadArgument:
                    continue

            if not leaders:
                leaders.append(0)

            result["leaders"] = leaders

        if invite:
            party_invite = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the invite link to the party's Discord server. "
                f"If they don't have one, just reply with gibberish."
            )

            if not self.discord_invite_pattern.fullmatch(party_invite):
                party_invite = "None"

            result["invite"] = party_invite

        if join_mode:
            view = SelectJoinModeView(ctx)

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Should this party be public, request-based, or private?",
                view=view,
            )

            join_mode = await view.prompt()
            result["join_mode"] = join_mode

        if commit:
            async with self.bot.db.acquire() as connection:

                if result["invite"] == "None":
                    result["invite"] = None

                async with connection.transaction():
                    try:
                        await connection.execute(
                            "INSERT INTO party (id, discord_invite, join_mode) VALUES ($1, $2, $3)"
                            "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, join_mode = $3 WHERE party.id = $1",
                            result["role"].id,
                            result["invite"],
                            result["join_mode"],
                        )
                    except asyncpg.UniqueViolationError:
                        raise exceptions.DemocracivBotException(
                            f"{config.NO} `{result['role'].name}` already is a "
                            f"political party. If you "
                            f"want to edit it, use `{config.BOT_PREFIX}party edit "
                            f"{result['role'].name}` "
                            f"instead. "
                        )

                    await connection.execute(
                        "INSERT INTO party_alias (party_id, alias) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                        result["role"].id,
                        result["role"].name.lower(),
                    )

                    for leader in result["leaders"]:
                        await connection.execute(
                            "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                            result["role"].id,
                            leader,
                        )

                return await PoliticalParty.convert(ctx, result["role"].id)

        return result

    @party.command(name="add", aliases=["create", "make"])
    @checks.moderation_or_nation_leader()
    async def addparty(self, ctx):
        """Add a new political party"""

        if "alias" in ctx.message.content.lower():
            return await ctx.send(
                f"{config.HINT} Did you mean the `{config.BOT_PREFIX}party addalias` command?"
            )

        party = await self.create_new_party(ctx, commit=True)
        await ctx.send(
            f"{config.YES} `{party.role.name}` was added as a new Political Party."
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

        menu = text.EditModelMenu(
            ctx,
            choices_with_formatted_explanation={
                "name": "Name",
                "leaders": "Leaders",
                "join_mode": "Join Mode",
                "invite": "Server Invite",
            },
        )

        result = await menu.prompt()
        to_change = result.choices

        if not result.confirmed or True not in to_change.values():
            return

        if to_change["name"]:
            new_name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new "
                f"name for `{party.role.name}`."
            )

            other_exists = None

            try:
                other_exists = await PoliticalParty.convert(ctx, new_name)
            except exceptions.NotFoundError:
                pass

            if other_exists:
                return await ctx.send(
                    f"{config.NO} Another political party is already named `{new_name}`."
                )

            old_name = party.role.name

            if old_name != new_name:
                await party.role.edit(name=new_name)

                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute(
                            "DELETE FROM party_alias WHERE alias = $1", old_name.lower()
                        )

                        await connection.execute(
                            "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            new_name.lower(),
                            party.role.id,
                        )

                party = await PoliticalParty.convert(ctx, argument=party.role.id)

        updated_party = await self.create_new_party(
            ctx,
            role=False,
            commit=False,
            invite=to_change["invite"],
            join_mode=to_change["join_mode"],
            leaders=to_change["leaders"],
        )

        if updated_party["invite"] == "None":
            new_invite = None
        elif not updated_party["invite"]:
            new_invite = party.discord_invite
        else:
            new_invite = updated_party["invite"]

        new_join_mode = updated_party["join_mode"] or party.join_mode.value
        new_leaders = updated_party["leaders"] or party.leader_ids

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE party SET discord_invite = $2, join_mode = $3 WHERE id = $1",
                    party.role.id,
                    new_invite,
                    new_join_mode,
                )

                await connection.execute(
                    "DELETE FROM party_leader WHERE party_id = $1", party.role.id
                )

                for leader in new_leaders:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        party.role.id,
                        leader,
                    )

        await ctx.send(
            f"{config.YES} `{party.role.name}` was edited."
            f"\n{config.HINT} Remember to update <https://reddit.com/r/democraciv/wiki> accordingly."
        )

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

        name = party.role.name

        delete_role_too = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} I will remove `{name}` from the list of "
            f"parties. Should I delete their Discord role too?"
        )

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

        await ctx.send(
            f"{config.YES} `{name}` and all its aliases were deleted."
            f"\n{config.HINT} Remember to update <https://reddit.com/r/democraciv/wiki> accordingly."
        )

    @party.command(name="addalias", aliases=["alias"])
    @checks.moderation_or_nation_leader()
    async def addalias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Add a new alias to a political party"""

        alias = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the new alias for `{party.role.name}`."
        )

        if not alias:
            return

        try:
            await self.bot.db.execute(
                "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                alias.lower(),
                party.role.id,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(
                f"{config.NO} `{alias}` is already an alias for `{party.role.name}`."
            )

        await ctx.send(
            f"{config.YES} Alias `{alias}` for party `{party.role.name}` was added."
        )

    @party.command(name="deletealias", aliases=["removealias"])
    @checks.moderation_or_nation_leader()
    async def deletealias(self, ctx, *, alias: str):
        """Delete a party's alias"""
        try:
            await PoliticalParty.convert(ctx, alias)
        except exceptions.NotFoundError:
            return await ctx.send(
                f"{config.NO} `{alias}` is not an alias of any party."
            )

        await self.bot.db.execute(
            "DELETE FROM party_alias WHERE alias = $1", alias.lower()
        )
        await ctx.send(
            f"{config.YES} Alias `{alias}` was deleted.\n{config.HINT} If you want to delete all aliases "
            f"of a party, consider using the `{config.BOT_PREFIX}party clearalias` command instead."
        )

    @party.command(name="clearalias")
    @checks.moderation_or_nation_leader()
    async def clearalias(self, ctx, *, party: Fuzzy[PoliticalParty]):
        """Delete all aliases of a party"""

        for alias in party.aliases:
            if alias == party.role.name.lower():
                continue

            await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias)

        sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to "
            f"delete all aliases of `{party.role.name}`?"
        )

        if sure:
            await ctx.send(
                f"{config.YES} All aliases of `{party.role.name}` were deleted."
            )
        else:
            await ctx.send("Cancelled.")

    @party.command(name="merge")
    @checks.moderation_or_nation_leader()
    async def mergeparties(self, ctx, amount_of_parties: int):
        """Merge multiple parties into a single, new party"""

        to_be_merged = set()

        for i in range(1, amount_of_parties + 1):
            name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} What's the name or alias for political party #{i}?"
            )

            if not name:
                return

            try:
                conv = Fuzzy[PoliticalParty]
                party = await conv.convert(ctx, name)
            except exceptions.NotFoundError:
                return await ctx.send(
                    f"{config.NO} There is no party that matches `{name}`. Aborted."
                )

            to_be_merged.add(party)

        members_to_merge = {
            member for party in to_be_merged for member in party.role.members
        }
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
            new_party = await self.create_new_party(ctx, commit=True, merge=True)
        except exceptions.DemocracivBotException as e:
            return await ctx.send(
                f"{e.message}\n{config.NO} Party creation failed, old parties were not deleted."
            )

        if new_party is None or new_party.role is None:
            return await ctx.send(
                f"{config.NO} Party creation failed, old parties were not deleted."
            )

        async with ctx.typing():
            for member in members_to_merge:
                await member.add_roles(new_party.role)

            for party in to_be_merged:
                # In case the merger keeps the name and thus role of an old party
                if party.role.id == new_party.role.id:
                    continue

                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute(
                            "DELETE FROM party WHERE id = $1", party.role.id
                        )

                        await party.role.delete()

        await ctx.send(
            f"{config.YES} The old parties were deleted and all their members now have the role of the new party.\n"
            f"{config.HINT} Remember to update <https://reddit.com/r/democraciv/wiki> accordingly."
        )


def setup(bot):
    bot.add_cog(Party(bot))
