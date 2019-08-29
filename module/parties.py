import config
import string
import discord
import datetime

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

    @commands.command(name='join')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def join(self, ctx, *party: str):
        """Join a Political Party"""
        if not party:
            await ctx.send(':x: You have to give me a party as argument!')
            return

        partyKeys = (config.getParties().keys())

        party = string.capwords(' '.join(party))

        party = self.getPartyFromAlias(party)

        member = ctx.message.author
        role = discord.utils.get(ctx.guild.roles, name=party)

        inviteOnlyParties = []

        if party in config.getParties():
            if party not in [y.name for y in member.roles]:
                if party == 'Independent':
                    msg = f':white_check_mark: You are now an {party}!'
                    await ctx.send(msg)
                    await member.add_roles(role)
                if party in inviteOnlyParties:
                    msg = f':x: {party} is invite-only. Ask the party leader for an invitation.'
                    await ctx.send(msg)
                else:
                    msg = f':white_check_mark: You joined {party}! Now head to their Discord Server and introduce yourself:'
                    await ctx.send(msg)
                    await ctx.send(config.getParties()[party])
                    await member.add_roles(role)
            elif party in [y.name for y in member.roles]:
                await ctx.send(f'You are already part of {party}!')
                return

            # Logging
            if config.getConfig()['enableLogging']:
                guild = ctx.guild
                logchannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                embed = discord.Embed(title=':family_mwgb: Joined Political Party', colour=0x7f0000)
                embed.add_field(name='Member', value=member.mention + ' ' + member.name + '#' + member.discriminator,
                                inline=False)
                embed.add_field(name='Party', value=party)
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_thumbnail(url=member.avatar_url)
                await logchannel.send(content=None, embed=embed)

        elif party not in config.getParties():
            await ctx.send(':x: I could not find that party!\n\nTry one of these:')
            msg = ''
            for key in partyKeys:
                msg += f'{key}\n'
            await ctx.send(msg)

    @commands.command(name='form')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def form(self, ctx):
        """Form a Political Party"""
        link = "https://goo.gl/forms/pW3lcPCYmYrUC41T2"
        await ctx.send(f"You can fill out this form with all the details to form a political party:\n{link}")

    @commands.command(name='leave')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def leave(self, ctx, *party: str):
        """Leave a Political Party"""

        if not party:
            await ctx.send(':x: You have to give me a party as argument!')
            return

        party = string.capwords(' '.join(party))
        partyKeys = (config.getParties().keys())

        party = self.getPartyFromAlias(party)

        member = ctx.message.author
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
            if config.getConfig()['enableLogging']:
                guild = ctx.guild
                logchannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                embed = discord.Embed(title=':triumph: Left Political Party', colour=0x7f0000)
                embed.add_field(name='Member', value=member.mention + ' ' + member.name + '#' + member.discriminator,
                                inline=False)
                embed.add_field(name='Party', value=party)
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_thumbnail(url=member.avatar_url)
                await logchannel.send(content=None, embed=embed)

        elif party not in config.getParties():
            await ctx.send(':x: I could not find that party!\n\nTry one of these:')
            msg = ''
            for key in partyKeys:
                msg += f'{key}\n'
            await ctx.send(msg)

    @commands.command(name='members')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def members(self, ctx, list: str = None, *party: str):
        """Lists all party members"""

        dcivGuild = self.bot.get_guild(int(config.getConfig()["homeServerID"]))

        if dcivGuild is None:
            await ctx.send(':x: You have to invite me to the Democraciv server first!')

        if not list:
            msg = ''
            partyKeys = config.getParties().keys()
            for party in partyKeys:
                role = discord.utils.get(dcivGuild.roles, name=party)
                if role is None:
                    await ctx.send(f':x: "{party}" was added as a party but has no role on this server!')
                    continue
                if len(role.members) == 1:
                    msg += f'**{party}**\n{len(role.members)} member\n\n'
                else:
                    msg += f'**{party}**\n{len(role.members)} members\n\n'
            embed = discord.Embed(title=f'Ranking of Political Parties', description=f'{msg}', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(embed=embed)

        if list == 'list':
            party = string.capwords(' '.join(party))

            party = self.getPartyFromAlias(party)

            role = discord.utils.get(dcivGuild.roles, name=party)
            msg = ''
            for member in dcivGuild.members:
                if role in member.roles:
                    msg += f'{member.name}\n'
            if msg == '':
                await ctx.send(":x: Couldn't find role!")
            else:
                embed = discord.Embed(title=f'Members of {role}', description=f'{msg}', colour=0x7f0000)
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                await ctx.send(embed=embed)

    @commands.command(name='addparty', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addparty(self, ctx, invite: str, *party: str):
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
    async def deleteparty(self, ctx, *party: str):
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
    async def addalias(self, ctx, *partyAndAlias: str):
        """Adds a new alias to party"""
        partyAndAlias: tuple = await self.getArguments(ctx, ' '.join(partyAndAlias), 2)
        if partyAndAlias is None:
            return
        party, alias = partyAndAlias
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
        capsParty = party

        parties, aliases = config.getParties(), config.getPartyAliases()
        if party in parties:
            pass
        elif party in aliases:
            party = aliases[party]
            capsParty = string.capwords(party)
        else:
            await ctx.send(f':x: {party} not found!')
            return

        msg = ''
        for alias in aliases:
            if aliases[alias] == party and alias != capsParty:
                msg += f'{alias}\n'

        if msg:
            embed = discord.Embed(title=f'Aliases of {party}', description=f'{msg}', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(embed=embed)
        else:
            await ctx.send(f":x: No aliases found for {party}!")

    async def getArguments(self, ctx, arguments: str, expectedArguments: int = -1):
        """Returns arguments split upon commas as a tuple of strings.
        If arguments does not equal expectedArguments or there are blank arguments, posts a discord message and returns None.
        If expectedArguments is -1, does not check for argument count."""
        argumentCount = arguments.count(',') + 1
        if expectedArguments != -1 and argumentCount != expectedArguments:
            await ctx.send(f':x: Was given {argumentCount} arguments but expected {expectedArguments}!')
            return None

        arguments = tuple(argument.strip() for argument in arguments.split(','))
        if '' in arguments:
            await ctx.send(f':x: Cannot accept blank arguments!')
            return None

        return arguments


def setup(bot):
    bot.add_cog(Party(bot))
