import textwrap
import typing
import discord
import functools

from bot.utils import exceptions
from bot.config import config, mk
from discord.ext import commands


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


def is_democraciv_guild():
    """Commands check decorator to check if a command was invoked on the Democraciv guild"""

    def check(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        return True

    return commands.check(check)


def has_democraciv_role(role: mk.DemocracivRole):
    """Commands check decorator to check if a command was invoked on the Democraciv guild AND to check whether the
        person has the specified role from utils.py"""

    def predicate(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        found = discord.utils.get(ctx.author.roles, id=role.value)

        if found is None:
            raise commands.MissingRole(role.printable_name)

        return True

    return commands.check(predicate)


def has_any_democraciv_role(*roles: mk.DemocracivRole):
    """Commands check decorator to check if a command was invoked on the Democraciv guild AND to check whether the
    person has any of the specified roles from utils.py"""

    def predicate(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        getter = functools.partial(discord.utils.get, ctx.author.roles)
        if any(getter(id=role.value) is not None for role in roles):
            return True
        raise commands.MissingAnyRole(roles)

    return commands.check(predicate)


def tag_check():
    """Check to see if tag creation is allowed by everyone or just Administrators."""

    async def check(ctx):
        is_allowed = await ctx.bot.is_tag_creation_allowed(ctx.guild.id)

        if is_allowed:
            return True
        else:
            if ctx.author.guild_permissions.administrator:
                return True
            else:
                raise exceptions.TagCheckError(message=":x: Only Administrators can add or remove tags on this server."
                                                       " Administrators can change this setting in "
                                                       f"`{config.BOT_PREFIX}server tagcreation`.")

    return commands.check(check)


class SafeEmbed(discord.Embed):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.colour:
            self.colour = config.BOT_EMBED_COLOUR

    def clean(self):
        # called by monkey patched Messageable.send

        if self.description:
            self.description = textwrap.shorten(self.description, width=2048, placeholder="...",
                                                drop_whitespace=False, replace_whitespace=False)

        if self.title:
            self.title = textwrap.shorten(self.title, width=256, placeholder="...",
                                          drop_whitespace=False, replace_whitespace=False)

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
