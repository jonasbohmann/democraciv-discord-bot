import typing
import discord
import asyncpg

from util.flow import Flow
from discord.ext import commands
from config import config, links
from util import utils, exceptions, mk
from util.exceptions import ForbiddenTask


class Party(commands.Cog, name='Political Parties'):
    """Interact with the political parties of Democraciv"""

    def __init__(self, bot):
        self.bot = bot

    async def get_parties_from_db(self) -> typing.Dict[int, str]:
        """Gets all parties from database and converts asyncpg.Record objects into Python dicts"""
        party_list = await self.bot.db.fetch("SELECT id, discord FROM parties")
        party_dict = {}

        for record in party_list:
            party_dict[record['id']] = record['discord']

        return party_dict

    async def get_party_role(self, party: str) -> typing.Optional[discord.Role]:
        """Returns role object that belongs to a political party.
        Gets aliases from party name first, if any exists get role object from party ID
        If no matching aliases were found in the database, try if discord.utils.get(name=...) can find the role.
        Returns None if every search/query failed."""

        lowercase_party = party.lower()
        party_id = await self.resolve_party_from_alias(lowercase_party)

        if isinstance(party_id, str):
            return discord.utils.get(self.bot.democraciv_guild_object.roles, name=party)
        elif isinstance(party_id, int):
            return self.bot.democraciv_guild_object.get_role(party_id)
        else:
            return None

    async def resolve_party_from_alias(self, party: str) -> typing.Union[str, int]:
        """Gets party name from related alias, returns input argument if no aliases are found"""
        party_id = await self.bot.db.fetchval("SELECT party_id FROM party_alias WHERE alias = $1", party)

        if party_id is None:
            return party
        else:
            return party_id

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv guild and their amount of members for -members."""
        parties_and_members = []
        party_keys = (await self.get_parties_from_db()).keys()
        error_string = "[DATABASE] The following ids were added as a party but have no role on the Democraciv guild: "

        for party in party_keys:
            role = self.bot.democraciv_guild_object.get_role(party)

            if role is None:
                error_string += f'{str(party)}, '
                continue

            parties_and_members.append((role.name, len(role.members)))

        if len(error_string) > 95:
            print(error_string)

        return parties_and_members

    @commands.command(name='join')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def join(self, ctx, *, party: str):
        """Join a political party"""

        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        role = await self.get_party_role(party)

        if role is None:
            await ctx.send(f":x: There is no party named `{party}`.")

            msg = ['**Try one of these:**\n']
            for key in available_parties_by_id:
                role = ctx.guild.get_role(key)
                if role is not None:
                    msg.append(role.name)

            if len(msg) < 1:
                await ctx.send('\n'.join(msg))
            return

        if role.id in available_parties_by_id:
            if role not in ctx.message.author.roles:

                is_private = await self.bot.db.fetchval("SELECT private FROM parties WHERE id = $1", role.id)

                if is_private:
                    party_leader_mention = self.bot.get_user(
                        await self.bot.db.fetchval("SELECT leader FROM parties WHERE id = $1", role.id))

                    if party_leader_mention is None:
                        msg = f':x: {role.name} is invite-only. Ask the party leader for an invitation.'
                    else:
                        msg = f':x: {role.name} is invite-only. Ask {party_leader_mention.mention} for an invitation.'

                    return await ctx.send(msg)

                try:
                    await ctx.message.author.add_roles(role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, role.name)

                if role.name == 'Independent':
                    await ctx.send(f':white_check_mark: You are now an {role.name}!')

                else:
                    await ctx.send(
                        f':white_check_mark: You\'ve joined {role.name}! Now head to their Discord Server and '
                        f'introduce yourself: ')
                    await ctx.send(available_parties[role.id])

            else:
                return await ctx.send(f':x: You are already part of {role.name}!')

        else:
            await ctx.send(
                f":x: That is not a political party! If you're trying to give yourself a role from `-roles`, "
                f"use `-role {role.name}`.")

    @commands.command(name='form')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def form(self, ctx):
        """Form a political party"""
        await ctx.send(f"You can fill out this form with all the details to form a political party:\n{links.formparty}")

    @commands.command(name='leave')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def leave(self, ctx, *, party: str):
        """Leave a political party"""

        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        role = await self.get_party_role(party)

        if role is None:
            await ctx.send(f":x: There is no party named `{party}`.")

            msg = ['**Try one of these:**\n']
            for key in available_parties_by_id:
                role = ctx.guild.get_role(key)
                if role is not None:
                    msg.append(role.name)

            if len(msg) < 1:
                await ctx.send('\n'.join(msg))
            return

        if role.id in available_parties_by_id:
            if role in ctx.message.author.roles:
                if role.name == 'Independent':
                    msg = f':white_check_mark: You are no longer an {role.name}!'
                else:
                    msg = f':white_check_mark: You left {role.name}!'
                await ctx.send(msg)

                try:
                    await ctx.message.author.remove_roles(role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(ForbiddenTask.REMOVE_ROLE, detail=role.name)

            else:
                return await ctx.send(f':x: You are not part of {role.name}!')

        else:
            await ctx.send(f":x: That is not a political party! If you're trying to remove a role from `-roles` from "
                           f"you, use `-role {role.name}`.")

    @commands.command(name='members')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def members(self, ctx, *, party: str = None):
        """Get the current political party ranking or a list of all party members on the Democraciv guild"""

        # Show Ranking
        if party is None:
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

            embed = self.bot.embeds.embed_builder(title=f'Ranking of Political Parties in {mk.NATION_NAME}',
                                                  description='\n\n'.join(party_list_embed_content), colour=0x7f0000)

            return await ctx.send(embed=embed)

        # Show member names of single party
        elif party:
            role = await self.get_party_role(party)

            if role is None:
                if ctx.guild.id != self.bot.democraciv_guild_object.id:
                    return await ctx.send(":x: This command uses the roles and members from the Democraciv guild,"
                                          " not the ones from this guild!")
                raise exceptions.RoleNotFoundError(party)

            list_of_members = [member.name for member in role.members]

            if len(list_of_members) == 0:
                list_of_members = ['No members.']

            title = 'Independent Citizens' if party == 'Independent' else f'Members of {role.name}'

            embed = self.bot.embeds.embed_builder(title=title, description='\n'.join(list_of_members), colour=0x7f0000)
            return await ctx.send(embed=embed)

    @commands.command(name='addparty')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addparty(self, ctx):
        """Add a new political party"""

        await ctx.send(":information_source: Reply with the name of the party you want to create:")

        flow = Flow(self.bot, ctx)
        role_name = await flow.get_new_role(240)

        if isinstance(role_name, str):
            await ctx.send(
                f":white_check_mark: I will **create a new role** on this guild named `{role_name}`"
                f" for the new party.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            discord_role = role_name

            await ctx.send(
                f":white_check_mark: I'll use the **pre-existing role** named "
                f"'{discord_role.name}' for the new party.")

        await ctx.send(":information_source: Reply with the invite link to the party's Discord guild:")

        party_invite = await flow.get_text_input(300)

        if not party_invite:
            return

        is_private = False
        private_question = await ctx.send(
            "Should this new party be private? React with :white_check_mark: if yes, or with :x: if not.")

        reaction = await flow.get_yes_no_reaction_confirm(private_question, 240)

        if reaction is None:
            return

        if reaction:
            is_private = True

            await ctx.send(":information_source: Reply with the name of the party's leader:")

            leader = await flow.get_text_input(240)

            if leader:
                try:
                    leader_role = await commands.MemberConverter().convert(ctx, leader)
                except commands.BadArgument:
                    raise exceptions.MemberNotFoundError(leader)

        elif not reaction:
            is_private = False

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                if is_private:
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO parties (id, discord, private, leader) VALUES ($1, $2, $3, $4)",
                            discord_role.id,
                            party_invite, True, leader_role.id)
                    except asyncpg.UniqueViolationError:
                        return await ctx.send(f":x: A party named `{discord_role.name}` already exists!")
                else:
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO parties (id, discord, private) VALUES ($1, $2, $3)", discord_role.id,
                            party_invite, False)
                    except asyncpg.UniqueViolationError:
                        return await ctx.send(f":x: A party named `{discord_role.name}` already exists!")

                status = await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                   discord_role.name.lower(), discord_role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name='deleteparty')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def deleteparty(self, ctx, hard: bool, *, party: str):
        """Remove a political party

                Usage:
                 `-deleteparty true <party>` will remove the party **and** delete its Discord role
                 `-deleteparty false <party>` will remove the party but not delete its Discord role

        """
        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        discord_role = await self.get_party_role(party)

        if discord_role is None:
            raise exceptions.RoleNotFoundError(party)

        if discord_role.id in available_parties_by_id:
            if hard:
                try:
                    await discord_role.delete()
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(ForbiddenTask.DELETE_ROLE, detail=discord_role.name)

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await self.bot.db.execute("DELETE FROM party_alias WHERE party_id = $1", discord_role.id)
                    await self.bot.db.execute("DELETE FROM parties WHERE id = $1", discord_role.id)

            await ctx.send(f':white_check_mark: `{discord_role.name}` and all its aliases were deleted.')

    @commands.command(name='addalias')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addalias(self, ctx):
        """Add a new alias to a political party"""

        await ctx.send(":information_source: Reply with the name of the party that the new alias should belong to:")

        flow = Flow(self.bot, ctx)

        party = await flow.get_text_input(240)

        if not party:
            return

        # Check if party role already exists
        discord_role = await self.get_party_role(party)

        if discord_role is None:
            raise exceptions.RoleNotFoundError(party)

        await ctx.send(f":information_source: Reply with the alias for `{discord_role.name}`:")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                status = await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                   alias.lower(), discord_role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Alias `{alias}` for party '
                           f'`{discord_role.name}` was added.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name='deletealias', aliases=['removealias'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def deletealias(self, ctx, *, alias: str):
        """Delete a party's alias"""
        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias.lower())
        await ctx.send(f':white_check_mark: Alias `{alias}` was deleted.')

    @commands.command(name='listaliases')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def listaliases(self, ctx, *, party: str):
        """List all aliases of a given party"""

        discord_role = await self.get_party_role(party)

        if discord_role is None:
            raise exceptions.RoleNotFoundError(party)

        aliases = await self.bot.db.fetch("SELECT alias FROM party_alias WHERE party_id = $1", discord_role.id)
        message = [record['alias'] for record in aliases]

        if len(message) == 0:
            return await ctx.send(f":x: There are no aliases for `{discord_role.name}`.")

        embed = self.bot.embeds.embed_builder(title=f'Aliases of {discord_role.name}', description='\n'.join(message))
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Party(bot))
