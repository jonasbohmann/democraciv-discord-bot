import discord

import bot.utils.text as utils
import bot.utils.exceptions as exceptions
from bot.config import config
from discord.ext import commands

class Guild(commands.Cog, name="Server"):
    """Configure various features of this bot for this server."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def emojiy_settings(boolean) -> str:
        # Thanks to Dutchy for the custom emojis used here

        if boolean:
            return f"{config.GUILD_SETTINGS_GRAY_DISABLED}{config.GUILD_SETTINGS_ENABLED}\u200b"
        else:
            return f"{config.GUILD_SETTINGS_DISABLED}{config.GUILD_SETTINGS_GRAY_ENABLED}\u200b"

    @commands.group(name='server', aliases=['settings', 'guild', 'config'], case_insensitive=True,
                    invoke_without_command=True)
    @commands.guild_only()
    async def guild(self, ctx):
        """Statistics and information about this server"""

        is_welcome_enabled = self.emojiy_settings(await self.bot.is_welcome_message_enabled(ctx.guild.id))
        is_logging_enabled = self.emojiy_settings(await self.bot.is_logging_enabled(ctx.guild.id))
        is_default_role_enabled = self.emojiy_settings(await self.bot.is_default_role_enabled(ctx.guild.id))
        is_tag_creation_allowed = self.emojiy_settings(await self.bot.is_tag_creation_allowed(ctx.guild.id))

        excluded_channels = await self.bot.db.fetchval("SELECT logging_excluded FROM guilds WHERE id = $1",
                                                       ctx.guild.id)
        excluded_channels = len(excluded_channels) if excluded_channels is not None else 0

        embed = self.bot.embeds.embed_builder(title=ctx.guild.name,
                                              description=f"Check `{config.BOT_PREFIX}help server` for help on "
                                                          f"how to configure me for this server.", has_footer=False)
        embed.add_field(name="Settings", value=f"{is_welcome_enabled} Welcome Messages\n"
                                               f"{is_logging_enabled} Logging ({excluded_channels} excluded channels)\n"
                                               f"{is_default_role_enabled} Default Role\n"
                                               f"{is_tag_creation_allowed} Tag Creation by Everyone")
        embed.add_field(name="Statistics", value=f"{ctx.guild.member_count} members\n"
                                                 f"{len(ctx.guild.text_channels)} text channels\n"
                                                 f"{len(ctx.guild.roles)} roles\n"
                                                 f"{len(ctx.guild.emojis)} custom emojis")
        embed.set_footer(text=f"Server was created on {ctx.guild.created_at.strftime('%A, %B %d %Y')}")
        embed.set_thumbnail(url=ctx.guild.icon_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def welcome_message_listener(self, member):
        if not await self.bot.is_welcome_message_enabled(member.guild.id):
            return

        welcome_channel = await self.bot.get_welcome_channel(member.guild)

        if welcome_channel is not None:
            welcome_message = (await self.bot.db.fetchval("SELECT welcome_message FROM guilds WHERE id = $1",
                                                          member.guild.id)).replace("{member}", f"{member.mention}")
            await welcome_channel.send(welcome_message)

    @guild.command(name='welcome')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx):
        """Add a welcome message that every new member will see once they join this server"""

        is_welcome_enabled = await self.bot.is_welcome_message_enabled(ctx.guild.id)
        current_welcome_channel = await self.bot.get_welcome_channel(ctx.guild)
        current_welcome_message = await self.bot.db.fetchval("SELECT welcome_message FROM guilds WHERE id = $1",
                                                             ctx.guild.id)

        if current_welcome_channel is None:
            current_welcome_channel = "-"
        else:
            current_welcome_channel = current_welcome_channel.mention

        if not current_welcome_message:
            current_welcome_message = "-"
        elif len(current_welcome_message) > 1024:
            current_welcome_message = "*The welcome message is too long to fit in here.*"

        embed = self.bot.embeds.embed_builder(title=f":wave:  Welcome Messages on {ctx.guild.name}",
                                              description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to change"
                                                          f" these settings.", has_footer=False)
        embed.add_field(name="Enabled", value=self.emojiy_settings(is_welcome_enabled))
        embed.add_field(name="Welcome Channel", value=current_welcome_channel)
        embed.add_field(name="Welcome Message", value=current_welcome_message, inline=False)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):
            status_question = await ctx.send(
                "React with :white_check_mark: to enable welcome messages,"
                " or with :x: to disable welcome messages.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute("UPDATE guilds SET welcome = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled welcome messages.")

                # Get new welcome channel
                await ctx.send(":information_source: Reply with the name of the welcome channel.")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET welcome_channel = $2 WHERE id = $1",
                                                   ctx.guild.id, channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the welcome channel to {channel_object.mention}.")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Reply with the message that should be sent to {channel_object.mention} "
                    f"every time a new member joins.\n\nWrite `{{member}}` "
                    f"to make the Bot mention the user.")

                welcome_message = await flow.get_text_input(300)

                if welcome_message:
                    status = await self.bot.db.execute("UPDATE guilds SET welcome_message = $2 WHERE id = $1",
                                                       ctx.guild.id, welcome_message)

                    if status == "UPDATE 1":
                        await ctx.send(f":white_check_mark: Welcome message was set.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET welcome = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Welcome messages were disabled.")

            await self.bot.update_guild_config_cache()

    @guild.command(name='logs', aliases=['log', 'logging'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx):
        """Log important events like message edits & deletions and more to a specific channel"""

        is_logging_enabled = await self.bot.is_logging_enabled(ctx.guild.id)
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            current_logging_channel = "-"
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy:  Event Logging on {ctx.guild.name}",
                                              description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji "
                                                          f"to change these settings.", has_footer=False)

        embed.add_field(name="Enabled", value=self.emojiy_settings(is_logging_enabled))
        embed.add_field(name="Log Channel", value=current_logging_channel)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send("React with :white_check_mark: to enable logging, "
                                             "or with :x: to disable logging.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute("UPDATE guilds SET logging = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Event logging was enabled.")
                await ctx.send(":information_source: Reply with the name of the channel"
                               " that I should use to log all events to.")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET logging_channel = $2 WHERE id = $1", ctx.guild.id,
                                                   channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the logging channel to {channel_object.mention}.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET logging = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Event logging was disabled.")

            await self.bot.update_guild_config_cache()

    @guild.command(name='exclude')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def exclude(self, ctx, channel: str = None):
        """Exclude message edits & deletions in a channel from showing up in your server's log channel


            **Usage:**
                `-server exclude` to see all excluded channels
                `-server exclude <channel>` to add/remove a channel to/from the excluded channels list
        """
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(":x: This server currently has no logging channel."
                                  " Please set one with `-server logs`.")

        help_description = "Add or remove a channel to the excluded channels with:\n`-server exclude [channel_name]`\n\n"

        excluded_channels = await self.bot.db.fetchval("SELECT logging_excluded FROM guilds WHERE id = $1",
                                                       ctx.guild.id)
        if not channel:
            current_excluded_channels_by_name = [help_description]

            if excluded_channels is None:
                return await ctx.send("There are no from logging excluded channels on this server.")

            for channel in excluded_channels:
                channel = self.bot.get_channel(channel)
                if channel is not None:
                    current_excluded_channels_by_name.append(channel.mention)

            pages = AlternativePages(ctx=ctx, entries=current_excluded_channels_by_name, show_entry_count=False,
                                     title=f"Logging-Excluded Channels on {ctx.guild.name}", show_index=False,
                                     per_page=20, show_amount_of_pages=True)
            return await pages.paginate()

        else:
            try:
                channel_object = await commands.TextChannelConverter().convert(ctx, channel)
            except commands.BadArgument:
                raise exceptions.ChannelNotFoundError(channel)

            if not channel_object:
                raise exceptions.ChannelNotFoundError(channel)

            # Remove channel
            if channel_object.id in excluded_channels:
                remove_status = await self.bot.db.execute(
                    "UPDATE guilds SET logging_excluded = array_remove(logging_excluded, $2 ) WHERE id = $1",
                    ctx.guild.id, channel_object.id)

                if remove_status == "UPDATE 1":
                    await self.bot.update_guild_config_cache()
                    return await ctx.send(f":white_check_mark: {channel_object.mention} is no longer excluded from"
                                          f" showing up in {current_logging_channel.mention}.")

            # Add channel
            add_status = await self.bot.db.execute("UPDATE guilds SET logging_excluded = array_append(logging_excluded,"
                                                   " $2) WHERE id = $1", ctx.guild.id, channel_object.id)

            if add_status == "UPDATE 1":
                await ctx.send(f":white_check_mark: Excluded channel {channel_object.mention} from showing up in "
                               f"{current_logging_channel.mention}.")
                await self.bot.update_guild_config_cache()

    @commands.Cog.listener(name="on_member_join")
    async def default_role_listener(self, member):
        if not await self.bot.is_default_role_enabled(member.guild.id):
            return

        default_role = await self.bot.db.fetchval("SELECT defaultrole_role FROM guilds WHERE id = $1", member.guild.id)
        default_role = member.guild.get_role(default_role)

        if default_role is not None:
            try:
                await member.add_roles(default_role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, default_role.name)

    @guild.command(name='defaultrole')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def defaultrole(self, ctx):
        """Give every new member a specific role once they join this server"""

        is_default_role_enabled = await self.bot.is_default_role_enabled(ctx.guild.id)

        current_default_role = await self.bot.db.fetchval("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                          ctx.guild.id)

        current_default_role = ctx.guild.get_role(current_default_role)

        if current_default_role is None:
            current_default_role = "-"
        else:
            current_default_role = current_default_role.mention

        embed = self.bot.embeds.embed_builder(title=f":partying_face:  Default Role on {ctx.guild.name}",
                                              description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji to"
                                                          f" change these settings.",
                                              has_footer=False)
        embed.add_field(name="Enabled", value=self.emojiy_settings(is_default_role_enabled))
        embed.add_field(name="Default Role", value=current_default_role)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the default role, or with :x: to disable the default role.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute("UPDATE guilds SET defaultrole = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the default role.")

                await ctx.send(
                    ":information_source: Reply with the name of the role that every "
                    "new member should get once they join.")

                new_default_role = await flow.get_new_role(240)

                if isinstance(new_default_role, str):
                    await ctx.send(
                        f":white_check_mark: I will **create a new role** on this server named `{new_default_role}`"
                        f" for the default role.")
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, new_default_role)

                else:
                    new_default_role_object = new_default_role

                    await ctx.send(
                        f":white_check_mark: I'll use the **pre-existing role** named "
                        f"`{new_default_role_object.name}` for the default role.")

                status = await self.bot.db.execute("UPDATE guilds SET defaultrole_role = $2 WHERE id = $1",
                                                   ctx.guild.id, new_default_role_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the default role to `{new_default_role_object.name}`.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET defaultrole = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the default role.")

            await self.bot.update_guild_config_cache()

    @guild.command(name='tagcreation')
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def tagcreation(self, ctx):
        """Allow everyone to make tags on this server, or just Administrators"""

        is_allowed = await self.bot.is_tag_creation_allowed(ctx.guild.id)

        pretty_is_allowed = "Only Administrators" if not is_allowed else "Everyone"

        embed = self.bot.embeds.embed_builder(title=f":pencil:  Tag Creation on {ctx.guild.name}",
                                              description=f"React with the {config.GUILD_SETTINGS_GEAR} emoji"
                                                          f" to change this setting.",
                                              has_footer=False)
        embed.add_field(name="Allowed Tag Creators", value=pretty_is_allowed)

        info_embed = await ctx.send(embed=embed)
        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):
            everyone = "\U0001f468\U0000200d\U0001f468\U0000200d\U0001f467\U0000200d\U0001f467"
            only_admins = "\U0001f46e"

            status_question = await ctx.send(f":information_source: Who should be able to create new tags "
                                             f"on this server with `-tag add`, "
                                             f"**everyone** or **just the Administrators** of this server?\n\n"
                                             f"React with {everyone} for everyone, or with {only_admins} for just "
                                             f"Administrators.")

            reaction, user = await flow.get_emoji_choice(everyone, only_admins, status_question, 240)

            if reaction is None:
                return

            if str(reaction) == everyone:
                await self.bot.db.execute("UPDATE guilds SET tag_creation_allowed = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Everyone can now make tags with `-tag add` on this server.")

            elif str(reaction) == only_admins:
                await self.bot.db.execute("UPDATE guilds SET tag_creation_allowed = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Only Administrators can now make"
                               " tags with `tag -add` on this server.")

            await self.bot.update_guild_config_cache()


def setup(bot):
    bot.add_cog(Guild(bot))
