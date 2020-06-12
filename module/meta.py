import time
import discord

from config import config
from discord.ext import commands
from util.help import PaginatedHelpCommand


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
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))

        embed = self.bot.embeds.embed_builder(title='About This Bot', description=f"[Invite this bot to your"
                                                                                  f" Discord Server.]({invite_url})")
        embed.add_field(name='Developer', value="DerJonas#8036 (u/Jovanos)", inline=True)
        embed.add_field(name='Version', value=config.BOT_VERSION, inline=True)
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        embed.add_field(name='Servers', value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name='Users', value=str(len(self.bot.users)), inline=True)
        embed.add_field(name='Prefix', value=f"`{config.BOT_PREFIX}`", inline=True)
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
        start = time.perf_counter()
        message = await ctx.send(":arrows_counterclockwise: Ping...")
        end = time.perf_counter()
        duration = (end - start) * 1000
        embed = self.bot.embeds.embed_builder(title=":ping_pong:  Pong!",
                                              description=f"REST API: {duration:.0f}ms\n"
                                                          f"Websocket: {self.bot.ping}ms\n"
                                                          f"[Discord Status](https://status.discord.com/)",
                                              has_footer=False)
        await message.edit(content=None, embed=embed)

    @staticmethod
    def collect_all_commands(cog):
        commands_list = []
        for cmd in cog.get_commands():
            if isinstance(cmd, discord.ext.commands.Group):
                for c in cmd.commands:
                    if isinstance(c, discord.ext.commands.Group):
                        if c.qualified_name != "legislature withdraw":  # hacky :(
                            commands_list.append(c)
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

        text = []

        hidden_cogs = ('Admin', 'ErrorHandler', 'Log', 'Reddit', 'YouTube', 'Twitch')
        amounts = 0
        i = 0
        p = config.BOT_PREFIX

        embed = self.bot.embeds.embed_builder(title='',
                                              description=f"Commands that you are not allowed to use (missing role "
                                                          f"or missing permissions) or that cannot be used on this "
                                                          f" server, have a :no_entry_sign: behind them.",
                                              has_footer=False)

        for name, cog in sorted(self.bot.cogs.items()):
            if name in hidden_cogs:
                continue

            amount, cog_cmds = self.collect_all_commands(cog)
            amounts += amount

            commands_list = []

            for command in cog_cmds:
                if not command.hidden:
                    try:
                        if await command.can_run(ctx):
                            commands_list.append(f"`{p}{command.qualified_name}`")
                        else:
                            commands_list.append(f"`{p}{command.qualified_name}`  :no_entry_sign:")
                    except commands.CommandError:
                        commands_list.append(f"`{p}{command.qualified_name}`  :no_entry_sign:")

            if i == 0:
                text.append(f"**__{name}__**\n")
            else:
                text.append(f"\n**__{name}__**\n")

            text.append('\n'.join(commands_list))
            text.append('\n')

            if i < 4:
                i += 1
                continue
            else:
                embed.add_field(name="\u200b", value=' '.join(text))
                text.clear()
                i = 0

        embed.title = f'All Commands ({amounts})'
        await ctx.send(embed=embed)

    @commands.command(name='addme', aliases=['inviteme'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        embed = self.bot.embeds.embed_builder(title='Add this bot to your own Discord server',
                                              description=invite_url,
                                              has_footer=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
