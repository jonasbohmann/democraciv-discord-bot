import dataclasses
import typing

import discord

from bot.config import config
from bot.services.context import CommandContextProtocol
from bot.services.results import OperationResult, PageResult
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


@dataclasses.dataclass
class HiddenChannelToggleResult:
    channel: typing.Union[discord.TextChannel, discord.CategoryChannel]
    logging_channel: discord.TextChannel
    is_hidden: bool
    message: str


class GuildService:
    def __init__(self, bot):
        self.bot = bot

    async def ensure_guild_settings(
        self, guild_id: int
    ) -> typing.Dict[str, typing.Any]:
        try:
            settings = self.bot.guild_config[guild_id]
            if settings:
                return settings
        except (AttributeError, TypeError, KeyError):
            pass

        settings_by_guild = await self.bot.update_guild_config_cache()
        return settings_by_guild[guild_id]

    async def refresh_settings(self):
        await self.bot.update_guild_config_cache()

    async def get_settings(self, ctx: CommandContextProtocol):
        return await self.ensure_guild_settings(ctx.guild.id)

    async def update_welcome_settings(
        self,
        ctx: CommandContextProtocol,
        *,
        enabled: typing.Optional[bool] = None,
        channel: typing.Optional[discord.TextChannel] = None,
        message: typing.Optional[str] = None,
    ) -> OperationResult:
        settings = await self.get_settings(ctx)
        await self.bot.db.execute(
            "UPDATE guild SET welcome_enabled = $1, welcome_channel = $2, "
            "welcome_message = $3 WHERE id = $4",
            settings["welcome_enabled"] if enabled is None else enabled,
            settings["welcome_channel"] if channel is None else channel.id,
            settings["welcome_message"] if message is None else message,
            ctx.guild.id,
        )
        await self.refresh_settings()
        return OperationResult(
            message=f"{config.YES} Welcome Message settings were updated."
        )

    async def update_logging_settings(
        self,
        ctx: CommandContextProtocol,
        *,
        enabled: typing.Optional[bool] = None,
        channel: typing.Optional[discord.TextChannel] = None,
    ) -> OperationResult:
        settings = await self.get_settings(ctx)
        await self.bot.db.execute(
            "UPDATE guild SET logging_enabled = $1, logging_channel = $2 WHERE id = $3",
            settings["logging_enabled"] if enabled is None else enabled,
            settings["logging_channel"] if channel is None else channel.id,
            ctx.guild.id,
        )
        await self.refresh_settings()
        return OperationResult(message=f"{config.YES} Logging settings were updated.")

    async def update_logging_events(
        self,
        ctx: CommandContextProtocol,
        choices: typing.Mapping[str, typing.Optional[bool]],
    ) -> OperationResult:
        settings = await self.get_settings(ctx)
        values = {
            column: settings[column] if choices.get(name) is None else choices[name]
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
        return OperationResult(
            message=f"{config.YES} The logging event settings were updated."
        )

    async def update_default_role_settings(
        self,
        ctx: CommandContextProtocol,
        *,
        enabled: typing.Optional[bool] = None,
        role: typing.Optional[discord.Role] = None,
    ) -> OperationResult:
        settings = await self.get_settings(ctx)
        await self.bot.db.execute(
            "UPDATE guild SET default_role_enabled = $1, default_role_role = $2 WHERE id = $3",
            settings["default_role_enabled"] if enabled is None else enabled,
            settings["default_role_role"] if role is None else role.id,
            ctx.guild.id,
        )
        await self.refresh_settings()
        return OperationResult(
            message=f"{config.YES} Role on Join settings were updated."
        )

    async def set_tag_creation(
        self,
        ctx: CommandContextProtocol,
        *,
        everyone: bool,
    ) -> OperationResult:
        await self.bot.db.execute(
            "UPDATE guild SET tag_creation_allowed = $1 WHERE id = $2",
            everyone,
            ctx.guild.id,
        )
        await self.refresh_settings()
        if everyone:
            message = (
                f"{config.YES} Everyone can now make tags with "
                f"`{config.BOT_PREFIX}tag add` on this server."
            )
        else:
            message = (
                f"{config.YES} Only Administrators can now make tags with "
                f"`{config.BOT_PREFIX}tag add` on this server."
            )
        return OperationResult(message=message)

    async def set_npc_usage(
        self,
        ctx: CommandContextProtocol,
        *,
        allowed: bool,
    ) -> OperationResult:
        await self.bot.db.execute(
            "UPDATE guild SET npc_usage_allowed = $1 WHERE id = $2",
            allowed,
            ctx.guild.id,
        )
        await self.refresh_settings()
        if allowed:
            message = f"{config.YES} NPCs can now be used on this server."
        else:
            message = f"{config.YES} NPCs can __no longer__ be used on this server."
        return OperationResult(message=message)

    async def get_logging_channel(
        self, guild: discord.Guild
    ) -> typing.Optional[discord.TextChannel]:
        return await self.bot.get_logging_channel(guild)

    async def get_welcome_channel(
        self, guild: discord.Guild
    ) -> typing.Optional[discord.TextChannel]:
        return await self.bot.get_welcome_channel(guild)

    async def toggle_hidden_channel(
        self,
        ctx: CommandContextProtocol,
        channel: typing.Union[discord.TextChannel, discord.CategoryChannel],
    ) -> HiddenChannelToggleResult:
        settings = await self.get_settings(ctx)
        logging_channel = await self.get_logging_channel(ctx.guild)

        if logging_channel is None:
            command = (
                "/server logs configure"
                if ctx.is_slash
                else f"{config.BOT_PREFIX}server logs"
            )
            raise exceptions.InvalidUserInputError(
                f"{config.NO} This server currently has no logging channel. "
                f"Please set one with `{command}`."
            )

        private_channels = settings["private_channels"]
        is_hidden = channel.id not in private_channels

        if is_hidden:
            await self.bot.db.execute(
                "INSERT INTO guild_private_channel (guild_id, channel_id) VALUES ($1, $2)",
                ctx.guild.id,
                channel.id,
            )
        else:
            await self.bot.db.execute(
                "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id,
                channel.id,
            )

        await self.refresh_settings()
        return HiddenChannelToggleResult(
            channel=channel,
            logging_channel=logging_channel,
            is_hidden=is_hidden,
            message=self.format_hidden_channel_toggle_message(
                ctx,
                channel=channel,
                logging_channel=logging_channel,
                is_hidden=is_hidden,
            ),
        )

    def format_hidden_channel_toggle_message(
        self,
        ctx: CommandContextProtocol,
        *,
        channel: typing.Union[discord.TextChannel, discord.CategoryChannel],
        logging_channel: discord.TextChannel,
        is_hidden: bool,
    ) -> str:
        is_category = isinstance(channel, discord.CategoryChannel)
        show_star_hint = ctx.guild.id == self.bot.dciv.id and config.STARBOARD_ENABLED

        if is_hidden:
            if is_category:
                star = (
                    f"\n{config.HINT} *Note that :star: reactions for the starboard "
                    "will also no longer count in any of these channels and their threads.*"
                    if show_star_hint
                    else ""
                )
                return (
                    f"{config.YES} The {channel} category **is now hidden**, and all the "
                    f"channels in it and their threads will no longer show up in "
                    f"{logging_channel.mention}.{star}"
                )

            star = (
                f"\n{config.HINT} *Note that :star: reactions for the starboard will "
                "also no longer count in this channel and its threads.*"
                if show_star_hint
                else ""
            )
            return (
                f"{config.YES} {channel.mention} (and all its threads) **are now "
                f"hidden** and will no longer show up in {logging_channel.mention}.{star}"
            )

        if is_category:
            star = (
                f"\n{config.HINT} *Note that :star: reactions for the starboard will now "
                "count again in every one of these channels and their threads.*"
                if show_star_hint
                else ""
            )
            return (
                f"{config.YES} The {channel} category **is no longer hidden**, and all "
                f"channels in it and their threads will show up in "
                f"{logging_channel.mention} again.{star}"
            )

        star = (
            f"\n{config.HINT} *Note that :star: reactions for the starboard will now "
            "count again in this channel and in all its threads.*"
            if show_star_hint
            else ""
        )
        return (
            f"{config.YES} {channel.mention} **is no longer hidden**, and it and all "
            f"its threads will show up in {logging_channel.mention} again.{star}"
        )

    async def remove_stale_hidden_channel(self, guild_id: int, channel_id: int):
        settings = await self.ensure_guild_settings(guild_id)

        if channel_id in settings["private_channels"]:
            await self.bot.db.execute(
                "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                guild_id,
                channel_id,
            )
            await self.refresh_settings()

    async def get_or_make_discord_webhook(
        self,
        channel: discord.TextChannel,
    ) -> typing.Optional[discord.Webhook]:
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
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You need to give me the `Manage Webhooks` permission in {channel.mention}."
            )

    async def list_reddit_feeds(self, ctx: CommandContextProtocol) -> PageResult:
        response = await self.bot.api_request("GET", f"reddit/list/{ctx.guild.id}")
        entries = []

        for webhook in response["webhooks"]:
            try:
                discord_webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            except discord.HTTPException:
                continue

            entries.append(
                f"**#{webhook['id']}**  -  [r/{webhook['subreddit']}](https://reddit.com/r/{webhook['subreddit']}) "
                f"to {discord_webhook.channel.mention}"
            )

        empty_message = "This server does not have any subreddit feeds yet."
        if not ctx.is_slash:
            empty_message = (
                "This server does not have any subreddit feeds yet.\n\nAdd some "
                f"with `{config.BOT_PREFIX}server reddit add`."
            )

        return PageResult(
            entries=entries,
            author=f"Subreddit Feeds on {ctx.guild.name}",
            icon="https://cdn.discordapp.com/attachments/730898526040752291/781547428087201792/Reddit_Mark_OnWhite.png",
            per_page=12,
            empty_message=empty_message,
        )

    def normalize_subreddit(self, subreddit: str) -> str:
        subreddit = (subreddit or "").strip()
        return subreddit.removeprefix("r/").removeprefix("/r/").strip()

    async def validate_subreddit(self, subreddit: str):
        if not subreddit:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You need to provide a subreddit."
            )

        async with self.bot.session.get(
            f"https://reddit.com/r/{subreddit}/new.json?limit=1"
        ) as resp:
            if (
                str(resp.url).startswith(
                    "https://www.reddit.com/subreddits/search.json?q="
                )
                or resp.status == 404
            ):
                raise exceptions.InvalidUserInputError(
                    f"{config.NO} `r/{subreddit}` is not a subreddit."
                )

    async def add_reddit_feed(
        self,
        ctx: CommandContextProtocol,
        *,
        subreddit: str,
        channel: discord.TextChannel,
    ) -> OperationResult:
        subreddit = self.normalize_subreddit(subreddit)
        await self.validate_subreddit(subreddit)

        webhook = await self.get_or_make_discord_webhook(channel)
        if not webhook:
            return OperationResult()

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
        return OperationResult(
            message=(
                f"{config.YES} New posts from `r/{subreddit}` will now be posted "
                f"to {channel.mention}."
            )
        )

    async def remove_reddit_feed(
        self,
        ctx: CommandContextProtocol,
        *,
        feed_id: int,
    ) -> OperationResult:
        try:
            response = await self.bot.api_request(
                "POST",
                "reddit/remove",
                json={"id": feed_id, "guild_id": ctx.guild.id},
            )
        except exceptions.DemocracivBotAPIError:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Something went wrong. Are you sure that `{feed_id}` is the ID of a existing subreddit feed on this server?"
            )

        if "error" in response:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Something went wrong. Are you sure that `{feed_id}` is the ID of a existing subreddit feed on this server?"
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
        return OperationResult(
            message=(
                f"{config.YES} New posts from `r/{response['subreddit']}` will no "
                f"longer be posted to {channel_fmt}."
            )
        )

    async def clear_reddit_feeds(
        self,
        ctx: CommandContextProtocol,
    ) -> OperationResult:
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

        return OperationResult(
            message=(
                f"{config.YES} All {len(response['removed'])} subreddit feed(s) "
                "on this server were removed."
            )
        )
