import re
import typing
import discord

from util.flow import Flow
from discord.ext import commands
from config import config
from util import utils, exceptions, mk
from util.converter import PoliticalParty
from util.exceptions import ForbiddenTask


class Party(commands.Cog, name='Political Parties'):
    """Interact with the political parties of Democraciv. Note that you can only join and
    leave parties on the Democraciv server."""

    def __init__(self, bot):
        self.bot = bot

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv server and their amount of members for -members."""
        parties_and_members = []

        parties = await self.bot.db.fetch("SELECT id FROM parties")
        parties = [record['id'] for record in parties]

        error_string = []

        for party in parties:
            role = self.bot.democraciv_guild_object.get_role(party)

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
    async def party(self, ctx, *, party: PoliticalParty):
        """Detailed information about a single political party"""

        if party.role is None:
            return await ctx.send(":x: This party was removed.")

        invite_value = party.discord_invite if party.discord_invite else "*This party does not have a Discord server.*"
        thumbnail = await party.get_logo()

        embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  {party.role.name}",
                                              description=f"[Platform and Description]"
                                                          f"({self.bot.mk.POLITICAL_PARTIES})")

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        if party.leader:
            embed.add_field(name="Leader or Representative", value=party.leader.mention)

        embed.add_field(name="Server", value=invite_value)

        if party.aliases is not None:
            embed.add_field(name="Aliases", value=', '.join(party.aliases) or '-', inline=False)

        embed.add_field(name=f"Members ({len(party.role.members)})",
                        value='\n'.join([f"{member.mention} {member}" for member in party.role.members]) or '-',
                        inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='join')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def join(self, ctx, *, party: PoliticalParty):
        """Join a political party"""

        if party.role in ctx.author.roles:
            return await ctx.send(f':x: You are already part of {party.role.name}.')

        if party.is_private:
            if party.leader is None:
                msg = f':x: {party.role.name} is invite-only. Ask the party leader for an invitation.'
            else:
                msg = f':x: {party.role.name} is invite-only. Ask {party.leader.mention} for an invitation.'

            return await ctx.send(msg)

        try:
            await ctx.author.add_roles(party.role)
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
    @utils.is_democraciv_guild()
    async def leave(self, ctx, *, party: PoliticalParty):
        """Leave a political party"""

        if party.role not in ctx.author.roles:
            return await ctx.send(f':x: You are not part of {party.role.name}.')

        try:
            await ctx.author.remove_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.REMOVE_ROLE, detail=party.role.name)

        if party.role.name == 'Independent':
            msg = f':white_check_mark: You are no longer an {party.role.name}.'
        else:
            msg = f':white_check_mark: You left {party.role.name}.'
        await ctx.send(msg)

    @commands.command(name='ranking', aliases=['rank', 'ranks', 'members', 'member', 'rankings'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def members(self, ctx):
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
        independent_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name='Independent')

        if independent_role is not None:
            if len(independent_role.members) == 1:
                party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                f'{len(independent_role.members)} citizen')
            else:
                party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                f'{len(independent_role.members)} citizens')
        if len(party_list_embed_content) == 0:
            party_list_embed_content = ['There are no political parties yet.']

        embed = self.bot.embeds.embed_builder(title=f'{self.bot.mk.NATION_EMOJI}  Ranking of Political Parties '
                                                    f'in {self.bot.mk.NATION_NAME}')
        embed.description = f"[Party Platforms]({self.bot.mk.POLITICAL_PARTIES})\n\n" + '\n\n'.join(party_list_embed_content)
        return await ctx.send(embed=embed)

    async def create_new_party(self, ctx) -> typing.Optional[PoliticalParty]:
        await ctx.send(":information_source: Reply with the name of the new party you want to create.")

        flow = Flow(self.bot, ctx)
        role_name = await flow.get_new_role(240)

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

        await ctx.send(":information_source: Reply with the name of the party's leader or representative.")
        leader = await flow.get_text_input(240)

        if not leader:
            return

        try:
            leader_member = await commands.MemberConverter().convert(ctx, leader)
        except commands.BadArgument:
            raise exceptions.MemberNotFoundError(leader)

        await ctx.send(":information_source: Reply with the invite link to the party's Discord server. "
                       "If they don't have one, just reply with gibberish.")

        party_invite = await flow.get_text_input(300)

        if not party_invite:
            return None

        discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
        if not discord_invite_pattern.fullmatch(party_invite):
            party_invite = None

        is_private = False
        private_question = await ctx.send("Should this new party be **public**, i.e. join-able by everyone? "
                                          "React with :white_check_mark: if yes, or with :x: if not.")

        reaction = await flow.get_yes_no_reaction_confirm(private_question, 240)

        if reaction is None:
            return None

        if reaction:
            is_private = False

        elif not reaction:
            is_private = True

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO parties (id, discord_invite, is_private, leader) VALUES ($1, $2, $3, $4)"
                    "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, is_private = $3,"
                    " leader = $4 WHERE parties.id = $1",
                    discord_role.id, party_invite, is_private, leader_member.id)

                await connection.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)"
                                         " ON CONFLICT DO NOTHING ",
                                         discord_role.name.lower(), discord_role.id)

                if not is_updated:
                    await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party.')
                else:
                    await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party or its '
                                   f'properties were updated if it already existed.')

        return await PoliticalParty.convert(ctx, discord_role.id)

    @party.command(name='add', aliases=['create', 'make'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addparty(self, ctx):
        """Add a new political party or edit an existing one"""
        await self.create_new_party(ctx)

    @party.command(name='delete', aliases=['remove'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def deleteparty(self, ctx, hard: typing.Optional[bool] = False, *, party: PoliticalParty):
        """Remove a political party

            **Usage:**
             `-deleteparty true <party>` will remove the party **and** delete its Discord role
             `-deleteparty false <party>` will remove the party but not delete its Discord role

        """

        name = party.role.name

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                await connection.execute("DELETE FROM parties WHERE id = $1", party.role.id)

        if hard:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.DELETE_ROLE, detail=party.role.name)

        await ctx.send(f':white_check_mark: `{name}` and all its aliases were deleted.')

    @party.command(name='addalias')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addalias(self, ctx, *, party: PoliticalParty):
        """Add a new alias to a political party"""

        flow = Flow(self.bot, ctx)

        await ctx.send(f":information_source: Reply with the new alias for `{party.role.name}`.")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                status = await connection.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                  alias.lower(), party.role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Alias `{alias}` for party '
                           f'`{party.role.name}` was added.')

    @party.command(name='deletealias', aliases=['removealias'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
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
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def mergeparties(self, ctx, amount_of_parties: int):
        """Merge one or multiple parties into a single, new party"""

        flow = Flow(self.bot, ctx)

        to_be_merged = []

        for i in range(1, amount_of_parties + 1):
            await ctx.send(f":information_source: What's the name or alias for political party #{i}?")

            name = await flow.get_text_input(120)

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

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 120)

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
                        await connection.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                        await connection.execute("DELETE FROM parties WHERE id = $1", party.role.id)

                await party.role.delete()

        await ctx.send(":white_check_mark: The old parties were deleted and"
                       " all their members have now the role of the new party.")


def setup(bot):
    bot.add_cog(Party(bot))
