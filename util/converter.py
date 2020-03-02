import enum
import typing
import discord

from datetime import datetime
from discord.ext import commands
from discord.ext.commands import BadArgument
from util.exceptions import DemocracivBotException, TagError, NotFoundError, PartyNotFoundError


class SessionStatus(enum.Enum):
    SUBMISSION_PERIOD = "Submission Period"
    VOTING_PERIOD = "Voting Period"
    CLOSED = "Closed"

    @staticmethod
    def from_str(label: str):
        if label.lower() == 'submission period':
            return SessionStatus.SUBMISSION_PERIOD
        elif label.lower() == 'voting period':
            return SessionStatus.VOTING_PERIOD
        elif label.lower() == 'closed':
            return SessionStatus.CLOSED
        else:
            raise NotImplementedError


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
        self.status: SessionStatus = kwargs.get('status')
        self.vote_form: str = kwargs.get('vote_form', None)
        self.opened_on: datetime = kwargs.get('opened_on')
        self.voting_started_on: datetime = kwargs.get('voting_started_on', None)
        self.closed_on: datetime = kwargs.get('closed_on', None)
        self.bills: typing.List[int] = kwargs.get('bills')
        self.motions: typing.List[int] = kwargs.get('motions')
        self._speaker: int = kwargs.get('speaker')
        self._bot = kwargs.get('bot')

    @property
    def speaker(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._speaker) or self._bot.get_user(self._speaker)
        return user

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, str):
            if argument.lower() == "all":
                return argument

        elif isinstance(argument, int):
            session = await ctx.bot.db.fetchrow("SELECT * FROM legislature_sessions WHERE id = $1", argument)

            if session is None:
                raise NotFoundError(f":x: There is no session with ID #{argument}!")

            bills = await ctx.bot.db.fetch("SELECT id FROM legislature_bills WHERE leg_session = $1", session['id'])
            bills = sorted([record['id'] for record in bills])

            motions = await ctx.bot.db.fetch("SELECT id FROM legislature_motions WHERE leg_session = $1", session['id'])
            motions = sorted([record['id'] for record in motions])

            return cls(id=session['id'], is_active=session['is_active'],
                       status=SessionStatus.from_str(session['status']),
                       vote_form=session['vote_form'], opened_on=session['opened_on'],
                       voting_started_on=session['voting_started_on'], closed_on=session['closed_on'],
                       speaker=session['speaker'], bills=bills, motions=motions, bot=ctx.bot)
        else:
            raise BadArgument(f":x: {argument} is neither a number nor 'all'.")


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

    async def is_law(self) -> bool:
        found = await self._bot.db.fetchval("SELECT law_id FROM legislature_laws WHERE bill_id = $1", self.id)

        if found:
            return True
        else:
            return False

    async def get_emojified_status(self, verbose: bool = True) -> str:
        status = []

        if not self.voted_on_by_leg:
            if verbose:
                return """Legislature: <:yellow:660562049817903116> *(Not Voted On Yet)*
                          Ministry:    <:yellow:660562049817903116> *(Not Voted On Yet)*
                          Law:         <:gray:660562063122497569>"""
            return "<:yellow:660562049817903116><:yellow:660562049817903116><:gray:660562063122497569>"
        else:
            if self.passed_leg:
                if verbose:
                    status.append("Legislature: <:green:660562089298886656> *(Passed)*")
                else:
                    status.append("<:green:660562089298886656>")

                if self.is_vetoable:
                    if not self.voted_on_by_ministry:
                        if verbose:
                            status.append("Ministry: <:yellow:660562049817903116> *(Not Voted On Yet)*")
                        else:
                            status.append("<:yellow:660562049817903116>")
                    else:
                        if self.passed_ministry:
                            if verbose:
                                status.append("Ministry: <:green:660562089298886656> *(Passed)*")
                            else:
                                status.append("<:green:660562089298886656>")
                        else:
                            if verbose:
                                status.append("Ministry: <:red:660562078217797647> *(Failed)*")
                            else:
                                status.append("<:red:660562078217797647>")
                else:
                    if verbose:
                        status.append("Ministry: <:gray:660562063122497569> *(Not Vetoable)*")
                    else:
                        status.append("<:gray:660562063122497569>")

                is_law = await self.is_law()

                if is_law:
                    if verbose:
                        status.append("Law: <:green:660562089298886656> *(Active Law)*")
                    else:
                        status.append("<:green:660562089298886656>")
                elif not is_law and ((self.is_vetoable and self.passed_leg and self.passed_ministry) or
                                     (not self.is_vetoable and self.passed_leg)):
                    if verbose:
                        status.append("Law: <:red:660562078217797647> *(Repealed)*")
                    else:
                        status.append("<:red:660562078217797647>")  # Repealed
            else:
                if verbose:
                    return """Legislature: <:red:660562078217797647> *(Failed)*
                              Ministry:    <:gray:660562063122497569> *(Failed in Legislature)*
                              Law:         <:gray:660562063122497569>"""
                return "<:red:660562078217797647><:gray:660562063122497569><:gray:660562063122497569>"

        if verbose:
            return '\n'.join(status)
        else:
            return ''.join(status)

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        try:
            argument = int(argument)
            bill = await ctx.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", argument)
        except ValueError:
            bill = await ctx.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE bill_name = $1", argument)
            if bill is None:
                bill = await ctx.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE link = $1", argument)

        if bill is None:
            raise NotFoundError(f":x: There is no bill with ID #{argument}!")

        session = await Session.convert(ctx, bill['leg_session'])

        return cls(id=bill['id'], name=bill['bill_name'], link=bill['link'], tiny_link=bill['tiny_link'],
                   description=bill['description'], is_vetoable=bill['is_vetoable'],
                   voted_on_by_leg=bill['voted_on_by_leg'], passed_leg=bill['has_passed_leg'],
                   voted_on_by_ministry=bill['voted_on_by_ministry'], passed_ministry=bill['has_passed_ministry'],
                   session=session, submitter=bill['submitter'], bot=ctx.bot)


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
    async def from_bill(cls, ctx, bill_id: int):
        law = await ctx.bot.db.fetchval("SELECT law_id FROM legislature_laws WHERE bill_id = $1", bill_id)

        if law is None:
            raise NotFoundError(f":x: There is no law with associated bill ID #{bill_id}!")

        return cls.convert(ctx, law)

    @classmethod
    async def convert(cls, ctx, argument: int):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f":x: {argument} is not a number.")

        law = await ctx.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", argument)

        if law is None:
            raise NotFoundError(f":x: There is no law with ID #{argument}!")

        bill = await Bill.convert(ctx, law['bill_id'])

        if bill is None:
            raise DemocracivBotException("Something fucked up")

        tags = await ctx.bot.db.fetch("SELECT * FROM legislature_tags WHERE id = $1", law['law_id'])
        tags = [record['tag'] for record in tags]

        return cls(id=law['law_id'], bill=bill, tags=tags)


class Motion(commands.Converter):
    """
    Represents a motion that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.title: str = kwargs.get('title')
        self.session: Session = kwargs.get('session')
        self.description: str = kwargs.get('description')
        self.link: str = kwargs.get('link')
        self._submitter: int = kwargs.get('submitter')
        self._bot = kwargs.get('bot')

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @classmethod
    async def convert(cls, ctx, argument: int):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f":x: {argument} is not a number.")

        motion = await ctx.bot.db.fetchrow("SELECT * FROM legislature_motions WHERE id = $1", argument)

        if motion is None:
            raise NotFoundError(f":x: There is no motion with ID #{argument}!")

        session = await Session.convert(ctx, motion['leg_session'])

        return cls(id=motion['id'], title=motion['title'], link=motion['hastebin'], description=motion['description'],
                   session=session, submitter=motion['submitter'], bot=ctx.bot)


class PoliticalParty(commands.Converter):
    """
    Represents a political party.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by Discord role ID on the Democraciv guild.
        2. Lookup via database by name/alias.
        3. Lookup via Discord roles on the Democraciv Guild by name/alias.

    """

    def __init__(self, **kwargs):
        self.is_private: str = kwargs.get('is_private')
        self.discord_invite: str = kwargs.get('discord_invite')
        self.aliases: typing.List[str] = kwargs.get('aliases')
        self._leader: str = kwargs.get('leader')
        self._id: int = kwargs.get('id')
        self._bot = kwargs.get('bot')

        if kwargs.get('role'):
            self._id = kwargs.get('role').id

    @property
    def leader(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._leader) or self._bot.get_user(self._leader)
        return user

    @property
    def role(self) -> typing.Optional[discord.Role]:
        return self._bot.democraciv_guild_object.get_role(self._id)

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, int):
            # Check if role still exists before doing DB query
            party = ctx.bot.democraciv_guild_object.get_role(argument)

            if party is None:
                raise PartyNotFoundError(argument)

            party_id = argument

        elif isinstance(argument, str):
            if argument.lower() == "independent" or argument.lower() == "ind":
                return cls(role=discord.utils.get(ctx.bot.democraciv_guild_object.roles, name="Independent"),
                           is_private=False, bot=ctx.bot)

            party_id = await ctx.bot.db.fetchval("SELECT party_id FROM party_alias WHERE alias = $1", argument.lower())

            if party_id is None:
                party = discord.utils.get(ctx.bot.democraciv_guild_object.roles, name=argument)

                if party is None:
                    raise PartyNotFoundError(argument)
                else:
                    party_id = party.id

        else:
            raise PartyNotFoundError(argument)

        party = await ctx.bot.db.fetchrow("SELECT * FROM parties WHERE id = $1", party_id)

        if party is None:
            raise PartyNotFoundError(argument)

        aliases = await ctx.bot.db.fetch("SELECT alias FROM party_alias WHERE party_id = $1", party['id'])
        aliases = [record['alias'] for record in aliases]

        return cls(id=party['id'], leader=party['leader'], discord_invite=party['discord_invite'],
                   is_private=party['is_private'], aliases=aliases, bot=ctx.bot)
