import asyncio

import config
import string
import discord

import util.utils as utils
import util.exceptions as exceptions

from discord.ext import commands


# -- parties.py | module.parties --
#
# Management of Political Parties
#


class Party(commands.Cog, name='Political Parties'):
    def __init__(self, bot):
        self.bot = bot

    async def get_parties_from_db(self):
        party_list = await self.bot.db.fetch("SELECT (id, discord) FROM parties")
        party_dict = {}

        for record in party_list:
            party_dict[record[0][0]] = record[0][1]

        return party_dict

    async def get_party_role(self, ctx, party):
        party_id = await self.resolve_party_from_alias(string.capwords(party))

        if isinstance(party_id, str):
            return discord.utils.get(ctx.guild.roles, name=party_id)
        elif isinstance(party_id, int):
            return ctx.guild.get_role(party_id)
        else:
            return None

    async def resolve_party_from_alias(self, party):
        """Gets party name from related alias, returns alias if it is not found"""
        party_id = await self.bot.db.fetchrow("SELECT party_id FROM party_alias WHERE alias = $1", party)

        if party_id is None:
            return party
        else:
            return party_id['party_id']

    async def collect_parties_and_members(self, ctx):
        parties_and_members = []
        party_keys = (await self.get_parties_from_db()).keys()
        error_string = "The following parties were added as a party but have no role on the Democraciv guild:\n"

        for party in party_keys:
            role = ctx.guild.get_role(party)

            if role is None:
                error_string += f'    -  `{str(party)}`\n'
                continue

            parties_and_members.append((role.name, len(role.members)))

        if len(error_string) > 85:
            print(error_string)

        return parties_and_members

    @commands.command(name='join')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def join(self, ctx, *, party):
        """Join a Political Party"""

        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        role = await self.get_party_role(ctx, party)

        if role is None:
            await ctx.send(f":x: Couldn't find a party named '{party}'!\n\nTry one of these:")
            msg = ''
            for key in available_parties_by_id:
                role = ctx.guild.get_role(key)
                if role is not None:
                    msg += f'{role.name}\n'
            await ctx.send(msg)
            return

        if role.id in available_parties_by_id:
            if role not in ctx.message.author.roles:
                is_private = (await self.bot.db.fetchrow("SELECT private FROM parties WHERE id = $1", role.id))[
                    'private']
                if is_private:
                    party_leader_mention = self.bot.get_user(
                        (await self.bot.db.fetchrow("SELECT leader FROM parties WHERE id = $1", role.id))['leader'])

                    if party_leader_mention is None:
                        msg = f':x: {role.name} is invite-only. Ask the party leader for an invitation.'
                    else:
                        msg = f':x: {role.name} is invite-only. Ask {party_leader_mention.mention} for an invitation.'

                    await ctx.send(msg)
                    return

                try:
                    await ctx.message.author.add_roles(role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError("add_roles", role.name)

                if role.name == 'Independent':
                    await ctx.send(f':white_check_mark: You are now an {role.name}!')

                else:
                    await ctx.send(
                        f':white_check_mark: You joined {role.name}! Now head to their Discord Server and '
                        f'introduce yourself: ')
                    await ctx.send(available_parties[role.id])

            else:
                await ctx.send(f':x: You are already part of {role.name}!')
                return

        else:
            await ctx.send(f":x: That is not a political party! If you're trying to give yourself a role from `-roles`, "
                           f"use `-role {role.name}`.")
    @join.error
    async def joinerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'party':
                await ctx.send(':x: You have to specify the party you want to join!\n\n**Usage**:\n'
                               '`-join <party>`')

    @commands.command(name='form')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def form(self, ctx):
        """Form a Political Party"""
        link = "https://forms.gle/ETyFrr6qucr95MMA9"
        await ctx.send(f"You can fill out this form with all the details to form a political party:\n{link}")

    @commands.command(name='leave')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def leave(self, ctx, *, party):
        """Leave a Political Party"""

        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        role = await self.get_party_role(ctx, party)

        if role is None:
            await ctx.send(f":x: Couldn't find a party named '{party}'!\n\nTry one of these:")
            msg = ''
            for key in available_parties_by_id:
                role = ctx.guild.get_role(key)
                if role is not None:
                    msg += f'{role.name}\n'
            await ctx.send(msg)
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
                    raise exceptions.ForbiddenError(task="remove_roles", detail=role.name)

            else:
                await ctx.send(f':x: You are not part of {role.name}!')
                return

        else:
            await ctx.send(f":x: That is not a political party! If you're trying to remove a role from `-roles` from "
                           f"you, use `-role {role.name}`.")

    @leave.error
    async def leaveerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'party':
                await ctx.send(':x: You have to specify the party you want to leave!\n\n**Usage**:\n'
                               '`-leave <party>`')

    @commands.command(name='members')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def members(self, ctx, *, party=''):
        """Lists all party members"""
        if not party:
            party_list_embed_content = ''

            async with ctx.typing():
                sorted_parties_and_members = sorted(await self.collect_parties_and_members(ctx), key=lambda x: x[1],
                                                    reverse=True)

                for party in sorted_parties_and_members:
                    if party[0] == 'Independent':
                        continue
                    if party[1] == 1:
                        party_list_embed_content += f'**{party[0]}**\n{party[1]} member\n\n'
                    else:
                        party_list_embed_content += f'**{party[0]}**\n{party[1]} members\n\n'

                # Append Independents to message
                independent_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name='Independent')
                if len(independent_role.members) == 1:
                    party_list_embed_content += f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n{len(independent_role.members)}' \
                                                f' citizen\n\n'
                else:
                    party_list_embed_content += f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n{len(independent_role.members)}' \
                                                f' citizens\n\n'

                embed = self.bot.embeds.embed_builder(title=f'Ranking of Political Parties in Arabia',
                                                      description=f'{party_list_embed_content}', colour=0x7f0000)

            await ctx.send(embed=embed)

        elif party:
            role = await self.get_party_role(ctx, party)

            if role is None:
                raise exceptions.RoleNotFoundError(party)

            msg = ''
            for member in self.bot.democraciv_guild_object.members:
                if role in member.roles:
                    msg += f'{member.name}\n'

            if msg == '':
                msg = 'No members.'

            else:
                if party == 'Independent':
                    title = 'Independent Citizens'
                else:
                    title = f'Members of {role.name}'

                embed = self.bot.embeds.embed_builder(title=title, description=f'{msg}', colour=0x7f0000)
                await ctx.send(embed=embed)

    @commands.command(name='addparty')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def addparty(self, ctx):
        """Add a new political party to the server. Takes no arguments."""

        await ctx.send(":information_source: Answer with the name of the party you want to create:")
        try:
            role_name = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                timeout=240)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        # Check if party role already exists
        discord_role = discord.utils.get(ctx.guild.roles, name=role_name.content)

        if discord_role:
            await ctx.send(f":white_check_mark: I will use the **already existing role** named '{discord_role.name}'"
                           f" for the new party.")
        else:
            await ctx.send(f":white_check_mark: I will **create a new role** on this guild named '{role_name.content}'"
                           f" for the new party.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name.content)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(task="create_role", detail=role_name.content)

        await ctx.send(":information_source: Answer with the invite link to the party's Discord guild:")

        try:
            party_invite = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                   timeout=300)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await self.bot.db.execute("INSERT INTO parties (id, discord) VALUES ($1, $2)", discord_role.id,
                                          party_invite.content)

                await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                          role_name.content, discord_role.id)
                status = await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                   string.capwords(role_name.content), discord_role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Added the party "{discord_role.name}" with the invite '
                           f'"{party_invite.content}"!')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name='deleteparty')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def deleteparty(self, ctx, hard: bool, *, party):
        """Remove a party.

                Usage:
                 `-deleteparty true <party>` will remove the party **and** delete its Discord role
                 `-deleteparty false <party>` will remove the party but not delete its Discord role

        """
        available_parties = await self.get_parties_from_db()
        available_parties_by_id = available_parties.keys()

        discord_role = await self.get_party_role(ctx, party)

        if discord_role is None:
            raise exceptions.RoleNotFoundError(party)

        if discord_role.id in available_parties_by_id:
            if hard:
                try:
                    await discord_role.delete()
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(task="delete_role", detail=discord_role.name)

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await self.bot.db.execute("DELETE FROM party_alias WHERE party_id = $1", discord_role.id)
                    await self.bot.db.execute("DELETE FROM parties WHERE id = $1", discord_role.id)

            await ctx.send(f':white_check_mark: Deleted the party "{discord_role.name}" and all its aliases.')

    @deleteparty.error
    async def deletepartyerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'hard':
                await ctx.send(':x: You have to specify if I should hard-delete or not!\n\n**Usage**:\n'
                               '`-deleteparty true <party>` will remove the party **and** delete its Discord role\n'
                               '`-deleteparty false <party>` will remove the party but not delete its Discord role')

            if error.param.name == 'party':
                await ctx.send(':x: You have to give me the name of a party to delete!\n\n**Usage**:\n'
                               '`-deleteparty true <party>` will remove the party **and** delete its Discord role\n'
                               '`-deleteparty false <party>` will remove the party but not delete its Discord role')

        elif isinstance(error, commands.BadArgument):
            await ctx.send(':x: Error!\n\n**Usage**:\n'
                           '`-deleteparty true <party>` will remove the party **and** delete its Discord role\n'
                           '`-deleteparty false <party>` will remove the party but not delete its Discord role')

    @commands.command(name='addalias')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def addalias(self, ctx, *party_and_alias: str):
        """Adds a new alias to party"""

        party_and_alias: tuple = await self.get_arguments(ctx, ' '.join(party_and_alias), 2)
        if party_and_alias is None:
            return
        party, alias = party_and_alias
        error = await config.addPartyAlias(party, alias)

        if error:
            await ctx.send(f':x: {error}')
        else:
            # Get proper names
            alias = string.capwords(alias)
            party = config.getPartyAliases()[alias]

            await ctx.send(f':white_check_mark: Added {alias} as an alias for {party}!')

    @commands.command(name='deletealias')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def deletealias(self, ctx, *alias: str):
        """Deletes pre-existing alias"""

        alias = ' '.join(alias)
        error = await config.deletePartyAlias(alias)

        if error:
            await ctx.send(f':x: {error}')
        else:
            # Get proper name
            alias = string.capwords(alias)
            await ctx.send(f':white_check_mark: Deleted {alias}!')

    @commands.command(name='listaliases')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def listaliases(self, ctx, *party: str):
        """Lists the given parties aliases, if any exist"""
        party = string.capwords(' '.join(party))
        caps_party = party

        parties, aliases = config.getParties(), config.getPartyAliases()
        if party in parties:
            pass
        elif party in aliases:
            party = aliases[party]
            caps_party = string.capwords(party)
        else:
            await ctx.send(f':x: {party} not found!')
            return

        msg = ''
        for alias in aliases:
            if aliases[alias] == party and alias != caps_party:
                msg += f'{alias}\n'

        if msg:
            embed = self.bot.embeds.embed_builder(title=f'Aliases of {party}', description=f'{msg}', colour=0x7f0000)

            await ctx.send(embed=embed)
        else:
            await ctx.send(f":x: No aliases found for {party}!")

    async def get_arguments(self, ctx, arguments: str, expected_arguments: int = -1):
        """Returns arguments split upon commas as a tuple of strings.
        If arguments does not equal expected_arguments or there are blank arguments, posts a discord message and returns
        None. If expected_arguments is -1, does not check for argument count."""
        argument_count = arguments.count(',') + 1
        if expected_arguments != -1 and argument_count != expected_arguments:
            await ctx.send(f':x: Was given {argument_count} arguments but expected {expected_arguments}!')
            return None

        arguments = tuple(argument.strip() for argument in arguments.split(','))
        if '' in arguments:
            await ctx.send(f':x: Cannot accept blank arguments!')
            return None

        return arguments


def setup(bot):
    bot.add_cog(Party(bot))
