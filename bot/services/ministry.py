import dataclasses
import typing

import discord

from bot.config import mk
from bot.services.context import CommandContextProtocol
from bot.utils import context, exceptions, models


@dataclasses.dataclass
class MinistryAdvisor:
    role_name: str
    member: typing.Optional[discord.Member]


@dataclasses.dataclass
class MinistryDashboardResult:
    prime_minister: typing.Optional[discord.Member]
    lt_prime_minister: typing.Optional[discord.Member]
    advisors: typing.Sequence[MinistryAdvisor]
    has_awaiting_bills: bool


@dataclasses.dataclass
class AwaitingBillsResult:
    records: typing.Sequence[typing.Mapping]
    paste_link: typing.Optional[str] = None


class MinistryService:
    def __init__(self, bot):
        self.bot = bot

    def _safe_get_member(self, role) -> typing.Optional[discord.Member]:
        try:
            return self.bot.get_democraciv_role(role).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    def _advisor_records(self) -> typing.List[MinistryAdvisor]:
        advisors = []

        for role in (
            mk.DemocracivRole.MK13_FINANCE_MIN,
            mk.DemocracivRole.MK13_FOREIGN_MIN,
            mk.DemocracivRole.MK13_DEFENCE_MIN,
            mk.DemocracivRole.MK13_ATTORNEY_GENERAL,
        ):
            try:
                discord_role = self.bot.get_democraciv_role(role)
            except exceptions.RoleNotFoundError:
                continue

            advisors.append(
                MinistryAdvisor(
                    role_name=discord_role.name,
                    member=self._safe_get_member(role),
                )
            )

        return advisors

    async def get_awaiting_bill_records(self) -> typing.Sequence[typing.Mapping]:
        return await self.bot.db.fetch(
            "SELECT id, name, link, executive_deadline_at FROM bill WHERE status = $1 ORDER BY id",
            models.BillAwaitingExecutive.flag.value,
        )

    async def get_dashboard(self) -> MinistryDashboardResult:
        awaiting_bills = await self.get_awaiting_bill_records()
        return MinistryDashboardResult(
            prime_minister=self._safe_get_member(mk.DemocracivRole.PRIME_MINISTER),
            lt_prime_minister=self._safe_get_member(
                mk.DemocracivRole.LT_PRIME_MINISTER
            ),
            advisors=self._advisor_records(),
            has_awaiting_bills=bool(awaiting_bills),
        )

    async def get_awaiting_bills(
        self,
        *,
        do_paste: bool = False,
    ) -> AwaitingBillsResult:
        records = await self.get_awaiting_bill_records()
        paste_link = None

        if do_paste and records:
            exported = [
                f"Export of Bills Awaiting Executive Action -- {discord.utils.utcnow().strftime('%c')}\n\n\n",
                "----- Bills Awaiting Executive Action -----\n",
            ]

            exported.extend(f"Bill #{record['id']}" for record in records)
            exported.append("\n")
            exported.extend(
                f"=HYPERLINK(\"{record['link']}\"; \"{record['name']}\")"
                for record in records
            )

            try:
                paste_link = await self.bot.make_paste("\n".join(exported))
            except Exception:
                paste_link = None

        return AwaitingBillsResult(records=records, paste_link=paste_link)

    async def auto_pass_expired_bills(self, scheduler) -> bool:
        expired_bills = await self.bot.db.fetch(
            "SELECT id FROM bill WHERE status = $1 AND executive_deadline_at IS NOT NULL "
            "AND executive_deadline_at <= $2 ORDER BY id",
            models.BillAwaitingExecutive.flag.value,
            discord.utils.utcnow().replace(tzinfo=None),
        )

        if not expired_bills:
            return False

        mock_ctx = context.MockContext(self.bot)
        added_any = False

        for record in expired_bills:
            try:
                bill = await models.Bill.convert(mock_ctx, record["id"])
                await bill.status.pass_into_law(auto_pass=True)
            except Exception:
                continue

            bill._auto_passed = True
            scheduler.add(bill)
            added_any = True

        return added_any

    async def prepare_bill_action(
        self,
        ctx: CommandContextProtocol,
        *,
        bills: typing.Sequence[models.Bill],
        action: typing.Callable,
    ) -> models.LegalConsumer:
        consumer = models.LegalConsumer(ctx=ctx, objects=bills, action=action)
        await consumer.filter()
        return consumer

    def get_scheduler(self, scheduler_name: str):
        ministry_cog = self.bot.get_cog(self.bot.mk.MINISTRY_NAME)
        if ministry_cog is None:
            return None
        return getattr(ministry_cog, scheduler_name, None)

    async def consume_bill_action(
        self,
        consumer: models.LegalConsumer,
        *,
        scheduler_name: str,
    ):
        await consumer.consume(scheduler=self.get_scheduler(scheduler_name))
