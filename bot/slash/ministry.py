import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config, mk
from bot.presenters import ministry as ministry_presenter
from bot.services.ministry import MinistryService
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import transformers, ui
from bot.utils import mixin, models, paginator

AwaitingBillOption = app_commands.Transform[
    models.Bill, transformers.AwaitingExecutiveBillTransformer
]

MINISTRY_COMMAND_NAME = mk.MarkConfig.MINISTRY_COMMAND.lower()


class MinistrySlash(commands.Cog, mixin.GovernmentMixin):
    ministry = app_commands.Group(
        name=MINISTRY_COMMAND_NAME,
        description="Executive Branch overview and bill action commands.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = MinistryService(bot)

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
        consumer = await self.service.prepare_bill_action(
            ctx,
            bills=[bill],
            action=action,
        )

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

        await self.service.consume_bill_action(
            consumer,
            scheduler_name=scheduler_name,
        )

        await ctx.send(success_body)

    @ministry.command(
        name="overview", description="Show the current Executive overview."
    )
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        result = await self.service.get_dashboard()
        embed = ministry_presenter.build_dashboard_embed(ctx, result)
        await ctx.send(embed=embed)

    @ministry.command(name="bills", description="List bills awaiting Executive action.")
    async def bills(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="executive")
        await ctx.defer()

        result = await self.service.get_awaiting_bills(do_paste=True)
        page = ministry_presenter.build_awaiting_bills_page(ctx, result)
        pages = paginator.SimplePages(
            entries=list(page.entries),
            icon=page.icon,
            author=page.author,
            empty_message=page.empty_message,
        )

        await pages.start(ctx)

    @ministry.command(name="pass", description="Pass a bill into law.")
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

    @ministry.command(name="veto", description="Veto a bill.")
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
            success_body=(
                f"{config.YES} This bill was vetoed by the Executive."
                f"\n{config.HINT} In case the Senate wants to give this bill a second "
                "chance, a veto can be overridden with `/senate override`, or the bill "
                "can be resubmitted to its origin house with `/bill resubmit`."
            ),
        )


async def setup(bot):
    await bot.add_cog(MinistrySlash(bot))
