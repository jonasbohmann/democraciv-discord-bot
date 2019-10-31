import config
import string
import discord
import datetime

from util.embed import embed_builder
from discord.ext import commands


# -- parties.py | module.parties --
#
# Management of Political Parties
#


class Party(commands.Cog, name='Political Parties'):
    def __init__(self, bot):
        self.bot = bot

    def getPartyFromAlias(self, alias: str):
        """Gets party name from related alias, returns alias if it is not found"""
        return config.getPartyAliases().get(alias, alias)

    async def collectPartiesAndMembers(self, ctx):
        parties_and_members = []
        party_keys = config.getParties().keys()
        dciv_guild = self.bot.get_guild(int(config.getConfig()["democracivServerID"]))

        for party in party_keys:
            role = discord.utils.get(dciv_guild.roles, name=party)

            if role is None:
                await ctx.send(f':x: "{party}" was added as a party but has '
                               f'no role on this server!')
                continue

            parties_and_members.append((party, len(role.members)))

        return parties_and_members

    @commands.command(name='join')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def join(self, ctx, *party: str):
        """Join a Political Party"""
        if not party:
            await ctx.send(':x: You have to give me a party as argument!')
            return

        party_keys = (config.getParties().keys())
        party = string.capwords(' '.join(party))
        party = self.getPartyFromAlias(party)
        member = ctx.message.author
        guild = ctx.message.guild
        role = discord.utils.get(ctx.guild.roles, name=party)

        # Dict with party: partyLeader
        invite_only_parties = {'المتنورين': 466851004290170902}

        if party in config.getParties():
            if party not in [y.name for y in member.roles]:
                if party in invite_only_parties:
                    party_leader_mention = self.bot.get_user(invite_only_parties[party])

                    msg = f':x: {party} is invite-only. Ask {party_leader_mention.mention} for an invitation. '
                    await ctx.send(msg)
                    return

                if party == 'Independent':
                    msg = f':white_check_mark: You are now an {party}!'
                    await ctx.send(msg)
                    await member.add_roles(role)
                else:
                    msg = f':white_check_mark: You joined {party}! Now head to their Discord Server and introduce ' \
                          f'yourself: '
                    await ctx.send(msg)
                    await ctx.send(config.getParties()[party])
                    await member.add_roles(role)

            elif party in [y.name for y in member.roles]:
                await ctx.send(f'You are already part of {party}!')
                return

            # Logging
            if config.getGuildConfig(guild.id)['enableLogging']:
                guild = ctx.guild
                logchannel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = embed_builder(title=':family_mwgb: Joined Political Party', description="")
                embed.add_field(name='Member', value=member.mention + ' ' + member.name + '#' + member.discriminator,
                                inline=False)
                embed.add_field(name='Party', value=party)
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_thumbnail(url=member.avatar_url)
                await logchannel.send(content=None, embed=embed)

        elif party not in config.getParties():
            await ctx.send(':x: I could not find that party!\n\nTry one of these:')
            msg = ''
            for key in party_keys:
                msg += f'{key}\n'
            await ctx.send(msg)

    @commands.command(name='form')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def form(self, ctx):
        """Form a Political Party"""
        link = "https://forms.gle/ETyFrr6qucr95MMA9"
        await ctx.send(f"You can fill out this form with all the details to form a political party:\n{link}")

    @commands.command(name='leave')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def leave(self, ctx, *party: str):
        """Leave a Political Party"""

        if not party:
            await ctx.send(':x: You have to give me a party as argument!')
            return

        party = string.capwords(' '.join(party))
        party_keys = (config.getParties().keys())

        party = self.getPartyFromAlias(party)

        member = ctx.message.author
        guild = ctx.message.guild
        role = discord.utils.get(ctx.guild.roles, name=party)

        if party in config.getParties():
            if party in [y.name for y in member.roles]:
                if party == 'Independent':
                    msg = f':white_check_mark: You are no longer an {party}!'
                else:
                    msg = f':white_check_mark: You left {party}!'
                await ctx.send(msg)
                await member.remove_roles(role)
            elif party not in [y.name for y in member.roles]:
                await ctx.send(f'You are not part of {party}!')
                return

            # Logging
            if config.getGuildConfig(guild.id)['enableLogging']:
                guild = ctx.guild
                logchannel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = embed_builder(title=':triumph: Left Political Party', description="")
                embed.add_field(name='Member', value=member.mention + ' ' + member.name + '#' + member.discriminator,
                                inline=False)
                embed.add_field(name='Party', value=party)
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_thumbnail(url=member.avatar_url)
                await logchannel.send(content=None, embed=embed)

        elif party not in config.getParties():
            await ctx.send(':x: I could not find that party!\n\nTry one of these:')
            msg = ''
            for key in party_keys:
                msg += f'{key}\n'
            await ctx.send(msg)

    @commands.command(name='members')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def members(self, ctx, *party: str):
        """Lists all party members"""

        dciv_guild = self.bot.get_guild(int(config.getConfig()["democracivServerID"]))

        if dciv_guild is None:
            await ctx.send(':x: You have to invite me to the Democraciv server first!')

        if not party:
            party_list_embed_content = ''

            sorted_parties_and_members = sorted(await self.collectPartiesAndMembers(ctx), key=lambda x: x[1], reverse=True)

            for party in sorted_parties_and_members:
                if party[0] == 'Independent':
                    continue
                if party[1] == 1:
                    party_list_embed_content += f'**{party[0]}**\n{party[1]} member\n\n'
                else:
                    party_list_embed_content += f'**{party[0]}**\n{party[1]} members\n\n'

            # Append Independents to message
            independent_role = discord.utils.get(dciv_guild.roles, name='Independent')
            if len(independent_role.members) == 1:
                party_list_embed_content += f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n{len(independent_role.members)} citizen' \
                                         f'\n\n '
            else:
                party_list_embed_content += f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n{len(independent_role.members)} citizen' \
                                         f's\n\n'

            embed = embed_builder(title=f'Ranking of Political Parties in Arabia',
                                  description=f'{party_list_embed_content}', colour=0x7f0000)
            
            await ctx.send(embed=embed)

        elif party:
            party = string.capwords(' '.join(party))

            party = self.getPartyFromAlias(party)

            role = discord.utils.get(dciv_guild.roles, name=party)

            msg = ''
            for member in dciv_guild.members:
                if role in member.roles:
                    msg += f'{member.name}\n'
            if msg == '':
                await ctx.send(f":x: '{party}' either doesn't exist or it has 0 members!")
            else:
                if party == 'Independent':
                    title = 'Independent Citizens'
                else:
                    title = f'Members of {role}'

                embed = embed_builder(title=title, description=f'{msg}', colour=0x7f0000)
                await ctx.send(embed=embed)

    @commands.command(name='addparty', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addParty(self, ctx, invite: str, *party: str):
        """Add a new political party to the server"""
        if not party or not invite:
            await ctx.send(':x: You have to give me both the name and server invite of a political party to add!')

        else:
            party = ' '.join(party)
            error = await config.addParty(ctx.guild, invite, party)

            if error:
                await ctx.send(f':x: {error}')
            else:
                await ctx.send(f':white_check_mark: Added {party} with {invite}!')

    @commands.command(name='deleteparty', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def deleteParty(self, ctx, *party: str):
        """Delete a political party from the server"""
        if not party:
            await ctx.send(':x: You have to give me the name of a political party to delete!')

        else:
            party = ' '.join(party)
            error = await config.deleteParty(ctx.guild, party)

            if error:
                await ctx.send(f':x: {error}')
            else:
                await ctx.send(f':white_check_mark: Deleted {party}!')

    @commands.command(name='addalias', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addAlias(self, ctx, *party_and_alias: str):
        """Adds a new alias to party"""
        party_and_alias: tuple = await self.getArguments(ctx, ' '.join(party_and_alias), 2)
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

    @commands.command(name='deletealias', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def deleteAlias(self, ctx, *alias: str):
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
    async def listAliases(self, ctx, *party: str):
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
            embed = embed_builder(title=f'Aliases of {party}', description=f'{msg}', colour=0x7f0000)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f":x: No aliases found for {party}!")

    async def getArguments(self, ctx, arguments: str, expected_arguments: int = -1):
        """Returns arguments split upon commas as a tuple of strings.
        If arguments does not equal expected_arguments or there are blank arguments, posts a discord message and returns None.
        If expected_arguments is -1, does not check for argument count."""
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
