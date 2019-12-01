import config
import discord
import asyncio

import util.exceptions as exceptions

from discord.ext import commands


# -- guild.py | module.guild --
#
# Commands that manage a guild's settings. Requires administrator permissions.
#


class Guild(commands.Cog):
    """Commands regarding this guild"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    async def guild(self, ctx):
        """Configure various features of this bot for this guild"""

        configuration_list_message = "`-guild welcome` to enable/disable welcome messages for this guild\n" \
                                     "`-guild logs` to enable/disable logging for this guild\n" \
                                     "`-guild exclude [name]` to add a channel to be excluded from " \
                                     "the logging channel\n" \
                                     "`-guild defaultrole` to enable/disable a default role that every new member gets"

        embed = self.bot.embeds.embed_builder(title=f"Guild Configuration for {ctx.guild.name}",
                                              description=f"Here is a list of things you can configure:"
                                                          f"\n\n{configuration_list_message}")
        await ctx.send(embed=embed)

    @guild.command(name='welcome')
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx):
        """Configure a welcome message that every new member will see once they join this guild"""

        is_welcome_enabled = (await self.bot.db.fetchrow("SELECT welcome FROM guilds WHERE id = $1", ctx.guild.id))[
            'welcome']

        current_welcome_channel = (await self.bot.db.fetchrow("SELECT welcome_channel FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['welcome_channel']
        current_welcome_channel = self.bot.get_channel(current_welcome_channel)

        current_welcome_message = (await self.bot.db.fetchrow("SELECT welcome_message FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['welcome_message']

        if current_welcome_channel is None:
            current_welcome_channel = "This guild currently has no welcome channel."
        else:
            current_welcome_channel = current_welcome_channel.mention

        if current_welcome_message is None or current_welcome_message == "":
            current_welcome_message = "This guild currently has no welcome message."

        embed = self.bot.embeds.embed_builder(title=f":wave: Welcome Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change "
                                                          "the settings of this module.")
        embed.add_field(name="Enabled", value=f"{str(is_welcome_enabled)}")
        embed.add_field(name="Channel", value=f"{current_welcome_channel}")
        embed.add_field(name="Message", value=f"{current_welcome_message}", inline=False)

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        try:
            await ctx.bot.wait_for('reaction_add',
                                   check=self.bot.checks.
                                   wait_for_gear_reaction_check(ctx, info_embed),
                                   timeout=300)

        except asyncio.TimeoutError:
            return

        else:
            await self.edit_welcome_settings(ctx)

    async def edit_welcome_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add',
                                                    check=self.bot.checks.wait_for_reaction_check(ctx, status_question),
                                                    timeout=240)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")
            return

        else:
            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET welcome = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the welcome module.")

                # Get new welcome channel
                await ctx.send(
                    ":information_source: Answer with the name of the channel the welcome module should use:")
                try:
                    channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                      timeout=120)
                except asyncio.TimeoutError:
                    await ctx.send(":x: Aborted.")
                    return

                if not channel.content:
                    await ctx.send(":x: Aborted.")
                    return

                new_welcome_channel = channel.content

                try:
                    channel_object = await commands.TextChannelConverter().convert(ctx, new_welcome_channel)
                except commands.BadArgument:
                    await ctx.send(f":x: Couldn't find a channel named '{new_welcome_channel}' on this guild!")
                    return

                if not channel_object:
                    await ctx.send(f":x: Couldn't find a channel named '{new_welcome_channel}' on this guild!")
                    return

                status = await self.bot.db.execute("UPDATE guilds SET welcome_channel = $2 WHERE id = $1",
                                                   ctx.guild.id, channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the welcome channel to {channel_object.mention}.")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Answer with the message that should be sent to #{new_welcome_channel} "
                    f"every time a new member joins.\n\n:warning: Write '{{member}}' to have the Bot mention the user!")
                try:
                    welcome_message = await self.bot.wait_for('message',
                                                              check=self.bot.checks.wait_for_message_check(ctx),
                                                              timeout=300)
                except asyncio.TimeoutError:
                    await ctx.send(":x: Aborted.")
                    return

                if welcome_message:
                    status = await self.bot.db.execute("UPDATE guilds SET welcome_message = $2 WHERE id = $1",
                                                       ctx.guild.id, welcome_message.content)

                    if status == "UPDATE 1":
                        await ctx.send(f":white_check_mark: Set welcome message to '{welcome_message.content}'.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET welcome = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the welcome module.")

    @guild.command(name='logs')
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx):
        """Configure the logging module that logs every guild event to a specified channel"""

        is_logging_enabled = (await self.bot.db.fetchrow("SELECT logging FROM guilds WHERE id = $1", ctx.guild.id))[
            'logging']

        current_logging_channel = (await self.bot.db.fetchrow("SELECT logging_channel FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['logging_channel']
        current_logging_channel = self.bot.get_channel(current_logging_channel)

        if current_logging_channel is None:
            current_logging_channel = "This guild currently has no logging channel."
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy: Logging Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the "
                                                          "settings of this module.")

        embed.add_field(name="Enabled", value=f"{str(is_logging_enabled)}")
        embed.add_field(name="Channel", value=f"{current_logging_channel}")

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        try:
            await ctx.bot.wait_for('reaction_add', check=self.bot.checks.wait_for_gear_reaction_check(ctx, info_embed),
                                   timeout=300)
        except asyncio.TimeoutError:
            return

        else:
            await self.edit_log_settings(ctx)

    async def edit_log_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add',
                                                    check=self.bot.checks.wait_for_reaction_check(ctx, status_question),
                                                    timeout=240)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")
            return

        else:
            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET logging = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the logging module.")

                await ctx.send(
                    ":information_source: Answer with the name of the channel the logging module should use:")
                try:
                    channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                      timeout=120)
                except asyncio.TimeoutError:
                    await ctx.send(":x: Aborted.")
                    return

                if not channel.content:
                    await ctx.send(":x: Aborted.")
                    return

                new_logging_channel = channel.content

                try:
                    channel_object = await commands.TextChannelConverter().convert(ctx, new_logging_channel)
                except commands.BadArgument:
                    await ctx.send(f":x: Couldn't find a channel named '{new_logging_channel}' on this guild!")
                    return

                if not channel_object:
                    await ctx.send(f":x: Couldn't find a channel named '{new_logging_channel}' on this guild!")
                    return

                status = await self.bot.db.execute("UPDATE guilds SET logging_channel = $2 WHERE id = $1", ctx.guild.id,
                                                   channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the logging channel to {channel_object.mention}.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET logging = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the logging module.")

    @guild.command(name='exclude')
    @commands.has_permissions(administrator=True)
    async def exclude(self, ctx, channel: str = None):
        """
        Configure the channels that should be excluded from the logging module on this guild

            Usage:
                `-guild exclude` to see all excluded channels
                `-guild exclude <channel>` too add/remove a channel to/from the excluded channels list
        """
        current_logging_channel = (await self.bot.db.fetchrow("SELECT logging_channel FROM guilds WHERE id = $1"
                                                              , ctx.guild.id))['logging_channel']
        current_logging_channel = self.bot.get_channel(current_logging_channel)

        if current_logging_channel is None:
            await ctx.send(":x: This guild currently has no logging channel. Please set one with `-guild logs`.")
            return

        help_description = "Add/Remove a channel to the excluded channels with:\n`-guild exclude [channel_name]`\n"

        excluded_channels = (await self.bot.db.fetchrow("SELECT logging_excluded FROM guilds WHERE id = $1"
                                                        , ctx.guild.id))['logging_excluded']
        if not channel:
            current_excluded_channels_by_name = ""

            if excluded_channels is None:
                await ctx.send("There are no from logging excluded channels on this guild.")
                return

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
                    await ctx.send(f":white_check_mark: {channel_object.mention} is no longer excluded from"
                                   f" showing up in {current_logging_channel.mention}!")
                    return
                else:
                    await ctx.send(f":x: Unexpected error occurred.")
                    return

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
    @commands.has_permissions(administrator=True)
    async def defaultrole(self, ctx):
        """Configure a default role that every new member will get once they join this guild"""

        is_default_role_enabled = (await self.bot.db.fetchrow("SELECT defaultrole FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['defaultrole']

        current_default_role = (await self.bot.db.fetchrow("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                           ctx.guild.id))['defaultrole_role']
        current_default_role = ctx.guild.get_role(current_default_role)

        if current_default_role is None:
            current_default_role = "This guild currently has no default role."
        else:
            current_default_role = current_default_role.mention

        embed = self.bot.embeds.embed_builder(title=f":partying_face: Default Role for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the settings"
                                                          " of this module.")
        embed.add_field(name="Enabled", value=f"{str(is_default_role_enabled)}")
        embed.add_field(name="Role", value=f"{current_default_role}")

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        try:
            await ctx.bot.wait_for('reaction_add', check=self.bot.checks.wait_for_gear_reaction_check(ctx, info_embed),
                                   timeout=300)

        except asyncio.TimeoutError:
            return

        else:
            await self.edit_default_role_settings(ctx)

    async def edit_default_role_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the default role, or with :x: to disable the default role.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add',
                                                    check=self.bot.
                                                    checks.wait_for_reaction_check(ctx, status_question),
                                                    timeout=240)

        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")
            return

        else:
            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET defaultrole = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the default role.")

                await ctx.send(
                    ":information_source: What's the name of the role that every "
                    "new member should get once they join?")
                try:
                    role = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                   timeout=120)
                except asyncio.TimeoutError:
                    await ctx.send(":x: Aborted.")
                    return

                if not role.content:
                    await ctx.send(":x: Aborted.")
                    return

                new_default_role = role.content

                try:
                    new_default_role_object = await commands.RoleConverter().convert(ctx, new_default_role)
                except commands.BadArgument:
                    new_default_role_object = None

                if new_default_role_object is None:
                    await ctx.send(
                        f":white_check_mark: I will **create a new role** on this guild named '{new_default_role}'"
                        f" for the default role.")
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError("create_role", new_default_role)

                else:
                    await ctx.send(
                        f":white_check_mark: I'll use the **pre-existing role** named "
                        f"'{new_default_role_object.name}' for the default role.")

                status = await self.bot.db.execute("UPDATE guilds SET defaultrole_role = $2 WHERE id = $1",
                                                   ctx.guild.id, new_default_role_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the default role to '{new_default_role_object.name}'.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET defaultrole = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the default role.")

    @commands.command(name='invite')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this guild"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)


def setup(bot):
    bot.add_cog(Guild(bot))
