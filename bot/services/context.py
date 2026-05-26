import typing

import discord


class CommandContextProtocol(typing.Protocol):
    bot: typing.Any
    guild: typing.Optional[discord.Guild]
    channel: typing.Optional[discord.abc.Messageable]
    author: typing.Union[discord.Member, discord.User]

    @property
    def db(self) -> typing.Any: ...

    @property
    def guild_icon(self) -> typing.Optional[str]: ...

    @property
    def author_icon(self) -> typing.Optional[str]: ...

    @property
    def is_slash(self) -> bool: ...
