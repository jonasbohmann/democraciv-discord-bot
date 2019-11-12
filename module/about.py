import config

from discord.ext import commands


# -- about.py | module.about --
#
# Commands regarding the bot itself.
#


class About(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='about')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def about(self, ctx):
        """About this bot"""
        embed = self.bot.embeds.embed_builder(title='About', description="")
        embed.add_field(name='Author', value=config.getConfig()['author'], inline=True)
        embed.add_field(name='Version', value=config.getConfig()['botVersion'], inline=True)
        embed.add_field(name='Uptime', value=self.bot.get_uptime(), inline=True)
        embed.add_field(name='Prefix', value=config.getPrefix(), inline=True)
        embed.add_field(name='Ping', value=(str(self.bot.get_ping()) + 'ms'), inline=True)
        embed.add_field(name='Commands', value='See ' + config.getPrefix() + 'help', inline=True)
        await ctx.send(embed=embed)

    @commands.command(name='uptime')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def uptime(self, ctx):
        """Check how long I've been working"""
        embed = self.bot.embeds.embed_builder(title='Uptime', description=self.bot.get_uptime())
        await ctx.send(embed=embed)

    @commands.command(name='ping')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def ping(self, ctx):
        """Pong!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.get_ping()) + 'ms'))
        await ctx.send(embed=embed)

    @commands.command(name='pong', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def pong(self, ctx):
        """Ping!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.get_ping()) + 'ms'))
        await ctx.send(embed=embed)

    @commands.command(name='source')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def source(self, ctx):
        """Check out the source code on GitHub"""
        embed = self.bot.embeds.embed_builder(title='Source',
                                              description="https://github.com/jonasbohmann/democraciv-discord-bot")
        await ctx.send(embed=embed)

    @commands.command(name='contributors')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def contributors(self, ctx):
        """See who helped with this project :heart:"""
        embed = self.bot.embeds.embed_builder(title='Contributors :heart:',
                                              description="https://github.com/jonasbohmann/democraciv"
                                                          "-discord-bot/graphs/contributors")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(About(bot))
