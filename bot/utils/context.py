import bot  # for type hint: https://www.python.org/dev/peps/pep-0484/#forward-references
import asyncio
import inspect
import discord
import typing

from discord.ext import commands
from bot.config import config
from utils import exceptions


class MockContext:
    """
    Mainly used when manually using the converter in bot.utils.converter, i.e. not as type hints in command arguments.

    Attributes
    ----------

     bot: DemocracivBot
        The bot instance
    """

    def __init__(self, bot):
        self.bot = bot


class CustomCog(commands.Cog):
    """
    Subclass of commands.Cog to allow the use of MarkConfig in the cog's description docstring, as well as in the
    docstrings of all of its commands. Makes the transition between marks easier.

    The standard command cooldown is also applied on every command in this cog.


    Attributes
    ----------

     hidden: bool
        Whether to hide this cog in -help and -commands

    """
    hidden = False

    def __init__(self, bot):
        self.bot: 'bot.DemocracivBot' = bot
        self.bot.loop.create_task(self._transform_description())
        self._bot_is_ready = False

        for command in self.walk_commands():
            if command.help:
                self.bot.loop.create_task(self._transform_command_help(command))

            if not command._buckets._cooldown:
                cooldown_deco = commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
                cooldown_deco(command)

    async def _transform_description(self):
        if not self._bot_is_ready:
            await self.bot.wait_until_ready()
            self._bot_is_ready = True

        doc = inspect.getdoc(self)
        if doc is not None:
            cleaned = doc.format_map(self.bot.mk.to_dict())
            self.__cog_cleaned_doc__ = cleaned

    async def _transform_command_help(self, command: commands.Command):
        if not self._bot_is_ready:
            await self.bot.wait_until_ready()
            self._bot_is_ready = True

        format_mapping = self.bot.mk.to_dict()
        format_mapping['COMMAND'] = command.qualified_name
        format_mapping['PREFIX'] = config.BOT_PREFIX
        command.help = command.help.format_map(format_mapping)


class CustomContext(commands.Context):

    def __init__(self, **attrs):
        self.bot: 'bot.DemocracivBot' = attrs.get('bot')  # for typing
        super().__init__(**attrs)

    @property
    def db(self):
        return self.bot.db

    @property
    def guild_icon(self):
        if self.guild:
            return self.guild.icon_url_as(static_format="png")

    @property
    def author_icon(self):
        return self.author.icon_url_as(static_format="png")

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

    async def choose(self, text=None, *, reactions: typing.Iterable[typing.Any], message: discord.Message = None,
                     timeout: int = 300) -> (
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
            raise exceptions.InvalidUserInputError(":zzz: You took too long to reply.")

        if not message.content:
            if image_allowed and message.attachments and not message.content:
                return message.attachments[0].url

            raise exceptions.InvalidUserInputError(":x: You didn't reply with text.")

        else:
            if delete_after:
                try:
                    await message.delete()
                except Exception:
                    pass

            return message.content

    async def converted_input(self, text=None, *, converter, timeout: int = 300, return_input_on_fail: bool = True):
        if text:
            await self.send(text)

        message = await self.input(timeout=timeout)

        if hasattr(converter, "convert"):
            try:
                return await converter().convert(self, message)
            except commands.BadArgument:
                if return_input_on_fail:
                    return message
                raise exceptions.InvalidUserInputError(":x: Something went wrong while converting your input. "
                                                       "Are you sure it was right?")
        else:
            # fallback
            return converter(message)
