import discord

from util.help import PaginatedHelpCommand
from config import config
from discord.ext import commands


class About(commands.Cog):
    """Information about this bot"""

    def __init__(self, bot):
        self.bot = bot
        self.old_help_command = bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.old_help_command

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    # TODO - Add -commands

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
        embed.add_field(name='Uptime', value=self.bot.uptime, inline=True)
        embed.add_field(name='Ping', value=(str(self.bot.ping) + 'ms'), inline=True)
        embed.add_field(name="Source Code", value="[Link](https://github.com/jonasbohmann/democraciv-discord-bot)",
                        inline=True)
        embed.add_field(name='Commands', value='See ' + config.BOT_PREFIX + 'help', inline=False)
        embed.set_thumbnail(url=self.bot.owner.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.command(name='ping', aliases=['pong'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ping(self, ctx):
        """Pong!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.ping) + 'ms'))
        await ctx.send(embed=embed)

    @commands.command(name='addme', aliases=['inviteme'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(2081418487))
        embed = self.bot.embeds.embed_builder(title='Add this bot to your own Discord server', description=invite_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(About(bot))
