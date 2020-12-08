import collections
import time
import discord

from bot.config import config
from discord.ext import commands, menus
from bot.utils import context, help, text, exceptions


class EditDMSettingsMenu(menus.Menu):
    def __init__(self, settings):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.settings = settings
        self._make_result()

    def _make_result(self):
        self.result = collections.namedtuple("EditDMSettingsMenuResult", ["confirmed", "result"])
        self.result.confirmed = False

        self.result.result = {"mute_kick_ban": self.settings["ban_kick_mute"],
                              "leg_session_open": self.settings["leg_session_open"],
                              "leg_session_update": self.settings["leg_session_update"],
                              "leg_session_submit": self.settings["leg_session_submit"],
                              "leg_session_withdraw": self.settings["leg_session_withdraw"],
                              "party_join_leave": self.settings["party_join_leave"]}

        return self.result

    def _make_embed(self):
        embed = text.SafeEmbed(
            description=f"You can toggle each notification on and off. Once you're done, hit {config.YES} to confirm, or {config.NO} to cancel.\n\n"
                        f":one:  -  {self.emojify_settings(self.result.result['mute_kick_ban'])} DM when you get muted, kicked or banned\n"
                        f":two:  -  {self.emojify_settings(self.result.result['leg_session_open'])} *({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session opens\n"
                        f":three:  -  {self.emojify_settings(self.result.result['leg_session_update'])} *({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when voting starts for a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session\n"
                        f":four:  -  {self.emojify_settings(self.result.result['leg_session_submit'])} "
                        f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                        f"someone submits a Bill or Motion\n"
                        f":five:  -  {self.emojify_settings(self.result.result['leg_session_withdraw'])} "
                        f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                        f"someone withdraws a Bill or Motion\n"
                        f":six:  -  {self.emojify_settings(self.result.result['party_join_leave'])} *(Faction Leaders Only)* DM when someone joins or leaves your religious faction\n"
        )
        embed.set_author(name=self.ctx.author, icon_url=self.ctx.author_icon)
        return embed

    async def send_initial_message(self, ctx, channel):
        return await ctx.send(embed=self._make_embed())

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def first(self, payload):
        self.result.result["mute_kick_ban"] = not self.result.result["mute_kick_ban"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def snd(self, payload):
        self.result.result["leg_session_open"] = not self.result.result["leg_session_open"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("3\N{variation selector-16}\N{combining enclosing keycap}")
    async def thrd(self, payload):
        self.result.result["leg_session_update"] = not self.result.result["leg_session_update"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("4\N{variation selector-16}\N{combining enclosing keycap}")
    async def fourth(self, payload):
        self.result.result["leg_session_submit"] = not self.result.result["leg_session_submit"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("5\N{variation selector-16}\N{combining enclosing keycap}")
    async def fifth(self, payload):
        self.result.result["leg_session_withdraw"] = not self.result.result["leg_session_withdraw"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("6\N{variation selector-16}\N{combining enclosing keycap}")
    async def sixth(self, payload):
        self.result.result["party_join_leave"] = not self.result.result["party_join_leave"]
        await self.message.edit(embed=self._make_embed())

    @menus.button(config.YES)
    async def confirm(self, payload):
        self.result.confirmed = True
        self.stop()

    @menus.button(config.NO)
    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        self.emojify_settings = ctx.bot.get_cog("Server").emojify_settings
        await self.start(ctx, wait=True)
        return self.result


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
    @commands.command(name="r", hidden=True)
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

    @commands.command(
        name="dms",
        aliases=["dm", "pm", "dmsettings", "dm-settings", "dmsetting"]
    )
    async def dmsettings(self, ctx):
        """Manage your DM notifications from me"""
        settings = await self.ensure_dm_settings(ctx.author.id)
        result = await EditDMSettingsMenu(settings).prompt(ctx)

        if result.confirmed:
            await self.bot.db.execute("UPDATE dm_setting SET ban_kick_mute = $1, leg_session_open = $2, "
                                      "leg_session_update = $3, leg_session_submit = $4, "
                                      "leg_session_withdraw = $5, party_join_leave = $6 WHERE user_id = $7",
                                      *result.result.values(), ctx.author.id)

            await ctx.send(f"{config.YES} Your settings were updated.")
        else:
            await ctx.send("Cancelled.")

    @commands.command(name="about", aliases=["info"])
    async def about(self, ctx):
        """About this bot"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))

        embed = text.SafeEmbed(
            description=f"[Invite this bot to your Discord Server.]({invite_url})",
        )

        embed.add_field(name="Developer", value="DerJonas#8036 (u/Jovanos)", inline=False)
        embed.add_field(name="Version", value=config.BOT_VERSION, inline=True)
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
            title=f":ping_pong:  {title}",
            description="[**status.discord.com**](https://status.discord.com/)\n\n"
        )
        embed.add_field(name="Discord",
                        value=f"HTTP API: {discord_http:.0f}ms\nGateway Websocket: {self.bot.ping}ms\n", inline=False)

        embed.add_field(name="Internal API",
                        value=f"{api_http:.0f}ms" if api_http else "*not running*")
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
                [
                    command
                    for command in cog.walk_commands()
                    if not command.hidden
                ],
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
            description=f"This lists every command, regardless whether you can use "
                        f"it in this context or not.\n\nFor more detailed "
                        f"explanations and example usage of commands, "
                        f"use `{p}help`, `{p}help <Category>`, "
                        f"or `{p}help <command>`."
                        f"\n\n{' '.join(description_text)}",
        )

        embed.add_field(name="\u200b", value=" ".join(field_text))
        await ctx.send(embed=embed)

    @commands.command(name="addme", aliases=["inviteme", "invite"])
    async def addme(self, ctx):
        """Invite this bot to your Discord server"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        await ctx.send(embed=text.SafeEmbed(title="Add this bot to your own Discord server", description=invite_url))


def setup(bot):
    bot.add_cog(Meta(bot))
