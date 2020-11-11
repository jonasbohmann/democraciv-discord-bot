import asyncio
import discord
import typing

from discord.ext.commands import Context
from discord.ext import commands


class MockContext:
    def __init__(self, bot):
        self.bot = bot


class CustomContext(Context):

    @property
    def db(self):
        return self.bot.db

    def _wait_for_message_check(self):
        def check(message):
            return message.author == self.message.author and message.channel == self.message.channel

        return check

    def _wait_for_reaction_check(self, *, original_message: discord.Message):
        def check(reaction, user):
            return user == self.author and reaction.message.id == original_message.id

        return check

    def _wait_for_specific_emoji_reaction_check(self, *, original_message: discord.Message, emoji: str):
        def check(reaction, user):
            return user == self.author and reaction.message.id == original_message.id and str(reaction.emoji) == emoji

        return check

    async def choose(self, text=None, *, reactions, message: discord.Message = None, timeout: int = 300) -> (
            discord.Reaction,
            typing.Union[
                discord.User, discord.Member]):

        if text:
            message = await self.send(text)

        for reaction in reactions:
            await message.add_reaction(reaction)

        try:
            reaction, user = await self.bot.wait_for('reaction_add',
                                                     check=self._wait_for_reaction_check(original_message=message),
                                                     timeout=timeout)
            return reaction

        except asyncio.TimeoutError:
            await self.send(":zzz: You took too long to react.")
            return None

    async def ask_to_continue(self, *, message: discord.Message, emoji: str, timeout: int = 300):
        await message.add_reaction(emoji)

        try:
            await self.bot.wait_for('reaction_add',
                                    check=self._wait_for_specific_emoji_reaction_check(original_message=message,
                                                                                       emoji=emoji),
                                    timeout=timeout)
        except asyncio.TimeoutError:
            return False
        else:
            return True

    async def confirm(self, text=None, *, message: discord.Message = None, timeout: int = 300) -> typing.Optional[bool]:
        """Adds the :white_check_mark: and :x: emoji to the message and returns the reaction and user if either
           reaction has been added by the original user.

           Returns None if the user did nothing."""

        if text:
            message = await self.send(text)

        yes_emoji = "\U00002705"
        no_emoji = "\U0000274c"

        await message.add_reaction(yes_emoji)
        await message.add_reaction(no_emoji)

        try:
            reaction, user = await self.bot.wait_for('reaction_add',
                                                     check=self._wait_for_reaction_check(original_message=message),
                                                     timeout=timeout)
        except asyncio.TimeoutError:
            await self.send(":zzz: You took too long to react.")
            return None

        else:
            if reaction is None:
                return None

            if str(reaction.emoji) == yes_emoji:
                return True

            elif str(reaction.emoji) == no_emoji:
                await self.send("Aborted.")
                return False

    async def input(self, text=None, *, timeout: int = 300, delete_after: bool = False,
                    image_allowed: bool = False) -> \
            typing.Optional[str]:
        """Waits for a reply by the original user in the original channel and returns reply as string.

           Returns None if the user did nothing."""

        if text:
            await self.send(text)

        try:
            message = await self.bot.wait_for('message', check=self._wait_for_message_check(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.send(":zzz: You took too long to reply.")
            return

        if not message.content:
            if image_allowed and message.attachments and not message.content:
                return message.attachments[0].url

            await self.send(":x: You didn't reply with text.")
            return

        else:
            if delete_after:
                try:
                    await message.delete()
                except Exception:
                    pass

            return message.content

    async def ask_for_model(self, *, converter, timeout: int = 300):
        text = await self.input(timeout=timeout)

        if not text:
            return

        if hasattr(converter, "convert"):
            try:
                model = await converter().convert(self, text)
            except commands.BadArgument:
                return text
        else:
            # fallback
            return converter(text)

        return model if model else text
