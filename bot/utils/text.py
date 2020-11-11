import datetime
import typing
import discord
from discord.ext import tasks

from bot.config import config, mk
from bot.utils.converter import Bill, Law, Session


def split_string(string: str, length: int):
    return list((string[0 + i:length + i] for i in range(0, len(string), length)))


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

        split_into_length[index] = split_into_length[index] + ''.join(paragraph)

        if (len(''.join(split_into_length[index]))) > length:
            index += 1

    return split_into_length


class AnnouncementScheduler:
    def __init__(self, bot, channel):
        self.bot = bot
        self._channel: mk.DemocracivChannel = channel
        self._objects: typing.List[typing.Union[Bill, Law, Session]] = []
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

            split_into_2000[index] = split_into_2000[index] + ''.join(paragraph)

            if (len(''.join(split_into_2000[index]))) > 1900:
                index += 1

        return list(split_into_2000.values())

    def add(self, obj: typing.Union[Bill, Law, Session]):
        if len(self._objects) == 0:
            self._task = copy.copy(self._wait)
            self._task.start()

        self._objects.append(obj)
        self._last_addition = datetime.datetime.utcnow()

    async def send_messages(self):
        message = self.get_message()

        if len(message) > 2000:
            split_messages = self.split_message(message)
            for msg in split_messages:
                await self.channel.send(msg)
        else:
            await self.channel.send(message)
        self._objects.clear()
        self._task.cancel()

    @tasks.loop(seconds=30)
    async def _wait(self):
        if self._last_addition is not None and \
                datetime.datetime.utcnow() - self._last_addition > datetime.timedelta(minutes=10):
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
            self.description = f"{self.description[:2045]}..."

        if len(self.title) > 256:
            self.title = f"{self.title[:253]}..."

    def add_field(self, *, name: typing.Any, value: typing.Any, inline: bool = True):
        field_index = len(self.fields)
        name = str(name)
        value = str(value)

        if len(value) > 1024:
            fields = split_string_by_paragraphs(value, 924)

            for index in fields:
                if index == 0:
                    super().add_field(name=name, value=fields[index], inline=inline)
                else:
                    super().add_field(name=f"{name} (Cont.)", value=fields[index], inline=inline)
        else:
            super().add_field(name=name, value=value, inline=inline)

        if len(self) > 6000 or len(self.fields) > 25:
            for _ in self.fields:
                self.remove_field(field_index)

            super().add_field(name=name, value="*Too long to display.*", inline=inline)
