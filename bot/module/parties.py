import contextlib
import re
import typing
import discord

from discord.ext import commands

from bot.config import config, mk
from bot.utils import exceptions, checks, converter, context
from bot.utils.context import CustomContext
from bot.utils.converter import PoliticalParty, PoliticalPartyJoinMode, CaseInsensitiveRole
from bot.utils.exceptions import ForbiddenTask
from bot.utils.context import MockContext
from bot.utils.text import SafeEmbed


class Party(context.CustomCog, name='Political Parties'):
    """Interact with the political parties of {NATION_NAME}. Note that you can only join and
    leave parties on the Democraciv server."""

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv server and their amount of members for -members."""
        parties_and_members = []

        parties = await self.bot.db.fetch("SELECT id FROM parties")
        parties = [record['id'] for record in parties]

        error_string = []

        for party in parties:
            role = self.bot.dciv.get_role(party)

            if role is None:
                error_string.append(str(party))
                continue

            parties_and_members.append((role.name, len(role.members)))

        if error_string:
            print("[DATABASE] The following ids were added as a party but have no role on the Democraciv guild: ")
            print(', '.join(error_string))

        return parties_and_members

    @commands.group(name='party', case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def party(self, ctx, *, party: PoliticalParty = None):
        """Detailed information about a single political party"""

        if party is None:
            return await ctx.invoke(self.bot.get_command("parties"))

        embed = SafeEmbed(title=party.role.name,
                          description=f"[Platform and Description]({self.bot.mk.POLITICAL_PARTIES})")

        thumbnail = await party.get_logo()

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        invite_value = party.discord_invite if party.discord_invite else "*This party does not have a Discord server.*"
        embed.add_field(name="Server", value=invite_value)

        embed.add_field(name="Join Setting", value=party.join_mode.value)

        if party.leaders:
            embed.add_field(name="Leaders or Representatives",
                            value='\n'.join([f"{leader.mention} {leader}" for leader in party.leaders]))

        if party.aliases is not None:
            embed.add_field(name="Aliases", value=', '.join(party.aliases) or '-', inline=False)

        party_members = '\n'.join([f"{member.mention} {member}" for member in party.role.members]) or '-'
        embed.add_field(name=f"Members ({len(party.role.members)})", value=party_members, inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener(name='on_raw_reaction_add')
    async def party_join_request_listener(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id:  # only ever happens in DMs
            return

        query = """SELECT party_join_request.id, party_join_request.party_id, party_join_request.requesting_member
                   FROM party_join_request, party_join_request_message
                   WHERE party_join_request_message.request_id = party_join_request.id
                   AND party_join_request_message.message_id = $1"""

        request_match = await self.bot.db.fetchrow(query, payload.message_id)

        if not request_match:
            return

        yes_emoji = "\U00002705"
        no_emoji = "\U0000274c"

        try:
            party = await PoliticalParty.convert(MockContext(self.bot), request_match['party_id'])
        except commands.BadArgument:
            return

        member = self.bot.dciv.get_member(request_match['requesting_member'])

        if not party or not party.role or not member:
            return

        if payload.user_id not in [leader.id for leader in party.leaders]:
            return

        if str(payload.emoji) == yes_emoji:
            await member.add_roles(party.role)
            message = f"{member}'s request to join {party.role.name} was **accepted**."

        elif str(payload.emoji) == no_emoji:
            message = f"{member}'s request to join {party.role.name} was **denied**."

        else:
            return

        await self.bot.db.execute("DELETE FROM party_join_request WHERE id = $1", request_match['id'])

        for leader in party.leaders:
            with contextlib.suppress(discord.Forbidden):
                await leader.send(message)

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
                    message = f"{before} just joined {role.name}."
                    break

        else:
            # left party
            for role in before.roles:
                if role not in after.roles:
                    possible_party = role
                    message = f"{before} just left {role.name}."
                    break

        if not possible_party or not message:
            return

        try:
            party = await PoliticalParty.convert(MockContext(self.bot), possible_party.id)
        except commands.BadArgument:
            return

        for leader in party.leaders:
            await self.bot.safe_send_dm(target=leader, message=message, reason="party_join_leave")

    @commands.command(name='join')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def join(self, ctx, *, party: PoliticalParty):
        """Join a political party"""

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(f":x: You're not in the {self.bot.dciv.name} server.")

        if party.role in person_in_dciv.roles:
            return await ctx.send(f":x: You're already part of {party.role.name}.")

        if party.join_mode is PoliticalPartyJoinMode.PRIVATE:
            return await ctx.send(f':x: {party.role.name} is a private party. '
                                  f'Contact the party leaders for further information.')

        elif party.join_mode is PoliticalPartyJoinMode.REQUEST:
            query = """SELECT * FROM party_join_request WHERE party_id = $1 AND requesting_member = $2"""
            existing_request = await self.bot.db.fetchrow(query, party.role.id, ctx.author.id)

            if existing_request:
                return await ctx.send(f":x: You already requested to join {party.role.name}. Once the leaders "
                                      f"accept or deny your request, I will notify you.")

            request_id = await self.bot.db.fetchval(
                "INSERT INTO party_join_request (party_id, requesting_member) VALUES ($1, $2) RETURNING id",
                party.role.id, ctx.author.id)

            for leader in party.leaders:
                try:
                    message = await leader.send(f"{ctx.author} wants to join your party, {party.role.name}. "
                                                f"Do you want to accept their request?")
                    await message.add_reaction("\U00002705")
                    await message.add_reaction("\U0000274c")

                except discord.Forbidden:
                    continue

                await self.bot.db.execute(
                    "INSERT INTO party_join_request_message (request_id, message_id) VALUES ($1, $2)",
                    request_id, message.id)

            return await ctx.send(
                f":white_check_mark: Your request to join {party.role.name} was sent to their leaders. "
                f"Once they accept or deny your request, I'll notify you.")

        elif party.join_mode is PoliticalPartyJoinMode.PUBLIC:
            try:
                await person_in_dciv.add_roles(party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

            if party.role.name == 'Independent':
                return await ctx.send(f':white_check_mark: You are now an {party.role.name}.')

            message = f":white_check_mark: You've joined {party.role.name}!"

            if party.discord_invite:
                message = f"{message} Now head to their Discord Server and introduce yourself: {party.discord_invite}"

            await ctx.send(message)

    @commands.command(name='leave')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def leave(self, ctx, *, party: PoliticalParty):
        """Leave a political party"""

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)

        if person_in_dciv is None:
            return await ctx.send(f":x: You're not in the {self.bot.dciv.name} server.")

        if party.role not in person_in_dciv.roles:
            return await ctx.send(f':x: You are not part of {party.role.name}.')

        try:
            await person_in_dciv.remove_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.REMOVE_ROLE, detail=party.role.name)

        if party.role.name == 'Independent':
            msg = f':white_check_mark: You are no longer an {party.role.name}.'
        else:
            msg = f':white_check_mark: You left {party.role.name}.'

        await ctx.send(msg)

    @commands.command(name='parties', aliases=['rank', 'ranks', 'members', 'member', 'rankings', 'ranking'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def parties(self, ctx):
        """Ranking of political parties by their amount of members"""

        party_list_embed_content = []

        sorted_parties_and_members = sorted(await self.collect_parties_and_members(), key=lambda x: x[1],
                                            reverse=True)

        for party in sorted_parties_and_members:
            if party[0] == 'Independent':
                continue
            if party[1] == 1:
                party_list_embed_content.append(f'**{party[0]}**\n{party[1]} member')
            else:
                party_list_embed_content.append(f'**{party[0]}**\n{party[1]} members')

        # Append Independents to message
        independent_role = discord.utils.get(self.bot.dciv.roles, name='Independent')

        if independent_role is not None:
            if len(independent_role.members) == 1:
                party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                f'{len(independent_role.members)} citizen')
            else:
                party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                f'{len(independent_role.members)} citizens')
        if len(party_list_embed_content) == 0:
            party_list_embed_content = ['There are no political parties yet.']

        party_list_embed_content = '\n\n'.join(party_list_embed_content)
        print(party_list_embed_content)

        embed = SafeEmbed(title=f'{self.bot.mk.NATION_EMOJI}  Ranking of Political Parties in '
                                f'{self.bot.mk.NATION_NAME}',
                          description=f"[Party Platforms]({self.bot.mk.POLITICAL_PARTIES})\n\n{party_list_embed_content}")

        return await ctx.send(embed=embed)

    async def create_new_party(self, ctx: CustomContext) -> typing.Optional[PoliticalParty]:
        await ctx.send(":information_source: Reply with the name of the new party you want to create.")

        role_name = await ctx.converted_input(converter=CaseInsensitiveRole)

        if isinstance(role_name, str):
            is_updated = False

            await ctx.send(
                f":white_check_mark: I will **create a new role** on this server named `{role_name}`"
                f" for the new party.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            is_updated = True
            discord_role = role_name

            await ctx.send(f":white_check_mark: I'll use the **pre-existing role**"
                           f" `{discord_role.name}` for the new party.")

        leaders_text = (await ctx.input(
            ":information_source: Reply with the name or mention of the party's leader or representative. "
            "If this party has multiple leaders, separate them with a newline.")).splitlines()

        leaders = []

        for leader in leaders_text:
            with contextlib.suppress(commands.BadArgument):
                converted = await converter.CaseInsensitiveMember().convert(ctx, leader.strip())
                if not converted.bot:
                    leaders.append(converted.id)

        party_invite = await ctx.input(
            ":information_source: Reply with the invite link to the party's Discord server. If they don't have one, "
            "just reply with gibberish.")

        discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
        if not discord_invite_pattern.fullmatch(party_invite):
            party_invite = None

        reactions = {
            "\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467": PoliticalPartyJoinMode.PUBLIC,
            "\U0001f4e9": PoliticalPartyJoinMode.REQUEST,
            "\U0001f575": PoliticalPartyJoinMode.PRIVATE
        }

        reaction = await ctx.choose(":information_source: Should this party be public, request-based, or private?\n\n",
                                    reactions=reactions.keys())

        join_mode = reactions[str(reaction)]

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO parties (id, discord_invite, join_mode) VALUES ($1, $2, $3)"
                    "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, join_mode = $3 WHERE parties.id = $1",
                    discord_role.id, party_invite, join_mode.value)

                await connection.execute("INSERT INTO party_alias (party_id, alias) VALUES ($1, $2)"
                                         " ON CONFLICT DO NOTHING ",
                                         discord_role.id, discord_role.name.lower())

                for leader in leaders:
                    await connection.execute("INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2)"
                                             " ON CONFLICT DO NOTHING ", discord_role.id, leader)

                if not is_updated:
                    await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party.')
                else:
                    await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party or its '
                                   f'properties were updated if it already existed.')

        return await PoliticalParty.convert(ctx, discord_role.id)

    @party.command(name='add', aliases=['create', 'make'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def addparty(self, ctx):
        """Add a new political party"""
        await self.create_new_party(ctx)

    @party.command(name='edit', aliases=['change'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def changeparty(self, ctx):
        """Edit an existing political party"""
        # todo
        await self.create_new_party(ctx)

    @party.command(name='delete', aliases=['remove'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def deleteparty(self, ctx, *, party: PoliticalParty):
        """Delete a political party

            **Usage:**
             `-party delete <party>`
        """

        name = party.role.name

        delete_role_too = await ctx.confirm(f":information_source: I will remove {name} from the list of "
                                            f"parties. Should I delete their Discord role too?")

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                await connection.execute("DELETE FROM parties WHERE id = $1", party.role.id)

        if delete_role_too:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.DELETE_ROLE, detail=party.role.name)

        await ctx.send(f':white_check_mark: `{name}` and all its aliases were deleted.')

    @party.command(name='addalias')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def addalias(self, ctx, *, party: PoliticalParty):
        """Add a new alias to a political party"""

        alias = await ctx.input(f":information_source: Reply with the new alias for `{party.role.name}`.")

        if not alias:
            return

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                         alias.lower(), party.role.id)

        await ctx.send(f':white_check_mark: Alias `{alias}` for party `{party.role.name}` was added.')

    @party.command(name='deletealias', aliases=['removealias'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def deletealias(self, ctx, *, alias: str):
        """Delete a party's alias"""
        try:
            await PoliticalParty.convert(ctx, alias)
        except exceptions.PartyNotFoundError:
            return await ctx.send(f":x: `{alias}` is not an alias of any party.")

        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias.lower())
        await ctx.send(f':white_check_mark: Alias `{alias}` was deleted.')

    @party.command(name='merge')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def mergeparties(self, ctx, amount_of_parties: int):
        """Merge one or multiple parties into a single, new party"""

        to_be_merged = []

        for i in range(1, amount_of_parties + 1):
            name = await ctx.input(f":information_source: What's the name or alias for political party #{i}?")

            if not name:
                return

            try:
                party = await PoliticalParty.convert(ctx, name)
            except exceptions.PartyNotFoundError:
                return await ctx.send(f":x: There is no party that matches `{name}`. Aborted.")

            to_be_merged.append(party)

        members_to_merge = {member for party in to_be_merged for member in party.role.members}
        pretty_parties = [f"`{party.role.name}`" for party in to_be_merged]

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to merge"
                                      f" {', '.join(pretty_parties)} into one, new party?")

        reaction = await ctx.confirm(message=are_you_sure)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        try:
            new_party = await self.create_new_party(ctx)
        except exceptions.DemocracivBotException as e:
            return await ctx.send(f"{e.message}\n:x: Party creation failed, old parties were not deleted.")

        if new_party is None or new_party.role is None:
            return await ctx.send(":x: Party creation failed, old parties were not deleted.")

        async with ctx.typing():
            for member in members_to_merge:
                await member.add_roles(new_party.role)

            for party in to_be_merged:
                # In case the merger keeps the name and thus role of an old party
                if party.role.id == new_party.role.id:
                    continue

                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("DELETE FROM party_alias WHERE party_id = $1; "
                                                 "DELETE FROM parties WHERE id = $1", party.role.id)

                await party.role.delete()

        await ctx.send(":white_check_mark: The old parties were deleted and"
                       " all their members have now the role of the new party.")


def setup(bot):
    bot.add_cog(Party(bot))