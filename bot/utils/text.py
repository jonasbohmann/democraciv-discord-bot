import collections
import copy
import datetime
import typing
import discord

from discord.ext import tasks, menus
from bot.config import config, mk
from bot.utils import models


def split_string(string: str, length: int):
    return list((string[0 + i: length + i] for i in range(0, len(string), length)))


# todo fix this shit


def split_string_by_paragraphs(string: str, length: int):
    lines = string.splitlines(keepends=True)
    split_into_length = dict()
    index = 0

    for paragraph in lines:
        if len(paragraph) > length:
            paragraph = split_string(paragraph, length)
        try:
            split_into_length[index]
        except KeyError:
            split_into_length[index] = ""

        split_into_length[index] = split_into_length[index] + "".join(paragraph)

        if (len("".join(split_into_length[index]))) > length:
            index += 1

    return split_into_length


class AnnouncementScheduler:
    def __init__(self, bot, channel):
        self.bot = bot
        self._channel: mk.DemocracivChannel = channel
        self._objects: typing.List[typing.Union[models.Bill, models.Law]] = []
        self._last_addition = None
        self._task = None

    def __del__(self):
        if self._task is not None:
            self._task.cancel()

    @property
    def channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.get_democraciv_channel(self._channel)

    def get_message(self) -> str:
        raise NotImplementedError()

    def split_message(self, message: str) -> typing.List[str]:
        lines = message.splitlines(keepends=True)
        split_into_2000 = dict()
        index = 0

        for paragraph in lines:
            try:
                split_into_2000[index]
            except KeyError:
                split_into_2000[index] = ""

            split_into_2000[index] = split_into_2000[index] + "".join(paragraph)

            if (len("".join(split_into_2000[index]))) > 1900:
                index += 1

        return list(split_into_2000.values())

    def add(self, obj: models.Bill):
        if len(self._objects) == 0:
            self._task = copy.copy(self._wait)
            self._task.start()

        self._objects.append(obj)
        self._last_addition = datetime.datetime.utcnow()

    async def send_messages(self):
        message = self.get_message()
        await self.channel.send(message, allowed_mentions=discord.AllowedMentions(roles=True))
        self._objects.clear()
        self._task.cancel()

    @tasks.loop(seconds=30)
    async def _wait(self):
        if self._last_addition is not None and datetime.datetime.utcnow() - self._last_addition > datetime.timedelta(
                minutes=5
        ):
            self._last_addition = None
            await self.send_messages()


class SafeEmbed(discord.Embed):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.colour:
            self.colour = config.BOT_EMBED_COLOUR

    def clean(self):
        # called by monkey patched Messageable.send

        if len(self.description) > 2048:
            self.description = f"{self.description[:2040]}..."

        if len(self.title) > 256:
            self.title = f"{self.title[:250]}..."

    def add_field(
            self,
            *,
            name: typing.Any,
            value: typing.Any,
            inline: bool = True,
            too_long_value: str = "*Too long to display.*",
    ):
        field_index = len(self.fields)
        name = str(name)
        value = str(value)

        if len(value) > 1024:
            fields = split_string_by_paragraphs(value, 924)

            for index in fields:
                if index == 0:
                    super().add_field(name=name, value=fields[index], inline=inline)
                else:
                    super().add_field(name=f"{name} (Cont.)", value=fields[index], inline=False)
        else:
            super().add_field(name=name, value=value, inline=inline)

        if len(self) > 6000 or len(self.fields) > 25:
            for _ in self.fields:
                self.remove_field(field_index)

            super().add_field(name=name, value=too_long_value, inline=inline)


class FuzzyChoose(menus.Menu):
    def __init__(self, question: str, choices: typing.Iterable):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.question = question
        self.choices = choices
        self.result = None
        self._mapping = {}

        for i, choice in enumerate(choices, start=1):
            emoji = f"{i}\N{variation selector-16}\N{combining enclosing keycap}"
            button = menus.Button(emoji=emoji, action=self.on_button)
            self.add_button(button=button)
            self._mapping[emoji] = choice

        cancel = menus.Button(emoji=config.NO, action=self.cancel)
        self.add_button(button=cancel)

    async def send_initial_message(self, ctx, channel):
        embed = SafeEmbed(title=f"{config.USER_INTERACTION_REQUIRED}  {self.question}")

        fmt = [f"Click {config.NO} to cancel.\n"]

        for emoji, choice in self._mapping.items():
            fmt.append(f"{emoji}  {choice}")

        fmt = "\n".join(fmt)

        embed.description = fmt
        return await ctx.send(embed=embed)

    async def on_button(self, payload):
        self.result = self._mapping[str(payload.emoji)]
        self.stop()

    async def cancel(self, payload):
        self.result = None
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


EditModelResult = collections.namedtuple("EditModelResult", ["confirmed", "choices"])


class EditModelMenu(menus.Menu):
    def __init__(self, choices_with_formatted_explanation: typing.Dict[str, str], *,
                 title=f"{config.USER_INTERACTION_REQUIRED}  What do you want to edit?"):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.choices = choices_with_formatted_explanation
        self.title = title
        self._confirmed = False
        self._result = {choice: False for choice in self.choices.keys()}
        self._mapping = {}
        self._make_result()

        for i, choice in enumerate(self.choices.keys(), start=1):
            emoji = f"{i}\N{variation selector-16}\N{combining enclosing keycap}"
            button = menus.Button(emoji=emoji, action=self.on_button)
            self.add_button(button=button)
            self._mapping[emoji] = choice

        confirm = menus.Button(emoji=config.YES, action=self.confirm)
        self.add_button(confirm)

        cancel = menus.Button(emoji=config.NO, action=self.cancel)
        self.add_button(cancel)

    def _make_result(self):
        self.result = EditModelResult(confirmed=self._confirmed, choices=self._result)
        return self.result

    async def send_initial_message(self, ctx, channel):
        embed = SafeEmbed(title=self.title)

        fmt = [f"Select as many things as you want, then click the {config.YES} button to continue, "
               f"or {config.NO} to cancel.\n"]

        for emoji, choice in self._mapping.items():
            fmt.append(f"{emoji}  {self.choices[choice]}")

        fmt = "\n".join(fmt)
        embed.description = fmt
        return await ctx.send(embed=embed)

    async def on_button(self, payload):
        choice = self._mapping[str(payload.emoji)]
        self._result[choice] = not self._result[choice]

    async def confirm(self, payload):
        self._confirmed = True
        self._make_result()
        self.stop()

    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result
