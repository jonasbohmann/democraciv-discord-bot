import dataclasses
import typing

import discord


@dataclasses.dataclass
class OperationResult:
    message: typing.Optional[str] = None
    embed: typing.Optional[discord.Embed] = None


@dataclasses.dataclass
class PageResult:
    entries: typing.Sequence[str]
    title: typing.Optional[str] = None
    author: typing.Optional[str] = None
    icon: typing.Optional[str] = None
    empty_message: str = "*No entries.*"
    per_page: typing.Optional[int] = None
