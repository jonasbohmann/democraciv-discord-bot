import textwrap
import discord
import typing

from bot.config import config
from discord.ext import commands

from bot.utils import text, converter, paginator, exceptions, context


class _Guild(context.CustomCog, name="Server"):
    """Configure various features of this bot for this server."""

    @staticmethod
    def emojify_settings(boolean) -> str:
        # Thanks to Dutchy for the custom emojis used here
        if boolean:
            return f"{config.GUILD_SETTINGS_GRAY_DISABLED}{config.GUILD_SETTINGS_ENABLED}\u200b"
        else:
            return f"{config.GUILD_SETTINGS_DISABLED}{config.GUILD_SETTINGS_GRAY_ENABLED}\u200b"

    async def ensure_guild_settings(self, guild_id: int) -> typing.Dict[str, typing.Any]:
        try:
            settings = self.bot.guild_config[guild_id]

            if not settings:
                return await self.bot.update_guild_config_cache()
            else:
                return settings

        except (TypeError, KeyError):
            return await self.bot.update_guild_config_cache()

    @commands.group(
        name="server",
        aliases=["settings", "guild", "config"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def guild(self, ctx):
        """Statistics and information about this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)

        is_welcome_enabled = self.emojify_settings(settings["welcome_enabled"])
        is_logging_enabled = self.emojify_settings(settings["logging_enabled"])
        is_default_role_enabled = self.emojify_settings(settings["default_role_enabled"])
        is_tag_creation_allowed = self.emojify_settings(settings["tag_creation_allowed"])
        excluded_channels = len(settings["private_channels"])

        embed = text.SafeEmbed(
            title=ctx.guild.name,
            description=f"Check `{config.BOT_PREFIX}help server` for help on " f"how to configure me for this server.",
        )

        embed.add_field(
            name="Settings",
            value=f"{is_welcome_enabled} Welcome Messages\n"
                  f"{is_logging_enabled} Logging ({excluded_channels} excluded channels)\n"
                  f"{is_default_role_enabled} Default Role\n"
                  f"{is_tag_creation_allowed} Tag Creation by Everyone",
        )
        embed.add_field(
            name="Statistics",
            value=f"{ctx.guild.member_count} members\n"
                  f"{len(ctx.guild.text_channels)} text channels\n"
                  f"{len(ctx.guild.roles)} roles\n"
                  f"{len(ctx.guild.emojis)} custom emojis",
        )
        embed.set_footer(text=f"Server was created on {ctx.guild.created_at.strftime('%A, %B %d %Y')}")
        embed.set_thumbnail(url=ctx.guild.icon_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def welcome_message_listener(self, member):
        settings = await self.ensure_guild_settings(member.guild.id)

        if not settings["welcome_enabled"]:
            return

        welcome_channel = await self.bot.get_welcome_channel(member.guild)

        if welcome_channel is not None:
            welcome_message = settings[member.guild.id]["welcome_message"].replace("{member}", member.mention)
            await welcome_channel.send(welcome_message, allowed_mentions=discord.AllowedMentions(users=True))

    @guild.command(name="welcome")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: context.CustomContext):
        """Add a welcome message that every new member will see once they join this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_welcome_channel = await self.bot.get_welcome_channel(ctx.guild)
        current_welcome_message = settings["welcome_message"]
        current_welcome_channel_value = "-" if not current_welcome_channel else current_welcome_channel.mention

        if not current_welcome_message:
            current_welcome_message = "-"
        elif len(current_welcome_message) > 1024:
            current_welcome_message = textwrap.shorten(current_welcome_message, 1024)

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change" f" these settings.",
        )

        embed.set_author(name=f"Welcome Messages on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=self.emojify_settings(settings["welcome_enabled"]))
        embed.add_field(name="Welcome Channel", value=current_welcome_channel_value)
        embed.add_field(name="Welcome Message", value=current_welcome_message, inline=False)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            reaction = await ctx.confirm(
                f"React with {config.YES} to enable welcome messages, or with {config.NO} to disable welcome messages."
            )

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET welcome_enabled = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Welcome messages are now enabled on this server.")

                channel_object = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the welcome channel.",
                    converter=converter.CaseInsensitiveTextChannel,
                )

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                await self.bot.db.execute(
                    "UPDATE guild SET welcome_channel = $2 WHERE id = $1",
                    ctx.guild.id,
                    channel_object.id,
                )

                await ctx.send(f"{config.YES} Set the welcome channel to {channel_object.mention}.")

                # Get new welcome message
                welcome_message = await ctx.input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the message that should be sent to {channel_object.mention} "
                    f"every time a new member joins.\n\nWrite `{{member}}` "
                    f"to make the Bot mention the user."
                )

                await self.bot.db.execute(
                    "UPDATE guild SET welcome_message = $2 WHERE id = $1",
                    ctx.guild.id,
                    welcome_message,
                )

                await ctx.send(f"{config.YES} Welcome message was set.")

            elif not reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET welcome_enabled = false WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Welcome messages were disabled on this server.")

            await self.bot.update_guild_config_cache()

    @guild.command(name="logs", aliases=["log", "logging"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx: context.CustomContext):
        """Log important events like message edits & deletions and more to a specific channel"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)
        current_logging_channel_value = "-" if not current_logging_channel else current_logging_channel.mention

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change these settings.",
        )

        embed.set_author(name=f"Event Logging on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=self.emojify_settings(settings["logging_enabled"]))
        embed.add_field(name="Log Channel", value=current_logging_channel_value)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            reaction = await ctx.confirm(
                f"React with {config.YES} to enable logging, or with {config.NO} to disable logging."
            )

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET logging_enabled = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Event logging was enabled.")

                channel_object = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the channel"
                    " that I should use to log all events to.",
                    converter=converter.CaseInsensitiveTextChannel,
                )

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                await self.bot.db.execute(
                    "UPDATE guild SET logging_channel = $2 WHERE id = $1",
                    ctx.guild.id,
                    channel_object.id,
                )

                await ctx.send(
                    f"{config.YES} The logging channel on this server was set to {channel_object.mention}."
                )

            elif not reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET logging_enabled = false WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Event logging was disabled.")

            await self.bot.update_guild_config_cache()

    @guild.command(name="exclude")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def exclude(self, ctx, channel: str = None):
        """Exclude message edits & deletions in a channel from showing up in your server's log channel

        Both text channels and entire categories can be excluded.

         **Usage:**
             `-server exclude` to see all excluded channels
             `-server exclude <channel>` to add/remove a channel to/from the excluded channels list
        """
        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(
                f"{config.NO} This server currently has no logging channel. Please set one with `-server logs`."
            )

        help_description = (
            f"Add or remove a channel to the excluded channels with:\n`{config.BOT_PREFIX}server exclude [channel_name]`\n\n"
        )
        private_channels = settings["private_channels"]

        if not channel:
            current_excluded_channels_by_name = [help_description]

            if not private_channels:
                return await ctx.send("There are no from logging excluded channels on this server.")

            for channel_id in private_channels:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    current_excluded_channels_by_name.append(channel.mention)

            pages = paginator.SimplePages(
                entries=current_excluded_channels_by_name,
                author=f"Logging-Excluded Channels on {ctx.guild.name}",
                icon=ctx.guild.icon_url_as(static_format="png"),
            )
            return await pages.start(ctx)

        else:
            try:
                channel_object = await converter.CaseInsensitiveTextChannelOrCategoryChannel().convert(ctx, channel)
            except commands.BadArgument:
                raise exceptions.ChannelNotFoundError(channel)

            # Remove channel
            if channel_object.id in private_channels:
                await self.bot.db.execute(
                    "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                    ctx.guild.id,
                    channel_object.id,
                )
                await self.bot.update_guild_config_cache()
                await ctx.send(
                    f"{config.YES} {channel_object.mention} is no longer excluded from showing up in {current_logging_channel.mention}."
                )

            # Add channel
            elif channel_object.id not in private_channels:
                await self.bot.db.execute(
                    "INSERT INTO guild_private_channel (guild_id, channel_id) VALUES ($1, $2)",
                    ctx.guild.id,
                    channel_object.id,
                )
                await ctx.send(
                    f"{config.YES} Excluded channel {channel_object.mention} from showing up in {current_logging_channel.mention}."
                )
                await self.bot.update_guild_config_cache()

    @commands.Cog.listener(name="on_member_join")
    async def default_role_listener(self, member):
        settings = await self.ensure_guild_settings(member.guild.id)

        if not settings["default_role_enabled"]:
            return

        default_role = member.guild.get_role(settings["default_role_role"])

        if default_role is not None:
            try:
                await member.add_roles(default_role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, default_role.name)

    @guild.command(name="defaultrole")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def defaultrole(self, ctx: context.CustomContext):
        """Give every new member a specific role once they join this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        is_default_role_enabled = self.emojify_settings(settings["default_role_enabled"])
        current_default_role = ctx.guild.get_role(settings["default_role_role"])
        current_default_role_value = "-" if not current_default_role else current_default_role.mention

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to" f" change these settings.",
        )
        embed.set_author(name=f"Default Role on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=is_default_role_enabled)
        embed.add_field(name="Default Role", value=current_default_role_value)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            reaction = await ctx.confirm(
                f"React with {config.YES} to enable the default role, or with {config.NO} to disable the default role."
            )

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET default_role_enabled = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Default role was enabled on this server.")

                new_default_role = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the role that every "
                    "new member should get once they join.",
                    converter=converter.CaseInsensitiveRole,
                )

                if isinstance(new_default_role, str):
                    await ctx.send(
                        f"{config.YES} I will **create a new role** on this server named `{new_default_role}`"
                        f" for the default role."
                    )
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, new_default_role)

                else:
                    new_default_role_object = new_default_role

                    await ctx.send(
                        f"{config.YES} I'll use the **pre-existing role** named "
                        f"`{new_default_role_object.name}` for the default role."
                    )

                await self.bot.db.execute(
                    "UPDATE guild SET default_role_role = $2 WHERE id = $1",
                    ctx.guild.id,
                    new_default_role_object.id,
                )

                await ctx.send(
                    f"{config.YES} The default role was set to `{new_default_role_object.name}` on this server."
                )

            elif not reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET default_role_enabled = false WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Default role was disabled on this server.")

            await self.bot.update_guild_config_cache()

    @guild.command(name="tagcreation")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def tagcreation(self, ctx: context.CustomContext):
        """Allow everyone to make tags on this server, or just Administrators"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        is_allowed = settings["tag_creation_allowed"]

        pretty_is_allowed = "Only Administrators" if not is_allowed else "Everyone"

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji" f" to change this setting.",
        )

        embed.set_author(name=f"Tag Creation on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Allowed Tag Creators", value=pretty_is_allowed)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            everyone = "\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467"
            only_admins = "\U0001f46e"

            reaction = await ctx.choose(
                f"{config.USER_INTERACTION_REQUIRED} Who should be able to create new tags "
                f"on this server with `-tag add`, "
                f"**everyone** or **just the Administrators** of this server?\n\n"
                f"React with {everyone} for everyone, or with {only_admins} for just "
                f"Administrators.",
                reactions=[everyone, only_admins],
            )

            if reaction is None:
                return

            if str(reaction) == everyone:
                await self.bot.db.execute(
                    "UPDATE guild SET tag_creation_allowed = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Everyone can now make tags with `-tag add` on this server.")

            elif str(reaction) == only_admins:
                await self.bot.db.execute(
                    "UPDATE guild SET tag_creation_allowed = false WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(
                    f"{config.YES} Only Administrators can now make" " tags with `tag -add` on this server."
                )

            await self.bot.update_guild_config_cache()

    async def _get_or_make_discord_webhook(self, ctx, channel):
        try:
            channel_webhooks = await channel.webhooks()

            # check to see if the current channel already has a webhook managed by us
            def pred(w):
                return (w.user and w.user.id == self.bot.user.id) or w.name == self.bot.user.name \
                       or w.avatar_url == self.bot.user.avatar_url

            webhook = discord.utils.find(pred, channel_webhooks)

            if webhook:
                return webhook
            else:
                return await channel.create_webhook(name=self.bot.user.name, avatar=await self.bot.avatar_bytes())

        except discord.Forbidden:
            await ctx.send(
                f"{config.NO} You need to give me the `Manage Webhooks` permission in {channel.mention}.")
            return

    async def _list_webhooks(self, ctx, *, endpoint: str, webhook_name: str, command_name: str, icon: str, fmt: typing.Callable):
        webhooks = await self.bot.api_request("GET", f"{endpoint}{ctx.guild.id}")
        entries = []

        for webhook in webhooks["webhooks"]:
            try:
                discord_webhook = await self.bot.fetch_webhook(webhook["webhook_id"])
            except discord.HTTPException:
                continue

            entries.append(fmt(webhook, discord_webhook))

        pages = paginator.SimplePages(
            author=f"{webhook_name.title()} on {ctx.guild.name}",
            icon=icon,
            entries=entries,
            empty_message=f"This server does not have any {webhook_name} yet.\n\nAdd some "
                          f"with `{config.BOT_PREFIX}server {command_name} add`.",
        )
        await pages.start(ctx)

    async def _remove_webhook(self, ctx, *, endpoint: str, webhook_name: str, command_name: str,
                              success_fmt: typing.Callable):
        file = await self.bot.make_file_from_image_link(
            "https://cdn.discordapp.com/attachments/499669824847478785/778778261450653706/redditds.PNG"
        )

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} What's the ID of the {webhook_name} you want to remove? "
            f"You can get the ID from `{config.BOT_PREFIX}server {command_name}`. "
            f"In case you want to remove every feed on this server, use `{config.BOT_PREFIX}server {command_name} "
            f"clear` instead.",
            file=file,
        )

        hook_id = await ctx.input()

        if hook_id.startswith("#"):
            hook_id = hook_id[1:]

        if not hook_id.isdigit():
            return await ctx.send(f"{config.NO} `{hook_id}` is not a real ID.")

        try:
            response = await self.bot.api_request(
                "POST",
                endpoint,
                json={"id": hook_id, "guild_id": ctx.guild.id},
            )
        except exceptions.DemocracivBotAPIError:
            return await ctx.send(
                f"{config.NO} Something went wrong. Are you sure that `{hook_id}` is the ID of a "
                f"existing {webhook_name} on this server?"
            )

        if "error" in response:
            return await ctx.send(
                f"{config.NO} Something went wrong. Are you sure that `{hook_id}` is the ID of a "
                f"existing {webhook_name} on this server?"
            )

        if response['safe_to_delete']:
            webhook = discord.Webhook.from_url(
                response["webhook_url"],
                adapter=discord.AsyncWebhookAdapter(self.bot.session),
            )

            try:
                await webhook.delete()
            except discord.HTTPException:
                pass

        channel = ctx.guild.get_channel(response["channel_id"])
        channel_fmt = channel.mention if channel else "#deleted-channel"
        await ctx.send(success_fmt(response, channel_fmt))

    async def _clear_webhooks(self, ctx, *, endpoint, webhook_name):
        response = await self.bot.api_request("POST", endpoint, json={"guild_id": ctx.guild.id})

        for removed_hook in response["removed"]:
            webhook = discord.Webhook.from_url(
                removed_hook["webhook_url"],
                adapter=discord.AsyncWebhookAdapter(self.bot.session),
            )
            try:
                await webhook.delete()
            except discord.HTTPException:
                continue

        await ctx.send(
            f"{config.YES} All {len(response['removed'])} {webhook_name} on this server were removed."
        )

    @guild.group(name="reddit", case_insensitive=True, invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit(self, ctx: context.CustomContext):
        def fmt(webhook, discord_webhook):
            return f"**#{webhook['id']}**  -  [r/{webhook['subreddit']}](https://reddit.com/r/{webhook['subreddit']}) to {discord_webhook.channel.mention}"

        await self._list_webhooks(ctx, endpoint="reddit/list/",
                                  command_name="reddit", webhook_name="subreddit feeds",
                                  fmt=fmt,
                                  icon="https://cdn.discordapp.com/attachments/730898526040752291/781547428087201792/Reddit_Mark_OnWhite.png")

    @reddit.command(name="add", aliases=["make", "create"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_add(self, ctx: context.CustomContext):
        subreddit = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the subreddit, **without the leading /r/**."
        )

        async with self.bot.session.get(f"https://reddit.com/r/{subreddit}/new.json?limit=1") as resp:
            if str(resp.url).startswith(f"https://www.reddit.com/subreddits/search.json?q=") or resp.status == 404:
                # subreddit not real
                return await ctx.send(f"{config.NO} `r/{subreddit}` is not a subreddit.")

        channel = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} In which channel should new posts from `r/{subreddit}` be posted?",
            converter=converter.CaseInsensitiveTextChannel,
            return_input_on_fail=False,
        )

        webhook = await self._get_or_make_discord_webhook(ctx, channel)

        if not webhook:
            return

        js = {
            "subreddit": subreddit,
            "webhook_url": webhook.url,
            "webhook_id": webhook.id,
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
        }

        await self.bot.api_request("POST", f"reddit/add", json=js)
        await ctx.send(f"{config.YES} New posts from `r/{subreddit}` will now be posted to {channel.mention}.")

    @reddit.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_remove(self, ctx: context.CustomContext):
        def fmt(response, channel_fmt):
            return f"{config.YES} New posts from `r/{response['subreddit']}` will no longer be posted to {channel_fmt}."

        await self._remove_webhook(ctx, endpoint="reddit/remove",
                                   command_name="reddit",
                                   webhook_name="subreddit feed",
                                   success_fmt=fmt)

    @reddit.command(name="clear", aliases=["removeall", "deleteall"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_clear(self, ctx: context.CustomContext):
        await self._clear_webhooks(ctx, endpoint="reddit/clear", webhook_name="subreddit feed(s)")

    @guild.group(name="twitch", case_insensitive=True, invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch(self, ctx: context.CustomContext):
        def fmt(webhook, discord_webhook):
            return f"**#{webhook['id']}**  -  [twitch.tv/{webhook['streamer']}]" \
                   f"(https://twitch.tv/{webhook['streamer']}) to {discord_webhook.channel.mention}"

        await self._list_webhooks(ctx, endpoint="twitch/list/",
                                  command_name="twitch", webhook_name="twitch notifications",
                                  fmt=fmt,
                                  icon="https://cdn.discordapp.com/attachments/730898526040752291/781547042471149598/TwitchGlitchPurple.png")

    @twitch.command(name="add", aliases=["make", "create"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch_add(self, ctx: context.CustomContext):
        streamer = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the streamer.")

        channel = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} In which channel should I post when `{streamer}` is going live?",
            converter=converter.CaseInsensitiveTextChannel,
            return_input_on_fail=False,
        )

        webhook = await self._get_or_make_discord_webhook(ctx, channel)

        if not webhook:
            return

        everyone = await ctx.confirm(f"{config.USER_INTERACTION_REQUIRED} Should I ping @ everyone in "
                                     f"{channel.mention} when `{streamer}` goes live?")

        js = {
            "streamer": streamer,
            "webhook_url": webhook.url,
            "webhook_id": webhook.id,
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "everyone_ping": everyone
        }

        response = await self.bot.api_request("POST", f"twitch/add", json=js)

        if "error" in response:
            return await ctx.send(f"{config.NO} `{streamer}` is not a real streamer.")

        await ctx.send(
            f"{config.YES} Notifications for when `{streamer}` goes live will be posted to {channel.mention}.")

    @twitch.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch_remove(self, ctx: context.CustomContext):
        def fmt(response, channel_fmt):
            return f"{config.YES} Notifications for when `{response['streamer']}` goes live will no longer be posted to {channel_fmt}."

        await self._remove_webhook(ctx, endpoint="twitch/remove",
                                   command_name="twitch",
                                   webhook_name="stream notification",
                                   success_fmt=fmt)

    @twitch.command(name="clear", aliases=["removeall", "deleteall"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch_clear(self, ctx: context.CustomContext):
        await self._clear_webhooks(ctx, endpoint="twitch/clear", webhook_name="twitch notifications")


def setup(bot):
    bot.add_cog(_Guild(bot))
