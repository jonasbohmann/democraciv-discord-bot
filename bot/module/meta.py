import time
import discord

from bot.config import config
from discord.ext import commands
from bot.utils import context, help, text, exceptions


class Meta(context.CustomCog):
    """Commands regarding the bot itself."""

    def __init__(self, bot):
        super().__init__(bot)
        self.old_help_command = bot.help_command
        bot.help_command = help.PaginatedHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self.old_help_command

    # shortcut to '-jsk reload ~' for faster debugging
    @commands.command(name="rr", hidden=True)
    @commands.is_owner()
    async def reload_all(self, ctx):
        """Alias to -jishaku reload ~"""
        if not self.bot.get_cog("Admin"):
            return await ctx.send(f"{config.NO} Admin module not loaded.")

        await ctx.invoke(self.bot.get_command("jsk reload"), list(self.bot.extensions))

    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow("SELECT * FROM dm_setting WHERE user_id = $1", user)

        if not settings:
            settings = await self.bot.db.fetchrow("INSERT INTO dm_setting (user_id) VALUES ($1) RETURNING *", user)

        return settings

    @commands.command(name="dms", aliases=["dm", "pm", "dmsettings", "dm-settings", "dmsetting"])
    async def dmsettings(self, ctx):
        """Manage your DM notifications from me"""

        choices = {
            "ban_kick_mute": ["DM when you get muted, kicked or banned"],
            "leg_session_open": [
                f"*({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session opens"],
            "leg_session_update": [
                f"*({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when voting starts for a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session"],
            "leg_session_submit": [
                f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when someone submits a Bill or Motion"],
            "leg_session_withdraw": [
                f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when someone withdraws a Bill or Motion"],
            "party_join_leave": [f"*(Party Leaders Only)* DM when someone joins or leaves your political party"],
        }

        current_settings = await self.ensure_dm_settings(ctx.author.id)

        for k, v in current_settings.items():
            if k in choices:
                choices[k].append(v)

        print(choices)

        menu = text.EditSettingsWithEmojifiedLiveToggles(settings=choices,
                                                         description=
                                                         f"You can toggle each notification on and off. Once you're "
                                                         f"done, hit {config.YES} to confirm, or {config.NO} to "
                                                         f"cancel.\n",
                                                         title=f"DM Notifications for {ctx.author}",
                                                         icon=ctx.author_icon)
        result = await menu.prompt(ctx)

        if not result.confirmed:
            return

        await self.bot.db.execute(
            "UPDATE dm_setting SET ban_kick_mute = $1, leg_session_open = $2, "
            "leg_session_update = $3, leg_session_submit = $4, "
            "leg_session_withdraw = $5, party_join_leave = $6 WHERE user_id = $7",
            *result.result.values(),
            ctx.author.id,
        )

        await ctx.send(f"{config.YES} Your settings were updated.")

    @commands.command(name="about", aliases=["info", "bot"])
    async def about(self, ctx):
        """About this bot"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))

        embed = text.SafeEmbed(
            description=f"[Invite this bot to your Discord Server.]({invite_url})",
        )

        embed.add_field(name="Developer", value="DerJonas#8036 (u/Jovanos)", inline=False)
        embed.add_field(name="Version", value=self.bot.BOT_VERSION, inline=True)
        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Prefix", value=f"`{config.BOT_PREFIX}`", inline=True)

        embed.add_field(
            name="Source Code",
            value="[Link](https://github.com/jonasbohmann/democraciv-discord-bot)",
            inline=False,
        )

        embed.add_field(
            name="List of Commands",
            value=f"Check `{config.BOT_PREFIX}commands` or `{config.BOT_PREFIX}help`",
            inline=False,
        )

        embed.set_author(
            icon_url=self.bot.owner.avatar_url_as(static_format="png"),
            name=f"Made by {self.bot.owner}",
        )

        embed.set_footer(text=f"Assisting {self.bot.dciv.name} since")
        embed.timestamp = self.bot.user.created_at
        await ctx.send(embed=embed)

    @commands.command(name="ping", aliases=["pong"])
    async def ping(self, ctx: context.CustomContext):
        """Pong!"""
        title = "Pong!" if ctx.invoked_with == "ping" else "Ping!"

        start = time.perf_counter()
        message = await ctx.send(":arrows_counterclockwise: Ping...")
        end = time.perf_counter()
        discord_http = (end - start) * 1000

        try:
            start = time.perf_counter()
            await self.bot.api_request("GET", "")
            end = time.perf_counter()
            api_http = (end - start) * 1000
        except exceptions.DemocracivBotAPIError:
            api_http = None

        embed = text.SafeEmbed(
            title=f":ping_pong:  {title}", description="**[status.discord.com](https://status.discord.com/)**\n\n"
        )
        embed.add_field(
            name="Discord",
            value=f"HTTP API: {discord_http:.0f}ms\nGateway Websocket: {self.bot.ping}ms\n",
            inline=False,
        )

        embed.add_field(name="Internal API", value=f"{api_http:.0f}ms" if api_http else "*not running*")
        await message.edit(content=None, embed=embed)

    @commands.command(name="commands", aliases=["cmd", "cmds"])
    async def allcmds(self, ctx):
        """List all commands"""

        description_text = []
        field_text = []

        amounts = 0
        i = 0
        p = config.BOT_PREFIX

        for name, cog in sorted(self.bot.cogs.items()):
            if cog.hidden:
                continue

            cog_cmds = sorted(
                [command for command in cog.walk_commands() if not command.hidden],
                key=lambda c: c.qualified_name,
            )

            amounts += len(cog_cmds)

            commands_list = []

            for command in cog_cmds:
                if not command.hidden:
                    commands_list.append(f"`{p}{command.qualified_name}`")

            if i == 0:
                description_text.append(f"**__{cog.qualified_name}__**\n")
                description_text.append("\n".join(commands_list))
                description_text.append("\n")
            elif i < 8:
                description_text.append(f"\n**__{cog.qualified_name}__**\n")
                description_text.append("\n".join(commands_list))
                description_text.append("\n")
            else:
                field_text.append(f"\n**__{cog.qualified_name}__**\n")
                field_text.append("\n".join(commands_list))
                field_text.append("\n")

            i += 1

        embed = text.SafeEmbed(
            title=f"All Commands ({amounts})",
            description=f"For more detailed explanations and example usage of commands, "
                        f"use `{p}help`, `{p}help <Category>`, "
                        f"or `{p}help <command>`."
                        f"\n\n{' '.join(description_text)}",
        )

        if field_text:
            embed.add_field(name="\u200b", value=" ".join(field_text))

        await ctx.send(embed=embed)

    @commands.command(name="addme", aliases=["inviteme", "invite"])
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        await ctx.send(embed=text.SafeEmbed(title="Add this bot to your own Discord server", description=invite_url))


def setup(bot):
    bot.add_cog(Meta(bot))
