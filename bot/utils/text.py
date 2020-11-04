import typing
import discord
from bot.config import config


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
