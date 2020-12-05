import time
import discord

from bot.config import config, exceptions
from discord.ext import commands
from bot.utils import context, help
from bot.utils.text import SafeEmbed


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

    @commands.command(name="about", aliases=["info"])
    async def about(self, ctx):
        """About this bot"""
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))

        embed = SafeEmbed(
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

        embed = SafeEmbed(
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

        embed = SafeEmbed(
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
        await ctx.send(embed=SafeEmbed(title="Add this bot to your own Discord server", description=invite_url))


def setup(bot):
    bot.add_cog(Meta(bot))
