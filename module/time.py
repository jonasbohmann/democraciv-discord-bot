import pytz
import config
import discord

from datetime import datetime
from discord.ext import commands
from util.embed import embed_builder


class Time(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def returnTime(self, ctx, us: str, time: datetime, name, aliases = []):
        """Displays the current time in based on the inputted values."""
        aliases = '/'.join([name] + aliases).upper() # Turns the list of aliases into a formatted string
        if us == 'us':
            embed = embed_builder(title='Time - ' + aliases + ' - US Format',
                                  description=datetime.strftime(time, "%m/%d/%Y, %I:%M:%S %p"), colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return
        embed = embed_builder(title='Time - ' + aliases, description=datetime.strftime(time, "%d.%m.%Y, %H:%M:%S"),
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.group(name='time', case_insensitive=True)
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
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('CET')), 'cet', ['cest'])

    @time.command(name='gmt')
    async def gmt(self, ctx, us: str = None):
        """Displays the current time in GMT."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('GMT')), 'gmt')

    @time.command(name='mst', aliases=['mdt'])
    async def mst(self, ctx, us: str = None):
        """Displays the current time in MST."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('MST7MDT')), 'mst', ['mdt'])

    @time.command(name='pst', aliases=['pdt'])
    async def pst(self, ctx, us: str = None):
        """Displays the current time in PST."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('PST8PDT')), 'pst', ['pdt'])

    @time.command(name='utc')
    async def utc(self, ctx, us: str = None):
        """Displays the current time in UTC."""
        await self.returnTime(ctx, us, datetime.utcnow(), 'utc')

    @time.command(name='cst', aliases=['cdt'])
    async def cst(self, ctx, us: str = None):
        """Displays the current time in CST."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('CST6CDT')), 'cst', ['cdt'])

    @time.command(name='eet', aliases=['eest'])
    async def eet(self, ctx, us: str = None):
        """Displays the current time in EET."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('EET')), 'eet', ['eest'])

    @time.command(name='ast', aliases=['adt'])
    async def ast(self, ctx, us: str = None):
        """Displays the current time in AST."""
        await self.returnTime(ctx, us, datetime.now(tz=pytz.timezone('Canada/Atlantic')), 'ast', ['adt'])


def setup(bot):
    bot.add_cog(Time(bot))
