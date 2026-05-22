import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import ui
from bot.utils import exceptions

LOG_EVENT_COLUMNS = {
    "message_edits": "logging_message_edit",
    "message_deletes": "logging_message_delete",
    "nickname_changes": "logging_member_nickname_change",
    "role_changes": "logging_member_role_change",
    "joins_and_leaves": "logging_member_join_leave",
    "bans_and_unbans": "logging_ban_unban",
    "channel_create_delete": "logging_guild_channel_create_delete",
    "role_create_delete": "logging_role_create_delete",
}


class GuildSlash(commands.Cog):
    server = app_commands.Group(
        name="server",
        description="Show and configure server settings.",
        guild_only=True,
    )
    logs = app_commands.Group(
        name="logs",
        description="Configure event logging.",
        parent=server,
    )
    reddit = app_commands.Group(
        name="reddit",
        description="Manage subreddit feeds.",
        parent=server,
    )

    def __init__(self, bot):
        self.bot = bot

    async def ensure_guild_settings(self, guild_id: int):
        try:
            settings = self.bot.guild_config[guild_id]
            if settings:
                return settings
        except (AttributeError, TypeError, KeyError):
            pass

        settings = await self.bot.update_guild_config_cache()
        return settings[guild_id]

    async def refresh_settings(self):
        await self.bot.update_guild_config_cache()

    async def get_or_make_discord_webhook(
        self,
        ctx: slash_context.InteractionContext,
        channel: discord.TextChannel,
    ):
        try:
            channel_webhooks = await channel.webhooks()

            def pred(webhook):
                return (
                    (webhook.user and webhook.user.id == self.bot.user.id)
                    or webhook.name == self.bot.user.name
                    or webhook.avatar == self.bot.user.display_avatar
                )

            webhook = discord.utils.find(pred, channel_webhooks)
            if webhook:
                return webhook

            return await channel.create_webhook(
                name=self.bot.user.name,
                avatar=await self.bot.avatar_bytes(),
            )
        except discord.Forbidden:
            await ctx.send(
                f"{config.NO} You need to give me the `Manage Webhooks` permission in {channel.mention}.",
                ephemeral=True,
            )

    async def list_reddit_feeds(self, ctx: slash_context.InteractionContext):
        response = await self.bot.api_request("GET", f"reddit/list/{ctx.guild.id}")
        entries = []

        for webhook in response["webhooks"]:
            try:
                discord_webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            except discord.HTTPException:
                continue

            entries.append(
                f"**#{webhook['id']}** - [r/{webhook['subreddit']}](https://reddit.com/r/{webhook['subreddit']}) "
                f"to {discord_webhook.channel.mention}"
            )

        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"Subreddit Feeds on {ctx.guild.name}",
            empty_message="This server does not have any subreddit feeds yet.",
            per_page=12,
        )

    @server.command(name="overview", description="Show server settings and statistics.")
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="server overview"
        )
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        excluded_channels = len(settings["private_channels"])

        await ui.send_static(
            ctx,
            title=ctx.guild.name,
            sections=[
                ui.LayoutSection(
                    "Settings",
                    f"{self.bot.emojify_boolean(settings['welcome_enabled'])} Welcome Messages\n"
                    f"{self.bot.emojify_boolean(settings['logging_enabled'])} Logging ({excluded_channels} hidden channels)\n"
                    f"{self.bot.emojify_boolean(settings['default_role_enabled'])} Role on Join\n"
                    f"{self.bot.emojify_boolean(settings['tag_creation_allowed'])} Tag Creation by Everyone\n"
                    f"{self.bot.emojify_boolean(settings['npc_usage_allowed'])} NPC Usage Allowed",
                ),
                ui.LayoutSection(
                    "Statistics",
                    f"{ctx.guild.member_count} members\n"
                    f"{len(ctx.guild.text_channels)} text channels\n"
                    f"{len(ctx.guild.voice_channels)} voice channels\n"
                    f"{len(ctx.guild.roles)} roles\n"
                    f"{len(ctx.guild.emojis)} custom emojis",
                ),
                ui.LayoutSection(
                    "Created",
                    ctx.guild.created_at.strftime("%A, %B %d %Y"),
                ),
            ],
        )

    @server.command(name="welcome", description="Configure welcome messages.")
    @slash_checks.has_guild_permissions(manage_guild=True)
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
            return await ui.send_static(
                ctx,
                title=f"Welcome Messages on {ctx.guild.name}",
                sections=[
                    ui.LayoutSection(
                        "Status",
                        self.bot.emojify_boolean(settings["welcome_enabled"]),
                    ),
                    ui.LayoutSection(
                        "Welcome Channel",
                        current_channel.mention if current_channel else "-",
                    ),
                    ui.LayoutSection(
                        "Welcome Message",
                        settings["welcome_message"] or "-",
                    ),
                ],
            )

        await self.bot.db.execute(
            "UPDATE guild SET welcome_enabled = $1, welcome_channel = $2, "
            "welcome_message = $3 WHERE id = $4",
            settings["welcome_enabled"] if enabled is None else enabled,
            settings["welcome_channel"] if channel is None else channel.id,
            settings["welcome_message"] if message is None else message,
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(f"{config.YES} Welcome Message settings were updated.")

    @logs.command(name="overview", description="Show logging settings.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def logs_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="server logs")
        await ctx.defer()
        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_channel = await self.bot.get_logging_channel(ctx.guild)

        await ui.send_static(
            ctx,
            title=f"Event Logging on {ctx.guild.name}",
            sections=[
                ui.LayoutSection(
                    "Status",
                    self.bot.emojify_boolean(settings["logging_enabled"]),
                ),
                ui.LayoutSection(
                    "Log Channel",
                    current_channel.mention if current_channel else "-",
                ),
            ],
        )

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
        settings = await self.ensure_guild_settings(ctx.guild.id)

        await self.bot.db.execute(
            "UPDATE guild SET logging_enabled = $1, logging_channel = $2 WHERE id = $3",
            settings["logging_enabled"] if enabled is None else enabled,
            settings["logging_channel"] if channel is None else channel.id,
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(f"{config.YES} Logging settings were updated.")

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
            return await ui.send_static(
                ctx,
                title=f"Events to Log on {ctx.guild.name}",
                sections=[
                    ui.LayoutSection(
                        "Events",
                        "\n".join(
                            f"{self.bot.emojify_boolean(settings[column])} {name.replace('_', ' ').title()}"
                            for name, column in LOG_EVENT_COLUMNS.items()
                        ),
                    )
                ],
            )

        values = {
            column: settings[column] if provided[name] is None else provided[name]
            for name, column in LOG_EVENT_COLUMNS.items()
        }
        await self.bot.db.execute(
            "UPDATE guild SET "
            "logging_message_edit = $1, "
            "logging_message_delete = $2, "
            "logging_member_nickname_change = $3, "
            "logging_member_role_change = $4, "
            "logging_member_join_leave = $5, "
            "logging_ban_unban = $6, "
            "logging_guild_channel_create_delete = $7, "
            "logging_role_create_delete = $8 "
            "WHERE id = $9",
            *values.values(),
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(f"{config.YES} The logging event settings were updated.")

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
        private_channels = settings["private_channels"]
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(
                f"{config.NO} This server currently has no logging channel. Please set one with `/server logs configure`.",
                ephemeral=True,
            )

        if channel is None:
            entries = []
            for channel_id in private_channels:
                found = self.bot.get_channel(channel_id)
                if found:
                    entries.append(
                        found.mention if hasattr(found, "mention") else found.name
                    )

            return await ui.send_pages(
                ctx,
                entries=entries,
                title=f"Hidden Channels on {ctx.guild.name}",
                empty_message="There are no hidden channels on this server.",
                per_page=20,
            )

        if channel.id in private_channels:
            await self.bot.db.execute(
                "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id,
                channel.id,
            )
            await self.refresh_settings()
            return await ctx.send(
                f"{config.YES} `{channel}` is no longer hidden from {current_logging_channel.mention}."
            )

        await self.bot.db.execute(
            "INSERT INTO guild_private_channel (guild_id, channel_id) VALUES ($1, $2)",
            ctx.guild.id,
            channel.id,
        )
        await self.refresh_settings()
        await ctx.send(
            f"{config.YES} `{channel}` is now hidden from {current_logging_channel.mention}."
        )

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
            current_role = ctx.guild.get_role(settings["default_role_role"])
            return await ui.send_static(
                ctx,
                title=f"Role on Join on {ctx.guild.name}",
                sections=[
                    ui.LayoutSection(
                        "Status",
                        self.bot.emojify_boolean(settings["default_role_enabled"]),
                    ),
                    ui.LayoutSection(
                        "Role", current_role.mention if current_role else "-"
                    ),
                ],
            )

        await self.bot.db.execute(
            "UPDATE guild SET default_role_enabled = $1, default_role_role = $2 WHERE id = $3",
            settings["default_role_enabled"] if enabled is None else enabled,
            settings["default_role_role"] if role is None else role.id,
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(f"{config.YES} Role on Join settings were updated.")

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
            pretty = (
                "Everyone"
                if settings["tag_creation_allowed"]
                else "Only Administrators"
            )
            return await ui.send_static(
                ctx,
                title=f"Tag Creation on {ctx.guild.name}",
                sections=[ui.LayoutSection("Allowed Tag Creators", pretty)],
            )

        await self.bot.db.execute(
            "UPDATE guild SET tag_creation_allowed = $1 WHERE id = $2",
            everyone,
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(
            f"{config.YES} {'Everyone can now make tags' if everyone else 'Only Administrators can now make tags'} on this server."
        )

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
            return await ui.send_static(
                ctx,
                title=f"NPC Usage on {ctx.guild.name}",
                sections=[
                    ui.LayoutSection(
                        "Allowed",
                        self.bot.emojify_boolean(settings["npc_usage_allowed"]),
                    )
                ],
            )

        await self.bot.db.execute(
            "UPDATE guild SET npc_usage_allowed = $1 WHERE id = $2",
            allowed,
            ctx.guild.id,
        )
        await self.refresh_settings()
        await ctx.send(
            f"{config.YES} NPCs {'can now' if allowed else 'can no longer'} be used on this server."
        )

    @reddit.command(name="list", description="List subreddit feeds on this server.")
    async def reddit_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="server reddit list"
        )
        await ctx.defer()
        await self.list_reddit_feeds(ctx)

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
        subreddit = subreddit.removeprefix("r/").removeprefix("/r/").strip()

        async with self.bot.session.get(
            f"https://reddit.com/r/{subreddit}/new.json?limit=1"
        ) as resp:
            if (
                str(resp.url).startswith(
                    "https://www.reddit.com/subreddits/search.json?q="
                )
                or resp.status == 404
            ):
                return await ctx.send(
                    f"{config.NO} `r/{subreddit}` is not a subreddit.",
                    ephemeral=True,
                )

        webhook = await self.get_or_make_discord_webhook(ctx, channel)
        if not webhook:
            return

        await self.bot.api_request(
            "POST",
            "reddit/add",
            json={
                "target": subreddit,
                "webhook_url": webhook.url,
                "webhook_id": webhook.id,
                "guild_id": ctx.guild.id,
                "channel_id": channel.id,
            },
        )
        await ctx.send(
            f"{config.YES} New posts from `r/{subreddit}` will now be posted to {channel.mention}."
        )

    @reddit.command(name="remove", description="Remove one subreddit feed by ID.")
    @slash_checks.has_guild_permissions(manage_guild=True)
    async def reddit_remove(self, interaction: discord.Interaction, feed_id: int):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="server reddit remove",
        )
        await ctx.defer()
        try:
            response = await self.bot.api_request(
                "POST",
                "reddit/remove",
                json={"id": feed_id, "guild_id": ctx.guild.id},
            )
        except exceptions.DemocracivBotAPIError:
            return await ctx.send(
                f"{config.NO} Something went wrong. Are you sure `{feed_id}` exists?",
                ephemeral=True,
            )

        if "error" in response:
            return await ctx.send(
                f"{config.NO} Something went wrong. Are you sure `{feed_id}` exists?",
                ephemeral=True,
            )

        if response["safe_to_delete"]:
            webhook = discord.Webhook.from_url(
                response["webhook_url"],
                session=self.bot.session,
            )
            try:
                await webhook.delete()
            except discord.HTTPException:
                pass

        channel = ctx.guild.get_channel(response["channel_id"])
        channel_fmt = channel.mention if channel else "#deleted-channel"
        await ctx.send(
            f"{config.YES} New posts from `r/{response['subreddit']}` will no longer be posted to {channel_fmt}."
        )

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

        response = await self.bot.api_request(
            "POST",
            "reddit/clear",
            json={"guild_id": ctx.guild.id},
        )
        for removed_hook in response["removed"]:
            if removed_hook["safe_to_delete"]:
                webhook = discord.Webhook.from_url(
                    removed_hook["webhook_url"],
                    session=self.bot.session,
                )
                try:
                    await webhook.delete()
                except discord.HTTPException:
                    continue

        await ctx.send(
            f"{config.YES} All {len(response['removed'])} subreddit feed(s) on this server were removed."
        )


async def setup(bot):
    await bot.add_cog(GuildSlash(bot))
