import re
import enum
import typing
import discord

from dciv_bot.config import config
from datetime import datetime
from discord.ext import commands
from discord.ext.commands import BadArgument
from dciv_bot.util.exceptions import DemocracivBotException, TagError, NotFoundError, PartyNotFoundError


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


class BillStatus(enum.Enum):
    SUBMITTED = 0
    LEG_FAILED = 1
    LEG_PASSED = 2
    MIN_FAILED = 3
    MIN_PASSED = 4
    VETO_OVERRIDDEN = 5
    REPEALED = 6


class Selfrole(commands.Converter):
    def __init__(self, **kwargs):
        self.join_message = kwargs.get('join_message')
        self._guild = kwargs.get('guild')
        self._role = kwargs.get('role')
        self._bot = kwargs.get('bot')

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        return self._bot.get_guild(self._guild)

    @property
    def role(self) -> typing.Optional[discord.Role]:
        if self.guild is not None:
            return self.guild.get_role(self._role)

        return None

    @classmethod
    async def convert(cls, ctx, argument):
        arg = argument.lower()

        def predicate(r):
            return r.name.lower() == arg

        role = discord.utils.find(predicate, ctx.guild.roles)

        if not role:
            raise NotFoundError(f":x: There is no selfrole on this server that matches `{argument}`. "
                                f"If you're trying to join or leave a political party,"
                                f" check `{config.BOT_PREFIX}help Political Parties`")

        role_record = await ctx.bot.db.fetchrow("SELECT * FROM roles WHERE guild_id = $1 AND role_id = $2",
                                                ctx.guild.id, role.id)

        if role_record:
            return cls(join_message=role_record['join_message'], role=role_record['role_id'],
                       guild=role_record['guild_id'], bot=ctx.bot)

        else:
            raise NotFoundError(f":x: There is no selfrole on this server that matches `{argument}`. "
                                f"If you're trying to join or leave a political party,"
                                f" check `{config.BOT_PREFIX}help Political Parties`")


class BanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        member = None

        try:
            member = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            id_regex = re.compile(r'([0-9]{15,21})$')
            if id_regex.match(argument):
                member = int(argument)

        if member:
            return member
        else:
            raise BadArgument(":x: I couldn't find that person.")


class UnbanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        user = None

        def find_by_name(ban_entry):
            return ban_entry.user.name.lower() == argument.lower()

        def find_by_id(ban_entry):
            return ban_entry.user.id == argument

        try:
            user = await commands.UserConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                argument = int(argument, base=10)
                ban = discord.utils.find(find_by_id, await ctx.guild.bans())
            except ValueError:
                ban = discord.utils.find(find_by_name, await ctx.guild.bans())

            if ban:
                user = ban.user

        if user:
            return user
        else:
            raise BadArgument(":x: I couldn't find that person.")


class FlowCaseInsensitiveTextChannel(commands.TextChannelConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            if arg.startswith("#"):
                arg = arg[1:]

            def predicate(c):
                return c.name.lower() == arg

            channel = discord.utils.find(predicate, ctx.guild.text_channels)

            if channel:
                return channel

            raise BadArgument(f":x: There is no channel named `{argument}` on this server.")


class FlowCaseInsensitiveRole(commands.RoleConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            if arg.startswith("@"):
                arg = arg[1:]

            def predicate(r):
                return r.name.lower() == arg

            role = discord.utils.find(predicate, ctx.guild.roles)

            if role:
                return role

            raise BadArgument(f":x: There is no role named `{argument}` on this server.")


class CaseInsensitiveRole(commands.Converter):
    async def convert(self, ctx, argument):
        arg = argument.lower()

        def predicate(r):
            return r.name.lower() == arg

        role = discord.utils.find(predicate, ctx.guild.roles)

        if role:
            return role

        role = discord.utils.find(predicate, ctx.bot.democraciv_guild_object.roles)

        if role:
            return role

        raise BadArgument(f":x: There is no role named `{argument}` on this or the Democraciv server.")


class CaseInsensitiveMember(commands.MemberConverter):
    async def convert(self, ctx, argument):
        arg = argument.lower()

        def predicate(m):
            return m.name.lower() == arg or (m.nick and m.nick.lower() == arg)

        member = discord.utils.find(predicate, ctx.guild.members)

        if member:
            return member

        raise BadArgument()


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
        self.is_embedded: bool = kwargs.get('is_embedded')
        self._author: int = kwargs.get('author', None)
        self._guild: int = kwargs.get('guild')
        self._bot = kwargs.get('bot')

    @property
    def guild(self) -> discord.Guild:
        return self._bot.get_guild(self._guild)

    @property
    def author(self) -> typing.Union[discord.Member, discord.User, None]:
        user = None

        if self.guild:
            user = self.guild.get_member(self._author)

        if user is None:
            user = self._bot.get_user(self._author)

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
            raise TagError(f":x: There is no global or local tag named `{argument}`.")

        tag_details = await ctx.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        aliases = await ctx.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1", tag_id)
        aliases = [record['alias'] for record in aliases]

        try:
            is_embedded = tag_details['is_embedded']
        except KeyError:  # backwards compatibility
            is_embedded = True

        return cls(id=tag_details['id'], name=tag_details['name'], title=tag_details['title'],
                   content=tag_details['content'], _global=tag_details['global'], uses=tag_details['uses'],
                   bot=ctx.bot, guild=tag_details['guild_id'], author=tag_details['author'], aliases=aliases,
                   is_embedded=is_embedded)


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
            raise TagError(f":x: There is no global or local tag named `{argument}`.")

        tag_details = await ctx.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        if tag_details['global'] and tag_details['guild_id'] != ctx.guild.id:
            raise TagError(f":x: Global tags can only be edited, transferred or removed on "
                           f"the server they were originally created on.")

        if tag_details['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
            raise TagError(f":x: That isn't your tag.")

        aliases = await ctx.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1", tag_id)
        aliases = [record['alias'] for record in aliases]

        try:
            is_embedded = tag_details['is_embedded']
        except KeyError:  # backwards compatibility
            is_embedded = True

        return cls(id=tag_details['id'], name=tag_details['name'], title=tag_details['title'],
                   content=tag_details['content'], _global=tag_details['global'], uses=tag_details['uses'],
                   bot=ctx.bot, guild=tag_details['guild_id'], author=tag_details['author'], aliases=aliases,
                   is_embedded=is_embedded, invoked_with=argument.lower())


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

    async def start_voting(self, voting_form):
        await self._bot.db.execute("UPDATE legislature_sessions SET status = 'Voting Period',"
                                   " voting_started_on = $2, vote_form = $3"
                                   " WHERE id = $1", self.id, datetime.utcnow(), voting_form)

    async def close(self):
        await self._bot.db.execute("UPDATE legislature_sessions SET is_active = false, closed_on = $2,"
                                   " status = 'Closed' WHERE id = $1", self.id, datetime.utcnow())

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, str):
            if argument.lower() == "all":
                return argument
            else:
                try:
                    argument = int(argument)
                except ValueError:
                    raise BadArgument(f":x: {argument} is neither a number nor 'all'.")

        session = await ctx.bot.db.fetchrow("SELECT * FROM legislature_sessions WHERE id = $1", argument)

        if session is None:
            raise NotFoundError(f":x: There is no session with ID #{argument}.")

        bills = await ctx.bot.db.fetch("SELECT id FROM legislature_bills WHERE leg_session = $1", session['id'])
        bills = sorted([record['id'] for record in bills])

        motions = await ctx.bot.db.fetch("SELECT id FROM legislature_motions WHERE leg_session = $1", session['id'])
        motions = sorted([record['id'] for record in motions])

        return cls(id=session['id'], is_active=session['is_active'],
                   status=SessionStatus.from_str(session['status']),
                   vote_form=session['vote_form'], opened_on=session['opened_on'],
                   voting_started_on=session['voting_started_on'], closed_on=session['closed_on'],
                   speaker=session['speaker'], bills=bills, motions=motions, bot=ctx.bot)


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
        self.google_docs_description: str = kwargs.get('google_docs_description')
        self.is_vetoable: bool = kwargs.get('is_vetoable')
        self.status: BillStatus = kwargs.get('status')
        self.repealed_on: typing.Optional[datetime] = kwargs.get('repealed_on')
        self._submitter: int = kwargs.get('submitter')
        self._bot = kwargs.get('bot')

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @property
    def short_name(self) -> str:
        length = len(self.name)
        if length > 35:
            to_remove = length - 35
            return self.name[:-to_remove] + '...'
        else:
            return self.name

    async def is_law(self) -> bool:
        found = await self._bot.db.fetchval("SELECT law_id FROM legislature_laws WHERE bill_id = $1", self.id)

        if found:
            return True
        else:
            return False

    async def withdraw(self):
        await self._bot.db.execute("DELETE FROM legislature_bills WHERE id = $1", self.id)

    async def pass_from_legislature(self):
        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   BillStatus.LEG_PASSED.value,
                                   self.id)

    async def veto(self):
        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   BillStatus.MIN_FAILED.value,
                                   self.id)

    async def pass_into_law(self, override: bool = False):
        if self.is_vetoable and not override:
            await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                       BillStatus.MIN_PASSED.value,
                                       self.id)
        if override:
            await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                       BillStatus.VETO_OVERRIDDEN.value,
                                       self.id)

        law_id = await self._bot.db.fetchval("INSERT INTO legislature_laws (bill_id, passed_on)"
                                             " VALUES ($1, $2) RETURNING law_id",
                                             self.id, datetime.utcnow())

        # The bot takes the submitter-provided description (from the -legislature submit command) *and* the description
        # from Google Docs (og:description property in HTML, usually the title of the Google Doc and the first
        # few sentence's of content.) and tokenizes those with nltk. Then, every noun from both descriptions is saved
        # into the legislature_tags table with the corresponding law_id.

        _tags = await self._bot.loop.run_in_executor(None, self._bot.laws.generate_law_tags,
                                                     self.google_docs_description, self.description)

        name_abbreviation = "".join([c[0].lower() for c in self.name.split()])

        if self.name.lower().startswith("the"):
            _tags.append(name_abbreviation[1:])

        _tags.append(name_abbreviation)

        for tag in _tags:
            await self._bot.db.execute("INSERT INTO legislature_tags (id, tag) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                                       law_id, tag.lower())

    async def get_emojified_status(self, verbose: bool = True) -> str:
        if self.status is BillStatus.SUBMITTED:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_YELLOW} *(Not Voted On Yet)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_YELLOW} *(Not Voted On Yet)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GRAY}\n"

            return f"{config.LEG_BILL_STATUS_YELLOW}{config.LEG_BILL_STATUS_YELLOW}{config.LEG_BILL_STATUS_GRAY}"

        elif self.status is BillStatus.LEG_FAILED:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_RED} *(Failed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_GRAY} *(Failed in Legislature)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GRAY}"

            return f"{config.LEG_BILL_STATUS_RED}{config.LEG_BILL_STATUS_GRAY}{config.LEG_BILL_STATUS_GRAY}"

        elif self.status is BillStatus.LEG_PASSED and not self.is_vetoable:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_GRAY} *(Not Vetoable)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GREEN} *(Active Law)*"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_GRAY}{config.LEG_BILL_STATUS_GREEN}"

        elif self.status is BillStatus.LEG_PASSED and self.is_vetoable:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_YELLOW} *(Not Voted On Yet)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GRAY}"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_YELLOW}{config.LEG_BILL_STATUS_GRAY}"

        elif self.status is BillStatus.MIN_FAILED:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_RED} *(Vetoed)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GRAY}"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_RED}{config.LEG_BILL_STATUS_GRAY}"

        elif self.status is BillStatus.MIN_PASSED:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GREEN} *(Active Law)*"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_GREEN}"

        elif self.status is BillStatus.VETO_OVERRIDDEN:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_RED} *(Vetoed)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_GREEN} *(Active Law due to Legislature Override of Veto)*"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_RED}{config.LEG_BILL_STATUS_GREEN}"

        elif self.status is BillStatus.REPEALED:
            if verbose:
                return f"Legislature: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Ministry: {config.LEG_BILL_STATUS_GREEN} *(Passed)*\n" \
                       f"Law: {config.LEG_BILL_STATUS_RED} *(Repealed)*"

            return f"{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_GREEN}{config.LEG_BILL_STATUS_RED}"

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        try:
            argument = int(argument)
            bill = await ctx.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", argument)
        except ValueError:
            bill = await ctx.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE"
                                             " lower(bill_name) = $2 or link = $1 or tiny_link = $1", argument,
                                             argument.lower())

        if bill is None:
            raise NotFoundError(f":x: There is no bill that matches `{argument}`.")

        session = await Session.convert(ctx, bill['leg_session'])

        return cls(id=bill['id'], name=bill['bill_name'], link=bill['link'], tiny_link=bill['tiny_link'],
                   description=bill['description'], is_vetoable=bill['is_vetoable'],
                   session=session, submitter=bill['submitter'], status=BillStatus(bill['status']),
                   google_docs_description=bill['google_docs_description'], bot=ctx.bot)


class Law(commands.Converter):
    """
    Represents a law that was either passed by just the Legislature or by both the Legislature and the Ministry.
    A law has always a bill associated with it.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
        2. Lookup by bill name (Google Docs Title).
        3. Lookup by Google Docs URL.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get('id')
        self.bill: Bill = kwargs.get('bill')
        self.passed_on: datetime = kwargs.get('passed_on')
        self.tags: typing.List[str] = kwargs.get('tags')
        self._bot = kwargs.get('bot')

    @classmethod
    async def from_bill(cls, ctx, bill_id: int):
        law = await ctx.bot.db.fetchval("SELECT law_id FROM legislature_laws WHERE bill_id = $1", bill_id)

        if law is None:
            raise NotFoundError(f":x: There is no law with associated bill ID #{bill_id}.")

        return await cls.convert(ctx, law)

    async def repeal(self):
        await self._bot.db.execute("UPDATE legislature_bills SET status = $1, repealed_on = $2 WHERE id = $3",
                                   BillStatus.REPEALED.value,
                                   datetime.utcnow(),
                                   self.bill.id)

        await self._bot.db.execute("DELETE FROM legislature_laws WHERE law_id = $1", self.id)

    async def amend(self, new_link: str):
        tiny_url = await self._bot.laws.post_to_tinyurl(new_link)

        if tiny_url is None:
            raise DemocracivBotException(":x: tinyurl.com returned an error, the link was not updated. "
                                         "Try again in a few minutes.")

        await self._bot.db.execute("UPDATE legislature_bills SET link = $1, tiny_link = $2 WHERE id = $3",
                                   new_link, tiny_url, self.bill.id)

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        try:
            argument = int(argument)
            law = await ctx.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", argument)
        except ValueError:
            query = """SELECT law_id FROM legislature_laws AS l
                       JOIN legislature_bills b on l.bill_id = b.id
                       WHERE (lower(b.bill_name) = $2 OR b.link = $1 OR b.tiny_link = $1)"""

            law_id = await ctx.bot.db.fetchval(query, argument, argument.lower())

            if law_id:
                law = await ctx.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", law_id)
            else:
                law = None

        if law is None:
            raise NotFoundError(f":x: There is no law with ID #{argument}.")

        bill = await Bill.convert(ctx, law['bill_id'])

        if bill is None:
            raise DemocracivBotException("Something fucked up")

        tags = await ctx.bot.db.fetch("SELECT * FROM legislature_tags WHERE id = $1", law['law_id'])
        tags = [record['tag'] for record in tags]

        return cls(id=law['law_id'], bill=bill, tags=tags, passed_on=law['passed_on'], bot=ctx.bot)


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
        self._link: str = kwargs.get('link')
        self.name: str = self.title  # compatibility
        self._submitter: int = kwargs.get('submitter')
        self._bot = kwargs.get('bot')

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.democraciv_guild_object.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @property
    def short_name(self) -> str:
        length = len(self.title)
        if length > 35:
            to_remove = length - 35
            return self.title[:-to_remove] + '...'
        else:
            return self.title

    @property
    def link(self) -> str:
        # If the motion's description is just a Google Docs link, use that link instead of the Hastebin

        is_google_docs = self._bot.laws.is_google_doc_link(self.description) and len(self.description) <= 100
        return self.description if is_google_docs else self._link

    async def withdraw(self):
        await self._bot.db.execute("DELETE FROM legislature_motions WHERE id = $1", self.id)

    @classmethod
    async def convert(cls, ctx, argument: int):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f":x: {argument} is not a number.")

        motion = await ctx.bot.db.fetchrow("SELECT * FROM legislature_motions WHERE id = $1", argument)

        if motion is None:
            raise NotFoundError(f":x: There is no motion with ID #{argument}.")

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

    async def get_logo(self):
        if not self.discord_invite:
            return None

        try:
            invite = await self._bot.fetch_invite(self.discord_invite)
            return invite.guild.icon_url_as(format='png')
        except (discord.NotFound, discord.HTTPException):
            return None

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, int):
            # Check if role still exists before doing DB query
            party = ctx.bot.democraciv_guild_object.get_role(argument)

            if party is None:
                raise PartyNotFoundError(argument)

            party_id = argument

        elif isinstance(argument, str):
            if argument.lower() in ("independent", "independant", "ind", "ind."):
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
