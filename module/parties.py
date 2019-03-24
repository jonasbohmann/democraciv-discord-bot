import config
import string
import discord
import datetime

from discord.ext import commands


# -- parties.py | module.parties --
#
# Management of Political Parties
#

class Party:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='join')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def join(self, ctx, *party: str):
        """Join a Political Party"""
        if not party:
            await ctx.send(':x: You have to give me a party as argument!')
            return

        partyKeys = (config.getParties().keys())

        party = string.capwords(' '.join(party))

        # Fix capwords
        if party == 'Democracorp':
            party = 'DemocraCorp'
        elif party == 'Monarchist Party Of Norway':
            party = 'Monarchist Party of Norway'
        elif party == 'Industro-optimists':
            party = 'Industro-Optimists'

        member = ctx.message.author
        role = discord.utils.get(ctx.guild.roles, name=party)

        if party in config.getParties():
            if party not in [y.name for y in member.roles]:
                if party == 'Independent':
                    msg = f':white_check_mark: You are now an {party}!'
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
        if not list:
            msg = ''
            partyKeys = config.getParties().keys()
            for party in partyKeys:
                role = discord.utils.get(ctx.guild.roles, name=party)
                if len(role.members) == 1:
                    msg += f'**{party}**\n{len(role.members)} member\n\n'
                else:
                    msg += f'**{party}**\n{len(role.members)} members\n\n'
            embed = discord.Embed(title=f'Ranking of Political Parties', description=f'{msg}', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(embed=embed)
        if list == 'list':
            roleName = ' '.join(party)
            role = discord.utils.get(ctx.guild.roles, name=roleName)
            msg = ''
            for member in ctx.guild.members:
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
    async def addparty(self, ctx, *party: str, invite: str):
        if not party or not invite:
            await ctx.send(':x: You have to give me both the name and server invite of a political party to add!')

        else:
            # config.addParty(party, invite)
            # await ctx.send(f':white_check_mark: Added {party} with {invite}!')
            await ctx.send(':x: This is under construction!')

    @commands.command(name='deleteparty', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def deleteparty(self, ctx, *party: str, invite: str):
        if not party or not invite:
            await ctx.send(':x: You have to give me both the name and server invite of a political party to add!')

        else:
            # config.deleteParty(party)
            # await ctx.send(f':white_check_mark: Deleted {party}!')
            await ctx.send(':x: This is under construction!')


def setup(bot):
    bot.add_cog(Party(bot))
