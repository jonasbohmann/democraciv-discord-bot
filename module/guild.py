import config
import discord
import asyncio
import logging

from discord.ext import commands
from util.embed import embed_builder
from util.checks import isDemocracivGuild

logging.basicConfig(level=logging.INFO)


# -- guild.py | module.guild --
#
# Commands that manage a guild's settings. Requires administrator permissions.
#


class Guild(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    async def guild(self, ctx):
        """Configure me for this guild."""

        configuration_list_message = "`-guild welcome` to enable/disable welcome messages for this guild\n" \
                                     "`-guild logs` to enable/disable logging for this guild\n" \
                                     "`-guild exclude [name]` to add a channel to be excluded from " \
                                     "the logging channel\n"

        embed = embed_builder(title=f"Guild Configuration for {ctx.guild.name}",
                              description=f"Here is a list of things you can configure:"
                                          f"\n\n{configuration_list_message}")
        await ctx.send(embed=embed)

    @guild.command(name='welcome')
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx):
        is_welcome_enabled = config.getGuildConfig(ctx.guild.id)['enableWelcomeMessage']
        current_welcome_channel = config.getGuildConfig(ctx.guild.id)['welcomeChannel']
        current_welcome_message = config.getStrings(ctx.guild.id)['welcomeMessage']

        if current_welcome_channel == "":
            current_welcome_channel = "This guild currently has no welcome channel."
        else:
            current_welcome_channel = "#" + current_welcome_channel

        if current_welcome_message == "":
            current_welcome_message = "This guild currently has no welcome message."

        embed = embed_builder(title=f":wave: Welcome Module for {ctx.guild.name}",
                              description="React with the :gear: emoji to change the settings of this module.")
        embed.add_field(name="Enabled", value=f"{str(is_welcome_enabled)}")
        embed.add_field(name="Channel", value=f"{current_welcome_channel}")
        embed.add_field(name="Message", value=f"{current_welcome_message}", inline=False)

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        def check(r_, u_):
            return u_ == ctx.author and r_.message.id == info_embed.id and str(r_.emoji) == "\U00002699"

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add', check=check, timeout=120),
                                            ctx.bot.wait_for('reaction_remove', check=check, timeout=120)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            dump = done.pop().result()
            await self.edit_welcome_settings(ctx)

        except (asyncio.TimeoutError, TimeoutError):
            pass

        for future in pending:
            future.cancel()

    async def edit_welcome_settings(self, ctx):

        def message_check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        def reaction_check(r_, u_):
            return u_ == ctx.author and r_.message.id == status_question.id

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add', check=reaction_check, timeout=60),
                                            ctx.bot.wait_for('reaction_remove', check=reaction_check, timeout=60)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            reaction, user = done.pop().result()

            if str(reaction.emoji) == "\U00002705":
                config.updateWelcomeModule(ctx.guild.id, True)
                await ctx.send(":white_check_mark: Enabled the welcome module.")

                # Get new welcome channel
                await ctx.send(
                    ":information_source: Answer with the name of the channel the welcome module should use:")
                try:
                    channel = await self.bot.wait_for('message', check=message_check, timeout=60.0)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    return

                if not channel:
                    await ctx.send(":x: Aborted.")
                    return

                new_welcome_channel = channel.content
                if new_welcome_channel.startswith("#"):
                    new_welcome_channel.strip("#")

                success = config.setWelcomeChannel(ctx.guild.id, new_welcome_channel)

                if success:
                    await ctx.send(f":white_check_mark: Set the welcome channel to #{new_welcome_channel}")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Answer with the message that should be sent to #{new_welcome_channel} "
                    f"every time a new member joins.\n\n:warning: Write '{{member}}' to have the Bot mention the user!")
                try:
                    welcome_message = await self.bot.wait_for('message', check=message_check, timeout=120.0)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    return

                if welcome_message:
                    config.setWelcomeMessage(ctx.guild.id, welcome_message.content)
                    await ctx.send(f":white_check_mark: Set welcome message to '{welcome_message.content}'.")

            elif str(reaction.emoji) == "\U0000274c":
                config.updateWelcomeModule(ctx.guild.id, False)
                await ctx.send(":white_check_mark: Disabled the welcome module.")

        except (asyncio.TimeoutError, TimeoutError):
            await ctx.send(":x: Aborted.")
            pass

        for future in pending:
            future.cancel()

    @guild.command(name='logs')
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx):
        is_logging_enabled = config.getGuildConfig(ctx.guild.id)['enableLogging']
        current_logging_channel = config.getGuildConfig(ctx.guild.id)['logChannel']

        if current_logging_channel == "":
            current_logging_channel = "This guild currently has no welcome channel."
        else:
            current_logging_channel = "#" + current_logging_channel

        embed = embed_builder(title=f":spy: Logging Module for {ctx.guild.name}",
                              description="React with the :gear: emoji to change the settings of this module.")

        embed.add_field(name="Enabled", value=f"{str(is_logging_enabled)}")
        embed.add_field(name="Channel", value=f"{current_logging_channel}")

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        def check(r_, u_):
            return u_ == ctx.author and r_.message.id == info_embed.id and str(r_.emoji) == "\U00002699"

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add', check=check, timeout=120),
                                            ctx.bot.wait_for('reaction_remove', check=check, timeout=120)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            dump = done.pop().result()
            await self.edit_log_settings(ctx)

        except (asyncio.TimeoutError, TimeoutError):
            pass

        for future in pending:
            future.cancel()

    async def edit_log_settings(self, ctx):

        def message_check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        def reaction_check(r_, u_):
            return u_ == ctx.author and r_.message.id == status_question.id

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add', check=reaction_check, timeout=60),
                                            ctx.bot.wait_for('reaction_remove', check=reaction_check, timeout=60)],
                                           return_when=asyncio.FIRST_COMPLETED)
        try:
            reaction, user = done.pop().result()

            if str(reaction.emoji) == "\U00002705":
                config.updateLoggingModule(ctx.guild.id, True)
                await ctx.send(":white_check_mark: Enabled the logging module.")

                await ctx.send(
                    ":information_source: Answer with the name of the channel the logging module should use:")
                try:
                    channel = await self.bot.wait_for('message', check=message_check, timeout=60.0)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    pass

                if not channel:
                    await ctx.send(":x: Aborted.")
                    return

                new_logging_channel = channel.content
                if new_logging_channel.startswith("#"):
                    new_logging_channel.strip("#")

                success = config.setLoggingChannel(ctx.guild.id, new_logging_channel)

                if success:
                    await ctx.send(f":white_check_mark: Set the logging channel to #{new_logging_channel}")

            elif str(reaction.emoji) == "\U0000274c":
                config.updateLoggingModule(ctx.guild.id, False)
                await ctx.send(":white_check_mark: Disabled the logging module.")

        except (asyncio.TimeoutError, TimeoutError):
            await ctx.send(":x: Aborted.")
            pass

        for future in pending:
            future.cancel()

    @guild.command(name='exclude')
    @commands.has_permissions(administrator=True)
    async def exclude(self, ctx, channel: str = None):
        """
        See all excluded channels with `-guild exclude`-
        Add a channel to the excluded channels with `-guild exclude [channel_name].
        Remove a channel from the excluded channels with `-guild exclude [excluded_channel_name]`.
        """
        current_logging_channel = config.getGuildConfig(ctx.guild.id)['logChannel']

        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        help_description = "Add a channel to the excluded channels with:\n`-guild exclude " \
                           "[channel_name]`\nand remove a channel from the excluded channels " \
                           "with:\n`-guild exclude [excluded_channel_name]`.\n"

        current_excluded_channels_by_name = ""

        for channels in config.getGuildConfig(ctx.guild.id)['excludedChannelsFromLogging']:
            channels = self.bot.get_channel(int(channels))
            current_excluded_channels_by_name += f"#{channels.name}\n"

        if current_excluded_channels_by_name == "":
            current_excluded_channels_by_name = "There are no from logging excluded channels on this guild."

        if not channel:
            embed = embed_builder(title=f"Logging-Excluded Channels on {ctx.guild.name}",
                                  description=help_description)
            embed.add_field(name="Currently Excluded Channels", value=current_excluded_channels_by_name)
            await ctx.send(embed=embed)
            return

        else:

            if channel.startswith("<#"):
                channel = channel.replace("<#", "")
                channel = channel.rstrip('>')
                channel_object = self.bot.get_channel(int(channel))

            else:
                channel_object = discord.utils.get(ctx.guild.text_channels, name=channel)

            if not channel_object:
                await ctx.send(f":x: Couldn't find #{channel}!")
                return

            # Remove channel
            if str(channel_object.id) in config.getGuildConfig(ctx.guild.id)['excludedChannelsFromLogging']:
                if config.removeExcludedLogChannel(ctx.guild.id, str(channel_object.id)):
                    await ctx.send(f":white_check_mark: #{channel_object.name} is no longer excluded from"
                                   f" showing up in #{current_logging_channel}!")
                    return
                else:
                    await ctx.send(f":x: Unexpected error occurred.")
                    return

            if config.addExcludedLogChannel(ctx.guild.id, str(channel_object.id)):
                await ctx.send(f":white_check_mark: Excluded channel #{channel_object.name} from showing up in "
                               f"#{current_logging_channel}!")
            else:
                await ctx.send(f":x: Unexpected error occurred.")
                return


def setup(bot):
    bot.add_cog(Guild(bot))
