import pytz
import config
import discord

from datetime import datetime
from discord.ext import commands


class Time:
    def __init__(self, bot):
        self.bot = bot
    
    async def returnTime(self, ctx, us: str, time, name, aliases):
        aliases = '/'.join([name] + aliases).upper()
        if us == 'us':
            embed = discord.Embed(title='Time - ' + aliases + ' - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - ' + aliases, description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.group(name='time')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def time(self, ctx):
        """Displays the current time. Specify the timezone as argument.\nExample: -time est\nAdd \"us\" at the end to get the time in US formatting."""

    @time.command(name='est', aliases=['edt'])
    async def est(self, ctx, us: str = None):
        """Displays the current time in EST."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('EST5EDT')), 'est', ['edt'])

    @time.command(name='cet', aliases=['cest'])
    async def cet(self, ctx, us: str = None):
        """Displays the current time in CET."""
        time = datetime.now(tz=pytz.timezone('CET'))
        if us == 'us':
            embed = discord.Embed(title='Time - CET/CEST - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - CET/CEST', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @time.command(name='gmt')
    async def gmt(self, ctx, us: str = None):
        """Displays the current time in GMT."""
        time = datetime.now(tz=pytz.timezone('GMT'))
        if us == 'us':
            embed = discord.Embed(title='Time - GMT - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - GMT', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @time.command(name='mst', aliases=['mdt'])
    async def mst(self, ctx, us: str = None):
        """Displays the current time in MST."""
        time = datetime.now(tz=pytz.timezone('MST7MDT'))
        if us == 'us':
            embed = discord.Embed(title='Time - MST/MDT - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - MST/MDT', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @time.command(name='pst', aliases=['pdt'])
    async def pst(self, ctx, us: str = None):
        """Displays the current time in PST."""
        time = datetime.now(tz=pytz.timezone('PST8PDT'))
        if us == 'us':
            embed = discord.Embed(title='Time - PST/PDT - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - PST/PDT', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @time.command(name='utc')
    async def utc(self, ctx, us: str = None):
        """Displays the current time in UTC."""
        time = datetime.utcnow()
        if us == 'us':
            embed = discord.Embed(title='Time - UTC - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - UTC ', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @time.command(name='cst', aliases=['cdt'])
    async def cst(self, ctx, us: str = None):
        """Displays the current time in CST."""
        time = datetime.now(tz=pytz.timezone('CST6CDT'))
        if us == 'us':
            embed = discord.Embed(title='Time - CST/CDT - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = discord.Embed(title='Time - CST/CDT', description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)


def setup(bot):
    bot.add_cog(Time(bot))
