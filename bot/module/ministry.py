import discord

from discord.ext import commands, tasks

from bot.config import config, mk
from bot.presenters import ministry as ministry_presenter
from bot.services.ministry import MinistryService
from bot.utils import text, context, mixin, models, checks, paginator


class LawPassScheduler(text.RedditAnnouncementScheduler):
    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Bills passed into law by the {self.bot.mk.MINISTRY_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        message = [
            f"The following bills were **passed into law** by the {self.bot.mk.MINISTRY_NAME}.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()
            auto_note = ""

            if getattr(obj, "_auto_passed", False):
                auto_note = "\n*Automatically became law after 48 hours without Executive action.*"

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description}{auto_note}\n"
            )

        embed.description = "\n".join(message)
        return embed

    def get_reddit_post_title(self) -> str:
        return f"New Bills passed into law by the {self.bot.mk.MINISTRY_NAME} - {discord.utils.utcnow().strftime('%d %B %Y')}"

    def get_reddit_post_content(self) -> str:
        content = [
            f"The following bills were passed into law by the {self.bot.mk.MINISTRY_NAME}."
            f"\n\n###Relevant Links\n\n"
            f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
            f"* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `{config.BOT_PREFIX}laws` in #bot on our "
            f"[Discord Server](https://discord.gg/tVmHVcZPVs)\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n---\n  &nbsp; \n\n"
        ]

        for bill in self._objects:
            submitter = bill.submitter or context.MockUser()
            auto_note = ""

            if getattr(bill, "_auto_passed", False):
                auto_note = "\n\n*Automatically became law after 48 hours without Executive action.*"
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{bill.description}{auto_note}\n\n &nbsp;"
            )

        outro = f"""\n\n &nbsp; \n\n---\n\nAll these bills are now laws.
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
                and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)


class LawVetoScheduler(text.RedditAnnouncementScheduler):
    def get_reddit_post_title(self) -> str:
        return f"New Bills vetoed by the {self.bot.mk.MINISTRY_NAME} - {discord.utils.utcnow().strftime('%d %B %Y')}"

    def get_reddit_post_content(self) -> str:
        content = [
            f"The following bills were vetoed by the {self.bot.mk.MINISTRY_NAME}."
            f"\n\n###Relevant Links\n\n"
            f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
            f"* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `{config.BOT_PREFIX}laws` in #bot on our "
            f"[Discord Server](https://discord.gg/tVmHVcZPVs)\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n---\n  &nbsp; \n\n"
        ]

        for bill in self._objects:
            submitter = bill.submitter or context.MockUser()
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{bill.description}\n\n &nbsp;"
            )

        outro = f"""\n\n &nbsp; \n\n---
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
                and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)

    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Vetoes",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        message = [
            f"The following bills were **vetoed** by the {self.bot.mk.MINISTRY_NAME}.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description}\n"
            )

        embed.description = "\n".join(message)
        return embed


class Ministry(
    context.CustomCog, mixin.GovernmentMixin, name=mk.MarkConfig.MINISTRY_NAME
):
    """Allows the {MINISTRY_NAME} to pass and veto bills"""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = MinistryService(bot)
        self.pass_scheduler = LawPassScheduler(
            bot,
            mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
            subreddit=config.DEMOCRACIV_SUBREDDIT,
        )
        self.veto_scheduler = LawVetoScheduler(
            bot,
            mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
            subreddit=config.DEMOCRACIV_SUBREDDIT,
        )
        self.auto_pass_bills.start()

    def cog_unload(self):
        self.auto_pass_bills.cancel()

    async def get_pretty_vetoes(self, ctx=None, do_paste=False):
        """Gets all bills awaiting Executive action."""

        result = await self.service.get_awaiting_bills(do_paste=do_paste)
        page = ministry_presenter.build_awaiting_bills_page(ctx, result)
        return list(page.entries)

    @tasks.loop(minutes=10)
    async def auto_pass_bills(self):
        if await self.service.auto_pass_expired_bills(self.pass_scheduler):
            await self.pass_scheduler.trigger_now()

    @auto_pass_bills.before_loop
    async def before_auto_pass_bills(self):
        await self.bot.wait_until_ready()

    MINISTRY_ALIASES = [
        "min",
        "exec",
        "cabinet",
        "minister",
        "ministry",
        "executive",
        "ministers",
        "m",
        "presidency",
        "president",
        "pres",
    ]

    try:
        MINISTRY_ALIASES.remove(mk.MarkConfig.MINISTRY_COMMAND.lower())
    except ValueError:
        pass

    @commands.group(
        name=mk.MarkConfig.MINISTRY_COMMAND,
        aliases=MINISTRY_ALIASES,
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def ministry(self, ctx):
        """Dashboard for {minister_term} with important links and updates on new bills"""

        result = await self.service.get_dashboard()
        embed = ministry_presenter.build_dashboard_embed(ctx, result)
        await ctx.send(embed=embed)

    @ministry.command(name="bills", aliases=["b"])
    async def bills(self, ctx):
        """See all open bills from the Legislature to vote on"""

        pretty_bills = await self.get_pretty_vetoes(ctx, do_paste=True)
        pages = paginator.SimplePages(
            entries=pretty_bills,
            icon=self.bot.mk.NATION_ICON_URL,
            author="Bills Awaiting Executive Action",
            empty_message="There are no bills awaiting Executive action.",
        )
        await pages.start(ctx)

    @ministry.command(name="veto", aliases=["v"])
    @checks.has_any_democraciv_role(
        mk.DemocracivRole.PRIME_MINISTER, mk.DemocracivRole.LT_PRIME_MINISTER
    )
    async def veto(
        self, ctx: context.CustomContext, bill_ids: commands.Greedy[models.Bill]
    ):
        """Veto one or multiple bills

        **Example**
            `{PREFIX}{COMMAND} 12` will veto Bill #12
            `{PREFIX}{COMMAND} 45 46 49 51 52` will veto all those bills"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        bills = bill_ids
        consumer = await self.service.prepare_bill_action(
            ctx,
            bills=bills,
            action=models.BillStatus.veto,
        )

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills can not be vetoed.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to veto the following bills?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await self.service.consume_bill_action(
            consumer,
            scheduler_name="veto_scheduler",
        )
        await ctx.send(
            f"{config.YES} All bills were vetoed.\n{config.HINT} In case the "
            f"Senate wants to give these bills a second chance, a veto can be "
            f"overridden with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} override`, or the bill can be "
            f"resubmitted to its origin house with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} resubmit`."
        )

    @ministry.command(name="pass", aliases=["p"])
    @checks.has_any_democraciv_role(
        mk.DemocracivRole.PRIME_MINISTER, mk.DemocracivRole.LT_PRIME_MINISTER
    )
    async def pass_bill(self, ctx, bill_ids: commands.Greedy[models.Bill]):
        """Pass one or multiple bills into law

        **Example**
            `{PREFIX}{COMMAND} 12` will pass Bill #12 into law
            `{PREFIX}{COMMAND} 45 46 49 51 52` will pass all those bills into law"""

        bills = bill_ids

        consumer = await self.service.prepare_bill_action(
            ctx,
            bills=bills,
            action=models.BillStatus.pass_into_law,
        )

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills can not be passed into law.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to pass the following bills into law?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await self.service.consume_bill_action(
            consumer,
            scheduler_name="pass_scheduler",
        )
        await ctx.send(
            f"{config.YES} All bills were passed into law and can now be found in `{config.BOT_PREFIX}laws`."
            f"\n{config.HINT} If the Legal Code needs to "
            f"be updated, the {self.bot.mk.speaker_term} can use my "
            f"`{config.BOT_PREFIX}laws export` command to make me generate a Google Docs Legal Code. "
        )


async def setup(bot):
    await bot.add_cog(Ministry(bot))
