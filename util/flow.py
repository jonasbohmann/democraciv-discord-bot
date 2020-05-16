import typing
import asyncio
import discord

from discord.ext import commands

from config import config


class Flow:
    """The Flow class helps with user input that require the bot to wait for replies or reactions."""

    def __init__(self, bot, ctx):
        self.bot = bot
        self.ctx = ctx

    async def get_emoji_choice(self, yes_emoji: str, no_emoji: str,
                               message: discord.Message, timeout: int) -> (discord.Reaction,
                                                                           typing.Union[discord.User, discord.Member]):
        """Adds the two specified emoji to the message and returns which one has been clicked by the
           original user in the specified time"""

        await message.add_reaction(yes_emoji)
        await message.add_reaction(no_emoji)

        try:
            reaction, user = await self.ctx.bot.wait_for('reaction_add',
                                                         check=self.bot.checks.wait_for_reaction_check(self.ctx,
                                                                                                       message),
                                                         timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to react.")
            return None, None

        else:
            return reaction, user

    async def gear_reaction_confirm(self, message: discord.Message, timeout: int) -> bool:
        """Adds the :gear: emoji to the message and returns whether it has been clicked by the
           original user in the specified time"""

        return await self.get_continue_confirm(message, config.GUILD_SETTINGS_GEAR, timeout)

    async def get_continue_confirm(self, message: discord.Message, emoji, timeout: int):
        await message.add_reaction(emoji)

        try:
            await self.ctx.bot.wait_for('reaction_add',
                                        check=self.bot.checks.wait_for_specific_emoji_reaction_check(self.ctx, message, emoji),
                                        timeout=timeout)

        except asyncio.TimeoutError:
            return False

        else:
            return True

    async def get_yes_no_reaction_confirm(self, message: discord.Message, timeout: int) -> typing.Optional[bool]:
        """Adds the :white_check_mark: and :x: emoji to the message and returns the reaction and user if either
           reaction has been added by the original user.

           Returns None if the user did nothing."""

        yes_emoji = "\U00002705"
        no_emoji = "\U0000274c"

        await message.add_reaction(yes_emoji)
        await message.add_reaction(no_emoji)

        try:
            reaction, user = await self.ctx.bot.wait_for('reaction_add',
                                                         check=self.bot.checks.wait_for_reaction_check(self.ctx,
                                                                                                       message),
                                                         timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to react.")
            return None

        else:
            if reaction is None:
                return None

            if str(reaction.emoji) == yes_emoji:
                return True

            elif str(reaction.emoji) == no_emoji:
                return False

    async def get_new_channel(self, timeout: int) -> typing.Union[discord.TextChannel, str, None]:
        """Waits for a reply by the original user in the original channel and coverts reply to a channel object
           reaction has been added by the original user.

           Returns None if the user did nothing.

           Returns user reply as string if conversion to channel object failed."""

        try:
            channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(self.ctx),
                                              timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to reply.")
            return None

        if not channel.content:
            await self.ctx.send(":x: You didn't reply with text.")
            return None

        try:
            channel_object = await commands.TextChannelConverter().convert(self.ctx, channel.content)
        except commands.BadArgument:
            return channel.content

        if not channel_object:
            return channel.content

        return channel_object

    async def get_text_input(self, timeout: int) -> typing.Optional[str]:
        """Waits for a reply by the original user in the original channel and returns reply as string.

           Returns None if the user did nothing."""

        try:
            text = await self.bot.wait_for('message',
                                           check=self.bot.checks.wait_for_message_check(self.ctx),
                                           timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to reply.")
            return None

        if not text.content:
            await self.ctx.send(":x: You didn't reply with text.")
            return None

        else:
            return text.content

    async def get_private_text_input(self, timeout: int) -> typing.Optional[str]:
        """Waits for a reply by the original user in the original channel and returns reply as string.

           Returns None if the user did nothing.

           Also deletes the original message."""

        try:
            text = await self.bot.wait_for('message',
                                           check=self.bot.checks.wait_for_message_check(self.ctx),
                                           timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to reply.")
            return None

        if not text.content:
            await self.ctx.send(":x: You didn't reply with text.")
            return None

        else:
            try:
                await text.delete()
            except Exception:
                pass

            return text.content

    async def get_tag_content(self, timeout: int) -> typing.Optional[str]:
        """Waits for a reply by the original user in the original channel and returns reply as string.

           Returns None if the user did nothing.

           Uploaded images are allowed."""

        try:
            message = await self.bot.wait_for('message',
                                              check=self.bot.checks.wait_for_message_check(self.ctx),
                                              timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to reply.")
            return None

        if not message.content:
            if message.attachments:
                return message.attachments[0].url
        else:
            return message.content

    async def get_new_role(self, timeout: int) -> typing.Union[discord.Role, str, None]:
        """Waits for a reply by the original user in the original channel and coverts reply to a role object
           reaction has been added by the original user.

           Returns None if the user did nothing.

           Returns user reply as string if conversion to role object failed."""

        try:
            role = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(self.ctx),
                                           timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":zzz: You took too long to reply.")
            return None

        if not role.content:
            await self.ctx.send(":x: You didn't reply with text.")
            return None

        try:
            role_object = await commands.RoleConverter().convert(self.ctx, role.content)
        except commands.BadArgument:
            role_object = role.content

        if not role_object:
            return role.content

        return role_object
