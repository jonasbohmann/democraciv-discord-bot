import textwrap
import discord
import typing

from bot.config import config
from discord.ext import commands

from bot.utils import text, converter, paginator, exceptions, context
from utils.converter import Fuzzy


class _Guild(context.CustomCog, name="Server"):
    """Configure various features of this bot for this server."""

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

        is_welcome_enabled = self.bot.emojify_boolean(settings["welcome_enabled"])
        is_logging_enabled = self.bot.emojify_boolean(settings["logging_enabled"])
        is_default_role_enabled = self.bot.emojify_boolean(settings["default_role_enabled"])
        is_tag_creation_allowed = self.bot.emojify_boolean(settings["tag_creation_allowed"])
        excluded_channels = len(settings["private_channels"])
        is_npc_allowed = self.bot.emojify_boolean(settings['npc_usage_allowed'])

        embed = text.SafeEmbed(
            description=f"Check **`{config.BOT_PREFIX}help server`** to see how you can configure me for this server.",
        )

        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild_icon)

        embed.add_field(
            name="Settings",
            value=f"{is_welcome_enabled} Welcome Messages\n"
                  f"{is_logging_enabled} Logging ({excluded_channels} hidden channels)\n"
                  f"{is_default_role_enabled} Role on Join\n"
                  f"{is_tag_creation_allowed} Tag Creation by Everyone\n"
                  f"{is_npc_allowed} NPC Usage Allowed",
        )
        embed.add_field(
            name="Statistics",
            value=f"{ctx.guild.member_count} members\n"
                  f"{len(ctx.guild.text_channels)} text channels\n"
                  f"{len(ctx.guild.voice_channels)} voice channels\n"
                  f"{len(ctx.guild.roles)} roles\n"
                  f"{len(ctx.guild.emojis)} custom emojis",
        )
        embed.set_footer(text=f"Server was created on {ctx.guild.created_at.strftime('%A, %B %d %Y')}")
        embed.set_thumbnail(url=ctx.guild_icon)
        await ctx.send(embed=embed)

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
            message = message.replace("{discriminator}", member.discriminator)
            message = message.replace("{user}", str(member))
            message = message.replace("{server}", member.guild.name)
            message = message.replace("{channel}", welcome_channel.mention)
            await welcome_channel.send(message, allowed_mentions=discord.AllowedMentions(users=True))

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
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change these settings.",
        )

        embed.set_author(name=f"Welcome Messages on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=self.bot.emojify_boolean(settings["welcome_enabled"]))
        embed.add_field(name="Welcome Channel", value=current_welcome_channel_value)
        embed.add_field(name="Welcome Message", value=current_welcome_message, inline=False)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            menu = text.EditModelMenu(choices_with_formatted_explanation={"status": "Enable Welcome Messages"
            if not settings['welcome_enabled'] else
            "Disable Welcome Messages",
                                                                          "channel": "Welcome Channel",
                                                                          "message": "Welcome Message"})
            result = await menu.prompt(ctx)

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change['status']:
                welcome_enabled = not settings['welcome_enabled']

                if welcome_enabled:
                    await ctx.send(f"{config.YES} Welcome messages are now **enabled** on this server.")
                else:
                    await ctx.send(f"{config.YES} Welcome messages are now **disabled** on this server.")

            else:
                welcome_enabled = settings['welcome_enabled']

            if to_change['channel']:
                current_welcome_channel = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name or mention of the new welcome channel.",
                    converter=converter.CaseInsensitiveTextChannel,
                )

                if isinstance(current_welcome_channel, str):
                    await ctx.send(f"{config.NO} There is no channel on this server that matches "
                                   f"`{current_welcome_channel}`. I will not change the welcome channel.")
                    welcome_channel = settings['welcome_channel']

                else:
                    welcome_channel = current_welcome_channel.id

            else:
                welcome_channel = settings['welcome_channel']

            if to_change['message']:

                translations = (
                    f"`{{mention}}` - Mention (ping) the person that just joined  (For example: @DerJonas)\n"
                    f"`{{user}}` - Username#Discriminator  (For example: DerJonas#8036)\n"
                    f"`{{username}}` - Username  (For example: DerJonas)\n"
                    f"`{{discriminator}}` - Discriminator  (For example: 8036)\n"
                    f"`{{server}}` - Name of the server  (For example: Democraciv)\n"
                    f"`{{channel}}` - The welcome channel  (For example: #welcome)\n"
                )

                welcome_message = await ctx.input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the message that should be sent to "
                    f"{current_welcome_channel.mention} every time a new person joins.\n{config.HINT} "
                    f"You can use the following variables in the welcome message.\n\n{translations}"
                )
            else:
                welcome_message = settings['welcome_message']

            await self.bot.db.execute("UPDATE guild SET welcome_enabled = $1, welcome_channel = $2, "
                                      "welcome_message = $3 WHERE id = $4", welcome_enabled, welcome_channel,
                                      welcome_message, ctx.guild.id)
            await self.bot.update_guild_config_cache()
            await ctx.send(f"{config.YES} Welcome Message settings were updated.")

    @guild.group(name="logs", aliases=["log", "logging"], case_insensitive=True, invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx: context.CustomContext):
        """Log important events like message edits & deletions and more to a specific channel"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        current_logging_channel = await self.bot.get_logging_channel(ctx.guild)
        current_logging_channel_value = "-" if not current_logging_channel else current_logging_channel.mention

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change these settings.\n\nIf you want "
                        f"to change what specific events I should log, use my `{config.BOT_PREFIX}server logs events` "
                        f"command."
        )

        embed.set_author(name=f"Event Logging on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=self.bot.emojify_boolean(settings["logging_enabled"]))
        embed.add_field(name="Log Channel", value=current_logging_channel_value)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            menu = text.EditModelMenu(choices_with_formatted_explanation={"status": "Enable Logging"
            if not settings['logging_enabled'] else
            "Disable Logging",
                                                                          "channel": "Logging Channel"}
                                      )
            result = await menu.prompt(ctx)

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change['status']:
                logging_enabled = not settings['logging_enabled']

                if logging_enabled:
                    await ctx.send(f"{config.YES} Logging is now **enabled** on this server.")
                else:
                    await ctx.send(f"{config.YES} Logging is now **disabled** on this server.")

            else:
                logging_enabled = settings['logging_enabled']

            if to_change['channel']:
                current_logging_channel = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name or mention of the channel"
                    " where I should log all events to.",
                    converter=converter.CaseInsensitiveTextChannel,
                )

                if isinstance(current_logging_channel, str):
                    await ctx.send(f"{config.NO} There is no channel on this server that matches "
                                   f"`{current_logging_channel}`. I will not change the channel.")
                    logging_channel = settings['logging_channel']

                else:
                    logging_channel = current_logging_channel.id

            else:
                logging_channel = settings['logging_channel']

            await self.bot.db.execute("UPDATE guild SET logging_enabled = $1, logging_channel = $2 WHERE id = $3",
                                      logging_enabled, logging_channel, ctx.guild.id)
            await self.bot.update_guild_config_cache()
            await ctx.send(f"{config.YES} Logging settings were updated.\n{config.HINT} If you want to "
                           f"change what specific events I should log, use my `{config.BOT_PREFIX}server logs events` "
                           f"command.")

    @logs.command(name="events", aliases=["event"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs_change_events(self, ctx: context.CustomContext):
        """Customize what specific events I should log on this server"""

        choices = {
            "logging_message_edit": ["Message edits"],
            "logging_message_delete": ["Message deletions"],
            "logging_member_nickname_change": ["Nickname changes"],
            "logging_member_role_change": ["Someone gets or loses a role"],
            "logging_member_join_leave": ["Joins & Leaves"],
            "logging_ban_unban": ["Bans & Unbans"],
            "logging_guild_channel_create_delete": ["Channel creations & deletions"],
            "logging_role_create_delete": ["Role creations & deletions"]
        }

        current_settings = await self.ensure_guild_settings(ctx.guild.id)

        for k, v in current_settings.items():
            if k in choices:
                choices[k].append(v)

        menu = text.EditSettingsWithEmojifiedLiveToggles(settings=choices,
                                                         description=
                                                         f"You can toggle as many events on and off as you want. "
                                                         f"Once you're done, hit {config.YES} to confirm, or "
                                                         f"{config.NO} to cancel.\n",
                                                         title=f"Events to Log on {ctx.guild.name}",
                                                         icon=ctx.guild_icon)

        result = await menu.prompt(ctx)

        if not result.confirmed:
            return

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
            *result.choices.values(),
            ctx.guild.id,
        )

        await self.bot.update_guild_config_cache()
        await ctx.send(f"{config.YES} The settings for this server were updated.")

    @guild.command(name="hidechannel", aliases=["exclude", "private", "hiddenchannels", "hide"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def exclude(self, ctx, *, channel: Fuzzy[converter.CaseInsensitiveTextChannel,
                                                   converter.CaseInsensitiveCategoryChannel] = None):
        """Hide a channel or category from your server's log channel

        Both text channels and entire categories can be hidden.

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

        help_description = (
            f"When you hide a channel, it will no longer show up in {current_logging_channel.mention}.\n\nAdditionally,"
            f" :star: reactions for the starboard will no longer count in that channel.\n\nYou can hide a channel, "
            f"or even an entire category at once, with "
            f"`{config.BOT_PREFIX}server hidechannel <channel_name>`\n\n__**Hidden Channels**__"
        )

        private_channels = settings["private_channels"]

        if not channel:
            current_excluded_channels_by_name = [help_description]

            if not private_channels:
                return await ctx.send(
                    f"{config.NO} There are no hidden channels on this server yet. "
                    f"You can hide a channel so that it no longer shows up in "
                    f"{current_logging_channel.mention} with "
                    f"`{config.BOT_PREFIX}server hidechannel <channel_name>`."
                    f"\n{config.HINT} You can also hide entire categories! Just hide the category "
                    f"and every channel in that category will be hidden automatically. "
                    f"Note that if channel is hidden, :star: reactions for the starboard will no "
                    f"longer count in it."
                )

            for channel_id in private_channels:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    current_excluded_channels_by_name.append(channel.mention)

            pages = paginator.SimplePages(
                entries=current_excluded_channels_by_name,
                author=f"Hidden Channels on {ctx.guild.name}",
                icon=ctx.guild_icon,
                empty_message="There are no hidden channels on this server.",
            )
            return await pages.start(ctx)

        else:
            is_category = isinstance(channel, discord.CategoryChannel)

            # Remove channel
            if channel.id in private_channels:
                await self.bot.db.execute(
                    "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                    ctx.guild.id,
                    channel.id,
                )
                await self.bot.update_guild_config_cache()

                if is_category:
                    star = (
                        f"\n{config.HINT} *Note that :star: reactions for the starboard will now count again in every one of these channels.*"
                        if ctx.guild.id == self.bot.dciv.id and config.STARBOARD_ENABLED
                        else ""
                    )
                    await ctx.send(
                        f"{config.YES} The {channel} category **is no longer hidden**, and all channels in it "
                        f"will show up in {current_logging_channel.mention} again.{star}"
                    )
                else:
                    star = (
                        f"\n{config.HINT} *Note that :star: reactions for the starboard will now count again in this channel.*"
                        if ctx.guild.id == self.bot.dciv.id and config.STARBOARD_ENABLED
                        else ""
                    )
                    await ctx.send(
                        f"{config.YES} {channel.mention} **is no longer hidden**, "
                        f"and it will show up in {current_logging_channel.mention} again.{star}"
                    )

            # Add channel
            elif channel.id not in private_channels:
                await self.bot.db.execute(
                    "INSERT INTO guild_private_channel (guild_id, channel_id) VALUES ($1, $2)",
                    ctx.guild.id,
                    channel.id,
                )

                if is_category:
                    star = (
                        f"\n{config.HINT} *Note that :star: reactions for the starboard will also no longer count in any of these channels.*"
                        if ctx.guild.id == self.bot.dciv.id and config.STARBOARD_ENABLED
                        else ""
                    )

                    await ctx.send(
                        f"{config.YES} The {channel} category **is now hidden**, and all the channel in it "
                        f"will no longer show up in {current_logging_channel.mention}.{star}"
                    )
                else:
                    star = (
                        f"\n{config.HINT} *Note that :star: reactions for the starboard will also no longer count in this channel.*"
                        if ctx.guild.id == self.bot.dciv.id and config.STARBOARD_ENABLED
                        else ""
                    )

                    await ctx.send(
                        f"{config.YES} {channel.mention} **is now hidden** and will no longer show up "
                        f"in {current_logging_channel.mention}.{star}"
                    )
                await self.bot.update_guild_config_cache()

    @commands.Cog.listener(name="on_guild_channel_delete")
    async def check_stale_hidden_channel(self, channel: typing.Union[discord.TextChannel, discord.VoiceChannel,
                                                                     discord.CategoryChannel]):
        settings = await self.ensure_guild_settings(channel.guild.id)

        if channel.id in settings['private_channels']:
            await self.bot.db.execute("DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                                      channel.guild.id, channel.id)

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

    @guild.command(name="joinrole", aliases=["defaultrole"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def defaultrole(self, ctx: context.CustomContext):
        """Give every new person that joins a specific role"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        is_default_role_enabled = self.bot.emojify_boolean(settings["default_role_enabled"])
        current_default_role = ctx.guild.get_role(settings["default_role_role"])
        current_default_role_value = "-" if not current_default_role else current_default_role.mention

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change these settings.",
        )
        embed.set_author(name=f"Role on Join on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Enabled", value=is_default_role_enabled)
        embed.add_field(name="Role", value=current_default_role_value)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            menu = text.EditModelMenu(choices_with_formatted_explanation={"status": "Enable Role on Join"
            if not settings['default_role_enabled'] else
            "Disable Role on Join",
                                                                          "role": "Role"}
                                      )
            result = await menu.prompt(ctx)

            if not result.confirmed or True not in result.choices.values():
                return

            to_change = result.choices

            if to_change['status']:
                default_role_enabled = not settings['default_role_enabled']

                if default_role_enabled:
                    await ctx.send(f"{config.YES} Role on Join is now **enabled** on this server.")
                else:
                    await ctx.send(f"{config.YES} Role on Join is now **disabled** on this server.")

            else:
                default_role_enabled = settings['default_role_enabled']

            if to_change['role']:
                current_default_role = await ctx.converted_input(
                    f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the role that every "
                    "new person should get once they join this server.",
                    converter=converter.CaseInsensitiveRole,
                )

                if isinstance(current_default_role, str):
                    await ctx.send(f"{config.NO} There is no role on this server that matches "
                                   f"`{current_default_role}`. I will not change the role.")
                    default_role_role = settings['default_role_role']

                else:
                    default_role_role = current_default_role.id

            else:
                default_role_role = settings['default_role_role']

            await self.bot.db.execute("UPDATE guild SET default_role_enabled = $1, default_role_role = $2 "
                                      "WHERE id = $3",
                                      default_role_enabled, default_role_role, ctx.guild.id)
            await self.bot.update_guild_config_cache()
            await ctx.send(f"{config.YES} Role on Join settings were updated.")

    @guild.command(name="tagcreation", aliases=['tag', 'tags'])
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
                f"on this server with `{config.BOT_PREFIX}tag add`?\n\n{everyone} - Everyone"
                f"\n{only_admins} - Only Server Administrators",
                reactions=[everyone, only_admins],
            )

            if str(reaction) == everyone:
                await self.bot.db.execute(
                    "UPDATE guild SET tag_creation_allowed = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(
                    f"{config.YES} Everyone can now make tags with `{config.BOT_PREFIX}tag add` on this server."
                )

            elif str(reaction) == only_admins:
                await self.bot.db.execute(
                    "UPDATE guild SET tag_creation_allowed = false WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} Only Administrators can now make tags with "
                               f"`{config.BOT_PREFIX}tag add` on this server.")

            await self.bot.update_guild_config_cache()

    @guild.command(name="npcs", aliases=['npc'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggle_npc(self, ctx: context.CustomContext):
        """Allow or deny the usage of NPCs on this server"""

        settings = await self.ensure_guild_settings(ctx.guild.id)
        is_allowed = settings["npc_usage_allowed"]

        pretty_is_allowed = self.bot.emojify_boolean(is_allowed)

        embed = text.SafeEmbed(
            description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change this setting.",
        )

        embed.set_author(name=f"NPC Usage on {ctx.guild.name}", icon_url=ctx.guild_icon)
        embed.add_field(name="Allowed", value=pretty_is_allowed)

        info_embed = await ctx.send(embed=embed)

        if await ctx.ask_to_continue(message=info_embed, emoji=config.GUILD_SETTINGS_GEAR):
            reaction = await ctx.confirm(
                f"React with {config.YES} to allow everyone to use NPCs on this server, "
                f"or with {config.NO} to not allow it."
            )

            if reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET npc_usage_allowed = true WHERE id = $1",
                    ctx.guild.id,
                )
                await ctx.send(
                    f"{config.YES} NPCs can now be used on this server."
                )

            elif not reaction:
                await self.bot.db.execute(
                    "UPDATE guild SET npc_usage_allowed = false WHERE id = $1",
                    ctx.guild.id,
                )

                await ctx.send(f"{config.YES} NPCs can __no longer__ be used on this server.")

            await self.bot.update_guild_config_cache()

    async def _get_or_make_discord_webhook(self, ctx, channel):
        try:
            channel_webhooks = await channel.webhooks()

            # check to see if the current channel already has a webhook managed by us
            def pred(w):
                return (
                        (w.user and w.user.id == self.bot.user.id)
                        or w.name == self.bot.user.name
                        or w.avatar_url == self.bot.user.avatar_url
                )

            webhook = discord.utils.find(pred, channel_webhooks)

            if webhook:
                return webhook
            else:
                return await channel.create_webhook(name=self.bot.user.name, avatar=await self.bot.avatar_bytes())

        except discord.Forbidden:
            await ctx.send(f"{config.NO} You need to give me the `Manage Webhooks` permission in {channel.mention}.")
            return

    async def _list_webhooks(
            self, ctx, *, endpoint: str, webhook_name: str, command_name: str, icon: str, fmt: typing.Callable
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
            img = await self.bot.make_file_from_image_link(
                "https://cdn.discordapp.com/attachments/499669824847478785/778778261450653706/redditds.PNG"
            )

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} What's the ID of the {webhook_name} you want to remove? "
                f"You can get the ID from `{config.BOT_PREFIX}server {command_name}`. "
                f"In case you want to remove every feed on this server, use `{config.BOT_PREFIX}server {command_name} "
                f"clear` instead.",
                file=img,
            )

            hook_id = await ctx.converted_input(converter=converter.InternalAPIWebhookConverter)

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
            if removed_hook["safe_to_delete"]:
                webhook = discord.Webhook.from_url(
                    removed_hook["webhook_url"],
                    adapter=discord.AsyncWebhookAdapter(self.bot.session),
                )
                try:
                    await webhook.delete()
                except discord.HTTPException:
                    continue

        await ctx.send(f"{config.YES} All {len(response['removed'])} {webhook_name} on this server were removed.")

    @guild.group(name="reddit", case_insensitive=True, invoke_without_command=True, aliases=["r"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit(self, ctx: context.CustomContext):
        """List all active subreddit feeds on this server"""

        def fmt(webhook, discord_webhook):
            return f"**#{webhook['id']}**  -  [r/{webhook['subreddit']}](https://reddit.com/r/{webhook['subreddit']}) to {discord_webhook.channel.mention}"

        await self._list_webhooks(
            ctx,
            endpoint="reddit/list/",
            command_name="reddit",
            webhook_name="subreddit feeds",
            fmt=fmt,
            icon="https://cdn.discordapp.com/attachments/730898526040752291/781547428087201792/Reddit_Mark_OnWhite.png",
        )

    @reddit.command(name="add", aliases=["make", "create", "a", "m"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_add(self, ctx: context.CustomContext):
        """Add a subreddit feeds to this server"""

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
            "target": subreddit,
            "webhook_url": webhook.url,
            "webhook_id": webhook.id,
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
        }

        await self.bot.api_request("POST", f"reddit/add", json=js)
        await ctx.send(f"{config.YES} New posts from `r/{subreddit}` will now be posted to {channel.mention}.")

    @reddit.command(name="remove", aliases=["delete", "r", "d"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_remove(
            self, ctx: context.CustomContext, subreddit_feed_id: converter.InternalAPIWebhookConverter = None
    ):
        """Remove a subreddit feeds from this server"""

        def fmt(response, channel_fmt):
            return f"{config.YES} New posts from `r/{response['subreddit']}` will no longer be posted to {channel_fmt}."

        await self._remove_webhook(
            ctx,
            hook_id=subreddit_feed_id,
            endpoint="reddit/remove",
            command_name="reddit",
            webhook_name="subreddit feed",
            success_fmt=fmt,
        )

    @reddit.command(name="clear", aliases=["removeall", "deleteall"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reddit_clear(self, ctx: context.CustomContext):
        """Remove all subreddit feeds on this server"""
        await self._clear_webhooks(ctx, endpoint="reddit/clear", webhook_name="subreddit feed(s)")

    @guild.group(name="twitch", case_insensitive=True, invoke_without_command=True, aliases=["t"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch(self, ctx: context.CustomContext):
        """List all active twitch notifications on this server"""

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
            icon="https://cdn.discordapp.com/attachments/730898526040752291/781547042471149598/TwitchGlitchPurple.png",
        )

    @twitch.command(name="add", aliases=["make", "create", "a", "m"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch_add(self, ctx: context.CustomContext):
        """Add a twitch notification to this server"""

        streamer = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the streamer.")

        channel = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} In which channel should I post when `{streamer}` is going live?",
            converter=converter.CaseInsensitiveTextChannel,
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
            post_to_reddit = await ctx.confirm(f"{config.USER_INTERACTION_REQUIRED} Should I also post an "
                                               f"announcement to **r/Democraciv** everytime `{streamer}` is "
                                               f"going live?")

        js = {
            "target": streamer,
            "webhook_url": webhook.url,
            "webhook_id": webhook.id,
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
            "everyone_ping": everyone,
            "post_to_reddit": post_to_reddit
        }

        response = await self.bot.api_request("POST", f"twitch/add", json=js)

        if "error" in response:
            return await ctx.send(f"{config.NO} `{streamer}` is not a real streamer.")

        await ctx.send(
            f"{config.YES} Notifications for when `{streamer}` goes live will be posted to {channel.mention}."
        )

    @twitch.command(name="remove", aliases=["delete", "r", "d"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def twitch_remove(
            self, ctx: context.CustomContext, notification_id: converter.InternalAPIWebhookConverter = None
    ):
        """Remove a twitch notification from this server"""

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
    @commands.has_permissions(manage_guild=True)
    async def twitch_clear(self, ctx: context.CustomContext):
        """Remove all twitch notifications on this server"""
        await self._clear_webhooks(ctx, endpoint="twitch/clear", webhook_name="twitch notifications")


def setup(bot):
    bot.add_cog(_Guild(bot))
