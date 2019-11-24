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
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    async def guild(self, ctx):
        """Configure me for this guild."""

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

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.checks.
                                                             wait_for_gear_reaction_check(ctx, info_embed),
                                                             timeout=240),
                                            ctx.bot.wait_for('reaction_remove', check=self.bot.checks.
                                                             wait_for_gear_reaction_check(ctx, info_embed)
                                                             , timeout=240)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            dump = done.pop().result()
            await self.edit_welcome_settings(ctx)

        except (asyncio.TimeoutError, TimeoutError):
            pass

        for future in pending:
            future.cancel()

    async def edit_welcome_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.checks.
                                                             wait_for_reaction_check(ctx, status_question),
                                                             timeout=240),
                                            ctx.bot.wait_for('reaction_remove',
                                                             check=self.bot.checks.
                                                             wait_for_reaction_check(ctx, status_question),
                                                             timeout=240)],
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
                    channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx)
                                                      , timeout=120)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    return

                if not channel:
                    await ctx.send(":x: Aborted.")
                    return

                new_welcome_channel = channel.content

                channel_object = await commands.TextChannelConverter().convert(ctx, new_welcome_channel)

                if not channel_object:
                    raise exceptions.ChannelNotFoundError(new_welcome_channel)

                success = config.setWelcomeChannel(ctx.guild.id, channel_object.name)

                if success:
                    await ctx.send(f":white_check_mark: Set the welcome channel to #{channel_object.name}")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Answer with the message that should be sent to #{new_welcome_channel} "
                    f"every time a new member joins.\n\n:warning: Write '{{member}}' to have the Bot mention the user!")
                try:
                    welcome_message = await self.bot.wait_for('message',
                                                              check=self.bot.checks.wait_for_message_check(ctx),
                                                              timeout=300)
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
        is_logging_enabled = (await self.bot.db.fetchrow("SELECT logging FROM guilds WHERE id = $1", ctx.guild.id))[
            'logging']

        current_logging_channel = (await self.bot.db.fetchrow("SELECT logging_channel FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['logging_channel']
        current_logging_channel = self.bot.get_channel(current_logging_channel)

        if current_logging_channel is None:
            current_logging_channel = "This guild currently has no welcome channel."
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy: Logging Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the "
                                                          "settings of this module.")

        embed.add_field(name="Enabled", value=f"{str(is_logging_enabled)}")
        embed.add_field(name="Channel", value=f"{current_logging_channel}")

        info_embed = await ctx.send(embed=embed)
        await info_embed.add_reaction("\U00002699")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.checks.wait_for_gear_reaction_check
                                                             (ctx, info_embed), timeout=240),
                                            ctx.bot.wait_for('reaction_remove', check=self.bot.checks.
                                                             wait_for_gear_reaction_check(ctx, info_embed),
                                                             timeout=240)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            dump = done.pop().result()
            await self.edit_log_settings(ctx)

        except (asyncio.TimeoutError, TimeoutError):
            pass

        for future in pending:
            future.cancel()

    async def edit_log_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.
                                                             checks.wait_for_reaction_check(ctx, status_question),
                                                             timeout=240),
                                            ctx.bot.wait_for('reaction_remove',
                                                             check=self.bot.
                                                             checks.wait_for_reaction_check(ctx, status_question),
                                                             timeout=240)],
                                           return_when=asyncio.FIRST_COMPLETED)
        try:
            reaction, user = done.pop().result()

            if str(reaction.emoji) == "\U00002705":
                config.updateLoggingModule(ctx.guild.id, True)
                await ctx.send(":white_check_mark: Enabled the logging module.")

                await ctx.send(
                    ":information_source: Answer with the name of the channel the logging module should use:")
                try:
                    channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                      timeout=120)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    pass

                if not channel:
                    await ctx.send(":x: Aborted.")
                    return

                new_logging_channel = channel.content

                channel_object = await commands.TextChannelConverter().convert(ctx, new_logging_channel)

                if not channel_object:
                    raise exceptions.ChannelNotFoundError(new_logging_channel)

                if new_logging_channel.startswith("#"):
                    new_logging_channel.strip("#")

                success = config.setLoggingChannel(ctx.guild.id, channel_object.name)

                if success:
                    await ctx.send(f":white_check_mark: Set the logging channel to #{channel_object.name}")

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
        current_logging_channel = (await self.bot.db.fetchrow("SELECT logging_channel FROM guilds WHERE id = $1"
                                                              , ctx.guild.id))['logging_channel']
        current_logging_channel = self.bot.get_channel(current_logging_channel)

        if current_logging_channel is None:
            await ctx.send("This guild currently has no logging channel. Please set one with `-guild logs`.")
            return

        help_description = "Add a channel to the excluded channels with:\n`-guild exclude " \
                           "[channel_name]`\nand remove a channel from the excluded channels " \
                           "with:\n`-guild exclude [excluded_channel_name]`.\n"

        if not channel:
            current_excluded_channels_by_name = ""

            excluded_channels = (await self.bot.db.fetchrow("SELECT logging_excluded FROM guilds WHERE id = $1"
                                                            , ctx.guild.id))['logging_excluded']

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

            channel_object = await commands.TextChannelConverter().convert(ctx, channel)

            if not channel_object:
                raise exceptions.ChannelNotFoundError(channel)

            # Remove channel
            if str(channel_object.id) in config.getGuildConfig(ctx.guild.id)['excludedChannelsFromLogging']:
                if config.removeExcludedLogChannel(ctx.guild.id, str(channel_object.id)):
                    await ctx.send(f":white_check_mark: #{channel_object.name} is no longer excluded from"
                                   f" showing up in #{current_logging_channel.mention}!")
                    return
                else:
                    await ctx.send(f":x: Unexpected error occurred.")
                    return

            if config.addExcludedLogChannel(ctx.guild.id, str(channel_object.id)):
                await ctx.send(f":white_check_mark: Excluded channel #{channel_object.name} from showing up in "
                               f"{current_logging_channel.mention}!")
            else:
                await ctx.send(f":x: Unexpected error occurred.")
                return

    @guild.command(name='defaultrole')
    @commands.has_permissions(administrator=True)
    async def defaultrole(self, ctx):
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

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.checks.
                                                             wait_for_gear_reaction_check(ctx, info_embed),
                                                             timeout=240),
                                            ctx.bot.wait_for('reaction_remove',
                                                             check=self.bot.checks.
                                                             wait_for_gear_reaction_check(ctx, info_embed),
                                                             timeout=240)],
                                           return_when=asyncio.FIRST_COMPLETED)

        try:
            dump = done.pop().result()
            await self.edit_default_role_settings(ctx)

        except (asyncio.TimeoutError, TimeoutError):
            pass

        for future in pending:
            future.cancel()

    async def edit_default_role_settings(self, ctx):

        status_question = await ctx.send(
            "React with :white_check_mark: to enable the default role, or with :x: to disable the default role.")
        await status_question.add_reaction("\U00002705")
        await status_question.add_reaction("\U0000274c")

        done, pending = await asyncio.wait([ctx.bot.wait_for('reaction_add',
                                                             check=self.bot.
                                                             checks.wait_for_reaction_check(ctx, status_question),
                                                             timeout=240),
                                            ctx.bot.wait_for('reaction_remove',
                                                             check=self.bot.
                                                             checks.wait_for_reaction_check(ctx, status_question),
                                                             timeout=240)],
                                           return_when=asyncio.FIRST_COMPLETED)
        try:
            reaction, user = done.pop().result()

            if str(reaction.emoji) == "\U00002705":
                config.updateDefaultRole(ctx.guild.id, True)
                await ctx.send(":white_check_mark: Enabled the default role.")

                await ctx.send(
                    ":information_source: What's the name of the role that every "
                    "new member should get once they join?")
                try:
                    role = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                   timeout=120)
                except (asyncio.TimeoutError, TimeoutError):
                    await ctx.send(":x: Aborted.")
                    pass

                if not role:
                    await ctx.send(":x: Aborted.")
                    return

                new_default_role = role.content

                try:
                    new_default_role_object = await commands.RoleConverter().convert(ctx, new_default_role)
                except Exception:
                    new_default_role_object = None

                if new_default_role_object is None:
                    await ctx.send(
                        f":information_source: Couldn't find a role named '{new_default_role}', creating new role...")
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError("create_role", new_default_role)

                else:
                    await ctx.send(
                        f":white_check_mark: I'll use the pre-existing role named "
                        f"'{new_default_role_object.name}' for the default role.")

                success = config.setDefaultRole(ctx.guild.id, new_default_role_object.name)

                if success:
                    await ctx.send(f":white_check_mark: Set the default role to '{new_default_role_object.name}'.")

            elif str(reaction.emoji) == "\U0000274c":
                config.updateDefaultRole(ctx.guild.id, False)
                await ctx.send(":white_check_mark: Disabled the default role.")

        except (asyncio.TimeoutError, TimeoutError):
            await ctx.send(":x: Aborted.")

        for future in pending:
            future.cancel()


def setup(bot):
    bot.add_cog(Guild(bot))
