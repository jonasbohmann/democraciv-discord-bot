import discord

from util.exceptions import DemocracivBotException
from util.help import PaginatedHelpCommand
from config import config
from discord.ext import commands
from discord.ext.commands import CheckFailure


class Meta(commands.Cog):
    """Commands regarding the bot itself."""

    def __init__(self, bot):
        self.bot = bot
        self.old_help_command = bot.help_command
        bot.help_command = PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.old_help_command

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
        embed.add_field(name='Commands', value=f'Check `{config.BOT_PREFIX}commands` '
                                               f'or `{config.BOT_PREFIX}help`', inline=False)
        embed.set_thumbnail(url=self.bot.owner.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.command(name='ping', aliases=['pong'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ping(self, ctx):
        """Pong!"""
        embed = self.bot.embeds.embed_builder(title='Ping', description=(str(self.bot.ping) + 'ms'))
        await ctx.send(embed=embed)

    @staticmethod
    def collect_all_commands(cog):
        commands_list = []
        for cmd in cog.get_commands():
            if isinstance(cmd, discord.ext.commands.Group):
                for c in cmd.commands:
                    if isinstance(c, discord.ext.commands.Group):
                        for co in c.commands:
                            commands_list.append(co)
                    else:
                        commands_list.append(c)
            commands_list.append(cmd)
        return len(commands_list), sorted(commands_list, key=lambda com: com.qualified_name)

    @commands.command(name='commands', aliases=['cmd', 'cmds'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def allcmds(self, ctx):
        """List all commands"""

        all_commands = []
        hidden_cogs = ('Admin', 'ErrorHandler', 'Log', 'Starboard')
        amounts = 0
        i = 0

        for name, cog in sorted(self.bot.cogs.items()):
            if name in hidden_cogs:
                continue

            if i == 0:
                all_commands.append(f"**__{name}__**\n")
            else:
                all_commands.append(f"\n**__{name}__**\n")

            i += 1

            amount, cog_cmds = self.collect_all_commands(cog)
            amounts += amount

            commands_list = []

            for command in cog_cmds:
                if not command.hidden:
                    try:
                        if await command.can_run(ctx):
                            commands_list.append(f"`{command.qualified_name}`")
                        else:
                            commands_list.append(f"*`{command.qualified_name}`*")
                    except (CheckFailure, DemocracivBotException):
                        commands_list.append(f"*`{command.qualified_name}`*")

            all_commands.append(' :: '.join(commands_list))
            all_commands.append("\n")

        embed = self.bot.embeds.embed_builder(title=f'All Commands ({amounts})',
                                              description=f"Commands that you are not allowed to use (missing role"
                                                          f" or missing permission) or that cannot be used"
                                                          f" on this server, "
                                                          f"are in _italic_.\n\n{' '.join(all_commands)}")
        await ctx.send(embed=embed)

    @commands.command(name='addme', aliases=['inviteme'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(2081418487))
        embed = self.bot.embeds.embed_builder(title='Add this bot to your own Discord server', description=invite_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
