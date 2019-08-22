import math
import time
import config
import discord
import datetime

from discord.ext import commands

# -- about.py | module.about --
#
# Commands regarding the bot itself.
#

startTime = time.time()


def getUptime():
    currentTime = time.time()
    difference = int(round(currentTime - startTime))
    return str(datetime.timedelta(seconds=difference))


class About(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def getPing(self):
        return math.floor(self.bot.latency * 1000)

    @commands.command(name='about')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def about(self, ctx):
        """About this bot"""
        embed = discord.Embed(title='About', colour=0x7f0000)
        embed.add_field(name='Author', value=config.getConfig()['author'], inline=True)
        embed.add_field(name='Version', value=config.getConfig()['botVersion'], inline=True)
        embed.add_field(name='Uptime', value=getUptime(), inline=True)
        embed.add_field(name='Prefix', value=config.getPrefix(), inline=True)
        embed.add_field(name='Ping', value=(str(self.getPing()) + 'ms'), inline=True)
        embed.add_field(name='Commands', value='See ' + config.getPrefix() + 'help', inline=True)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='uptime')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def uptime(self, ctx):
        """Check how long I've been working"""
        embed = discord.Embed(title='Uptime', description=getUptime(), colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='ping')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def ping(self, ctx):
        """Pong!"""
        embed = discord.Embed(title='Ping', description=(str(self.getPing()) + 'ms'), colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='pong', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def pong(self, ctx):
        """Ping!"""
        embed = discord.Embed(title='Ping', description=(str(self.getPing()) + 'ms'), colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='source')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def source(self, ctx):
        """Check out the source code on GitHub"""
        embed = discord.Embed(title='Source', description="https://github.com/jonasbohmann/democraciv-discord-bot",
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='contributors')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def contributors(self, ctx):
        """See who helped with this project :heart:"""
        embed = discord.Embed(title='Contributors :heart:', description="https://github.com/jonasbohmann/democraciv-discord-bot/graphs/contributors",
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)


def setup(bot):
    bot.add_cog(About(bot))



