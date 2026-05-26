import discord
import typing

from bot.config import config
from discord.ext import commands

from bot.presenters import guild as guild_presenter, guild_forms
from bot.services.guild import GuildService, LOG_EVENT_COLUMNS
from bot.utils import text, converter, paginator, exceptions, context
from bot.utils.converter import Fuzzy


class SelectTagCreationView(text.PromptView):
    @discord.ui.select(
        options=[
            discord.SelectOption(
                label="Everyone",
                value="Everyone",
                emoji="\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467",
            ),
            discord.SelectOption(
                label="Only Server Administrators",
                value="Administrators",
                emoji="\U0001f46e",
            ),
        ]
    )
    async def slct(self, interaction: discord.Interaction, select):
        await interaction.response.defer()
        self.result = select.values[0]
        self.stop()


class _Guild(context.CustomCog, name="Server"):
    """Configure various features of this bot for this server."""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = GuildService(bot)

    async def ensure_guild_settings(
        self, guild_id: int
    ) -> typing.Dict[str, typing.Any]:
        return await self.service.ensure_guild_settings(guild_id)

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
        await ctx.send(embed=guild_presenter.build_server_overview_embed(ctx, settings))

    @commands.Cog.listener(name="on_member_join")
    async def welcome_message_listener(self, member: discord.Member):
        settings = await self.ensure_guild_settings(member.guild.id)

        if not settings["welcome_enabled"]:
            return

        welcome_channel = await self.bot.get_welcome_channel(member.guild)

        message = settings["welcome_message"]

        if welcome_channel and message:
            message = message.replace("{member}", member.mention)  # deprecated
            message = message.replace("{mention}", member.mention)
            message = message.replace("{username}", member.name)
            message = message.replace("{user}", member.display_name)
            message = message.replace("{server}", member.guild.name)
            message = message.replace("{channel}", welcome_channel.mention)
            await welcome_channel.send(
                message, allowed_mentions=discord.AllowedMentions(users=True)
            )

    @guild.command(name="welcome")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: context.CustomContext):
        """Add a welcome message that every new person will see once they join this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_welcome_channel = await self.bot.get_welcome_channel(ctx.guild)
        embed = guild_presenter.build_welcome_embed(
            ctx, settings, current_welcome_channel
        )

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(
            message=info_embed,
            emoji=config.GUILD_SETTINGS_GEAR,
            label="Change Settings",
        ):
            menu = text.EditModelMenu(
                ctx,
                choices_with_formatted_explanation={
                    "status": (
                        "Enable Welcome Messages"
                        if not settings["welcome_enabled"]
                        else "Disable Welcome Messages"
                    ),
                    "channel": "Welcome Channel",
                    "message": "Welcome Message",
                },
            )
            result = await menu.prompt()

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change["status"]:
                welcome_enabled = not settings["welcome_enabled"]

                if welcome_enabled:
                    await ctx.send(
                        f"{config.YES} Welcome messages are now **enabled** on this server."
                    )
                else:
                    await ctx.send(
                        f"{config.YES} Welcome messages are now **disabled** on this server."
                    )

            else:
                welcome_enabled = settings["welcome_enabled"]

            if to_change["channel"]:
                current_welcome_channel = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name or mention of the new welcome channel.",
                    converter=Fuzzy[converter.CaseInsensitiveTextChannel],
                )

                if isinstance(current_welcome_channel, str):
                    await ctx.send(
                        f"{config.NO} There is no channel on this server that matches "
                        f"`{current_welcome_channel}`. I will not change the welcome channel."
                    )
                    welcome_channel = settings["welcome_channel"]

                else:
                    welcome_channel = current_welcome_channel.id

            else:
                welcome_channel = settings["welcome_channel"]

            if to_change["message"]:
                view = text.ModalPromptView(
                    ctx,
                    modal_factory=lambda: guild_forms.WelcomeMessageModal(
                        current_message=settings["welcome_message"] or ""
                    ),
                    button_label="Edit Welcome Message",
                    timeout=300,
                )
                form = await view.prompt_message(
                    f"{config.USER_INTERACTION_REQUIRED} Fill out the welcome message form.\n"
                    f"{config.HINT} You can use `{{mention}}`, `{{user}}`, `{{username}}`, "
                    f"`{{server}}`, and `{{channel}}`."
                )

                if form is None:
                    return

                welcome_message = form.message
            else:
                welcome_message = settings["welcome_message"]

            result = await self.service.update_welcome_settings(
                ctx,
                enabled=welcome_enabled,
                channel=(
                    ctx.guild.get_channel(welcome_channel) if welcome_channel else None
                ),
                message=welcome_message,
            )
            await ctx.send(result.message)

    @guild.group(
        name="logs",
        aliases=["log", "logging"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx: context.CustomContext):
        """Log important events like message edits & deletions and more to a specific channel"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)
        embed = guild_presenter.build_logging_embed(
            ctx, settings, current_logging_channel
        )

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(
            message=info_embed,
            emoji=config.GUILD_SETTINGS_GEAR,
            label="Change Settings",
        ):
            menu = text.EditModelMenu(
                ctx,
                choices_with_formatted_explanation={
                    "status": (
                        "Enable Logging"
                        if not settings["logging_enabled"]
                        else "Disable Logging"
                    ),
                    "channel": "Logging Channel",
                },
            )
            result = await menu.prompt()

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change["status"]:
                logging_enabled = not settings["logging_enabled"]

                if logging_enabled:
                    await ctx.send(
                        f"{config.YES} Logging is now **enabled** on this server."
                    )
                else:
                    await ctx.send(
                        f"{config.YES} Logging is now **disabled** on this server."
                    )

            else:
                logging_enabled = settings["logging_enabled"]

            if to_change["channel"]:
                current_logging_channel = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name or mention of the channel"
                    " where I should log all events to.",
                    converter=Fuzzy[converter.CaseInsensitiveTextChannel],
                )

                if isinstance(current_logging_channel, str):
                    await ctx.send(
                        f"{config.NO} There is no channel on this server that matches "
                        f"`{current_logging_channel}`. I will not change the channel."
                    )
                    logging_channel = settings["logging_channel"]

                else:
                    logging_channel = current_logging_channel.id

            else:
                logging_channel = settings["logging_channel"]

            result = await self.service.update_logging_settings(
                ctx,
                enabled=logging_enabled,
                channel=(
                    ctx.guild.get_channel(logging_channel) if logging_channel else None
                ),
            )
            await ctx.send(
                f"{result.message}\n{config.HINT} If you want to "
                f"change what specific events I should log, use my `{config.BOT_PREFIX}server logs events` "
                f"command."
            )

    @logs.command(name="events", aliases=["event"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs_change_events(self, ctx: context.CustomContext):
        """Customize what specific events I should log on this server"""

        choices = {
            LOG_EVENT_COLUMNS["message_edits"]: [("", "Message edits")],
            LOG_EVENT_COLUMNS["message_deletes"]: [("", "Message deletions")],
            LOG_EVENT_COLUMNS["nickname_changes"]: [("", "Nickname changes")],
            LOG_EVENT_COLUMNS["role_changes"]: [("", "Someone gets or loses a role")],
            LOG_EVENT_COLUMNS["joins_and_leaves"]: [("", "Joins & Leaves")],
            LOG_EVENT_COLUMNS["bans_and_unbans"]: [("", "Bans & Unbans")],
            LOG_EVENT_COLUMNS["channel_create_delete"]: [
                ("", "Channel creations & deletions")
            ],
            LOG_EVENT_COLUMNS["role_create_delete"]: [
                ("", "Role creations & deletions")
            ],
        }

        current_settings = await self.ensure_guild_settings(ctx.guild.id)

        for k, v in current_settings.items():
            if k in choices:
                choices[k].append(v)

        menu = text.EditSettingsWithEmojifiedLiveToggles(
            ctx,
            settings=choices,
            description=f"You can toggle as many events on and off as you want. "
            f"Once you're done, either confirm to save the updated settings, or "
            f"cancel.\n",
            title=f"Events to Log on {ctx.guild.name}",
            icon=ctx.guild_icon,
        )

        result = await menu.prompt()

        if not result.confirmed:
            return

        reverse_columns = {column: name for name, column in LOG_EVENT_COLUMNS.items()}
        choices_by_event = {
            reverse_columns[column]: value for column, value in result.choices.items()
        }
        service_result = await self.service.update_logging_events(ctx, choices_by_event)
        await ctx.send(service_result.message)

    @guild.command(
        name="hidechannel", aliases=["exclude", "private", "hiddenchannels", "hide"]
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def exclude(
        self,
        ctx,
        *,
        channel: Fuzzy[
            converter.CaseInsensitiveTextChannel,
            converter.CaseInsensitiveCategoryChannel,
        ] = None,
    ):
        """Hide a channel or category from your server's log channel

        Both text channels and entire categories can be hidden.

        Threads inherit whether they are hidden from the channel they belong to.

         **Usage**
             `{PREFIX}{COMMAND}` to see all hidden channels/categories
             `{PREFIX}{COMMAND} <channel>` to hide or unhide a channel or category
        """
        channel: typing.Union[discord.TextChannel, discord.CategoryChannel]
        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(
                f"{config.NO} This server currently has no logging channel. "
                f"Please set one with `{config.BOT_PREFIX}server logs`."
            )

        private_channels = settings["private_channels"]

        if not channel:
            if not private_channels:
                return await ctx.send(
                    guild_presenter.hidden_channels_empty_message(
                        ctx, current_logging_channel
                    )
                )

            page = guild_presenter.build_hidden_channels_page(
                ctx, settings, current_logging_channel
            )

            pages = paginator.SimplePages(
                entries=list(page.entries),
                author=page.author,
                icon=page.icon,
                empty_message=page.empty_message,
            )
            return await pages.start(ctx)

        else:
            result = await self.service.toggle_hidden_channel(ctx, channel)
            await ctx.send(result.message)

    @commands.Cog.listener(name="on_guild_channel_delete")
    async def check_stale_hidden_channel(
        self,
        channel: typing.Union[
            discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel
        ],
    ):
        await self.service.remove_stale_hidden_channel(channel.guild.id, channel.id)

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
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.ADD_ROLE, default_role.name
                )

    @guild.command(name="joinrole", aliases=["defaultrole"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def defaultrole(self, ctx: context.CustomContext):
        """Give every new person that joins a specific role"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        embed = guild_presenter.build_default_role_embed(ctx, settings)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(
            message=info_embed,
            emoji=config.GUILD_SETTINGS_GEAR,
            label="Change Settings",
        ):
            menu = text.EditModelMenu(
                ctx,
                choices_with_formatted_explanation={
                    "status": (
                        "Enable Role on Join"
                        if not settings["default_role_enabled"]
                        else "Disable Role on Join"
                    ),
                    "role": "Role",
                },
            )
            result = await menu.prompt()

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change["status"]:
                default_role_enabled = not settings["default_role_enabled"]

                if default_role_enabled:
                    await ctx.send(
                        f"{config.YES} Role on Join is now **enabled** on this server."
                    )
                else:
                    await ctx.send(
                        f"{config.YES} Role on Join is now **disabled** on this server."
                    )

            else:
                default_role_enabled = settings["default_role_enabled"]

            if to_change["role"]:
                current_default_role = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the role that every "
                    "new person should get once they join this server.",
                    converter=Fuzzy[converter.CaseInsensitiveRole],
                )

                if isinstance(current_default_role, str):
                    await ctx.send(
                        f"{config.NO} There is no role on this server that matches "
                        f"`{current_default_role}`. I will not change the role."
                    )
                    default_role_role = settings["default_role_role"]

                else:
                    default_role_role = current_default_role.id

            else:
                default_role_role = settings["default_role_role"]

            result = await self.service.update_default_role_settings(
                ctx,
                enabled=default_role_enabled,
                role=(
                    ctx.guild.get_role(default_role_role) if default_role_role else None
                ),
            )
            await ctx.send(result.message)

    @guild.command(name="tagcreation", aliases=["tag", "tags"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def tagcreation(self, ctx: context.CustomContext):
        """Allow everyone to make tags on this server, or just Administrators"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        embed = guild_presenter.build_tag_creation_embed(ctx, settings)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(
            message=info_embed,
            emoji=config.GUILD_SETTINGS_GEAR,
            label="Change Settings",
        ):
            view = SelectTagCreationView(ctx)

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Who should be able to create new tags "
                f"on this server with `{config.BOT_PREFIX}tag add`?",
                view=view,
            )

            result = await view.prompt()

            if not result:
                return

            if result == "Everyone":
                service_result = await self.service.set_tag_creation(ctx, everyone=True)
                await ctx.send(service_result.message)

            elif result == "Administrators":
                service_result = await self.service.set_tag_creation(
                    ctx, everyone=False
                )
                await ctx.send(service_result.message)

    @guild.command(name="npcs", aliases=["npc"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggle_npc(self, ctx: context.CustomContext):
        """Allow or deny the usage of NPCs on this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        embed = guild_presenter.build_npc_usage_embed(ctx, settings)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(
            message=info_embed,
            emoji=config.GUILD_SETTINGS_GEAR,
            label="Change Settings",
        ):
            reaction = await ctx.confirm(
                f"React with {config.YES} to allow everyone to use NPCs on this server, "
                f"or with {config.NO} to not allow it."
            )

            if reaction:
                result = await self.service.set_npc_usage(ctx, allowed=True)
                await ctx.send(result.message)

            elif not reaction:
                result = await self.service.set_npc_usage(ctx, allowed=False)
                await ctx.send(result.message)

    async def _get_or_make_discord_webhook(self, ctx, channel):
        try:
            channel_webhooks = await channel.webhooks()

            # check to see if the current channel already has a webhook managed by us
            def pred(w):
                return (
                    (w.user and w.user.id == self.bot.user.id)
                    or w.name == self.bot.user.name
                    or w.avatar == self.bot.user.display_avatar
                )

            webhook = discord.utils.find(pred, channel_webhooks)

            if webhook:
                return webhook
            else:
                return await channel.create_webhook(
                    name=self.bot.user.name, avatar=await self.bot.avatar_bytes()
                )

        except discord.Forbidden:
            await ctx.send(
                f"{config.NO} You need to give me the `Manage Webhooks` permission in {channel.mention}."
            )
            return

    async def _list_webhooks(
        self,
        ctx,
        *,
        endpoint: str,
        webhook_name: str,
        command_name: str,
        icon: str,
        fmt: typing.Callable,
    ):
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
            per_page=12,
            empty_message=f"This server does not have any {webhook_name} yet.\n\nAdd some "
            f"with `{config.BOT_PREFIX}server {command_name} add`.",
        )
        await pages.start(ctx)

    async def _remove_webhook(
        self,
        ctx,
        *,
        hook_id: int = None,
        endpoint: str,
        webhook_name: str,
        command_name: str,
        success_fmt: typing.Callable,
    ):
        if not hook_id:
            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} What's the ID of the {webhook_name} you want to remove? "
                f"You can get the ID from `{config.BOT_PREFIX}server {command_name}`. "
                f"In case you want to remove every feed on this server, use `{config.BOT_PREFIX}server {command_name} "
                f"clear` instead.\n\nhttps://cdn.discordapp.com/attachments/499669824847478785/778778261450653706/redditds.PNG",
            )

            hook_id = await ctx.converted_input(
                converter=converter.InternalAPIWebhookConverter,
                return_input_on_fail=False,
            )

            if not hook_id:
                return

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
        await ctx.send(success_fmt(response, channel_fmt))

    async def _clear_webhooks(self, ctx, *, endpoint, webhook_name):
        response = await self.bot.api_request(
            "POST", endpoint, json={"guild_id": ctx.guild.id}
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
            f"{config.YES} All {len(response['removed'])} {webhook_name} on this server were removed."
        )

    @guild.group(
        name="reddit", case_insensitive=True, invoke_without_command=True, aliases=["r"]
    )
    @commands.guild_only()
    # @commands.has_permissions(manage_guild=True)
    async def reddit(self, ctx: context.CustomContext):
        """List all active subreddit feeds on this server"""

        page = await self.service.list_reddit_feeds(ctx)
        pages = paginator.SimplePages(
            entries=list(page.entries),
            author=page.author,
            icon=page.icon,
            per_page=page.per_page,
            empty_message=page.empty_message,
        )
        await pages.start(ctx)

    @reddit.command(name="add", aliases=["make", "create", "a", "m"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_add(self, ctx: context.CustomContext):
        """Add a subreddit feeds to this server"""

        view = text.ModalPromptView(
            ctx,
            modal_factory=guild_forms.RedditFeedModal,
            button_label="Add Subreddit Feed",
            timeout=300,
        )
        form = await view.prompt_message(
            f"{config.USER_INTERACTION_REQUIRED} Fill out the subreddit feed form."
        )

        if form is None:
            return

        subreddit = self.service.normalize_subreddit(form.subreddit)
        await self.service.validate_subreddit(subreddit)

        channel = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} In which channel should new posts from `r/{subreddit}` be posted?",
            converter=Fuzzy[converter.CaseInsensitiveTextChannel],
            return_input_on_fail=False,
        )

        result = await self.service.add_reddit_feed(
            ctx, subreddit=subreddit, channel=channel
        )
        if result.message:
            await ctx.send(result.message)

    @reddit.command(name="remove", aliases=["delete", "r", "d"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_remove(
        self,
        ctx: context.CustomContext,
        subreddit_feed_id: converter.InternalAPIWebhookConverter = None,
    ):
        """Remove a subreddit feeds from this server"""

        if not subreddit_feed_id:
            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} What's the ID of the subreddit feed you want to remove? "
                f"You can get the ID from `{config.BOT_PREFIX}server reddit`. "
                f"In case you want to remove every feed on this server, use `{config.BOT_PREFIX}server reddit "
                f"clear` instead.\n\nhttps://cdn.discordapp.com/attachments/499669824847478785/778778261450653706/redditds.PNG",
            )

            subreddit_feed_id = await ctx.converted_input(
                converter=converter.InternalAPIWebhookConverter,
                return_input_on_fail=False,
            )

            if not subreddit_feed_id:
                return

        result = await self.service.remove_reddit_feed(ctx, feed_id=subreddit_feed_id)
        await ctx.send(result.message)

    @reddit.command(name="clear", aliases=["removeall", "deleteall"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_clear(self, ctx: context.CustomContext):
        """Remove all subreddit feeds on this server"""
        result = await self.service.clear_reddit_feeds(ctx)
        await ctx.send(result.message)

    @guild.group(
        name="twitch", case_insensitive=True, invoke_without_command=True, aliases=["t"]
    )
    @commands.guild_only()
    # @commands.has_permissions(manage_guild=True)
    async def twitch(self, ctx: context.CustomContext):
        """List all active twitch notifications on this server"""
        return await ctx.send(
            f"{config.NO} Twitch notifications are disabled due to democracivbank.com, which is needed for them to work, being offline. Reddit notifications continue to work. See `-bank` for more details."
        )

        def fmt(webhook, discord_webhook):
            return (
                f"**#{webhook['id']}**  -  [twitch.tv/{webhook['streamer']}]"
                f"(https://twitch.tv/{webhook['streamer']}) to {discord_webhook.channel.mention}"
            )

        await self._list_webhooks(
            ctx,
            endpoint="twitch/list/",
            command_name="twitch",
            webhook_name="twitch notifications",
            fmt=fmt,
            icon="https://cdn.discordapp.com/attachments/738903909535318086/844946761353134100/testamesta.png",
        )

    @twitch.command(name="add", aliases=["make", "create", "a", "m"])
    @commands.guild_only()
    # @commands.has_permissions(manage_guild=True)
    async def twitch_add(self, ctx: context.CustomContext):
        """Add a twitch notification to this server"""
        return await ctx.send(
            f"{config.NO} Twitch notifications are disabled due to democracivbank.com, which is needed for them to work, being offline. Reddit notifications continue to work. See `-bank` for more details."
        )
        streamer = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the streamer."
        )

        channel = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} In which channel should I post when `{streamer}` is going live?",
            converter=Fuzzy[converter.CaseInsensitiveTextChannel],
            return_input_on_fail=False,
        )

        webhook = await self._get_or_make_discord_webhook(ctx, channel)

        if not webhook:
            return

        everyone = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Should I ping @ everyone in "
            f"{channel.mention} when `{streamer}` goes live?"
        )

        post_to_reddit = False

        if ctx.guild.id == self.bot.dciv.id:
            post_to_reddit = await ctx.confirm(
                f"{config.USER_INTERACTION_REQUIRED} Should I also post an "
                f"announcement to **r/Democraciv** everytime `{streamer}` is "
                f"going live?"
            )

        js = {
            "target": streamer,
            "webhook_url": webhook.url,
            "webhook_id": webhook.id,
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
            "everyone_ping": everyone,
            "post_to_reddit": post_to_reddit,
        }

        response = await self.bot.api_request("POST", f"twitch/add", json=js)

        if "error" in response:
            return await ctx.send(f"{config.NO} `{streamer}` is not a real streamer.")

        await ctx.send(
            f"{config.YES} Notifications for when `{streamer}` goes live will be posted to {channel.mention}."
        )

    @twitch.command(name="remove", aliases=["delete", "r", "d"])
    @commands.guild_only()
    # @commands.has_permissions(manage_guild=True)
    async def twitch_remove(
        self,
        ctx: context.CustomContext,
        notification_id: converter.InternalAPIWebhookConverter = None,
    ):
        """Remove a twitch notification from this server"""
        return await ctx.send(
            f"{config.NO} Twitch notifications are disabled due to democracivbank.com, which is needed for them to work, being offline. Reddit notifications continue to work. See `-bank` for more details."
        )

        def fmt(response, channel_fmt):
            return f"{config.YES} Notifications for when `{response['streamer']}` goes live will no longer be posted to {channel_fmt}."

        await self._remove_webhook(
            ctx,
            hook_id=notification_id,
            endpoint="twitch/remove",
            command_name="twitch",
            webhook_name="stream notification",
            success_fmt=fmt,
        )

    @twitch.command(name="clear", aliases=["removeall", "deleteall"])
    @commands.guild_only()
    # @commands.has_permissions(manage_guild=True)
    async def twitch_clear(self, ctx: context.CustomContext):
        """Remove all twitch notifications on this server"""
        return await ctx.send(
            f"{config.NO} Twitch notifications are disabled due to democracivbank.com, which is needed for them to work, being offline. Reddit notifications continue to work. See `-bank` for more details."
        )
        await self._clear_webhooks(
            ctx, endpoint="twitch/clear", webhook_name="twitch notifications"
        )


async def setup(bot):
    await bot.add_cog(_Guild(bot))
