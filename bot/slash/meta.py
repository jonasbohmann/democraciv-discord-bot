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
    slash = app_commands.Group(
        name="slash",
        description="Owner-only slash command staging tools.",
    )

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

        await ui.send_static(
            ctx,
            title=f"Made by {owner_name}",
            body=f"[Invite this bot to your Discord Server.]({invite_url})",
            sections=[
                ui.LayoutSection("Developer", "DerJonas (u/Jovanos)"),
                ui.LayoutSection(
                    "Bot",
                    f"Version: {self.bot.BOT_VERSION}\n"
                    f"Servers: {len(self.bot.guilds)}\n"
                    f"Text Prefix: `{config.BOT_PREFIX}`",
                ),
                ui.LayoutSection(
                    "Commands",
                    "Use `/commands` for slash commands or the text help command for legacy commands.",
                ),
            ],
            links=[
                ui.LayoutLink(
                    "Source Code",
                    "https://github.com/jonasbohmann/democraciv-discord-bot",
                    "\U0001f5c3",
                ),
                ui.LayoutLink("Invite", invite_url, "\U0001f517"),
            ],
        )

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

        await message.edit(
            content=None,
            view=ui.RichLayout(
                title="Pong!",
                title_emoji="\U0001f3d3",
                body="**[status.discord.com](https://status.discord.com/)**",
                sections=[
                    ui.LayoutSection(
                        "Discord",
                        f"HTTP API: {discord_http:.0f}ms\n"
                        f"Gateway Websocket: {self.bot.ping * 1000:.0f}ms",
                    ),
                    ui.LayoutSection(
                        "Internal API",
                        f"{api_http:.0f}ms" if api_http else "*not running*",
                    ),
                ],
                author_id=ctx.author.id,
            ),
        )

    @app_commands.command(name="commands", description="List all text commands.")
    async def commands_command(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="commands")
        await ctx.defer()

        p = config.BOT_PREFIX
        entries = []
        total_cmds = 0

        for name, cog in sorted(self.bot.cogs.items()):
            if not isinstance(cog, context.CustomCog):
                continue

            if cog.hidden and cog.qualified_name != "Bank":
                continue

            cog_cmds = sorted(
                [command for command in cog.walk_commands() if not command.hidden],
                key=lambda c: c.qualified_name,
            )

            if not cog_cmds:
                continue

            total_cmds += len(cog_cmds)
            lines = [f"### {cog.qualified_name}"]
            for command in cog_cmds:
                lines.append(f"`{p}{command.qualified_name}`")
            entries.append("\n".join(lines))

        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"Text Commands ({total_cmds})",
            per_page=4,
            empty_message="No text commands are loaded.",
        )

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
            view=ui.RichLayout(
                title="Add this bot to your own Discord server",
                links=[ui.LayoutLink("Invite", invite_url, "\U0001f517")],
                author_id=ctx.author.id,
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

    @slash.command(
        name="tree", description="Show the current in-memory app command tree."
    )
    @slash_checks.is_owner()
    async def slash_tree(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="slash tree",
            ephemeral=True,
        )
        await ctx.defer(ephemeral=True)
        commands_ = sorted(
            self.bot.tree.walk_commands(),
            key=lambda command: command.qualified_name,
        )
        entries = [
            f"`/{command.qualified_name}` - {command.description or 'No description'}"
            for command in commands_
        ]
        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"Current app command tree ({len(entries)} entries)",
            per_page=15,
            empty_message="No slash commands are loaded.",
            ephemeral=True,
        )

    @slash.command(
        name="sync", description="Sync slash commands to one guild for staging."
    )
    @slash_checks.is_owner()
    async def slash_sync(
        self,
        interaction: discord.Interaction,
        guild_id: str = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="slash sync",
            ephemeral=True,
        )
        await ctx.defer(ephemeral=True)
        target_id = int(guild_id) if guild_id else (ctx.guild.id if ctx.guild else None)
        if target_id is None:
            return await ctx.send(f"{config.NO} No guild.", ephemeral=True)

        target = discord.Object(id=target_id)
        self.bot.tree.clear_commands(guild=target)
        self.bot.tree.copy_global_to(guild=target)
        synced = await self.bot.tree.sync(guild=target)
        await ctx.send(
            f"{config.YES} Synced {len(synced)} slash command(s) to guild `{target_id}`.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(MetaSlash(bot))
