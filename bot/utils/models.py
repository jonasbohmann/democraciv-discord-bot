import abc
import datetime
import functools
import enum
import bot

from config import config, mk
from utils import converter
from utils.exceptions import DemocracivBotException


class _BillStatusFlag(enum.Enum):
    SUBMITTED = 0
    LEG_FAILED = 1
    LEG_PASSED = 2
    MIN_FAILED = 3
    MIN_PASSED = 4
    VETO_OVERRIDDEN = 5
    REPEALED = 6


class IllegalBillOperation(DemocracivBotException):
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

    def __init__(self, bot, bill):
        self._bot: 'bot.DemocracivBot' = bot
        self._bill: converter.Bill = bill

    def __eq__(self, other):
        return isinstance(other, BillStatus) and self.flag == other.flag

    def __int__(self):
        return self.flag.value

    def __str__(self):
        return self.verbose_name

    def __repr__(self):
        return f"<{self.__class__.__name__} flag={self.flag} stale={self.stale}>"

    def make_stale(self, func):
        @functools.wraps(func)
        def wrapper():
            func()
            self.stale = True

        return wrapper

    async def log_history(self, old_status: _BillStatusFlag, new_status: _BillStatusFlag):
        await self._bot.db.execute("INSERT INTO bill_history (bill_id, date, before_status, after_status) "
                                   "VALUES ($1, $2, $3, $4)", self._bill.id, datetime.datetime.utcnow(), old_status.value,
                                   new_status.value)

    async def veto(self):
        raise IllegalBillOperation("")

    async def withdraw(self):
        raise IllegalBillOperation("")

    async def pass_into_law(self):
        raise IllegalBillOperation("")

    async def pass_from_legislature(self):
        raise IllegalBillOperation("")

    async def override_veto(self):
        raise IllegalBillOperation("")

    async def repeal(self):
        raise IllegalBillOperation("")

    async def resubmit(self):
        raise IllegalBillOperation("")

    @abc.abstractmethod
    def emojified_status(self, verbose=True):
        pass


class BillSubmitted(BillStatus):
    is_law = False
    flag = _BillStatusFlag.SUBMITTED
    verbose_name = "Submitted"

    async def withdraw(self):
        await self._bot.db.execute("DELETE FROM legislature_bills WHERE id = $1", self._bill.id)

    async def fail_in_legislature(self):
        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   _BillStatusFlag.LEG_FAILED.value, self._bill.id)

    async def pass_from_legislature(self):

        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   _BillStatusFlag.LEG_PASSED.value, self._bill.id)
        await self.log_history(self.flag, _BillStatusFlag.LEG_PASSED)

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.YELLOW} *(Not Voted On Yet)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Waiting on {self._bot.mk.LEGISLATURE_NAME})*\n" \
                   f"Law: {self.GRAY}\n"

        return f"{self.YELLOW}{self.YELLOW}{self.GRAY}"


class BillFailedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_FAILED
    verbose_name = f"Failed in the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def resubmit(self):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.RED} *(Failed)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.GRAY} *(Failed in the {self._bot.mk.LEGISLATURE_NAME})*\n" \
                   f"Law: {self.GRAY}\n"

        return f"{self.RED}{self.GRAY}{self.GRAY}"


class BillPassedLegislature(BillStatus):
    is_law = False
    flag = _BillStatusFlag.LEG_PASSED
    verbose_name = f"Passed the {mk.MarkConfig.LEGISLATURE_NAME}"

    async def veto(self):
        if not self._bill.is_vetoable:
            raise IllegalBillOperation("")

        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   _BillStatusFlag.MIN_FAILED.value, self._bill.id)
        await self.log_history(self.flag, _BillStatusFlag.MIN_FAILED)

    async def pass_into_law(self):
        await self._bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE id = $2",
                                   _BillStatusFlag.MIN_PASSED.value, self._bill.id)
        await self.log_history(self.flag, _BillStatusFlag.MIN_PASSED)

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.YELLOW} *(Not Voted on Yet)*\n" \
                   f"Law: {self.GRAY}\n"

        return f"{self.GREEN}{self.YELLOW}{self.GRAY}"


class BillVetoed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.MIN_FAILED
    verbose_name = f"Vetoed by the {mk.MarkConfig.MINISTRY_NAME}"

    async def override_veto(self):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.RED} *(Vetoed)*\n" \
                   f"Law: {self.GRAY}\n"

        return f"{self.GREEN}{self.RED}{self.GRAY}"


class BillPassedMinistry(BillStatus):
    is_law = True
    flag = _BillStatusFlag.MIN_PASSED
    verbose_name = "Active Law"

    async def repeal(self):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"Law: {self.GREEN} *(Active Law)*\n"

        return f"{self.GREEN}{self.GREEN}{self.GREEN}"


class BillRepealed(BillStatus):
    is_law = False
    flag = _BillStatusFlag.REPEALED
    verbose_name = "Repealed"

    async def resubmit(self):
        pass

    def emojified_status(self, verbose=True):
        if verbose:
            return f"{self._bot.mk.LEGISLATURE_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"{self._bot.mk.MINISTRY_NAME}: {self.GREEN} *(Passed)*\n" \
                   f"Law: {self.RED} *(Repealed)*\n"

        return f"{self.GREEN}{self.GREEN}{self.RED}"
