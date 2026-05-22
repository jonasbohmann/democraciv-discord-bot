import datetime

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from bot.config import config, mk
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import transformers, ui
from bot.utils import exceptions, mixin, models

AwaitingBillOption = app_commands.Transform[
    models.Bill, transformers.AwaitingExecutiveBillTransformer
]

MINISTRY_COMMAND_NAME = mk.MarkConfig.MINISTRY_COMMAND.lower()


def _member_line(member: discord.Member) -> str:
    return f"{member.mention} {escape_markdown(str(member))}"


def _member_or_dash(member: discord.Member, term: str) -> str:
    if isinstance(member, discord.Member):
        return f"{term}: {_member_line(member)}"

    return f"{term}: -"


class MinistrySlash(commands.Cog, mixin.GovernmentMixin):
    ministry = app_commands.Group(
        name=MINISTRY_COMMAND_NAME,
        description="Executive overview and bill action commands.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    def _links(self, *, bill: models.Bill = None):
        links = []

        if bill is not None:
            links.extend(
                [
                    ui.LayoutLink("Document", bill.link, "\U0001f4c3"),
                    ui.LayoutLink(
                        "laws.democraciv.com",
                        f"https://laws.democraciv.com/bill/{bill.id}",
                        "\U0001f517",
                    ),
                ]
            )

        links.extend(
            [
                ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
                ui.LayoutLink(
                    "Worksheet", self.bot.mk.MINISTRY_WORKSHEET, "\U0001f4ca"
                ),
                ui.LayoutLink(
                    "Procedures", self.bot.mk.MINISTRY_PROCEDURES, "\U0001f4d6"
                ),
                ui.LayoutLink("Laws Site", "https://laws.democraciv.com", "\U0001f517"),
            ]
        )
        return links

    def _advisor_lines(self):
        lines = []

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

            lines.append(
                _member_or_dash(self._safe_get_member(role), discord_role.name)
            )

        return lines or ["-"]

    async def _awaiting_bills(self, ctx: slash_context.InteractionContext):
        records = await self.bot.db.fetch(
            "SELECT id FROM bill WHERE status = $1 ORDER BY id",
            models.BillAwaitingExecutive.flag.value,
        )
        return [await models.Bill.convert(ctx, record["id"]) for record in records]

    def _bill_entry(self, bill: models.Bill):
        deadline = bill.executive_deadline_at
        if deadline is not None:
            deadline = deadline.replace(tzinfo=datetime.timezone.utc)
            deadline_text = f"<t:{int(deadline.timestamp())}:R>"
        else:
            deadline_text = "No deadline set"

        return f"* {bill.formatted}\n-# Executive deadline: {deadline_text}"

    def _ministry_cog(self):
        return self.bot.get_cog(self.bot.mk.MINISTRY_NAME)

    async def _consume_bill_action(
        self,
        ctx: slash_context.InteractionContext,
        *,
        bill: models.Bill,
        action,
        scheduler_name: str,
        title: str,
        confirm_label: str,
        success_body: str,
    ):
        consumer = models.LegalConsumer(ctx=ctx, objects=[bill], action=action)
        await consumer.filter()

        if consumer.failed:
            await ctx.send(
                f":warning: This bill cannot be changed.\n{consumer.failed_formatted}",
                ephemeral=True,
            )

        if not consumer.passed:
            return

        confirmed = await ui.confirm(
            ctx,
            title=title,
            body=consumer.passed_formatted,
            confirm_label=confirm_label,
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        scheduler = getattr(self._ministry_cog(), scheduler_name, None)
        await consumer.consume(scheduler=scheduler)

        await ui.send_static(
            ctx,
            title=f"{bill.name} (#{bill.id})",
            body=success_body,
            sections=[
                ui.LayoutSection("Status", bill.status.emojified_status(verbose=True)),
                ui.LayoutSection(
                    "Summary", bill.description or "*No summary provided.*"
                ),
            ],
            links=self._links(bill=bill),
        )

    @ministry.command(
        name="overview", description="Show the current Executive overview."
    )
    @slash_checks.is_democraciv_guild()
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        awaiting = await self._awaiting_bills(ctx)
        awaiting_text = (
            "There are no bills awaiting Executive action."
            if not awaiting
            else f"{len(awaiting)} bill{'s' if len(awaiting) != 1 else ''} awaiting action. Use `/{MINISTRY_COMMAND_NAME} bills`."
        )

        await ui.send_static(
            ctx,
            title=f"The {self.bot.mk.MINISTRY_NAME} of {self.bot.mk.NATION_FULL_NAME}",
            sections=[
                ui.LayoutSection(
                    self.bot.mk.MINISTRY_LEADERSHIP_NAME,
                    "\n".join(
                        [
                            _member_or_dash(self.prime_minister, self.bot.mk.pm_term),
                            _member_or_dash(
                                self.lt_prime_minister, self.bot.mk.lt_pm_term
                            ),
                        ]
                    ),
                ),
                ui.LayoutSection(
                    "Cabinet of Advisors", "\n".join(self._advisor_lines())
                ),
                ui.LayoutSection("Bills Awaiting Executive Action", awaiting_text),
            ],
            links=self._links(),
        )

    @ministry.command(name="bills", description="List bills awaiting Executive action.")
    @slash_checks.is_democraciv_guild()
    async def bills(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        bills = await self._awaiting_bills(ctx)
        await ui.send_pages(
            ctx,
            entries=[self._bill_entry(bill) for bill in bills],
            title="Bills Awaiting Executive Action",
            links=self._links(),
            empty_message="There are no bills awaiting Executive action.",
        )

    @ministry.command(name="pass", description="Pass one bill into law.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.PRIME_MINISTER,
        mk.DemocracivRole.LT_PRIME_MINISTER,
    )
    @app_commands.describe(bill="Bill awaiting Executive action")
    async def pass_bill(
        self, interaction: discord.Interaction, bill: AwaitingBillOption
    ):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        await self._consume_bill_action(
            ctx,
            bill=bill,
            action=models.BillStatus.pass_into_law,
            scheduler_name="pass_scheduler",
            title="Pass Bill Into Law",
            confirm_label="Pass Into Law",
            success_body=(
                f"{config.YES} This bill was passed into law and can now be found "
                "in `/law list` and on laws.democraciv.com."
            ),
        )

    @ministry.command(name="veto", description="Veto one bill.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.PRIME_MINISTER,
        mk.DemocracivRole.LT_PRIME_MINISTER,
    )
    @app_commands.describe(bill="Bill awaiting Executive action")
    async def veto_bill(
        self, interaction: discord.Interaction, bill: AwaitingBillOption
    ):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        await self._consume_bill_action(
            ctx,
            bill=bill,
            action=models.BillStatus.veto,
            scheduler_name="veto_scheduler",
            title="Veto Bill",
            confirm_label="Veto",
            success_body=f"{config.YES} This bill was vetoed by the Executive.",
        )


async def setup(bot):
    await bot.add_cog(MinistrySlash(bot))
