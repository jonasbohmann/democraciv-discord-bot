import typing
from datetime import datetime

import discord

from discord.ext import commands
from discord.ext.commands import BadArgument

from util import law_helper
from util.exceptions import DemocracivBotException


class TagError(DemocracivBotException):
    pass


class Tag(commands.Converter):
    """
    Represents a Tag. Can be global or local.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup through global tags by alias
        2. Lookup through guild tags by alias

    """

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
    """
    Represents a Tag that the Context.author owns.
    """

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


class Session(commands.Converter):
    """
    Represents a session of the Legislature.

        The lookup strategy for the converter is as follows (in order):
            1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.is_active: bool = kwargs.get('is_active')
        self.status: law_helper.SessionStatus = kwargs.get('status')
        self.vote_form: str = kwargs.get('vote_form', None)
        self.opened_on: datetime = kwargs.get('opened_on')
        self.voting_started_on: datetime = kwargs.get('voting_started_on', None)
        self.closed_on: datetime = kwargs.get('closed_on', None)
        self._speaker: int = kwargs.get('speaker')
        self._bot = kwargs.get('bot')

    @property
    def speaker(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._speaker) or self._bot.get_user(self._speaker)
        return user

    @classmethod
    async def convert(cls, ctx, argument: str):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f":x: {argument} is not a number.")

        session = await ctx.bot.fetchrow("SELECT * FROM legislature_sessions WHERE id = $1", argument)

        if session is None:
            raise BadArgument(f":x: Couldn't find any session with ID #{argument}")

        return cls(id=session['id'], is_active=session['is_active'], status=session['status'],
                   vote_form=session['vote_form'], opened_on=session['start_unixtime'],
                   voting_started_on=session['voting_start_unixtime'], closed_on=session['end_unixtime'],
                   speaker=session['speaker'], bot=ctx.bot)


class Bill(commands.Converter):
    """
    Represents a bill that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
        2. Lookup by bill name (Google Docs Title).
        3. Lookup by Google Docs URL.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.name: str = kwargs.get('name')
        self.session: Session = kwargs.get('session')
        self.link: str = kwargs.get('link')
        self.tiny_link: str = kwargs.get('tiny_link')
        self.description: str = kwargs.get('description')
        self.is_vetoable: bool = kwargs.get('is_vetoable')
        self.voted_on_by_leg: bool = kwargs.get('voted_on_by_leg')
        self.passed_leg: bool = kwargs.get('passed_leg')
        self.voted_on_by_ministry: bool = kwargs.get('voted_on_by_ministry')
        self.passed_ministry: bool = kwargs.get('passed_ministry')
        self._submitter: int = kwargs.get('submitter')
        self._bot = kwargs.get('bot')

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @classmethod
    async def convert(cls, ctx, argument: str):
        try:
            argument = int(argument)
            bill = await ctx.bot.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", argument)
        except ValueError:
            bill = await ctx.bot.fetchrow("SELECT * FROM legislature_bills WHERE bill_name = $1", argument)
            if bill is None:
                bill = await ctx.bot.fetchrow("SELECT * FROM legislature_bills WHERE link = $1", argument)

        if bill is None:
            raise BadArgument(f":x: Couldn't find any bill that matches {argument}.")

        session = await Session.convert(ctx, bill['leg_session'])

        return cls(id=bill['id'], name=bill['name'], link=bill['link'], tiny_link=bill['tiny_link'],
                   description=bill['description'], is_vetoable=bill['is_vetoable'],
                   voted_on_by_leg=bill['voted_on_by_leg'], passed_leg=bill['passed_leg'],
                   voted_on_by_ministry=bill['voted_on_by_ministry'], passed_ministry=bill['passed_ministry'],
                   session=session, submitter=['submitter'], bot=ctx.bot)


class Law(commands.Converter):
    """
    Represents a law that was either passed by just the Legislature or by both the Legislature and the Ministry.
    A law has always a bill associated with it.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.bill: Bill = kwargs.get('bill')
        self.tags: typing.List[str] = kwargs.get('tags')

    @classmethod
    async def convert(cls, ctx, argument: str):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f":x: {argument} is not a number.")

        law = await ctx.bot.fetchrow("SELECT * FROM legislature_laws WHERE id = $1", argument)

        if law is None:
            raise BadArgument(f":x: Couldn't find any law with ID #{argument}")

        bill = Bill.convert(ctx, law['bill_id'])

        if bill is None:
            raise BadArgument()

        tags = await ctx.bot.fetch("SELECT * FROM legislature_tags WHERE id = $1", law['id'])
        tags = [record['tag'] for record in tags]

        return cls(id=law['id'], bill=bill, tags=tags)
