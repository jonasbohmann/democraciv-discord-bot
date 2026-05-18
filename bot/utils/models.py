import datetime
import enum
import re
import textwrap
import typing
import yake
import discord

from collections import namedtuple

from discord.ext import commands
from discord.utils import maybe_coroutine

from bot.config import config, mk
from bot.utils import context
from bot.utils.exceptions import DemocracivBotException, NotFoundError, NotLawError
from bot.utils.converter import FuzzyableMixin


class SessionStatus(enum.Enum):
    SUBMISSION_PERIOD = "Submission Period"
    LOCKED = "Submissions Locked"
    VOTING_PERIOD = "Voting Period"
    CLOSED = "Closed"


HOUSE_NAMES = {"senate": "Senate", "commons": "Commons"}


def display_house_name(house: typing.Optional[str]) -> str:
    if house is None:
        return "Legislature"

    return HOUSE_NAMES.get(house, house.title())


class Session(commands.Converter):
    """
    Represents a session of the Legislature.

        The lookup strategy for the converter is as follows (in order):
            1. Lookup by ID.
    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.status: SessionStatus = kwargs.get("session_status")
        self.vote_form: str = kwargs.get("vote_form")
        self.opened_on: datetime = kwargs.get("opened_on")
        self.voting_started_on: datetime = kwargs.get("voting_started_on")
        self.closed_on: datetime = kwargs.get("closed_on")
        self.bills: typing.List[int] = kwargs.get("bills", [])
        self.motions: typing.List[int] = kwargs.get("motions", [])
        self.house: typing.Optional[str] = kwargs.get("house")
        self.mk13_house_id: typing.Optional[int] = kwargs.get("mk13_house_id")
        self._speaker: int = kwargs.get("speaker")
        self._bot = kwargs.get("bot")

    @property
    def speaker(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self._speaker) or self._bot.get_user(
            self._speaker
        )
        return user

    @property
    def display_id(self) -> int:
        return self.mk13_house_id or self.id

    @property
    def display_name(self) -> str:
        return f"{display_house_name(self.house)} Session #{self.display_id}"

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
            "UPDATE legislature_session SET closed_on = $2, status = 'Closed' WHERE id = $1",
            self.id,
            datetime.datetime.utcnow(),
        )

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        if isinstance(argument, str):
            if argument.startswith("#"):
                argument = argument[1:]
            try:
                argument = int(argument)
            except ValueError:
                raise commands.BadArgument(f"{config.NO} `{argument}` is not a number.")

        session = await ctx.bot.db.fetchrow(
            "SELECT * FROM legislature_session WHERE id = $1", argument
        )

        if not session:
            raise NotFoundError(
                f"{config.NO} There hasn't been a session #{argument} yet."
            )

        status = SessionStatus(session["status"])
        bills = await ctx.bot.db.fetch(
            "SELECT bill_id AS id FROM bill_session WHERE leg_session = $1",
            session["id"],
        )

        if not bills:
            bills = await ctx.bot.db.fetch(
                "SELECT id FROM bill WHERE leg_session = $1", session["id"]
            )

        bills = sorted([record["id"] for record in bills])
        motions = await ctx.bot.db.fetch(
            "SELECT id FROM motion WHERE leg_session = $1", session["id"]
        )
        motions = sorted([record["id"] for record in motions])
        return cls(
            **session, bills=bills, motions=motions, bot=ctx.bot, session_status=status
        )


sponsor_regex = re.compile(r"([<>=!]=?)\s?(\d+)")


class SessionSponsorFilter(commands.Converter):
    async def convert(
        self, ctx, argument
    ) -> typing.Optional[typing.Tuple[typing.Callable, str]]:
        match = sponsor_regex.match(argument)

        if not match:
            return

        try:
            filter_func = match.group(1)
            amount = int(match.group(2))
        except (IndexError, ValueError):
            return

        translation = {
            "<": lambda b: len(b.sponsors) < amount,
            "<=": lambda b: len(b.sponsors) <= amount,
            "=": lambda b: len(b.sponsors) == amount,
            ">": lambda b: len(b.sponsors) > amount,
            ">=": lambda b: len(b.sponsors) >= amount,
            "!": lambda b: len(b.sponsors) != amount,
        }

        translation["=="] = translation["="]
        translation["!="] = translation["!"]

        try:
            return translation[filter_func], argument
        except KeyError:
            return


BillHistoryEntry = namedtuple("BillHistoryEntry", "before after date note")


class Bill(commands.Converter, FuzzyableMixin):
    """
    Represents a bill that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
        2. Lookup by bill name (Google Docs Title).
        3. Lookup by Google Docs URL.
    """

    model = "Bill"
    fuzzy_description = f"Maybe you were looking for the `{config.BOT_PREFIX}bill search` command instead?\n"

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.session: Session = kwargs.get("session")
        self.link: str = kwargs.get("link")
        self.tiny_link: str = self.link  # deprecated
        self.description: str = kwargs.get("submitter_description")
        self.is_vetoable: bool = kwargs.get("is_vetoable")
        self.is_procedure: bool = bool(kwargs.get("is_procedure"))
        self.status: BillStatus = kwargs.get("status")
        self.content: str = kwargs.get("content")
        self.submitter_id: int = kwargs.get("submitter")
        self._bot = kwargs.get("bot")
        self.sponsor_ids: typing.List[int] = kwargs.get("sponsors", [])
        self.origin_house: str = kwargs.get("origin_house")
        self.executive_deadline_at: typing.Optional[datetime.datetime] = kwargs.get(
            "executive_deadline_at"
        )

        self.history = kwargs.get("history")

        if self.status is None:
            self.status = BillStatus(self._bot, self)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Bill) and self.id == other.id

    def __str__(self):
        return self.name

    @property
    def _fuzzy_menu_description(self):
        return f"Bill #{self.id}"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        lowered = argument.lower()

        matches = await ctx.bot.db.fetch(
            "SELECT id FROM bill WHERE lower(name) % $1 OR lower(name) LIKE '%' || $1 || '%'"
            " ORDER BY similarity(lower(name), $1) DESC LIMIT 5;",
            lowered,
        )

        tag_matches = await ctx.bot.db.fetch(
            "SELECT DISTINCT bill_id AS id FROM bill_lookup_tag WHERE tag % $1 LIMIT 2;",
            lowered,
        )

        matches.extend(tag_matches)

        matches = {await Bill.convert(ctx, match["id"]): None for match in matches}

        return list(matches.keys())

    async def update_link(self, new_link: str):
        self.link = new_link
        name, keywords, content = await self.fetch_name_and_keywords()

        if not name or not content:
            raise DemocracivBotException(
                f"There was an error while fetching the name & content of "
                f"this bill. Do I have view permissions for this bill's Google Docs document?"
            )

        await self._bot.db.execute(
            "UPDATE bill SET name = $1, content = $2, link = $3 WHERE id = $4",
            name,
            content,
            new_link,
            self.id,
        )

        await self._bot.db.execute(
            "DELETE FROM bill_lookup_tag WHERE bill_id = $1", self.id
        )
        await self._bot.api_request(
            "POST", "document/update", silent=True, json={"id": self.id, "type": "bill"}
        )

        id_with_kws = [(self.id, keyword) for keyword in keywords]
        self._bot.loop.create_task(
            self._bot.db.executemany(
                "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                id_with_kws,
            )
        )

    @property
    def sponsors(self) -> typing.List[typing.Union[discord.Member, discord.User]]:
        return list(
            filter(
                None,
                [
                    self._bot.dciv.get_member(sponsor) or self._bot.get_user(sponsor)
                    for sponsor in self.sponsor_ids
                ],
            )
        )

    def extract_keywords(self, content):
        kw_extractor = yake.KeywordExtractor(lan="en", n=2, top=20)
        keywords = kw_extractor.extract_keywords(content)
        return [kw[0] for kw in keywords if kw[0]]

    async def fetch_name_and_keywords(self) -> typing.Tuple[str, typing.List[str], str]:

        try:
            response: typing.Dict = await self._bot.run_apps_script(
                script_id="MtyscpHHIi0Ck1h8XfuBIn2qnXKElby-M",
                function="main",
                parameters=[self.link],
            )

            self.name = name = response["response"]["result"]["title"]
            self.content = content = response["response"]["result"]["content"]
            keywords = await self._bot.loop.run_in_executor(
                None, self.extract_keywords, content
            )

        except (DemocracivBotException, KeyError):
            keywords = []
            self.name = name = ""
            self.content = content = ""

        name_abbreviation = "".join([c[0].lower() for c in self.name.split()])

        if self.name.lower().startswith("the"):
            keywords.append(name_abbreviation[1:])

        keywords.append(name_abbreviation)
        return name, list(set(keywords)), content

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self.submitter_id) or self._bot.get_user(
            self.submitter_id
        )
        return user

    @property
    def short_name(self) -> str:
        return textwrap.shorten(self.name, width=70)

    @property
    def origin_house_name(self) -> str:
        return display_house_name(self.origin_house)

    @property
    def type_name(self) -> str:
        if self.is_procedure and self.origin_house in HOUSE_NAMES:
            return f"{self.origin_house_name} Procedure"

        return "Bill"

    @property
    def formatted(self):
        return f"Bill #{self.id} - [{self.name}]({self.link}) {self.status.emojified_status(verbose=False)}"

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str]):
        try:
            arg = argument

            if isinstance(arg, str) and arg.startswith("#"):
                arg = arg[1:]

            arg = int(arg)
            bill = await ctx.bot.db.fetchrow("SELECT * FROM bill WHERE id = $1", arg)
        except ValueError:
            bill = await ctx.bot.db.fetchrow(
                "SELECT * FROM bill WHERE lower(name) = $2 or link = $1",
                argument,
                argument.lower(),
            )

        if bill is None:
            raise NotFoundError(
                f"{config.NO} There is no bill that matches `{argument}`."
            )

        session = await Session.convert(ctx, bill["leg_session"])

        sponsors = await ctx.bot.db.fetch(
            "SELECT sponsor FROM bill_sponsor WHERE bill_id = $1", bill["id"]
        )
        sponsors = [record["sponsor"] for record in sponsors]

        obj = cls(**bill, session=session, bot=ctx.bot, sponsors=sponsors)

        status = BillStatus.from_flag_value(bill["status"])(ctx.bot, obj)
        obj.status = status

        history_record = await ctx.bot.db.fetch(
            "SELECT * FROM bill_history WHERE bill_id = $1 ORDER BY date DESC", obj.id
        )
        history = []

        for record in history_record:
            entry = BillHistoryEntry(
                date=record["date"],
                before=BillStatus.from_flag_value(record["before_status"])(
                    ctx.bot, obj
                ),
                after=BillStatus.from_flag_value(record["after_status"])(ctx.bot, obj),
                note=record["note"],
            )
            history.append(entry)

        obj.history = history
        return obj


class Law(Bill, FuzzyableMixin):
    model = "Law"
    fuzzy_description = (
        f"Maybe you were looking for the "
        f"`{config.BOT_PREFIX}law search` "
        f"command instead?\n"
    )

    @property
    def formatted(self):
        return f"Law #{self.id} - [{self.name}]({self.link})"

    @property
    def _fuzzy_menu_description(self):
        return f"Law #{self.id}"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        lowered = argument.lower()

        matches = await ctx.bot.db.fetch(
            "SELECT id FROM bill WHERE status = $2 AND (lower(name) % $1 OR lower(name) LIKE '%' || $1 || '%')"
            " ORDER BY similarity(lower(name), $1) DESC LIMIT 5;",
            lowered,
            BillIsLaw.flag.value,
        )

        tag_matches = await ctx.bot.db.fetch(
            "SELECT DISTINCT bill_id AS id FROM bill_lookup_tag WHERE tag % $1 LIMIT 2;",
            lowered,
        )

        matches.extend(tag_matches)

        matches = {
            await Law.convert(ctx, match["id"], silent=True): None for match in matches
        }
        return list(filter(None, matches))

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[int, str], silent=False):
        try:
            bill = await super().convert(ctx, argument)
        except NotFoundError:
            raise NotFoundError(
                f"{config.NO} There is no law that matches `{argument}`."
            )

        if not bill.status.is_law:
            if silent:
                return None
            else:
                if ctx.command and ctx.command.name == "law":
                    fmt_msg = f"{config.NO} `{bill.name}` (#{bill.id}) is not an active law.\n{config.HINT} You can use `{config.BOT_PREFIX}bill {bill.id}` instead."

                else:
                    f"{config.NO} `{bill.name}` (#{bill.id}) is not an active law."

                raise NotLawError(fmt_msg)

        return bill


class Motion(commands.Converter, FuzzyableMixin):
    """
    Represents a motion that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
    """

    model = "Motion"
    fuzzy_description = f"Maybe you were looking for the `{config.BOT_PREFIX}motion search` command instead?\n"

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.title: str = kwargs.get("title")
        self.session: Session = kwargs.get("session")
        self.description: str = kwargs.get("description")
        self._link: str = kwargs.get("paste_link")
        self.name: str = self.title  # compatibility
        self.submitter_id: int = kwargs.get("submitter")
        self._bot = kwargs.get("bot")
        self.sponsor_ids: typing.List[int] = kwargs.get("sponsors", [])

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Motion) and self.id == other.id

    def __str__(self):
        return self.name

    @property
    def _fuzzy_menu_description(self):
        return f"Motion #{self.id}"

    @property
    def sponsors(self) -> typing.List[typing.Union[discord.Member, discord.User]]:
        return list(
            filter(
                None,
                [
                    self._bot.dciv.get_member(sponsor) or self._bot.get_user(sponsor)
                    for sponsor in self.sponsor_ids
                ],
            )
        )

    @property
    def formatted(self):
        return f"Motion #{self.id} - [{self.name}]({self.link})"

    @property
    def submitter(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self.submitter_id) or self._bot.get_user(
            self.submitter_id
        )
        return user

    @property
    def short_name(self) -> str:
        return textwrap.shorten(self.name, width=70)

    @property
    def link(self) -> str:
        # If the motion's description is just a Google Docs link, use that link instead of the paste link
        is_google_docs = (
            self._bot.get_cog("Law").is_google_doc_link(self.description)
            and len(self.description) <= 100
        )
        return self.description if is_google_docs else self._link

    async def withdraw(self):
        await self._bot.db.execute("DELETE FROM motion WHERE id = $1", self.id)
        await self._bot.api_request(
            "POST",
            "document/delete",
            silent=True,
            json={"id": self.id, "type": "motion"},
        )

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        matches = await ctx.bot.db.fetch(
            "SELECT id FROM motion WHERE lower(title) % $1 OR lower(title) LIKE '%' || $1 || '%'"
            " ORDER BY similarity(lower(title), $1) DESC LIMIT 6;",
            argument.lower(),
        )

        return [await Motion.convert(ctx, match["id"]) for match in matches]

    @classmethod
    async def convert(cls, ctx, argument: typing.Union[str, int]):
        try:
            arg = argument

            if isinstance(arg, str) and arg.startswith("#"):
                arg = arg[1:]

            arg = int(arg)
            motion = await ctx.bot.db.fetchrow(
                "SELECT * FROM motion WHERE id = $1", arg
            )
        except ValueError:
            motion = await ctx.bot.db.fetchrow(
                "SELECT * FROM motion WHERE lower(title) = $2 or paste_link = $1",
                argument,
                argument.lower(),
            )

        if motion is None:
            raise NotFoundError(
                f"{config.NO} There is no motion that matches `{argument}`."
            )

        sponsors = await ctx.bot.db.fetch(
            "SELECT sponsor FROM motion_sponsor WHERE motion_id = $1", motion["id"]
        )
        sponsors = [record["sponsor"] for record in sponsors]

        session = await Session.convert(ctx, motion["leg_session"])
        return cls(**motion, session=session, bot=ctx.bot, sponsors=sponsors)


class LegalConsumer:
    def __init__(
        self,
        *,
        ctx: context.CustomContext,
        objects: typing.Iterable[Bill],
        action: typing.Callable,
    ):
        self.objects = set(objects)
        self.ctx = ctx
        self.action = action
        self._filtered_out_objs = set()
        self._errors = {}

    async def filter(self, *, filter_func: typing.Callable = None, **kwargs):
        for obj in self.objects:
            if filter_func:
                fail = await maybe_coroutine(filter_func, self.ctx, obj, **kwargs)

                if fail:
                    self._filtered_out_objs.add(obj)
                    self._errors[obj] = fail

            if obj not in self._filtered_out_objs:
                try:
                    action = getattr(
                        obj.status, self.action.__name__
                    )  # this is some bullshit
                    await maybe_coroutine(action, dry=True, **kwargs)
                except IllegalOperation as e:
                    self._filtered_out_objs.add(obj)
                    self._errors[obj] = e.message

        self._passed_objs = self.objects - self._filtered_out_objs

    async def consume(self, *, scheduler=None, **kwargs):
        for obj in self.passed:
            action = getattr(obj.status, self.action.__name__)
            await maybe_coroutine(action, dry=False, **kwargs)

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
        return "\n".join(
            [
                f"-  **{obj.name}** (#{obj.id}): _{reason}_"
                for obj, reason in self._errors.items()
            ]
        )


class _BillStatusFlag(enum.Enum):
    SUBMITTED = 0
    LEG_FAILED = 1  # not for mk13
    LEG_PASSED = 2  # not for mk13
    MIN_FAILED = 3  # not for mk13
    REPEALED = 5
    LAW = 10
    FAILED_SENATE = 20
    FAILED_COMMONS = 21
    PASSED_SENATE_PENDING_COMMONS = 22
    PASSED_COMMONS_PENDING_SENATE = 23
    AWAITING_EXECUTIVE = 24
    EXECUTIVE_VETOED = 25


class IllegalOperation(DemocracivBotException):
    pass


class IllegalBillOperation(IllegalOperation):
    def __init__(
        self,
        message="You cannot perform this action on this bill in its current state.",
    ):
        self.message = message


_UNCHANGED = object()


class BillStatus:
    flag: _BillStatusFlag
    verbose_name: str
    is_law: bool = False

    GREEN = config.LEG_BILL_STATUS_GREEN
    YELLOW = config.LEG_BILL_STATUS_YELLOW
    RED = config.LEG_BILL_STATUS_RED
    GRAY = config.LEG_BILL_STATUS_GRAY

    @staticmethod
    def from_flag_value(flag):
        translation = {
            0: BillSubmitted,
            1: BillFailedLegislature,  # not for mk13
            2: BillPassedLegislature,  # not for mk13
            3: BillVetoed,  # not for mk13
            5: BillRepealed,
            10: BillIsLaw,
            20: BillFailedSenate,
            21: BillFailedCommons,
            22: BillPassedSenatePendingCommons,
            23: BillPassedCommonsPendingSenate,
            24: BillAwaitingExecutive,
            25: BillExecutiveVetoed,
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
        return f"<{self.__class__.__name__} flag={self.flag}"

    async def log_history(
        self, old_status: _BillStatusFlag, new_status: _BillStatusFlag, *, note=None
    ):
        logged_at = datetime.datetime.utcnow()
        await self._bot.db.execute(
            "INSERT INTO bill_history (bill_id, date, before_status, after_status, note) VALUES ($1, $2, $3, $4, $5)",
            self._bill.id,
            logged_at,
            old_status.value,
            new_status.value,
            note,
        )

        self._bill.status = BillStatus.from_flag_value(new_status.value)(
            self._bot, self._bill
        )
        if self._bill.history is not None:
            self._bill.history.insert(
                0,
                BillHistoryEntry(
                    before=BillStatus.from_flag_value(old_status.value)(
                        self._bot, self._bill
                    ),
                    after=BillStatus.from_flag_value(new_status.value)(
                        self._bot, self._bill
                    ),
                    date=logged_at,
                    note=note,
                ),
            )

        if old_status is _BillStatusFlag.LAW or new_status is _BillStatusFlag.LAW:
            await self._bot.api_request(
                "POST",
                "document/update",
                silent=True,
                json={"id": self._bill.id, "type": "bill"},
            )

    async def veto(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def withdraw(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def pass_into_law(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def pass_from_legislature(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def fail_in_legislature(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def override_veto(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def repeal(self, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def resubmit(self, dry=False, *, resubmitter: discord.Member, **kwargs):
        raise IllegalBillOperation()

    async def superpass(self, *, dry=False, **kwargs):
        raise IllegalBillOperation()

    async def sponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        raise IllegalBillOperation(
            "You can only sponsor recently submitted bills that were not voted on yet."
        )

    async def unsponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        raise IllegalBillOperation(
            "You can only unsponsor recently submitted bills that were not voted on yet."
        )

    @property
    def _uses_bicameral_rendering(self) -> bool:
        return (
            self._bill.session is not None and self._bill.session.house in HOUSE_NAMES
        )

    @property
    def _uses_procedure_rendering(self) -> bool:
        return self._uses_bicameral_rendering and self._bill.is_procedure

    @staticmethod
    def house_name(house: typing.Optional[str]) -> str:
        return display_house_name(house)

    @staticmethod
    def other_house(house: str) -> str:
        try:
            return {"senate": "commons", "commons": "senate"}[house]
        except KeyError as exc:
            raise IllegalBillOperation(
                "This action requires either the Senate or the Commons."
            )

    def _format_session_name(self, session: typing.Optional[Session] = None) -> str:
        session = session or self._bill.session

        if session is None:
            return "Session"

        if session.house in HOUSE_NAMES:
            return session.display_name

        return f"Session #{session.id}"

    def _hidden_resubmitter(self, resubmitter: discord.Member) -> str:
        return (
            f"[{resubmitter}](https://democracivbank.com/u/{resubmitter.id} "
            f'"{resubmitter.id}")'
        )

    def _render_bicameral_status(
        self,
        *,
        senate: typing.Tuple[str, str],
        commons: typing.Tuple[str, str],
        executive: typing.Tuple[str, str],
        law: typing.Tuple[str, str],
        verbose=True,
    ):
        if verbose:
            return (
                f"Senate: {senate[0]} *({senate[1]})*\n"
                f"Commons: {commons[0]} *({commons[1]})*\n"
                f"Executive: {executive[0]} *({executive[1]})*\n"
                f"Law: {law[0]} *({law[1]})*\n"
            )

        return f"{senate[0]}{commons[0]}{executive[0]}{law[0]}"

    def _render_procedure_status(
        self,
        *,
        senate: typing.Optional[typing.Tuple[str, str]] = None,
        commons: typing.Optional[typing.Tuple[str, str]] = None,
        law: typing.Tuple[str, str],
        verbose=True,
    ):
        return self._render_bicameral_status(
            senate=senate or (self.GRAY, "Not Required"),
            commons=commons or (self.GRAY, "Not Required"),
            executive=(self.GRAY, "Not Required"),
            law=law,
            verbose=verbose,
        )

    def _bicameral_law_executive_status(self) -> typing.Tuple[str, str]:
        default = (self.GREEN, "Approved")

        for entry in self._bill.history or []:
            if entry.after.flag is not _BillStatusFlag.LAW:
                continue

            if entry.before.flag is _BillStatusFlag.EXECUTIVE_VETOED:
                return self.GREEN, "Veto Overridden by Senate"

            if entry.before.flag is _BillStatusFlag.AWAITING_EXECUTIVE:
                if entry.note and "automatically after 48 hours" in entry.note.lower():
                    return self.GREEN, "Auto-passed after 48 hours"

                return default

            break

        return default

    def _require_current_house(self, acting_house: str):
        if self._bill.session is None or self._bill.session.house != acting_house:
            raise IllegalBillOperation(
                f"This bill is not currently before the {self.house_name(acting_house)}."
            )

    async def _fetch_session(self, session_id: int) -> Session:
        return await Session.convert(context.MockContext(self._bot), session_id)

    async def _get_open_session(self, house: str) -> typing.Optional[Session]:
        session_id = await self._bot.db.fetchval(
            "SELECT id FROM legislature_session WHERE status != 'Closed' AND house = $1 ORDER BY id DESC LIMIT 1",
            house,
        )

        if session_id is None:
            return None

        return await self._fetch_session(session_id)

    async def _get_submission_session(
        self, house: typing.Optional[str]
    ) -> typing.Optional[Session]:
        if house in HOUSE_NAMES:
            session_id = await self._bot.db.fetchval(
                "SELECT id FROM legislature_session WHERE status = 'Submission Period' AND house = $1 ORDER BY id DESC LIMIT 1",
                house,
            )
        else:
            session_id = await self._bot.db.fetchval(
                "SELECT id FROM legislature_session WHERE status = 'Submission Period' ORDER BY id DESC LIMIT 1"
            )

        if session_id is None:
            return None

        return await self._fetch_session(session_id)

    async def _apply_status(
        self,
        old_status: _BillStatusFlag,
        new_status: _BillStatusFlag,
        *,
        note=None,
        leg_session=_UNCHANGED,
        executive_deadline_at=_UNCHANGED,
    ):
        query = ["status = $1"]
        args = [new_status.value]
        param_no = 2

        if leg_session is not _UNCHANGED:
            query.append(f"leg_session = ${param_no}")
            args.append(leg_session)
            param_no += 1

        if executive_deadline_at is not _UNCHANGED:
            query.append(f"executive_deadline_at = ${param_no}")
            args.append(executive_deadline_at)
            param_no += 1

        args.append(self._bill.id)

        await self._bot.db.execute(
            f"UPDATE bill SET {', '.join(query)} WHERE id = ${param_no}", *args
        )

        if leg_session is not _UNCHANGED:
            await self._bot.db.execute(
                "INSERT INTO bill_session (bill_id, leg_session) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                self._bill.id,
                leg_session,
            )
            self._bill.session = await self._fetch_session(leg_session)

        if executive_deadline_at is not _UNCHANGED:
            self._bill.executive_deadline_at = executive_deadline_at

        await self.log_history(old_status, new_status, note=note)

    async def _delete_matching_history(
        self, *, after_status: _BillStatusFlag, note: str
    ):
        await self._bot.db.execute(
            "DELETE FROM bill_history WHERE bill_id = $1 AND after_status = $2 AND note = $3",
            self._bill.id,
            after_status.value,
            note,
        )

    async def _mark_failed_in_house(
        self, *, acting_house: str, old_status: _BillStatusFlag
    ):
        self._require_current_house(acting_house)
        new_status = (
            _BillStatusFlag.FAILED_SENATE
            if acting_house == "senate"
            else _BillStatusFlag.FAILED_COMMONS
        )

        await self._apply_status(
            old_status,
            new_status,
            note=f"Failed in {self._format_session_name()}",
            executive_deadline_at=None,
        )

    async def _pass_procedure_in_house(
        self, *, acting_house: str, old_status: _BillStatusFlag
    ):
        self._require_current_house(acting_house)

        if acting_house != self._bill.origin_house:
            raise IllegalBillOperation(
                f"Only the {self._bill.origin_house_name} can pass this chamber procedure."
            )

        await self._apply_status(
            old_status,
            _BillStatusFlag.LAW,
            note=(
                f"Passed into law as a {self.house_name(acting_house)} procedure during "
                f"{self._format_session_name()}."
            ),
            executive_deadline_at=None,
        )

    async def _forward_after_house_pass(
        self, *, acting_house: str, old_status: _BillStatusFlag
    ):
        self._require_current_house(acting_house)
        other_house = self.other_house(acting_house)
        new_status = (
            _BillStatusFlag.PASSED_SENATE_PENDING_COMMONS
            if acting_house == "senate"
            else _BillStatusFlag.PASSED_COMMONS_PENDING_SENATE
        )
        other_session = await self._get_open_session(other_house)
        note = f"Passed the {self.house_name(acting_house)} during {self._format_session_name()}"

        if other_session is not None:
            await self._apply_status(
                old_status,
                new_status,
                note=f"{note} and sent to {other_session.display_name}",
                leg_session=other_session.id,
                executive_deadline_at=None,
            )
            return

        await self._apply_status(
            old_status,
            new_status,
            note=(
                f"{note} and queued for the next "
                f"{self.house_name(other_house)} session"
            ),
            executive_deadline_at=None,
        )

    async def _send_to_executive(
        self, *, acting_house: str, old_status: _BillStatusFlag
    ):
        self._require_current_house(acting_house)
        deadline = datetime.datetime.utcnow() + datetime.timedelta(hours=48)
        # deadline_fmt = (
        #    f"<t:{int(deadline.replace(tzinfo=datetime.timezone.utc).timestamp())}:F>"
        # )

        deadline_fmt = deadline.strftime("%B %d, %Y at %H:%M")

        await self._apply_status(
            old_status,
            _BillStatusFlag.AWAITING_EXECUTIVE,
            note=(
                f"Passed the {self.house_name(acting_house)} during {self._format_session_name()} "
                f"and sent to the Executive until {deadline_fmt}"
            ),
            executive_deadline_at=deadline,
        )

    async def _resubmit_to_origin_house(
        self, *, old_status: _BillStatusFlag, resubmitter: discord.Member
    ):
        target_session = await self._get_submission_session(self._bill.origin_house)

        if target_session is None:
            raise IllegalBillOperation(
                f"There is no {self._bill.origin_house_name} session in Submission Period right now, so the bill cannot be resubmitted."
            )

        await self._apply_status(
            old_status,
            _BillStatusFlag.SUBMITTED,
            note=(
                f"Resubmitted from {self._format_session_name()} to "
                f"{target_session.display_name} by {self._hidden_resubmitter(resubmitter)}"
            ),
            leg_session=target_session.id,
            executive_deadline_at=None,
        )

    def emojified_status(self, verbose=True):
        raise NotImplementedError()


class BillSubmitted(BillStatus):
    is_law = False
    flag = _BillStatusFlag.SUBMITTED
    verbose_name = "Submitted"

    async def withdraw(self, dry=False, **kwargs):
        if dry:
            return

        await self._bot.db.execute("DELETE FROM bill WHERE id = $1", self._bill.id)
        await self._bot.api_request(
            "POST",
            "document/delete",
            silent=True,
            json={"id": self._bill.id, "type": "bill"},
        )

    async def fail_in_legislature(self, dry=False, **kwargs):
        if dry:
            return

        acting_house = kwargs.get("acting_house")

        if acting_house in HOUSE_NAMES:
            await self._mark_failed_in_house(
                acting_house=acting_house, old_status=self.flag
            )
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LEG_FAILED,
            note=f"Failed in Session #{self._bill.session.id}",
            executive_deadline_at=None,
        )

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        acting_house = kwargs.get("acting_house")

        if acting_house in HOUSE_NAMES:
            if self._bill.is_procedure:
                await self._pass_procedure_in_house(
                    acting_house=acting_house, old_status=self.flag
                )
                return

            await self._forward_after_house_pass(
                acting_house=acting_house, old_status=self.flag
            )
            return

        # non-mk13 bills
        if self._bill.is_vetoable:
            await self._apply_status(
                self.flag,
                _BillStatusFlag.LEG_PASSED,
                note=f"Passed the {mk.MarkConfig.LEGISLATURE_NAME} during Session #{self._bill.session.id}",
                executive_deadline_at=None,
            )
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=(
                f"Passed into law by the {mk.MarkConfig.LEGISLATURE_NAME} during Session "
                f"#{self._bill.session.id}. This bill was set to be non-vetoable so it "
                f"skipped the {mk.MarkConfig.MINISTRY_NAME}."
            ),
            executive_deadline_at=None,
        )

    async def sponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        if dry:
            return

        await self._bot.db.execute(
            "INSERT INTO bill_sponsor (bill_id, sponsor) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            self._bill.id,
            sponsor.id,
        )

    async def unsponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        if dry:
            return

        await self._bot.db.execute(
            "DELETE FROM bill_sponsor WHERE bill_id = $1 AND sponsor = $2",
            self._bill.id,
            sponsor.id,
        )

    async def superpass(self, dry=False, **kwargs):
        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=(
                f"Passed into law with a super-majority by the "
                f"{mk.MarkConfig.LEGISLATURE_NAME} during Session #{self._bill.session.id}"
            ),
            executive_deadline_at=None,
        )

    def emojified_status(self, verbose=True):
        if self._uses_procedure_rendering:
            if self._bill.origin_house == "senate":
                return self._render_procedure_status(
                    senate=(self.YELLOW, "Waiting on Senate"),
                    law=(self.GRAY, "Not Yet Law"),
                    verbose=verbose,
                )

            return self._render_procedure_status(
                commons=(self.YELLOW, "Waiting on Commons"),
                law=(self.GRAY, "Not Yet Law"),
                verbose=verbose,
            )

        if self._uses_bicameral_rendering:
            senate = (
                (self.YELLOW, "Waiting on Senate")
                if self._bill.session.house == "senate"
                else (self.GRAY, "Waiting on Commons First")
            )
            commons = (
                (self.YELLOW, "Waiting on Commons")
                if self._bill.session.house == "commons"
                else (self.GRAY, "Waiting on Senate First")
            )
            return self._render_bicameral_status(
                senate=senate,
                commons=commons,
                executive=(self.GRAY, "Waiting on Both Houses"),
                law=(self.GRAY, "Not Yet Law"),
                verbose=verbose,
            )

        if verbose:
            if self._bill.is_vetoable:
                ministry = f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Waiting on {self._bot.mk.LEGISLATURE_NAME})*\n"
            else:
                ministry = (
                    f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Not Vetoable)*\n"
                )

            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.YELLOW} *(Not Voted On Yet)*\n"
                f"{ministry}"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.YELLOW}{self.YELLOW if self._bill.is_vetoable else self.GRAY}{self.GRAY}"


class BillFailedSenate(BillStatus):
    is_law = False
    flag = _BillStatusFlag.FAILED_SENATE
    verbose_name = "Failed in the Senate"

    async def pass_from_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "senate":
            raise IllegalBillOperation("Only the Senate can pass a Senate-failed bill.")

        if dry:
            return

        await self._delete_matching_history(
            after_status=self.flag, note=f"Failed in {self._format_session_name()}"
        )

        if self._bill.is_procedure:
            await self._pass_procedure_in_house(
                acting_house=acting_house, old_status=self.flag
            )
            return

        if self._bill.origin_house == "commons":
            await self._send_to_executive(
                acting_house=acting_house, old_status=self.flag
            )
            return

        await self._forward_after_house_pass(
            acting_house=acting_house, old_status=self.flag
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    def emojified_status(self, verbose=True):
        if self._uses_procedure_rendering:
            return self._render_procedure_status(
                senate=(self.RED, "Failed"),
                law=(self.GRAY, "Not Yet Law"),
                verbose=verbose,
            )

        commons = (
            (self.GREEN, "Passed")
            if self._bill.origin_house == "commons"
            else (self.GRAY, "Not Yet Before Commons")
        )
        return self._render_bicameral_status(
            senate=(self.RED, "Failed"),
            commons=commons,
            executive=(self.GRAY, "Waiting on Both Houses"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillFailedCommons(BillStatus):
    is_law = False
    flag = _BillStatusFlag.FAILED_COMMONS
    verbose_name = "Failed in the Commons"

    async def pass_from_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "commons":
            raise IllegalBillOperation(
                "Only the Commons can pass a Commons-failed bill."
            )

        if dry:
            return

        await self._delete_matching_history(
            after_status=self.flag, note=f"Failed in {self._format_session_name()}"
        )

        if self._bill.is_procedure:
            await self._pass_procedure_in_house(
                acting_house=acting_house, old_status=self.flag
            )
            return

        if self._bill.origin_house == "senate":
            await self._send_to_executive(
                acting_house=acting_house, old_status=self.flag
            )
            return

        await self._forward_after_house_pass(
            acting_house=acting_house, old_status=self.flag
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    def emojified_status(self, verbose=True):
        if self._uses_procedure_rendering:
            return self._render_procedure_status(
                commons=(self.RED, "Failed"),
                law=(self.GRAY, "Not Yet Law"),
                verbose=verbose,
            )

        senate = (
            (self.GREEN, "Passed")
            if self._bill.origin_house == "senate"
            else (self.GRAY, "Not Yet Before Senate")
        )
        return self._render_bicameral_status(
            senate=senate,
            commons=(self.RED, "Failed"),
            executive=(self.GRAY, "Waiting on Both Houses"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillPassedSenatePendingCommons(BillStatus):
    is_law = False
    flag = _BillStatusFlag.PASSED_SENATE_PENDING_COMMONS
    verbose_name = "Passed the Senate"

    async def fail_in_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "commons":
            raise IllegalBillOperation("Only the Commons can fail this bill now.")

        if dry:
            return

        await self._mark_failed_in_house(
            acting_house=acting_house, old_status=self.flag
        )

    async def pass_from_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "commons":
            raise IllegalBillOperation(
                "This bill still needs to be passed by the Commons."
            )

        if dry:
            return

        await self._send_to_executive(acting_house=acting_house, old_status=self.flag)

    def emojified_status(self, verbose=True):
        commons_label = (
            "Waiting on Commons"
            if self._bill.session.house == "commons"
            else "Queued for the next Commons session"
        )
        return self._render_bicameral_status(
            senate=(self.GREEN, "Passed"),
            commons=(self.YELLOW, commons_label),
            executive=(self.GRAY, "Waiting on Commons"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillPassedCommonsPendingSenate(BillStatus):
    is_law = False
    flag = _BillStatusFlag.PASSED_COMMONS_PENDING_SENATE
    verbose_name = "Passed the Commons"

    async def fail_in_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "senate":
            raise IllegalBillOperation("Only the Senate can fail this bill now.")

        if dry:
            return

        await self._mark_failed_in_house(
            acting_house=acting_house, old_status=self.flag
        )

    async def pass_from_legislature(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "senate":
            raise IllegalBillOperation(
                "This bill still needs to be passed by the Senate."
            )

        if dry:
            return

        await self._send_to_executive(acting_house=acting_house, old_status=self.flag)

    def emojified_status(self, verbose=True):
        senate_label = (
            "Waiting on Senate"
            if self._bill.session.house == "senate"
            else "Queued for the next Senate session"
        )
        return self._render_bicameral_status(
            senate=(self.YELLOW, senate_label),
            commons=(self.GREEN, "Passed"),
            executive=(self.GRAY, "Waiting on Senate"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillFailedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_FAILED
    verbose_name = f"Failed in the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        await self._delete_matching_history(
            after_status=self.flag, note=f"Failed in Session #{self._bill.session.id}"
        )

        if self._bill.is_vetoable:
            await self._apply_status(
                self.flag,
                _BillStatusFlag.LEG_PASSED,
                note=f"Passed the {mk.MarkConfig.LEGISLATURE_NAME} during Session #{self._bill.session.id}",
                executive_deadline_at=None,
            )
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=(
                f"Passed into law by the {mk.MarkConfig.LEGISLATURE_NAME} during Session "
                f"#{self._bill.session.id}. This bill was set to be non-vetoable so it "
                f"skipped the {mk.MarkConfig.MINISTRY_NAME}."
            ),
            executive_deadline_at=None,
        )

    async def superpass(self, dry=False, **kwargs):
        if dry:
            return

        await self._delete_matching_history(
            after_status=self.flag, note=f"Failed in Session #{self._bill.session.id}"
        )

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=(
                f"Passed into law with a super-majority by the "
                f"{mk.MarkConfig.LEGISLATURE_NAME} during Session #{self._bill.session.id}"
            ),
            executive_deadline_at=None,
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.RED} *(Failed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Failed in the {self._bot.mk.LEGISLATURE_NAME})*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.RED}{self.GRAY}{self.GRAY}"


# todo: auto pass after 48h
class BillPassedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_PASSED
    verbose_name = f"Passed the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def veto(self, dry=False):
        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.MIN_FAILED,
            executive_deadline_at=None,
        )

    async def pass_into_law(self, dry=False):
        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=f"Passed into Law by the {mk.MarkConfig.MINISTRY_NAME}",
            executive_deadline_at=None,
        )

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

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    async def override_veto(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house in HOUSE_NAMES and acting_house != "senate":
            raise IllegalBillOperation(
                "Only the Senate can override an Executive veto."
            )

        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=f"Veto was overridden by the {mk.MarkConfig.LEGISLATURE_NAME}",
            executive_deadline_at=None,
        )

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.RED} *(Vetoed)*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.GREEN}{self.RED}{self.GRAY}"


class BillAwaitingExecutive(BillStatus):
    is_law = False
    flag = _BillStatusFlag.AWAITING_EXECUTIVE
    verbose_name = "Awaiting Executive Action"

    async def veto(self, dry=False, **kwargs):
        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.EXECUTIVE_VETOED,
            note=f"Vetoed by the {self._bot.mk.MINISTRY_NAME}",
            executive_deadline_at=None,
        )

    async def pass_into_law(self, dry=False, **kwargs):
        if dry:
            return

        auto_pass = kwargs.get("auto_pass", False)
        note = (
            f"Passed into law automatically after 48 hours without action by the {self._bot.mk.MINISTRY_NAME}"
            if auto_pass
            else f"Passed into law by the {self._bot.mk.MINISTRY_NAME}"
        )

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=note,
            executive_deadline_at=None,
        )

    def emojified_status(self, verbose=True):
        return self._render_bicameral_status(
            senate=(self.GREEN, "Passed"),
            commons=(self.GREEN, "Passed"),
            executive=(self.YELLOW, "Waiting on Executive"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillExecutiveVetoed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.EXECUTIVE_VETOED
    verbose_name = "Vetoed by the Executive"

    async def override_veto(self, dry=False, **kwargs):
        acting_house = kwargs.get("acting_house")

        if acting_house != "senate":
            raise IllegalBillOperation(
                "Only the Senate can override an Executive veto."
            )

        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note="Veto overridden by the Senate",
            executive_deadline_at=None,
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    def emojified_status(self, verbose=True):
        return self._render_bicameral_status(
            senate=(self.GREEN, "Passed"),
            commons=(self.GREEN, "Passed"),
            executive=(self.RED, "Vetoed"),
            law=(self.GRAY, "Not Yet Law"),
            verbose=verbose,
        )


class BillIsLaw(BillStatus):
    is_law = True
    verbose_name = "Active Law"
    flag = _BillStatusFlag.LAW

    async def repeal(self, dry=False):
        if dry:
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.REPEALED,
            executive_deadline_at=None,
        )

    def emojified_status(self, verbose=True):
        if self._uses_procedure_rendering:
            if self._bill.origin_house == "senate":
                return self._render_procedure_status(
                    senate=(self.GREEN, "Passed"),
                    law=(self.GREEN, "Active Law"),
                    verbose=verbose,
                )

            return self._render_procedure_status(
                commons=(self.GREEN, "Passed"),
                law=(self.GREEN, "Active Law"),
                verbose=verbose,
            )

        if self._uses_bicameral_rendering:
            return self._render_bicameral_status(
                senate=(self.GREEN, "Passed"),
                commons=(self.GREEN, "Passed"),
                executive=self._bicameral_law_executive_status(),
                law=(self.GREEN, "Active Law"),
                verbose=verbose,
            )

        if verbose:
            if self._bill.is_vetoable:
                min = f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
            else:
                min = f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Not Vetoable)*\n"

            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{min}"
                f"Law: {self.GREEN} *(Active Law)*\n"
            )

        return f"{self.GREEN}{self.GREEN if self._bill.is_vetoable else self.GRAY}{self.GREEN}"


class BillRepealed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.REPEALED
    verbose_name = "Repealed"

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        if self._bill.is_vetoable:
            await self._apply_status(
                self.flag,
                _BillStatusFlag.LEG_PASSED,
                note=f"Repeal reversed & Passed the {mk.MarkConfig.LEGISLATURE_NAME}",
                executive_deadline_at=None,
            )
            return

        await self._apply_status(
            self.flag,
            _BillStatusFlag.LAW,
            note=(
                f"Repeal reversed & Passed into law by the "
                f"{mk.MarkConfig.LEGISLATURE_NAME}. This bill was set to be non-vetoable "
                f"so it skipped the {mk.MarkConfig.MINISTRY_NAME}."
            ),
            executive_deadline_at=None,
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        if dry:
            return

        await self._resubmit_to_origin_house(
            old_status=self.flag, resubmitter=resubmitter
        )

    def emojified_status(self, verbose=True):
        if self._uses_procedure_rendering:
            if self._bill.origin_house == "senate":
                return self._render_procedure_status(
                    senate=(self.GREEN, "Passed"),
                    law=(self.RED, "Repealed"),
                    verbose=verbose,
                )

            return self._render_procedure_status(
                commons=(self.GREEN, "Passed"),
                law=(self.RED, "Repealed"),
                verbose=verbose,
            )

        if self._uses_bicameral_rendering:
            return self._render_bicameral_status(
                senate=(self.GREEN, "Passed"),
                commons=(self.GREEN, "Passed"),
                executive=self._bicameral_law_executive_status(),
                law=(self.RED, "Repealed"),
                verbose=verbose,
            )

        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
                f"Law: {self.RED} *(Repealed)*\n"
            )

        return f"{self.GREEN}{self.GREEN}{self.RED}"
