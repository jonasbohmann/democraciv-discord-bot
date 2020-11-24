import abc
import datetime
import functools
import enum
import textwrap
import asyncpg
import typing
import discord

from discord.ext import commands
from discord.utils import maybe_coroutine

from bot.config import config, mk
from bot.utils import context, exceptions
from bot.utils.exceptions import DemocracivBotException, NotFoundError


class NonePassed(exceptions.DemocracivBotException):
    pass


class SessionStatus(enum.Enum):
    SUBMISSION_PERIOD = "Submission Period"
    VOTING_PERIOD = "Voting Period"
    CLOSED = "Closed"


class Session(commands.Converter):
    """
    Represents a session of the Legislature.

        The lookup strategy for the converter is as follows (in order):
            1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.is_active: bool = kwargs.get("is_active")
        self.status: SessionStatus = kwargs.get("session_status")
        self.vote_form: str = kwargs.get("vote_form", None)
        self.opened_on: datetime = kwargs.get("opened_on")
        self.voting_started_on: datetime = kwargs.get("voting_started_on", None)
        self.closed_on: datetime = kwargs.get("closed_on", None)
        self.bills: typing.List[int] = kwargs.get("bills")
        self.motions: typing.List[int] = kwargs.get("motions")  # weakref ? TODO
        self._speaker: int = kwargs.get("speaker")
        self._bot = kwargs.get("bot")

    @property
    def speaker(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self._speaker) or self._bot.get_user(self._speaker)
        return user

    async def start_voting(self, voting_form):
        await self._bot.db.execute(
            "UPDATE legislature_session SET status = 'Voting Period',"
            " voting_started_on = $2, vote_form = $3"
            " WHERE id = $1",
            self.id,
            datetime.datetime.utcnow(),
            voting_form,
        )

    async def close(self):
        await self._bot.db.execute(
            "UPDATE legislature_session SET is_active = false, closed_on = $2," " status = 'Closed' WHERE id = $1",
            self.id,
            datetime.datetime.utcnow(),
        )

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, str):
            if argument.lower() == "all":
                return argument
            else:
                try:
                    argument = int(argument)
                except ValueError:
                    raise commands.BadArgument(f"{config.NO} {argument} is neither a number nor 'all'.")

        session = await ctx.bot.db.fetchrow("SELECT * FROM legislature_session WHERE id = $1", argument)
        status = SessionStatus(session["status"])

        if session is None:
            raise NotFoundError(f"{config.NO} There is no session with ID #{argument}.")

        bills = await ctx.bot.db.fetch("SELECT id FROM bill WHERE leg_session = $1", session["id"])
        bills = sorted([record["id"] for record in bills])
        motions = await ctx.bot.db.fetch("SELECT id FROM motion WHERE leg_session = $1", session["id"])
        motions = sorted([record["id"] for record in motions])
        return cls(**session, bills=bills, motions=motions, bot=ctx.bot, session_status=status)


class Bill(commands.Converter):
    """
    Represents a bill that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
        2. Lookup by bill name (Google Docs Title).
        3. Lookup by Google Docs URL.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id", 0)
        self.name: str = kwargs.get("name", None)
        self.session: Session = kwargs.get("session", None)
        self.link: str = kwargs.get("link")
        self.tiny_link: str = kwargs.get("tiny_link", None)
        self.description: str = kwargs.get("submitter_description", None)
        self.is_vetoable: bool = kwargs.get("is_vetoable", None)
        self.status: BillStatus = kwargs.get("status", None)
        self.repealed_on: typing.Optional[datetime] = kwargs.get("repealed_on", None)
        self._submitter: int = kwargs.get("submitter", None)
        self._bot = kwargs.get("bot")

    async def generate_lookup_tags(self) -> typing.List[str]:
        """Generates tags from all nouns of submitter-provided description and the Google Docs description"""

        try:
            response: typing.Dict = await self._bot.google_api.run_apps_script(
                script_id="MtyscpHHIi0Ck1h8XfuBIn2qnXKElby-M",
                function="get_keywords",
                parameters=[self.link])

            keywords = [word['ngram'] for word in response['response']['result']['keywords']]
        except (DemocracivBotException, KeyError):
            keywords = []

        async with self._bot.session.post(
                "http://yake.inesctec.pt/yake/v2/extract_keywords?max_ngram_size=2&number_of_keywords=20&highlight=false",
                data={'content': self.description}, raise_for_status=True) as r:
            js = await r.json()

            try:
                keywords.extend([word['ngram'] for word in js['keywords']])
            except KeyError:
                pass

        name_abbreviation = "".join([c[0].lower() for c in self.name.split()])

        if self.name.lower().startswith("the"):
            keywords.append(name_abbreviation[1:])

        keywords.append(name_abbreviation)
        return list(set(keywords))

    async def make_lookup_tags(self):
        tags = await self.generate_lookup_tags()

        for tag in tags:
            await self._bot.db.execute("INSERT INTO bill_lookup_tag (bill_id, tag) VALUES "
                                       "($1, $2) ON CONFLICT DO NOTHING ", self.id, tag)

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @property
    def short_name(self) -> str:
        return textwrap.shorten(self.name, width=35)

    @property
    def formatted(self):
        return f"Bill #{self.id} - [{self.name}]({self.link}) {self.status.emojified_status(verbose=False)}"

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        try:
            argument = int(argument)
            bill = await ctx.bot.db.fetchrow("SELECT * FROM bill WHERE id = $1", argument)
        except ValueError:
            bill = await ctx.bot.db.fetchrow(
                "SELECT * FROM bill WHERE" " lower(name) = $2 or link = $1 or tiny_link = $1",
                argument,
                argument.lower(),
            )

        if bill is None:
            raise NotFoundError(f"{config.NO} There is no bill that matches `{argument}`.")

        session = await Session.convert(ctx, bill["leg_session"])
        obj = cls(**bill, session=session, bot=ctx.bot)
        status = BillStatus.from_flag_value(bill["status"])(ctx.bot, obj)
        obj.status = status
        return obj


class Law(Bill):
    @property
    def formatted(self):
        return f"Law #{self.id} - [{self.name}]({self.link})"

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        bill = await super().convert(ctx, argument)

        if not bill.status.is_law:
            raise commands.BadArgument(f"{config.NO} `{bill.name}` (#{bill.id}) is not an active law.")


class Motion(commands.Converter):
    """
    Represents a motion that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.title: str = kwargs.get("title")
        self.session: Session = kwargs.get("session")
        self.description: str = kwargs.get("description")
        self._link: str = kwargs.get("paste_link")
        self.name: str = self.title  # compatibility
        self._submitter: int = kwargs.get("submitter")
        self._bot = kwargs.get("bot")

    @property
    def formatted(self):
        return f"Motion #{self.id} - [{self.name}]({self.link})"

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self._submitter) or self._bot.get_user(self._submitter)
        return user

    @property
    def short_name(self) -> str:
        return textwrap.shorten(self.name, width=35)

    @property
    def link(self) -> str:
        # If the motion's description is just a Google Docs link, use that link instead of the paste link
        is_google_docs = self._bot.laws.is_google_doc_link(self.description) and len(self.description) <= 100
        return self.description if is_google_docs else self._link

    @classmethod
    async def convert(cls, ctx, argument: int):
        try:
            argument = int(argument)
        except ValueError:
            raise commands.BadArgument(f"{config.NO} {argument} is not a number.")

        motion = await ctx.bot.db.fetchrow("SELECT * FROM motion WHERE id = $1", argument)

        if motion is None:
            raise NotFoundError(f"{config.NO} There is no motion with ID #{argument}.")

        session = await Session.convert(ctx, motion["leg_session"])
        return cls(**motion, session=session, bot=ctx.bot)


class LegalConsumer:
    def __init__(
            self,
            *,
            ctx: context.CustomContext,
            objects: typing.Iterable[typing.Union[Bill, Motion]],
            action: typing.Callable,
    ):
        self.objects = set(objects)
        self.ctx = ctx
        self.action = action
        self._filtered_out_objs = set()

    async def filter(self, *, filter_func: typing.Callable = None, **kwargs):
        for obj in self.objects:
            if filter_func:
                fail = await maybe_coroutine(filter_func, self.ctx, obj, **kwargs)

                if fail:
                    self._filtered_out_objs.add((obj, fail))

            try:
                await maybe_coroutine(self.action(obj.status), dry=True)
            except IllegalOperation as e:
                self._filtered_out_objs.add((obj, e.message))

        self._passed_objs = self.objects - self._filtered_out_objs

        if not self._passed_objs:
            raise NonePassed("")

    async def consume(self, *, scheduler=None):
        for obj in self.passed:
            await maybe_coroutine(self.action(obj.status), dry=False)

            if scheduler:
                scheduler.add(obj)

    @property
    def passed(self) -> typing.Set:
        return self._passed_objs

    @property
    def failed(self) -> typing.Set:
        return self._filtered_out_objs

    @property
    def passed_formatted(self) -> str:
        return "\n".join([f"-  **{obj.name}** (#{obj.id})" for obj in self.passed])

    @property
    def failed_formatted(self) -> str:
        return "\n".join([f"-  **{obj.name}** (#{obj.id}): _{reason}_" for obj, reason in self.failed])


class _BillStatusFlag(enum.Enum):
    SUBMITTED = 0
    LEG_FAILED = 1
    LEG_PASSED = 2
    MIN_FAILED = 3
    MIN_PASSED = 4
    REPEALED = 5


class IllegalOperation(DemocracivBotException):
    pass


class IllegalBillOperation(IllegalOperation):
    pass


class BillStatus(abc.ABC):
    flag: _BillStatusFlag
    verbose_name: str
    stale: bool = False
    is_law: bool = False

    GREEN = config.LEG_BILL_STATUS_GREEN
    YELLOW = config.LEG_BILL_STATUS_YELLOW
    RED = config.LEG_BILL_STATUS_RED
    GRAY = config.LEG_BILL_STATUS_GRAY

    @staticmethod
    def from_flag_value(flag):
        translation = {
            0: BillSubmitted,
            1: BillFailedLegislature,
            2: BillPassedLegislature,
            3: BillVetoed,
            4: BillPassedMinistry,
            5: BillRepealed,
        }

        return translation[flag]

    def __init__(self, bot, bill):
        self._bot: "bot.DemocracivBot" = bot
        self._bill: Bill = bill

    def __eq__(self, other):
        return isinstance(other, BillStatus) and self.flag == other.flag

    def __int__(self):
        return self.flag.value

    def __str__(self):
        return self.verbose_name

    def __repr__(self):
        return f"<{self.__class__.__name__} flag={self.flag} stale={self.stale}>"

    async def log_history(self, old_status: _BillStatusFlag, new_status: _BillStatusFlag):
        await self._bot.db.execute(
            "INSERT INTO bill_history (bill_id, date, before_status, after_status) " "VALUES ($1, $2, $3, $4)",
            self._bill.id,
            datetime.datetime.utcnow(),
            old_status.value,
            new_status.value,
        )

    async def veto(self, dry=False):
        raise IllegalBillOperation("")

    async def withdraw(self, dry=False):
        raise IllegalBillOperation("")

    async def pass_into_law(self, dry=False):
        raise IllegalBillOperation("")

    async def pass_from_legislature(self, dry=False):
        raise IllegalBillOperation("")

    async def fail_in_legislature(self, dry=False):
        raise IllegalBillOperation("")

    async def override_veto(self, dry=False):
        raise IllegalBillOperation("")

    async def repeal(self, dry=False):
        raise IllegalBillOperation("")

    async def resubmit(self, dry=False):
        raise IllegalBillOperation("")

    async def amend(self, *, dry=False, new_link: str):
        raise IllegalBillOperation("")

    @abc.abstractmethod
    def emojified_status(self, verbose=True):
        pass


class BillSubmitted(BillStatus):
    is_law = False
    flag = _BillStatusFlag.SUBMITTED
    verbose_name = "Submitted"

    async def withdraw(self, dry=False):
        try:
            await self._bot.db.execute("DELETE FROM bill WHERE id = $1", self._bill.id)
        except asyncpg.ForeignKeyViolationError:  # ? not needed
            raise IllegalBillOperation(f":warning: Bill #{self._bill.id} is already a law and cannot be withdrawn.")

    async def fail_in_legislature(self, dry=False):
        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_FAILED.value,
            self._bill.id,
        )

    async def pass_from_legislature(self, dry=False):
        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_PASSED.value,
            self._bill.id,
        )
        await self.log_history(self.flag, _BillStatusFlag.LEG_PASSED)

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.YELLOW} *(Not Voted On Yet)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Waiting on {self._bot.mk.LEGISLATURE_NAME})*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.YELLOW}{self.YELLOW}{self.GRAY}"


class BillFailedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_FAILED
    verbose_name = f"Failed in the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def resubmit(self, dry=False):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.RED} *(Failed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Failed in the {self._bot.mk.LEGISLATURE_NAME})*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.RED}{self.GRAY}{self.GRAY}"


class BillPassedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_PASSED
    verbose_name = f"Passed the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def veto(self, dry=False):
        if not self._bill.is_vetoable:
            raise IllegalBillOperation("")

        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.MIN_FAILED.value,
            self._bill.id,
        )
        await self.log_history(self.flag, _BillStatusFlag.MIN_FAILED)

    async def pass_into_law(self, dry=False):
        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.MIN_PASSED.value,
            self._bill.id,
        )
        await self.log_history(self.flag, _BillStatusFlag.MIN_PASSED)

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Not Voted on Yet)*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.GREEN}{self.YELLOW}{self.GRAY}"


class BillVetoed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.MIN_FAILED
    verbose_name = f"Vetoed by the {mk.MarkConfig.MINISTRY_NAME}"

    async def override_veto(self, dry=False):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.RED} *(Vetoed)*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.GREEN}{self.RED}{self.GRAY}"


class BillPassedMinistry(BillStatus):
    is_law = True
    flag = _BillStatusFlag.MIN_PASSED
    verbose_name = "Active Law"

    async def repeal(self, dry=False):
        pass

    async def amend(self, *, dry=False, new_link: str):
        if not dry:
            new_tiny = await self._bot.tinyurl(new_link)
            await self._bot.db.execute(
                "UPDATE bill SET link = $1, tiny_link = $2 WHERE id = $3",
                new_link,
                new_tiny,
                self._bill.id,
            )

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
                f"Law: {self.GREEN} *(Active Law)*\n"
            )

        return f"{self.GREEN}{self.GREEN}{self.GREEN}"


BillIsLaw = BillPassedMinistry


class BillRepealed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.REPEALED
    verbose_name = "Repealed"

    async def resubmit(self, dry=False):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
                f"Law: {self.RED} *(Repealed)*\n"
            )

        return f"{self.GREEN}{self.GREEN}{self.RED}"
