import discord

from config import config
from discord.ext import commands


class About(commands.Cog):
    """Information about this bot"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='about')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def about(self, ctx):
        """About this bot"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(2081418487))

        embed = self.bot.embeds.embed_builder(title='About This Bot', description=f"[Invite this bot to your"
                                                                                  f" Discord Guild.]({invite_url})")
        embed.add_field(name='Author', value=str(self.bot.owner), inline=True)
        embed.add_field(name='Version', value=config.BOT_VERSION, inline=True)
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name='Guilds', value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name='Users', value=str(len(self.bot.users)), inline=True)
        embed.add_field(name='Prefix', value=config.BOT_PREFIX, inline=True)
        embed.add_field(name='Uptime', value=self.bot.get_uptime(), inline=True)
        embed.add_field(name='Ping', value=(str(self.bot.get_ping()) + 'ms'), inline=True)
        embed.add_field(name="Source Code", value="[Link](https://github.com/jonasbohmann/democraciv-discord-bot)",
                        inline=True)
        embed.add_field(name='Commands', value='See ' + config.BOT_PREFIX + 'help', inline=False)
        embed.set_thumbnail(url=self.bot.owner.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.command(name='uptime')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def uptime(self, ctx):
        """Check how long I've been working"""
        embed = self.bot.embeds.embed_builder(title='Uptime', description=self.bot.get_uptime())
        await ctx.send(embed=embed)

    @commands.command(name='ping')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ping(self, ctx):
        """Pong!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.get_ping()) + 'ms'))
        await ctx.send(embed=embed)

    @commands.command(name='pong', hidden=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def pong(self, ctx):
        """Ping!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.get_ping()) + 'ms'))
        await ctx.send(embed=embed)

    @commands.command(name='source')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def source(self, ctx):
        """Check out the source code on GitHub"""
        embed = self.bot.embeds.embed_builder(title='Source',
                                              description="https://github.com/jonasbohmann/democraciv-discord-bot")
        await ctx.send(embed=embed)

    @commands.command(name='contributors')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def contributors(self, ctx):
        """See who helped with this project"""
        embed = self.bot.embeds.embed_builder(title='Contributors :heart:',
                                              description="https://github.com/jonasbohmann/democraciv"
                                                          "-discord-bot/graphs/contributors")
        await ctx.send(embed=embed)

    @commands.command(name='addme')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(2081418487))
        embed = self.bot.embeds.embed_builder(title='Add this bot to your own Discord server', description=invite_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(About(bot))
