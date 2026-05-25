import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import ui
from bot.utils import context, exceptions, text

DM_SETTING_LABELS = {
    "ban_kick_mute": "You get muted, kicked, or banned",
    "leg_session_open": "Legislative session opens",
    "leg_session_update": "Voting starts for a legislative session",
    "leg_session_submit": "Someone submits a bill or motion",
    "leg_session_withdraw": "Someone withdraws a bill or motion",
    "party_join_leave": "Someone joins or leaves your political party",
}


class MetaSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow(
            "SELECT * FROM dm_setting WHERE user_id = $1",
            user,
        )

        if not settings:
            settings = await self.bot.db.fetchrow(
                "INSERT INTO dm_setting (user_id) VALUES ($1) RETURNING *",
                user,
            )

        return settings

    @app_commands.command(name="about", description="About this bot.")
    async def about(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="about")
        await ctx.defer()

        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(8),
        )

        owner = getattr(self.bot, "owner", None)
        owner_name = str(owner) if owner else "DerJonas"
        owner_avatar = (
            owner.display_avatar.url
            if owner and hasattr(owner, "display_avatar")
            else None
        )

        embed = text.SafeEmbed(
            description=f"[Invite this bot to your Discord Server.]({invite_url})",
        )
        embed.add_field(name="Developer", value="DerJonas (u/Jovanos)", inline=False)
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
            value=f"Check `{config.BOT_PREFIX}commands` and `{config.BOT_PREFIX}help`",
            inline=False,
        )
        embed.set_author(
            icon_url=owner_avatar,
            name=f"Made by {owner_name}",
        )

        embed.set_footer(text=f"Assisting {self.bot.dciv.name} since")
        embed.timestamp = self.bot.user.created_at
        await ctx.send(embed=embed)

    @app_commands.command(name="ping", description="Show bot latency.")
    async def ping(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="ping")
        await ctx.defer()

        start = time.perf_counter()
        message = await interaction.followup.send(":arrows_counterclockwise: Ping...")
        end = time.perf_counter()
        discord_http = (end - start) * 1000

        try:
            start = time.perf_counter()
            await self.bot.api_request("GET", "")
            end = time.perf_counter()
            api_http = (end - start) * 1000
        except exceptions.DemocracivBotAPIError:
            api_http = None

        try:
            start2 = time.perf_counter()
            async with self.bot.session.get(self.bot.mk.NATION_ICON_URL) as resp:
                await resp.read()
            end2 = time.perf_counter()
            cdn_http = (end2 - start2) * 1000
        except Exception:
            cdn_http = None

        embed = text.SafeEmbed(
            title="Pong!",
            description="**[status.discord.com](https://status.discord.com/)**",
        )
        embed.add_field(
            name="Discord",
            value=f"HTTP API: {discord_http:.0f}ms\n"
            f"Gateway Websocket: {self.bot.ping * 1000:.0f}ms",
            inline=False,
        )
        embed.add_field(
            name="Internal API",
            value=f"{api_http:.0f}ms" if api_http else "*not running*",
            inline=False,
        )
        embed.add_field(
            name="Democraciv CDN",
            value=f"{cdn_http:.0f}ms" if cdn_http else "*unreachable*",
            inline=False,
        )

        await message.edit(content=None, embed=embed)

    @app_commands.command(name="commands", description="List all text commands.")
    async def commands_command(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="commands")
        await ctx.defer()

        p = config.BOT_PREFIX
        description_text = []
        field_text = []
        amounts = 0
        i = 0

        for name, cog in sorted(self.bot.cogs.items()):
            if not isinstance(cog, context.CustomCog):
                continue
            if cog.hidden and cog.qualified_name != "Bank":
                continue
            cog_cmds = sorted(
                [command for command in cog.walk_commands() if not command.hidden],
                key=lambda c: c.qualified_name,
            )

            amounts += len(cog_cmds)
            commands_list = [f"`{p}{command.qualified_name}`" for command in cog_cmds]

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
            description=(
                f"For more detailed explanations and example usage of commands, "
                f"use `{p}help`, `{p}help <Category>`, "
                f"or `{p}help <command>`."
                f"\n\n{' '.join(description_text)}"
            ),
        )

        if field_text:
            embed.add_field(name="\u200b", value=" ".join(field_text))

        await ctx.send(embed=embed)

    @app_commands.command(
        name="invite", description="Invite this bot to another server."
    )
    async def invite(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="invite")
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(8),
        )
        await ctx.send(
            embed=text.SafeEmbed(
                title="Add this bot to your own Discord server",
                description=invite_url,
            )
        )

    @app_commands.command(
        name="dm-settings", description="Manage your DM notification settings."
    )
    async def dm_settings(
        self,
        interaction: discord.Interaction,
        ban_kick_mute: bool = None,
        leg_session_open: bool = None,
        leg_session_update: bool = None,
        leg_session_submit: bool = None,
        leg_session_withdraw: bool = None,
        party_join_leave: bool = None,
    ):

        ctx = slash_context.from_interaction(
            interaction,
            command_name="dm-settings",
            ephemeral=True,
        )

        await ctx.defer(ephemeral=True)

        settings = await self.ensure_dm_settings(ctx.author.id)
        provided = {
            "ban_kick_mute": ban_kick_mute,
            "leg_session_open": leg_session_open,
            "leg_session_update": leg_session_update,
            "leg_session_submit": leg_session_submit,
            "leg_session_withdraw": leg_session_withdraw,
            "party_join_leave": party_join_leave,
        }

        if all(value is None for value in provided.values()):
            embed = text.SafeEmbed(
                description="\n".join(
                    f"{self.bot.emojify_boolean(settings[key])} {label}"
                    for key, label in DM_SETTING_LABELS.items()
                )
            )
            embed.set_author(
                name=f"DM Notifications for {ctx.author}",
                icon_url=ctx.author_icon,
            )
            return await ctx.send(embed=embed, ephemeral=True)

        values = {
            key: settings[key] if value is None else value
            for key, value in provided.items()
        }

        await self.bot.db.execute(
            "UPDATE dm_setting SET ban_kick_mute = $1, leg_session_open = $2, "
            "leg_session_update = $3, leg_session_submit = $4, "
            "leg_session_withdraw = $5, party_join_leave = $6 WHERE user_id = $7",
            *values.values(),
            ctx.author.id,
        )

        await ctx.send(f"{config.YES} Your DM settings were updated.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MetaSlash(bot))
