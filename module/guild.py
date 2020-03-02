import discord

import util.utils as utils
import util.exceptions as exceptions
from util.flow import Flow
from discord.ext import commands


class Guild(commands.Cog):
    """Configure various features of this bot for this guild."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def emojiy_settings(boolean) -> str:
        if boolean:
            return "<:gray_x:683808378501333058><:enabled:683808377989890049>"
        else:
            return "<:disabled:683808378132365315><:gray_yes:683808378329628680>"

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def guild(self, ctx):
        """Summary of this guild's configuration"""

        is_welcome_enabled = await self.bot.checks.is_welcome_message_enabled(ctx.guild.id)
        is_welcome_enabled = self.emojiy_settings(is_welcome_enabled)

        is_logging_enabled = await self.bot.checks.is_logging_enabled(ctx.guild.id)
        is_logging_enabled = self.emojiy_settings(is_logging_enabled)

        is_default_role_enabled = await self.bot.checks.is_default_role_enabled(ctx.guild.id)
        is_default_role_enabled = self.emojiy_settings(is_default_role_enabled)

        excluded_channels = await self.bot.db.fetchval("SELECT logging_excluded FROM guilds WHERE id = $1",
                                                       ctx.guild.id)
        excluded_channels = len(excluded_channels) if excluded_channels is not None else 0

        embed = self.bot.embeds.embed_builder(title=ctx.guild.name,
                                              description=f"Check `{ctx.prefix}help Guild` for help on "
                                                          f"how to configure me for this guild.", has_footer=False)
        embed.add_field(name="Settings", value=f"{is_welcome_enabled} Welcome Messages\n"
                                               f"{is_logging_enabled} Logging ({excluded_channels} excluded channels)\n"
                                               f"{is_default_role_enabled} Default Roles")
        embed.add_field(name="Statistics", value=f"{ctx.guild.member_count} members\n"
                                                 f"{len(ctx.guild.text_channels)} text channels\n"
                                                 f"{len(ctx.guild.roles)} roles")
        embed.set_footer(text=f"Guild was created on {ctx.guild.created_at.strftime('%A, %B %d %Y')}")
        embed.set_thumbnail(url=ctx.guild.icon_url_as(format='png'))
        await ctx.send(embed=embed)

    @guild.command(name='welcome')
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx):
        """Configure a welcome message that every new member will see once they join this guild"""

        is_welcome_enabled = await self.bot.checks.is_welcome_message_enabled(ctx.guild.id)
        current_welcome_channel = await utils.get_welcome_channel(self.bot, ctx.guild)
        current_welcome_message = await self.bot.db.fetchval("SELECT welcome_message FROM guilds WHERE id = $1",
                                                             ctx.guild.id)

        if current_welcome_channel is None:
            current_welcome_channel = "This guild currently has no welcome channel."
        else:
            current_welcome_channel = current_welcome_channel.mention

        if not current_welcome_message:
            current_welcome_message = "This guild currently has no welcome message."

        embed = self.bot.embeds.embed_builder(title=f":wave:  Welcome Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change "
                                                          "the settings of this module.")
        embed.add_field(name="Enabled", value=str(is_welcome_enabled))
        embed.add_field(name="Channel", value=current_welcome_channel)
        embed.add_field(name="Message", value=current_welcome_message, inline=False)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):
            status_question = await ctx.send(
                "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute("UPDATE guilds SET welcome = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the welcome module.")

                # Get new welcome channel
                await ctx.send(
                    ":information_source: Answer with the name of the channel the welcome module should use:")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET welcome_channel = $2 WHERE id = $1",
                                                   ctx.guild.id, channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the welcome channel to {channel_object.mention}.")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Answer with the message that should be sent to {channel_object.mention} "
                    f"every time a new member joins.\n\nWrite '{{member}}' "
                    f"to make the Bot mention the user!")

                welcome_message = await flow.get_text_input(300)

                if welcome_message:
                    status = await self.bot.db.execute("UPDATE guilds SET welcome_message = $2 WHERE id = $1",
                                                       ctx.guild.id, welcome_message)

                    if status == "UPDATE 1":
                        await ctx.send(f":white_check_mark: Set welcome message to '{welcome_message}'.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET welcome = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the welcome module.")

    @guild.command(name='logs')
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx):
        """Configure the logging module that logs every guild event to a specified channel"""

        is_logging_enabled = await self.bot.checks.is_logging_enabled(ctx.guild.id)
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            current_logging_channel = "This guild currently has no logging channel."
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy:  Logging Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the "
                                                          "settings of this module.")

        embed.add_field(name="Enabled", value=str(is_logging_enabled))
        embed.add_field(name="Channel", value=current_logging_channel)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
                await self.bot.db.execute("UPDATE guilds SET logging = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the logging module.")

                await ctx.send(
                    ":information_source: Answer with the name of the channel the logging module should use:")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET logging_channel = $2 WHERE id = $1", ctx.guild.id,
                                                   channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the logging channel to {channel_object.mention}.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET logging = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the logging module.")

    @guild.command(name='exclude')
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def exclude(self, ctx, channel: str = None):
        """
        Configure the channels that should be excluded from the logging module on this guild

            **Usage:**
                `-guild exclude` to see all excluded channels
                `-guild exclude <channel>` too add/remove a channel to/from the excluded channels list
        """
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(":x: This guild currently has no logging channel. Please set one with `-guild logs`.")

        help_description = "Add/Remove a channel to the excluded channels with:\n`-guild exclude [channel_name]`\n"

        excluded_channels = await self.bot.db.fetchval("SELECT logging_excluded FROM guilds WHERE id = $1",
                                                       ctx.guild.id)
        if not channel:
            current_excluded_channels_by_name = ""

            if excluded_channels is None:
                return await ctx.send("There are no from logging excluded channels on this guild.")

            for channel in excluded_channels:
                channel = self.bot.get_channel(channel)
                if channel is not None:
                    current_excluded_channels_by_name += f"{channel.mention}\n"

            if current_excluded_channels_by_name == "":
                current_excluded_channels_by_name = "There are no from logging excluded channels on this guild."

            embed = self.bot.embeds.embed_builder(title=f"Logging-Excluded Channels on {ctx.guild.name}",
                                                  description=help_description)
            embed.add_field(name="Currently Excluded Channels", value=current_excluded_channels_by_name)
            await ctx.send(embed=embed)
            return

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
                    return await ctx.send(f":white_check_mark: {channel_object.mention} is no longer excluded from"
                                          f" showing up in {current_logging_channel.mention}!")

                else:
                    return await ctx.send(f":x: Unexpected error occurred.")

            # Add channel
            add_status = await self.bot.db.execute("UPDATE guilds SET logging_excluded = array_append(logging_excluded,"
                                                   " $2) WHERE id = $1"
                                                   , ctx.guild.id, channel_object.id)

            if add_status == "UPDATE 1":
                await ctx.send(f":white_check_mark: Excluded channel {channel_object.mention} from showing up in "
                               f"{current_logging_channel.mention}!")
            else:
                await ctx.send(f":x: Unexpected error occurred.")

            return

    @guild.command(name='defaultrole')
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def defaultrole(self, ctx):
        """Configure a default role that every new member will get once they join this guild"""

        is_default_role_enabled = await self.bot.checks.is_default_role_enabled(ctx.guild.id)

        current_default_role = await self.bot.db.fetchval("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                          ctx.guild.id)

        current_default_role = ctx.guild.get_role(current_default_role)

        if current_default_role is None:
            current_default_role = "This guild currently has no default role."
        else:
            current_default_role = current_default_role.mention

        embed = self.bot.embeds.embed_builder(title=f":partying_face:  Default Role for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the settings"
                                                          " of this module.")
        embed.add_field(name="Enabled", value=str(is_default_role_enabled))
        embed.add_field(name="Role", value=current_default_role)

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
                    ":information_source: What's the name of the role that every "
                    "new member should get once they join?")

                new_default_role = await flow.get_new_role(240)

                if isinstance(new_default_role, str):
                    await ctx.send(
                        f":white_check_mark: I will **create a new role** on this guild named '{new_default_role}'"
                        f" for the default role.")
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, new_default_role)

                else:
                    new_default_role_object = new_default_role

                    await ctx.send(
                        f":white_check_mark: I'll use the **pre-existing role** named "
                        f"'{new_default_role_object.name}' for the default role.")

                status = await self.bot.db.execute("UPDATE guilds SET defaultrole_role = $2 WHERE id = $1",
                                                   ctx.guild.id, new_default_role_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the default role to '{new_default_role_object.name}'.")

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET defaultrole = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the default role.")


def setup(bot):
    bot.add_cog(Guild(bot))
