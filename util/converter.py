import typing
import discord

from discord.ext import commands
from discord.ext.commands import BadArgument

from util.exceptions import DemocracivBotException


class TagError(DemocracivBotException):
    pass


class Tag(commands.Converter):
    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.name: str = kwargs.get('name')
        self.title: str = kwargs.get('title')
        self.content: str = kwargs.get('content')
        self.is_global: bool = kwargs.get('_global')
        self.uses: int = kwargs.get('uses')
        self.aliases: typing.List[str] = kwargs.get('aliases')
        self._author: int = kwargs.get('author', None)
        self._guild: int = kwargs.get('guild')
        self._bot = kwargs.get('bot')

    @property
    def guild(self) -> discord.Guild:
        return self._bot.get_guild(self._guild)

    @property
    def author(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self.guild.get_member(self._author) or self._bot.get_user(self._author) or None
        return user

    @property
    def clean_content(self) -> str:
        return discord.utils.escape_mentions(self.content)

    @classmethod
    async def convert(cls, ctx, argument: str):
        tag_id = await ctx.bot.db.fetchval("SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
                                           argument.lower())

        if tag_id is None:
            tag_id = await ctx.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE alias = $1 AND guild_id = $2",
                argument.lower(), ctx.guild.id)

        if tag_id is None:
            raise TagError(f":x: There is no global or local tag named `{argument}`!")

        tag_details = await ctx.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        aliases = await ctx.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1", tag_id)
        aliases = [record['alias'] for record in aliases]

        return cls(id=tag_details['id'], name=tag_details['name'], title=tag_details['title'],
                   content=tag_details['content'], _global=tag_details['global'], uses=tag_details['uses'],
                   bot=ctx.bot, guild=tag_details['guild_id'], author=tag_details['author'], aliases=aliases)


class OwnedTag(Tag):

    def __init__(self, **kwargs):
        self.invoked_with: str = kwargs.get("invoked_with")
        super().__init__(**kwargs)

    @classmethod
    async def convert(cls, ctx, argument: str):
        tag_id = await ctx.bot.db.fetchval("SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
                                           argument.lower())

        if tag_id is None:
            tag_id = await ctx.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE alias = $1 AND guild_id = $2",
                argument.lower(), ctx.guild.id)

        if tag_id is None:
            raise TagError(f":x: There is no global or local tag named `{argument}`!")

        tag_details = await ctx.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        if tag_details['global'] and tag_details['guild_id'] != ctx.guild.id:
            raise TagError(f":x: Global tags can only be edited or removed on "
                           f"the guild they were originally created on!")

        if tag_details['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
            raise TagError(f":x: This isn't your tag!")

        aliases = await ctx.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1", tag_id)
        aliases = [record['alias'] for record in aliases]

        return cls(id=tag_details['id'], name=tag_details['name'], title=tag_details['title'],
                   content=tag_details['content'], _global=tag_details['global'], uses=tag_details['uses'],
                   bot=ctx.bot, guild=tag_details['guild_id'], author=tag_details['author'], aliases=aliases,
                   invoked_with=argument.lower())
