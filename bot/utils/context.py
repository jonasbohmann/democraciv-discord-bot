import bot  # for type hint: https://www.python.org/dev/peps/pep-0484/#forward-references
import asyncio
import inspect
import discord
import typing

from discord.ext import commands
from bot.config import config
from bot.utils import exceptions
from bot.utils.text import PromptView


class MockContext:
    """
    Mainly used when manually using the converter in bot.utils.converter, i.e. not as type hints in command arguments.

    Attributes
    ----------

     bot: DemocracivBot
        The bot instance
    """

    def __init__(self, bot: "bot.DemocracivBot", *, guild=None):
        self.bot = bot
        self.guild = guild


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

    def __init__(self, _bot):
        self.bot: "bot.DemocracivBot" = _bot
        self.bot.loop.create_task(self._transform_description())

        for command in self.walk_commands():
            if command.help:
                self.bot.loop.create_task(self._transform_command_help(command))

            if not command._buckets._cooldown:
                cooldown_deco = commands.cooldown(
                    1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user
                )
                cooldown_deco(command)

    async def _transform_description(self):
        await self.bot.wait_until_ready()

        doc = inspect.getdoc(self)
        if doc is not None:
            cleaned = doc.format_map(self.bot.mk.to_dict())
            self.description = cleaned

    async def _transform_command_help(self, command: commands.Command):
        await self.bot.wait_until_ready()

        format_mapping = self.bot.mk.to_dict()
        format_mapping["COMMAND"] = command.qualified_name
        format_mapping["PREFIX"] = config.BOT_PREFIX
        command.help = command.help.format_map(format_mapping)


class CustomContext(commands.Context):
    def __init__(self, **attrs):
        self.bot: "bot.DemocracivBot" = attrs.get("bot")  # for typing
        super().__init__(**attrs)

    @property
    def db(self):
        return self.bot.db

    @property
    def guild_icon(self):
        if self.guild:
            return self.guild.icon.url

    @property
    def author_icon(self):
        return self.author.display_avatar.url

    def _wait_for_message_check(self):
        def check(message):
            return (
                message.author == self.message.author
                and message.channel == self.message.channel
            )

        return check

    def _wait_for_reaction_check(self, *, original_message: discord.Message):
        def check(reaction, user):
            return user == self.author and reaction.message.id == original_message.id

        return check

    def _wait_for_specific_emoji_reaction_check(
        self, *, original_message: discord.Message, emoji: str
    ):
        def check(reaction, user):
            return (
                user == self.author
                and reaction.message.id == original_message.id
                and str(reaction.emoji) == emoji
            )

        return check

    async def choose(
        self,
        text=None,
        *,
        reactions: typing.Iterable[typing.Any],
        message: discord.Message = None,
        timeout: int = 300,
    ) -> discord.Reaction:

        if text:
            message = await self.send(text)

        for reaction in reactions:
            await message.add_reaction(reaction)

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add",
                check=self._wait_for_reaction_check(original_message=message),
                timeout=timeout,
            )
            return reaction

        except asyncio.TimeoutError:
            raise exceptions.InvalidUserInputError(":zzz: You took too long to react.")

    async def ask_to_continue(
        self,
        *,
        message: discord.Message,
        emoji: str = None,
        timeout: int = 300,
        label=None,
    ) -> bool:
        class ContinueView(PromptView):
            @discord.ui.button(label=label, emoji=emoji)
            async def btn(self, button, interaction):
                self.result = True
                self.stop()

        view = ContinueView(self, timeout=timeout)
        await message.edit(view=view)
        result = await view.prompt(silent=True)

        return bool(result)

    async def confirm(
        self, text: str = None, *, message: discord.Message = None, timeout=300
    ) -> bool:
        """Adds the {config.YES} and {config.NO} emoji to the message and returns the reaction and user if either
        reaction has been added by the original user.

        Returns None if the user did nothing."""

        class ConfirmView(PromptView):
            @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
            async def yes(self, *args, **kwargs):
                self.result = True
                self.stop()

            @discord.ui.button(label="No", style=discord.ButtonStyle.red)
            async def no(self, *args, **kwargs):
                self.result = False
                self.stop()

        view = ConfirmView(self, timeout=timeout)

        if text:
            message = await self.send(text, view=view)

        if message:
            await message.edit(view=view)

        result = await view.prompt()
        return bool(result)

    async def send_with_timed_delete(self, content=None, *, embed=None, timeout=200):
        message = await self.send(content=content, embed=embed)
        should_delete = await self.ask_to_continue(
            message=message,
            emoji="\U0001f5d1",
            timeout=timeout,
            label="Delete this Message",
        )

        if should_delete:
            await message.delete()
        else:
            await message.remove_reaction(emoji="\U0001f5d1", member=self.guild.me)

    async def input(
        self,
        text=None,
        *,
        timeout: int = 300,
        delete_after: bool = False,
        image_allowed: bool = False,
        return_cleaned: bool = False,
    ) -> str:
        """Waits for a reply by the original user in the original channel and returns reply as string.

        Returns None if the user did nothing.
        :rtype: object"""

        if text:
            await self.send(text)

        try:
            message = await self.bot.wait_for(
                "message", check=self._wait_for_message_check(), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise exceptions.InvalidUserInputError(":zzz: You took too long to reply.")

        if image_allowed and message.attachments:
            return message.attachments[0].url

        if not message.content:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You didn't reply with text."
            )

        else:
            if delete_after:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

            return message.clean_content if return_cleaned else message.content

    async def converted_input(
        self,
        text=None,
        *,
        converter,
        timeout: int = 300,
        return_input_on_fail: bool = True,
    ):
        if text:
            await self.send(text)

        message = await self.input(timeout=timeout)

        if hasattr(converter, "convert"):
            try:
                return await converter().convert(self, message)
            except commands.BadArgument:
                if return_input_on_fail:
                    return message
                if hasattr(converter, "model"):
                    error_msg = (
                        f"{config.NO} Something went wrong while converting your input "
                        f"into a {converter.model}. Are you sure it was right and that "
                        f"the {converter.model} exists?"
                    )
                else:
                    error_msg = f"{config.NO} Something went wrong while converting your input. Are you sure it was right?"

                raise exceptions.InvalidUserInputError(error_msg)
        else:
            # fallback
            return converter(message)


class MockUser:
    id = 0
    discriminator = "0000"
    name = mention = display_name = "Unknown Person"

    def __str__(self):
        return self.name

    async def send(self, *args, **kwargs):
        pass
