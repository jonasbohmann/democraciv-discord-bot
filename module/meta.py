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

    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow("SELECT * FROM dm_settings WHERE user_id = $1", user)

        if not settings:
            settings = await self.bot.db.fetchrow("INSERT INTO dm_settings (user_id) VALUES ($1) RETURNING *", user)

        return settings

    async def toggle_dm_setting(self, user: int, setting: str):
        settings = await self.ensure_dm_settings(user)
        current_setting = settings[setting]
        await self.bot.db.execute(f"UPDATE dm_settings SET {setting} = $1 WHERE user_id = $2",
                                  not current_setting,
                                  user)
        return not current_setting

    @commands.group(name='dms', aliases=['dm', 'pm', 'dmsettings', 'dm-settings'], case_insensitive=True,
                    invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def dmsettings(self, ctx):
        """See your currently enabled DMs from me"""

        emojify_settings = self.bot.get_cog("Server").emojiy_settings
        settings = await self.ensure_dm_settings(ctx.author.id)

        mute_kick_ban = emojify_settings(settings['ban_kick_mute'])
        leg_session_open = emojify_settings(settings['leg_session_open'])
        leg_session_update = emojify_settings(settings['leg_session_update'])
        leg_session_submit = emojify_settings(settings['leg_session_submit'])
        leg_session_withdraw = emojify_settings(settings['leg_session_withdraw'])

        embed = self.bot.embeds.embed_builder(title=f"Direct Messages for {ctx.author.name}",
                                              description=f"Check `{config.BOT_PREFIX}help dms` for help on "
                                                          f"how to enable or disable these settings.\n\n"
                                                          f"{mute_kick_ban} DM when you get muted, kicked or banned\n"
                                                          f"{leg_session_open} *(Legislator Only)* DM when a Legislative Session opens\n"
                                                          f"{leg_session_update} *(Legislator Only)* DM when voting starts for a Legislative Session\n"
                                                          f"{leg_session_submit} *(Cabinet Only)* DM when someone submits a Bill or Motion\n"
                                                          f"{leg_session_withdraw} *(Cabinet Only)* DM when someone withdraws a Bill or Motion\n",
                                              has_footer=False)
        await ctx.send(embed=embed)

    @dmsettings.command(name='enableall')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def enableall(self, ctx):
        """Enable all DMs"""

        await self.bot.db.execute("UPDATE dm_settings SET"
                                  " ban_kick_mute = true, leg_session_open = true,"
                                  " leg_session_update = true, leg_session_submit = true,"
                                  " leg_session_withdraw = true"
                                  " WHERE user_id = $1", ctx.author.id)

        await ctx.send(":white_check_mark: All DMs from me are now enabled.")

    @dmsettings.command(name='disableall')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def disableall(self, ctx):
        """Disable all DMs"""

        await self.bot.db.execute("UPDATE dm_settings SET"
                                  " ban_kick_mute = false, leg_session_open = false,"
                                  " leg_session_update = false, leg_session_submit = false,"
                                  " leg_session_withdraw = false"
                                  " WHERE user_id = $1", ctx.author.id)

        await ctx.send(":white_check_mark: All DMs from me are now disabled.")

    @dmsettings.command(name='moderation', aliases=['mod', 'kick', 'ban', 'mute'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def moderation(self, ctx):
        """Toggle DMs for when you get muted, kicked or banned"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "ban_kick_mute")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you get muted, kicked or banned by me."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you get muted, kicked or banned."

        await ctx.send(message)

    @dmsettings.command(name='legsessionopen')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legsessionopen(self, ctx):
        """Toggle DMs for when a Legislative Session opens"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_open")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you are a Legislator " \
                      "and a new Legislative Session is opened."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you are a Legislator " \
                      "and a new Legislative Session is opened."

        await ctx.send(message)

    @dmsettings.command(name='legsessionvoting')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legsessionvoting(self, ctx):
        """Toggle DMs for when voting starts for a Legislative Session"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_update")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you are a Legislator " \
                      "and voting starts for a Legislative Session."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you are a Legislator " \
                      "and voting starts for a Legislative Session."

        await ctx.send(message)

    @dmsettings.command(name='legsubmit')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legsubmit(self, ctx):
        """Toggle DMs for when someone submits a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_submit")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you are a member of the Cabinet " \
                      "and someone submits a Bill or Motion."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you are a member of the Cabinet " \
                      "and someone submits a Bill or Motion."

        await ctx.send(message)

    @dmsettings.command(name='legwithdraw')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legwithdraw(self, ctx):
        """Toggle DMs for when someone withdraws a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_withdraw")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you are a member of the Cabinet " \
                      "and someone withdraws their Bill or Motion."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you are a member of the Cabinet " \
                      "and someone withdraws their Bill or Motion."

        await ctx.send(message)

    @commands.command(name='commands', aliases=['cmd', 'cmds'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def allcmds(self, ctx):
        """List all commands"""

        text = []

        hidden_cogs = ('Admin', 'ErrorHandler', 'Log', 'Reddit', 'YouTube', 'Twitch')
        amounts = 0
        i = 0
        p = config.BOT_PREFIX

        embed = self.bot.embeds.embed_builder(title="",
                                              description=f"This lists every command, regardless whether you can "
                                                          f"use it in this context or not.\n\nFor more detailed "
                                                          f"explanations and example usage of commands, use `{p}help`, "
                                                          f"`{p}help <Category>`, or `{p}help <command>`.",
                                              has_footer=False)

        for name, cog in sorted(self.bot.cogs.items()):
            if name in hidden_cogs:
                continue

            amount, cog_cmds = self.collect_all_commands(cog)
            amounts += amount

            commands_list = []

            for command in cog_cmds:
                if not command.hidden:
                    commands_list.append(f"`{p}{command.qualified_name}`")

            if i == 0:
                text.append(f"**__{name}__**\n")
            else:
                text.append(f"\n**__{name}__**\n")

            text.append('\n'.join(commands_list))
            text.append('\n')

            if i <= 3:
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
