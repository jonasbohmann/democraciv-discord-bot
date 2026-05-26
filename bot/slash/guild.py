import discord

from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import guild as guild_presenter
from bot.services.guild import GuildService
from bot.slash import ui, checks as slash_checks, context as slash_context
from bot.utils import paginator


class GuildSlash(commands.Cog):
    server = app_commands.Group(
        name="server",
        description="Show and configure server settings.",
        guild_only=True,
    )

    logs = app_commands.Group(
        name="logs",
        description="Configure event logging on this server.",
        parent=server,
    )

    reddit = app_commands.Group(
        name="reddit",
        description="Manage subreddit feeds on this server.",
        parent=server,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = GuildService(bot)

    async def ensure_guild_settings(self, guild_id: int):
        return await self.service.ensure_guild_settings(guild_id)

    @server.command(name="overview", description="Show server settings and statistics.")
    @app_commands.guild_only()
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="server overview"
        )

        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        embed = guild_presenter.build_server_overview_embed(ctx, settings)
        await ctx.send(embed=embed)

    @server.command(name="welcome", description="Configure welcome message.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def welcome(
        self,
        interaction: discord.Interaction,
        enabled: bool = None,
        channel: discord.TextChannel = None,
        message: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="server welcome")
        await ctx.defer()

        settings = await self.ensure_guild_settings(ctx.guild.id)

        if enabled is None and channel is None and message is None:
            current_channel = await self.bot.get_welcome_channel(ctx.guild)
            embed = guild_presenter.build_welcome_embed(ctx, settings, current_channel)

            return await ctx.send(embed=embed)

        result = await self.service.update_welcome_settings(
            ctx,
            enabled=enabled,
            channel=channel,
            message=message,
        )
        await ctx.send(result.message)

    @logs.command(name="overview", description="Show logging settings.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def logs_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="server logs")
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_channel = await self.bot.get_logging_channel(ctx.guild)

        embed = guild_presenter.build_logging_embed(ctx, settings, current_channel)
        await ctx.send(embed=embed)

    @logs.command(name="configure", description="Configure logging status and channel.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def logs_configure(
        self,
        interaction: discord.Interaction,
        enabled: bool = None,
        channel: discord.TextChannel = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server logs configure",
        )

        await ctx.defer()
        result = await self.service.update_logging_settings(
            ctx,
            enabled=enabled,
            channel=channel,
        )
        await ctx.send(result.message)

    @logs.command(name="events", description="Configure which events are logged.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def logs_events(
        self,
        interaction: discord.Interaction,
        message_edits: bool = None,
        message_deletes: bool = None,
        nickname_changes: bool = None,
        role_changes: bool = None,
        joins_and_leaves: bool = None,
        bans_and_unbans: bool = None,
        channel_create_delete: bool = None,
        role_create_delete: bool = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server logs events",
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        provided = {
            "message_edits": message_edits,
            "message_deletes": message_deletes,
            "nickname_changes": nickname_changes,
            "role_changes": role_changes,
            "joins_and_leaves": joins_and_leaves,
            "bans_and_unbans": bans_and_unbans,
            "channel_create_delete": channel_create_delete,
            "role_create_delete": role_create_delete,
        }

        if all(value is None for value in provided.values()):
            embed = guild_presenter.build_logging_events_embed(ctx, settings)
            return await ctx.send(embed=embed)

        result = await self.service.update_logging_events(ctx, provided)
        await ctx.send(result.message)

    @server.command(
        name="hide-channel",
        description="Toggle a channel/category hidden from logs and starboard.",
    )
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def hide_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.CategoryChannel = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server hide-channel",
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(
                f"{config.NO} This server currently has no logging channel. Please set one with `/server logs configure`.",
                ephemeral=True,
            )

        if channel is None:
            page = guild_presenter.build_hidden_channels_page(
                ctx, settings, current_logging_channel
            )
            if len(page.entries) == 1:
                return await ctx.send(
                    guild_presenter.hidden_channels_empty_message(
                        ctx, current_logging_channel
                    ),
                    ephemeral=True,
                )
            pages = paginator.SimplePages(
                entries=list(page.entries),
                author=page.author,
                icon=page.icon,
                empty_message=page.empty_message,
            )
            return await pages.start(ctx)

        result = await self.service.toggle_hidden_channel(ctx, channel)
        await ctx.send(result.message)

    @server.command(
        name="join-role", description="Configure the role given to new members."
    )
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def join_role(
        self,
        interaction: discord.Interaction,
        enabled: bool = None,
        role: discord.Role = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="server join-role"
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)

        if enabled is None and role is None:
            embed = guild_presenter.build_default_role_embed(ctx, settings)
            return await ctx.send(embed=embed)

        result = await self.service.update_default_role_settings(
            ctx,
            enabled=enabled,
            role=role,
        )
        await ctx.send(result.message)

    @server.command(name="tag-creation", description="Configure who can create tags.")
    @slash_checks.has_guild_permissions(administrator=True)
    async def tag_creation(
        self,
        interaction: discord.Interaction,
        everyone: bool = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server tag-creation",
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)

        if everyone is None:
            embed = guild_presenter.build_tag_creation_embed(ctx, settings)
            return await ctx.send(embed=embed)

        result = await self.service.set_tag_creation(ctx, everyone=everyone)
        await ctx.send(result.message)

    @server.command(
        name="npc-usage", description="Allow or deny NPC usage on this server."
    )
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def npc_usage(
        self,
        interaction: discord.Interaction,
        allowed: bool = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="server npc-usage"
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)

        if allowed is None:
            embed = guild_presenter.build_npc_usage_embed(ctx, settings)
            return await ctx.send(embed=embed)

        result = await self.service.set_npc_usage(ctx, allowed=allowed)
        await ctx.send(result.message)

    @reddit.command(name="list", description="List subreddit feeds on this server.")
    async def reddit_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="server reddit list"
        )
        await ctx.defer()
        page = await self.service.list_reddit_feeds(ctx)
        pages = paginator.SimplePages(
            entries=list(page.entries),
            author=page.author,
            icon=page.icon,
            per_page=page.per_page,
            empty_message=page.empty_message,
        )
        await pages.start(ctx)

    @reddit.command(name="add", description="Add a subreddit feed to this server.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    @slash_checks.bot_has_guild_permissions(manage_webhooks=True)
    async def reddit_add(
        self,
        interaction: discord.Interaction,
        subreddit: str,
        channel: discord.TextChannel,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="server reddit add"
        )
        await ctx.defer()
        result = await self.service.add_reddit_feed(
            ctx,
            subreddit=subreddit,
            channel=channel,
        )
        if result.message:
            await ctx.send(result.message)

    @reddit.command(name="remove", description="Remove one subreddit feed by ID.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def reddit_remove(self, interaction: discord.Interaction, feed_id: int):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server reddit remove",
        )
        await ctx.defer()
        result = await self.service.remove_reddit_feed(ctx, feed_id=feed_id)
        await ctx.send(result.message)

    @reddit.command(
        name="clear", description="Remove all subreddit feeds on this server."
    )
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def reddit_clear(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server reddit clear",
        )
        await ctx.defer()
        confirmed = await ui.confirm(
            ctx,
            title="Clear Subreddit Feeds",
            body="Remove all subreddit feeds on this server?",
            confirm_label="Clear",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.clear_reddit_feeds(ctx)
        await ctx.send(result.message)


async def setup(bot):
    await bot.add_cog(GuildSlash(bot))
