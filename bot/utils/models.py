import datetime
import enum
import re
import textwrap
import typing
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
        self._speaker: int = kwargs.get("speaker")
        self._bot = kwargs.get("bot")

    @property
    def speaker(self) -> typing.Union[discord.Member, discord.User, None]:
        user = self._bot.dciv.get_member(self._speaker) or self._bot.get_user(
            self._speaker
        )
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
    fuzzy_description = (
        f"Maybe you were looking for the "
        f"`{config.BOT_PREFIX}{mk.MarkConfig.LEGISLATURE_COMMAND} bill search` "
        f"command instead?\n"
    )

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.session: Session = kwargs.get("session")
        self.link: str = kwargs.get("link")
        self.tiny_link: str = self.link  # deprecated
        self.description: str = kwargs.get("submitter_description")
        self.is_vetoable: bool = kwargs.get("is_vetoable")
        self.status: BillStatus = kwargs.get("status")
        self.content: str = kwargs.get("content")
        self.submitter_id: int = kwargs.get("submitter")
        self._bot = kwargs.get("bot")
        self.sponsor_ids: typing.List[int] = kwargs.get("sponsors", [])

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
            "POST", "document/update", silent=True, json={"label": f"bill_{self.id}"}
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

    async def fetch_name_and_keywords(self) -> typing.Tuple[str, typing.List[str], str]:

        try:
            response: typing.Dict = await self._bot.run_apps_script(
                script_id="MtyscpHHIi0Ck1h8XfuBIn2qnXKElby-M",
                function="main",
                parameters=[self.link],
            )

            self.name = name = response["response"]["result"]["title"]
            self.content = content = response["response"]["result"]["content"]
            keywords = [
                word["ngram"]
                for word in response["response"]["result"]["keywords"]["keywords"]
                if word["ngram"]
            ]

        except (DemocracivBotException, KeyError):
            keywords = []
            self.name = name = ""
            self.content = content = ""

        async with self._bot.session.post(
            "http://yake.inesctec.pt/yake/v2/extract_keywords?max_ngram_size=2&number_of_keywords=20&highlight=false",
            data={"content": self.description},
        ) as r:

            if r.status == 200:
                js = await r.json()

                try:
                    keywords.extend(
                        [word["ngram"] for word in js["keywords"] if word["ngram"]]
                    )
                except KeyError:
                    pass

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
                raise NotLawError(
                    f"{config.NO} `{bill.name}` (#{bill.id}) is not an active law."
                )

        return bill


class Motion(commands.Converter, FuzzyableMixin):
    """
    Represents a motion that someone submitted to a session of the Legislature.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by ID.
    """

    model = "Motion"
    fuzzy_description = (
        f"Maybe you were looking for the "
        f"`{config.BOT_PREFIX}{mk.MarkConfig.LEGISLATURE_COMMAND} motion search` "
        f"command instead?\n"
    )

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
            "POST", "document/delete", silent=True, json={"label": f"motion_{self.id}"}
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
    LEG_FAILED = 1
    LEG_PASSED = 2
    # MIN_FAILED = 3
    # MIN_PASSED = 4
    REPEALED = 5


class IllegalOperation(DemocracivBotException):
    pass


class IllegalBillOperation(IllegalOperation):
    def __init__(
        self,
        message="You cannot perform this action on this bill in its current state.",
    ):
        self.message = message


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
            1: BillFailedLegislature,
            2: BillPassedLegislature,
            # 3: BillVetoed,
            # 4: BillPassedMinistry,
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
        return f"<{self.__class__.__name__} flag={self.flag}"

    async def log_history(
        self, old_status: _BillStatusFlag, new_status: _BillStatusFlag, *, note=None
    ):
        await self._bot.db.execute(
            "INSERT INTO bill_history (bill_id, date, before_status, after_status, note) VALUES ($1, $2, $3, $4, $5)",
            self._bill.id,
            datetime.datetime.utcnow(),
            old_status.value,
            new_status.value,
            note,
        )

        self._bill.status = BillStatus.from_flag_value(new_status.value)(
            self._bot, self._bill
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

    async def sponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        raise IllegalBillOperation(
            "You can only sponsor recently submitted bills that were not voted on yet."
        )

    async def unsponsor(self, *, dry=False, sponsor: discord.Member, **kwargs):
        raise IllegalBillOperation(
            "You can only unsponsor recently submitted bills that were not voted on yet."
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
            json={"label": f"bill_{self._bill.id}"},
        )

    async def fail_in_legislature(self, dry=False, **kwargs):
        if dry:
            return

        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_FAILED.value,
            self._bill.id,
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.LEG_FAILED,
            note=f"Failed in Session #{self._bill.session.id}",
        )

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        # if self._bill.is_vetoable:
        #     await self._bot.db.execute(
        #         "UPDATE bill SET status = $1 WHERE id = $2",
        #         _BillStatusFlag.LEG_PASSED.value,
        #         self._bill.id,
        #     )
        #
        #     await self.log_history(self.flag, _BillStatusFlag.LEG_PASSED)
        #
        # else:
        #     await self._bot.db.execute(
        #         "UPDATE bill SET status = $1 WHERE id = $2",
        #         _BillStatusFlag.MIN_PASSED.value,
        #         self._bill.id,
        #     )
        #
        #     await self.log_history(self.flag, _BillStatusFlag.LEG_PASSED)
        #     await self.log_history(_BillStatusFlag.LEG_PASSED, _BillStatusFlag.MIN_PASSED)

        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_PASSED.value,
            self._bill.id,
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.LEG_PASSED,
            note=f"Passed into law by {mk.MarkConfig.LEGISLATURE_NAME} "
            f"during Session #{self._bill.session.id}",
        )
        # await self.log_history(_BillStatusFlag.LEG_PASSED, _BillStatusFlag.MIN_PASSED)

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

    def emojified_status(self, verbose=True):
        if verbose:
            # if self._bill.is_vetoable:
            #     ministry = (
            #         f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Waiting on {self._bot.mk.LEGISLATURE_NAME})*\n"
            #     )
            # else:
            #     ministry = f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Not Veto-able)*\n"

            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.YELLOW} *(Not Voted On Yet)*\n"
                # f"{ministry}"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.YELLOW}{self.GRAY}"


class BillFailedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_FAILED
    verbose_name = f"Failed in {mk.MarkConfig.LEGISLATURE_NAME}"

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        # if self._bill.is_vetoable:
        #     await self._bot.db.execute(
        #         "UPDATE bill SET status = $1 WHERE id = $2",
        #         _BillStatusFlag.LEG_PASSED.value,
        #         self._bill.id,
        #     )
        #
        #     await self.log_history(self.flag, _BillStatusFlag.LEG_PASSED)
        #
        # else:
        #     await self._bot.db.execute(
        #         "UPDATE bill SET status = $1 WHERE id = $2",
        #         _BillStatusFlag.MIN_PASSED.value,
        #         self._bill.id,
        #     )
        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_PASSED.value,
            self._bill.id,
        )

        # delete "Failed in Session .." history record
        await self._bot.db.execute(
            "DELETE FROM bill_history WHERE bill_id = $1 AND before_status = $2 "
            "AND after_status = $3 AND note = $4",
            self._bill.id,
            _BillStatusFlag.SUBMITTED.value,
            _BillStatusFlag.LEG_FAILED.value,
            f"Failed in Session #{self._bill.session.id}",
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.LEG_PASSED,
            note=f"Passed into law by {mk.MarkConfig.LEGISLATURE_NAME} "
            f"during Session #{self._bill.session.id}",
        )
        # await self.log_history(_BillStatusFlag.LEG_PASSED, _BillStatusFlag.MIN_PASSED)

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        session = await self._bot.db.fetchval(
            "SELECT id FROM legislature_session WHERE status = 'Submission Period'"
        )

        if not session:
            raise IllegalBillOperation(
                f"There is no session in Submission Period right now, so the bill cannot be resubmitted."
            )

        if dry:
            return

        await self._bot.db.execute(
            "UPDATE bill SET status = $1, leg_session = $3 WHERE id = $2",
            _BillStatusFlag.SUBMITTED.value,
            self._bill.id,
            session,
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.SUBMITTED,
            note=f"Resubmitted from Session #{self._bill.session.id} to Session #{session} by "
            f"[{resubmitter}](https://democracivbank.com/u/{resubmitter.id} "
            f'"{resubmitter.id}")',
        )  # hyperlink to "hide" discord user id in embed, but
        # show if user clicks on url. doesn't matter what url,
        # just want to be able to see the resubmitter's id but
        # in a nice way

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.RED} *(Failed)*\n"
                # f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Failed in the {self._bot.mk.LEGISLATURE_NAME})*\n"
                f"Law: {self.GRAY}\n"
            )

        return f"{self.RED}{self.GRAY}"


class BillPassedLegislature(BillStatus):
    is_law = True
    flag = _BillStatusFlag.LEG_PASSED
    verbose_name = f"Passed into law by {mk.MarkConfig.LEGISLATURE_NAME}"

    # async def veto(self, dry=False):
    #     if dry:
    #         return
    #
    #     await self._bot.db.execute(
    #         "UPDATE bill SET status = $1 WHERE id = $2",
    #         _BillStatusFlag.MIN_FAILED.value,
    #         self._bill.id,
    #     )
    #     await self.log_history(self.flag, _BillStatusFlag.MIN_FAILED)

    # async def pass_into_law(self, dry=False):
    #     if dry:
    #         return
    #
    #     await self._bot.db.execute(
    #         "UPDATE bill SET status = $1 WHERE id = $2",
    #         _BillStatusFlag.MIN_PASSED.value,
    #         self._bill.id,
    #     )
    #     await self.log_history(self.flag, _BillStatusFlag.MIN_PASSED)

    async def repeal(self, dry=False, **kwargs):
        if dry:
            return

        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.REPEALED.value,
            self._bill.id,
        )

        await self.log_history(self.flag, _BillStatusFlag.REPEALED, note="Repealed")

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                f"Law: {self.GREEN} *(Active Law)*\n"
            )

        return f"{self.GREEN}{self.GREEN}"


# class BillVetoed(BillStatus):
#     is_law = False
#     flag = _BillStatusFlag.MIN_FAILED
#     verbose_name = f"Vetoed by the {mk.MarkConfig.MINISTRY_NAME}"
#
#     async def override_veto(self, dry=False):
#         if dry:
#             return
#
#         await self._bot.db.execute(
#             "UPDATE bill SET status = $1 WHERE id = $2",
#             _BillStatusFlag.MIN_PASSED.value,
#             self._bill.id,
#         )
#
#         await self.log_history(self.flag, _BillStatusFlag.MIN_PASSED)
#
#     def emojified_status(self, verbose=True):
#         if verbose:
#             return (
#                 f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
#                 f"{self._bot.mk.MINISTRY_NAME}: {self.RED} *(Vetoed)*\n"
#                 f"Law: {self.GRAY}\n"
#             )
#
#         return f"{self.GREEN}{self.RED}{self.GRAY}"
#
#
# class BillPassedMinistry(BillStatus):
#     is_law = True
#     flag = _BillStatusFlag.MIN_PASSED
#     verbose_name = "Passed into Law"
#
#     async def repeal(self, dry=False):
#         if dry:
#             return
#
#         await self._bot.db.execute(
#             "UPDATE bill SET status = $1 WHERE id = $2",
#             _BillStatusFlag.REPEALED.value,
#             self._bill.id,
#         )
#
#         await self.log_history(self.flag, _BillStatusFlag.REPEALED)
#
#     def emojified_status(self, verbose=True):
#         if verbose:
#             if self._bill.is_vetoable:
#                 ministry = f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
#             else:
#                 ministry = f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Not Veto-able)*\n"
#
#             return (
#                 f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
#                 f"{ministry}"
#                 f"Law: {self.GREEN} *(Active Law)*\n"
#             )
#
#         return f"{self.GREEN}{self.GREEN if self._bill.is_vetoable else self.GRAY}{self.GREEN}"


BillIsLaw = BillPassedLegislature


class BillRepealed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.REPEALED
    verbose_name = "Repealed"

    async def pass_from_legislature(self, dry=False, **kwargs):
        if dry:
            return

        await self._bot.db.execute(
            "UPDATE bill SET status = $1 WHERE id = $2",
            _BillStatusFlag.LEG_PASSED.value,
            self._bill.id,
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.LEG_PASSED,
            note=f"Repeal reversed & Passed into law by {mk.MarkConfig.LEGISLATURE_NAME}",
        )

    async def resubmit(self, dry=False, *, resubmitter, **kwargs):
        session = await self._bot.db.fetchval(
            "SELECT id FROM legislature_session WHERE status = 'Submission Period'"
        )

        if not session:
            raise IllegalBillOperation(
                f"There is no session in Submission Period right now, so the bill cannot be resubmitted."
            )

        if dry:
            return

        await self._bot.db.execute(
            "UPDATE bill SET status = $1, leg_session = $3 WHERE id = $2",
            _BillStatusFlag.SUBMITTED.value,
            self._bill.id,
            session,
        )

        await self.log_history(
            self.flag,
            _BillStatusFlag.SUBMITTED,
            note=f"Resubmitted from Session #{self._bill.session.id} to Session #{session} by "
            f"[{resubmitter}](https://democracivbank.com/u/{resubmitter.id} "
            f'"{resubmitter.id}")',
        )  # hyperlink to "hide" discord user id in embed, but
        # show if user clicks on url. doesn't matter what url,
        # just want to be able to see the resubmitter's id but
        # in a nice way

    def emojified_status(self, verbose=True):
        if verbose:
            return (
                f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n"
                # f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n"
                f"Law: {self.RED} *(Repealed)*\n"
            )

        return f"{self.GREEN}{self.RED}"
