import asyncio
import collections
import contextlib
import logging
import re
import typing

import asyncpg
import discord

from discord.ext import commands, menus

from bot.config import config, mk
from bot.utils import exceptions, checks, converter, context
from bot.utils.context import CustomContext
from bot.utils.converter import (
    PoliticalParty,
    PoliticalPartyJoinMode,
    CaseInsensitiveRole,
)
from bot.utils.context import MockContext
from bot.utils.text import SafeEmbed
from utils import text
from utils.exceptions import ForbiddenTask


class EditPartyMenu(menus.Menu):
    def __init__(self):
        super().__init__(timeout=120.0, delete_message_after=True)
        self._make_result()

    def _make_result(self):
        self.result = collections.namedtuple("EditPartyMenuResult", ["confirmed", "result"])
        self.result.confirmed = False
        self.result.result = {"invite": False, "leaders": False, "join_mode": False, "name": False}
        return self.result

    async def send_initial_message(self, ctx, channel):
        embed = text.SafeEmbed(
            title=f"{config.USER_INTERACTION_REQUIRED}  What do you want to edit?",
            description=f"Select as many things as you want, then click "
                        f"the {config.YES} button to continue, or {config.NO} to cancel.\n\n"
                        f":one: Name\n"
                        f":two: Discord Server Invite\n"
                        f":three: Faction Leaders\n"
                        f":four: Join Mode"
        )

        return await ctx.send(embed=embed)

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_first_choice(self, payload):
        self.result.result["name"] = not self.result.result["name"]

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def second(self, payload):
        self.result.result["invite"] = not self.result.result["invite"]

    @menus.button("3\N{variation selector-16}\N{combining enclosing keycap}")
    async def third(self, payload):
        self.result.result["leaders"] = not self.result.result["leaders"]

    @menus.button("4\N{variation selector-16}\N{combining enclosing keycap}")
    async def fourth(self, payload):
        self.result.result["join_mode"] = not self.result.result["join_mode"]

    @menus.button(config.YES)
    async def confirm(self, payload):
        self.result.confirmed = True
        self.stop()

    @menus.button(config.NO)
    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class Party(context.CustomCog, name="Religions"):
    """Interact with the religious factions of {NATION_NAME}."""

    def __init__(self, bot):
        super().__init__(bot)
        self._party_lock = asyncio.Lock()
        self.discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv server and their amount of members for -members."""
        parties_and_members = []

        parties = await self.bot.db.fetch("SELECT id FROM party")
        parties = [record["id"] for record in parties]

        error_string = []

        for party in parties:
            role = self.bot.dciv.get_role(party)

            if role is None:
                error_string.append(str(party))
                continue

            parties_and_members.append((role.name, len(role.members)))

        if error_string:
            errored = ", ".join(error_string)
            logging.warning(
                f"The following ids were added as a party but have no role on the Democraciv guild: {errored}")

        return parties_and_members

    @commands.group(name="religion", case_insensitive=True, invoke_without_command=True)
    async def party(self, ctx, *, faction: PoliticalParty = None):
        """Detailed information about a single religious faction"""

        party = faction

        if party is None:
            return await ctx.invoke(self.bot.get_command("religions"))

        embed = SafeEmbed(
            title=party.role.name,
            description=f"[Religious Manifestos]({self.bot.mk.POLITICAL_PARTIES})",
        )

        thumbnail = await party.get_logo()

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        invite_value = party.discord_invite if party.discord_invite else "*This religion does not have a Discord server.*"
        embed.add_field(name="Server", value=invite_value)

        embed.add_field(name="Join Setting", value=party.join_mode.value)

        if party.leaders:
            embed.add_field(
                name="Leaders",
                value="\n".join([f"{leader.mention} {leader}" for leader in party.leaders]),
                inline=False
            )

        if party.aliases is not None:
            embed.add_field(name="Aliases", value=", ".join(party.aliases) or "-", inline=False)

        party_members = "\n".join([f"{member.mention} {member}" for member in party.role.members]) or "-"
        embed.add_field(
            name=f"Members ({len(party.role.members)})",
            value=party_members,
            inline=False,
        )
        embed.set_footer(text=f"Join this religion with: {config.BOT_PREFIX}join {party.role.name}")
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def party_join_request_listener(self, payload: discord.RawReactionActionEvent):
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
                party = await PoliticalParty.convert(MockContext(self.bot), request_match["party_id"])
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
                    return await reactor.send(f"{config.NO} I don't have `Manage Roles` permissions "
                                              f"on the {self.bot.dciv.name} server, so unfortunately I cannot give "
                                              f"`{member}` your religion's role. Please contact Moderation.")

                message = f"{config.HINT}  {member.display_name}'s request to join {party.role.name} was " \
                          f"accepted by {reactor.display_name}."

                if party.discord_invite:
                    invite_fmt = f"\n\nGo ahead and join their Discord server if you haven't already: {party.discord_invite}"
                else:
                    invite_fmt = ""

                member_embed = text.SafeEmbed(title=f"{yes_emoji}  Religious Faction Join Request Accepted",
                                              description=f"Your request to join **{party.role.name}** was accepted by "
                                                          f"{reactor}.{invite_fmt}")

            elif str(payload.emoji) == no_emoji:
                message = f"{config.HINT}  {member.display_name}'s request to join {party.role.name} was " \
                          f"denied by {reactor.display_name}."

                member_embed = text.SafeEmbed(title=f"{no_emoji}  Religious Faction Join Request Denied",
                                              description=f"Your request to join **{party.role.name}** was denied by {reactor}.")

            else:
                return

            await self.bot.db.execute("DELETE FROM party_join_request WHERE id = $1", request_match["id"])
            await member.send(embed=member_embed)

            leaders_without_reactor = [l.id for l in party.leaders]
            leaders_without_reactor.remove(reactor.id)

            for leader in leaders_without_reactor:
                try:
                    leader_obj = self.bot.get_user(leader)
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
                    message = f"{config.JOIN}  {before.display_name} just joined your religious faction **{role.name}**."
                    break

        else:
            # left party
            for role in before.roles:
                if role not in after.roles:
                    possible_party = role
                    message = f"{config.LEAVE}  {before.display_name} just left your religious faction **{role.name}**."
                    break

        if not possible_party or not message:
            return

        try:
            party = await PoliticalParty.convert(MockContext(self.bot), possible_party.id)
        except exceptions.NotFoundError:
            return

        embed = SafeEmbed(description=message)
        embed.set_author(name=before, icon_url=before.avatar_url_as(static_format="png"))

        for leader in party.leaders:
            await self.bot.safe_send_dm(target=leader, embed=embed, reason="party_join_leave")

    @commands.command(name="join")
    async def join(self, ctx, *, faction: PoliticalParty):
        """Join a Religious Faction"""
        party = faction
        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(f"{config.NO} You're not in the {self.bot.dciv.name} server.")

        if party.role in person_in_dciv.roles:
            return await ctx.send(f"{config.NO} You're already part of `{party.role.name}`.")

        if party.join_mode is PoliticalPartyJoinMode.PRIVATE:
            return await ctx.send(
                f"{config.NO} {party.role.name} is a private religious faction. Contact their leaders for further information."
            )

        elif party.join_mode is PoliticalPartyJoinMode.REQUEST:
            if person_in_dciv in party.leaders:

                try:
                    await person_in_dciv.add_roles(party.role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

                return await ctx.send(f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                                      f"*As you're a leader of this religious faction, you skipped the request step.*\n")

            query = """SELECT * FROM party_join_request WHERE party_id = $1 AND requesting_member = $2"""
            existing_request = await self.bot.db.fetchrow(query, party.role.id, ctx.author.id)

            if existing_request:
                return await ctx.send(
                    f"{config.NO} You already requested to join `{party.role.name}`. Once the leaders "
                    f"accept or deny your request, I will notify you."
                )

            if not party.leaders:
                return await ctx.send(f"{config.NO} I was not told who `{party.role.name}`'s leaders are, so "
                                      f"I can't send your join request to anyone. Please tell {self.bot.dciv.name} "
                                      f"Moderation to add the leaders with `{config.BOT_PREFIX}religion edit "
                                      f"{party.role.name}`, then try again.")

            request_id = await self.bot.db.fetchval(
                "INSERT INTO party_join_request (party_id, requesting_member) VALUES ($1, $2) RETURNING id",
                party.role.id,
                ctx.author.id,
            )

            fmt_leader = ', '.join([f"`{leader}`" for leader in party.leaders])

            await ctx.send(
                f"{config.YES} Your request to join `{party.role.name}` was sent to their leaders ({fmt_leader}). "
                f"Once they accept or deny your request, I'll notify you."
            )

            for leader in party.leaders:
                try:
                    other_leaders = party.leaders
                    other_leaders.remove(leader)

                    if other_leaders:
                        other_leaders_fmt = ', '.join([f"`{le}`" for le in other_leaders])
                        other_help = f"\nThe other leaders, {other_leaders_fmt}, also received this message. " \
                                     f"Once any of you either accept or deny, that is the final decision."

                    else:
                        other_help = ""

                    embed = text.SafeEmbed(title=f"Request to join {party.role.name}",
                                           description=f"{ctx.author.display_name} wants to join your religious faction "
                                                       f"**{party.role.name}**. Do you want to accept "
                                                       f"their request?\n\n{config.HINT} This has no timeout, so "
                                                       f"you don't have to decide immediately.{other_help}")

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

    @commands.command(name="leave")
    async def leave(self, ctx, *, faction: PoliticalParty):
        """Leave a Religious Faction"""
        party = faction
        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(f"{config.NO} You're not in the {self.bot.dciv.name} server.")

        if party.role not in person_in_dciv.roles:
            return await ctx.send(f"{config.NO} You are not part of {party.role.name}.")

        try:
            await person_in_dciv.remove_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.REMOVE_ROLE, detail=party.role.name)

        if party.role.name == "Independent":
            msg = f"{config.YES} You are no longer an {party.role.name}."
        else:
            msg = f"{config.YES} You left {party.role.name}."

        await ctx.send(msg)

    @commands.command(
        name="religions",
        aliases=["rank", "ranks", "members", "member", "rankings", "ranking", "reli"],
    )
    async def parties(self, ctx):
        """Ranking of religious factions by their amount of members"""

        party_list_embed_content = []

        sorted_parties_and_members = sorted(await self.collect_parties_and_members(), key=lambda x: x[1], reverse=True)

        for party in sorted_parties_and_members:
            if party[0] == "Independent":
                continue
            if party[1] == 1:
                party_list_embed_content.append(f"**{party[0]}**\n{party[1]} member")
            else:
                party_list_embed_content.append(f"**{party[0]}**\n{party[1]} members")

        # Append Independents to message
        independent_role = discord.utils.get(self.bot.dciv.roles, name="Independent")

        if independent_role is not None:
            if len(independent_role.members) == 1:
                party_list_embed_content.append(
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n" f"{len(independent_role.members)} citizen"
                )
            else:
                party_list_embed_content.append(
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n" f"{len(independent_role.members)} citizens"
                )
        if len(party_list_embed_content) == 0:
            party_list_embed_content = ["There are no religious factions yet."]

        party_list_embed_content = "\n\n".join(party_list_embed_content)

        embed = SafeEmbed(
            description=f"[Religious Manifestos]({self.bot.mk.POLITICAL_PARTIES})\n\n{party_list_embed_content}",
        )

        embed.set_author(name=f"Ranking of Religious Factions in {self.bot.mk.NATION_NAME}",
                         icon_url=self.bot.mk.NATION_ICON_URL)

        embed.set_footer(text=f"For more information about a religious faction, use: {config.BOT_PREFIX}religion <faction>")
        return await ctx.send(embed=embed)

    async def create_new_party(self, ctx: CustomContext, *,
                               role=True, leaders=True, invite=True, join_mode=True, commit=True) -> typing.Union[
        typing.Dict, PoliticalParty]:

        result = {
            'role': None,
            'invite': None,
            'leaders': [],
            'join_mode': None
        }

        if role:
            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the new religious faction you want to create.")

            role_name = await ctx.converted_input(converter=CaseInsensitiveRole)

            if isinstance(role_name, str):
                await ctx.send(
                    f"{config.YES} I will **create a new role** on this server named `{role_name}`"
                    f" for the new religious faction."
                )
                try:
                    discord_role = await ctx.guild.create_role(name=role_name)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

            else:
                discord_role = role_name

                await ctx.send(
                    f"{config.YES} I'll use the **pre-existing role** `{discord_role.name}` for the new religious faction."
                )

            result['role'] = discord_role

        if leaders:
            img = await self.bot.make_file_from_image_link(
                "https://cdn.discordapp.com/attachments/499669824847478785/784584955921301554/partyjoin.PNG")
            img.seek(0)
            file = discord.File(img, filename="image.png")
            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the religious faction's leaders or "
                f"representatives. If this religious faction has multiple leaders, separate them with a newline, like in the "
                f"image below.\n\n "
                f"{config.HINT} *Religious faction leaders get DM notifications by me when someone joins or leaves their "
                f"faction, and they are the ones that can accept and deny join requests if the faction's join mode "
                f"is request-based.*", file=file)

            leaders_text = (
                await ctx.input()
            ).splitlines()

            leaders = []

            for leader in leaders_text:
                try:
                    converted = await converter.CaseInsensitiveMember().convert(ctx, leader.strip())

                    if not converted.bot:
                        leaders.append(converted.id)

                except commands.BadArgument:
                    continue

            if not leaders:
                leaders.append(0)

            result['leaders'] = leaders

        if invite:
            party_invite = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the invite link to the religious faction's Discord server. "
                f"If they don't have one, just reply with gibberish."
            )

            if not self.discord_invite_pattern.fullmatch(party_invite):
                party_invite = "None"

            result['invite'] = party_invite

        if join_mode:
            reactions = {
                "\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467": PoliticalPartyJoinMode.PUBLIC,
                "\U0001f4e9": PoliticalPartyJoinMode.REQUEST,
                "\U0001f575": PoliticalPartyJoinMode.PRIVATE,
            }

            reaction = await ctx.choose(
                f"{config.USER_INTERACTION_REQUIRED} Should this religious faction be public, request-based, or private?\n"
                f"\n\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467 - **Public**: Everyone can join\n"
                f"\U0001f4e9 - **Request-based**: Everyone can request to join this religious faction, and the faction's leaders can then accept/deny each request\n"
                f"\U0001f575 - **Private**: No one can join, and only {self.bot.dciv.name} Moderation can give out the faction's role",
                reactions=reactions.keys(),
            )

            join_mode = reactions[str(reaction)]
            result['join_mode'] = join_mode.value

        if commit:
            async with self.bot.db.acquire() as connection:

                if result['invite'] == "None":
                    result['invite'] = None

                async with connection.transaction():
                    try:
                        await connection.execute(
                            "INSERT INTO party (id, discord_invite, join_mode) VALUES ($1, $2, $3)"
                            "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, join_mode = $3 WHERE party.id = $1",
                            result['role'].id,
                            result['invite'],
                            result['join_mode'],
                        )
                    except asyncpg.UniqueViolationError:
                        raise exceptions.DemocracivBotException(f"{config.NO} `{result['role'].name}` already is a "
                                                                f"religious faction. If you "
                                                                f"want to edit it, use `{config.BOT_PREFIX}religion edit "
                                                                f"{result['role'].name}` "
                                                                f"instead. ")

                    await connection.execute(
                        "INSERT INTO party_alias (party_id, alias) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                        result['role'].id,
                        result['role'].name.lower(),
                    )

                    for leader in result['leaders']:
                        await connection.execute(
                            "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                            result['role'].id,
                            leader,
                        )

                return await PoliticalParty.convert(ctx, result['role'].id)

        return result

    @party.command(name="add", aliases=["create", "make"])
    @checks.moderation_or_nation_leader()
    async def addparty(self, ctx):
        """Add a new religious faction"""
        party = await self.create_new_party(ctx, commit=True)
        await ctx.send(f"{config.YES} `{party.role.name}` was added as a new religious faction.")

    @party.command(name="edit", aliases=["change"])
    @checks.moderation_or_nation_leader()
    async def changeparty(self, ctx, *, faction: PoliticalParty):
        """Edit an existing religious faction

        **Example**
            `{PREFIX}{COMMAND} Ecological Democratic Union`
            `{PREFIX}{COMMAND} scp`
            `{PREFIX}{COMMAND} progressive union`"""

        party = faction

        if party.is_independent:
            return await ctx.send(f"{config.NO} You can't change the Independent party.")

        result = await EditPartyMenu().prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to change.")

        to_change = result.result

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to change.")

        if to_change['name']:
            new_name = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the new "
                                       f"name for `{party.role.name}`.")

            other_exists = None

            try:
                other_exists = await PoliticalParty.convert(ctx, new_name)
            except exceptions.NotFoundError:
                pass

            if other_exists:
                return await ctx.send(f"{config.NO} Another religious faction is already named `{new_name}`.")

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

        updated_party = await self.create_new_party(ctx,
                                                    role=False,
                                                    commit=False,
                                                    invite=to_change['invite'],
                                                    join_mode=to_change['join_mode'],
                                                    leaders=to_change['leaders'])

        if updated_party['invite'] == "None":
            new_invite = None
        elif not updated_party:
            new_invite = party.discord_invite
        else:
            new_invite = updated_party['invite']

        new_join_mode = updated_party['join_mode'] or party.join_mode.value
        new_leaders = updated_party['leaders'] or party._leaders

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE party SET discord_invite = $2, join_mode = $3 WHERE id = $1",
                    party.role.id,
                    new_invite,
                    new_join_mode,
                )

                await connection.execute("DELETE FROM party_leader WHERE party_id = $1", party.role.id)

                for leader in new_leaders:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        party.role.id,
                        leader,
                    )

        await ctx.send(f"{config.YES} `{party.role.name}` was edited.")

    @party.command(name="delete", aliases=["remove"])
    @checks.moderation_or_nation_leader()
    async def deleteparty(self, ctx, *, faction: PoliticalParty):
        """Delete a religious faction

        **Usage**
         `{PREFIX}{COMMAND} <faction>`
        """
        party = faction
        name = party.role.name

        delete_role_too = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} I will remove {name} from the list of "
            f"religious factions. Should I delete their Discord role too?"
        )

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                await connection.execute("DELETE FROM party_leader WHERE party_id = $1", party.role.id)
                await connection.execute("DELETE FROM party WHERE id = $1", party.role.id)

        if delete_role_too and party.role:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.DELETE_ROLE, detail=party.role.name)

        await ctx.send(f"{config.YES} `{name}` and all its aliases were deleted.")

    @party.command(name="addalias")
    @checks.moderation_or_nation_leader()
    async def addalias(self, ctx, *, faction: PoliticalParty):
        """Add a new alias to a religious faction"""

        party = faction

        alias = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the new alias for `{party.role.name}`.")

        if not alias:
            return

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                    alias.lower(),
                    party.role.id,
                )

        await ctx.send(f"{config.YES} Alias `{alias}` for religious faction `{party.role.name}` was added.")

    @party.command(name="deletealias", aliases=["removealias"])
    @checks.moderation_or_nation_leader()
    async def deletealias(self, ctx, *, alias: str):
        """Delete a religious faction's alias"""
        try:
            await PoliticalParty.convert(ctx, alias)
        except exceptions.NotFoundError:
            return await ctx.send(f"{config.NO} `{alias}` is not an alias of any religious faction.")

        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias.lower())
        await ctx.send(f"{config.YES} Alias `{alias}` was deleted.")

    @party.command(name="merge")
    @checks.moderation_or_nation_leader()
    async def mergeparties(self, ctx, amount_of_factions: int):
        """Merge one or multiple religious factions into a single, new religious faction"""

        # todo
        amount_of_parties = amount_of_factions

        to_be_merged = []

        for i in range(1, amount_of_parties + 1):
            name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} What's the name or alias for religious faction #{i}?")

            if not name:
                return

            try:
                party = await PoliticalParty.convert(ctx, name)
            except exceptions.NotFoundError:
                return await ctx.send(f"{config.NO} There is no religious faction that matches `{name}`. Aborted.")

            to_be_merged.append(party)

        members_to_merge = {member for party in to_be_merged for member in party.role.members}
        pretty_parties = [f"`{party.role.name}`" for party in to_be_merged]

        reaction = await ctx.confirm(f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to merge"
                                     f" {', '.join(pretty_parties)} into one, new religious faction?")

        if not reaction:
            return await ctx.send("Cancelled.")

        try:
            new_party = await self.create_new_party(ctx, commit=True)
        except exceptions.DemocracivBotException as e:
            return await ctx.send(f"{e.message}\n{config.NO} Religious faction creation failed, old religious factions were not deleted.")

        if new_party is None or new_party.role is None:
            return await ctx.send(f"{config.NO} Religious faction creation failed, old religious factions were not deleted.")

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
                            "DELETE FROM party_alias WHERE party_id = $1; " "DELETE FROM party WHERE id = $1",
                            party.role.id,
                        )

                await party.role.delete()

        await ctx.send(
            f"{config.YES} The old religious factions were deleted and"
            " all their members have now the role of the new religious faction."
        )


def setup(bot):
    bot.add_cog(Party(bot))
