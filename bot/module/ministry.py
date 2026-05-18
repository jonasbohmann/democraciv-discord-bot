import datetime
import typing
import discord

from discord.ext import commands, tasks
from discord.utils import escape_markdown

from bot.config import config, mk
from bot.utils import text, context, mixin, models, exceptions, checks, paginator


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

    async def get_pretty_vetoes(self) -> typing.List[str]:
        """Gets all bills awaiting Executive action."""

        open_bills = await self.bot.db.fetch(
            "SELECT id, name, link, executive_deadline_at FROM bill WHERE status = $1 ORDER BY id",
            models.BillAwaitingExecutive.flag.value,
        )

        if not open_bills:
            return []

        pretty_bills = []
        b_ids = []
        b_hyperlinks = []

        for record in open_bills:
            b_ids.append(f"Bill #{record['id']}")
            b_hyperlinks.append(
                f"=HYPERLINK(\"{record['link']}\"; \"{record['name']}\")"
            )
            deadline = record["executive_deadline_at"]
            deadline_fmt = (
                f"<t:{int(deadline.replace(tzinfo=datetime.timezone.utc).timestamp())}:F>"
                if deadline is not None
                else "No deadline set"
            )
            pretty_bills.append(
                f"Bill #{record['id']} - [{record['name']}]({record['link']}) "
                f"*(Deadline: {deadline_fmt})*"
            )

        exported = [
            f"Export of Bills Awaiting Executive Action -- {discord.utils.utcnow().strftime('%c')}\n\n\n",
            "----- Bills Awaiting Executive Action -----\n",
        ]

        exported.extend(b_ids)
        exported.append("\n")
        exported.extend(b_hyperlinks)

        link = None

        try:
            link = await self.bot.make_paste("\n".join(exported))
        except Exception:
            pass

        if link:
            pretty_bills.insert(
                0,
                f"[*View this list in Google Spreadsheets formatting for easy copy & pasting*]({link})\n",
            )

        return pretty_bills

    @tasks.loop(minutes=10)
    async def auto_pass_bills(self):
        expired_bills = await self.bot.db.fetch(
            "SELECT id FROM bill WHERE status = $1 AND executive_deadline_at IS NOT NULL "
            "AND executive_deadline_at <= $2 ORDER BY id",
            models.BillAwaitingExecutive.flag.value,
            discord.utils.utcnow().replace(tzinfo=None),
        )

        if not expired_bills:
            return

        mock_ctx = context.MockContext(self.bot)
        added_any = False

        for record in expired_bills:
            try:
                bill = await models.Bill.convert(mock_ctx, record["id"])
                await bill.status.pass_into_law(auto_pass=True)
            except Exception:
                continue

            bill._auto_passed = True
            self.pass_scheduler.add(bill)
            added_any = True

        if added_any:
            await self.pass_scheduler.trigger_now()

    @auto_pass_bills.before_loop
    async def before_auto_pass_bills(self):
        await self.bot.wait_until_ready()

    MINISTRY_ALIASES = [
        "min",
        "exec",
        "cabinet",
        "minister",
        "executive",
        "ministers",
        "m",
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

        embed = text.SafeEmbed()
        embed.set_author(
            icon_url=self.bot.mk.NATION_ICON_URL,
            name=f"The {self.bot.mk.MINISTRY_NAME} of {self.bot.mk.NATION_FULL_NAME}",
        )

        pretty_bills = await self.get_pretty_vetoes()
        if not pretty_bills:
            pretty_bills = "There are no bills awaiting Executive action."
        else:
            pretty_bills = (
                f"{config.HINT}    You can review pending bills with "
                f"`{config.BOT_PREFIX}{mk.MarkConfig.MINISTRY_COMMAND} bills`."
            )

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.pm_term}: {self.prime_minister.mention} {escape_markdown(str(self.prime_minister))}"
            )
        else:
            minister_value.append(f"{self.bot.mk.pm_term}: -")

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}"
            )
        else:
            minister_value.append(f"{self.bot.mk.lt_pm_term}: -")
        # attorney_general = self._safe_get_member(mk.DemocracivRole.ATTORNEY_GENERAL)

        # if isinstance(attorney_general, discord.Member):
        #    minister_value.append(
        #        f"Attorney General: {attorney_general.mention} {escape_markdown(str(attorney_general))}"
        #    )
        # else:
        #    minister_value.append(f"Attorney General: -")

        # supreme_commander = self._safe_get_member(mk.DemocracivRole.SUPREME_COMMANDER)

        # if isinstance(supreme_commander, discord.Member):
        #    minister_value.append(
        #        f"Supreme Commander: {supreme_commander.mention} {escape_markdown(str(supreme_commander))}"
        #    )
        # else:
        #    minister_value.append(f"Supreme Commander: -")

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=False,
        )
        """ try:
            ministers = self.bot.get_democraciv_role(mk.DemocracivRole.MINISTER)
            ministers = [
                f"{m.mention} {escape_markdown(str(m))}" for m in ministers.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            ministers = ["-"] """

        mk13_min_value = []

        for mk13_min in [
            mk.DemocracivRole.MK13_FINANCE_MIN,
            mk.DemocracivRole.MK13_FOREIGN_MIN,
            mk.DemocracivRole.MK13_DEFENCE_MIN,
            mk.DemocracivRole.MK13_ATTORNEY_GENERAL,
        ]:
            as_member = self._safe_get_member(mk13_min)
            as_role = self.bot.get_democraciv_role(mk13_min)
            if isinstance(as_member, discord.Member):
                mk13_min_value.append(
                    f"{as_role.name}: {as_member.mention} {escape_markdown(str(as_member))}"
                )
            else:
                mk13_min_value.append(f"{as_role.name}: -")
        # try:
        #    governors = self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNOR)
        #    governors = [
        #        f"{g.mention} {escape_markdown(str(g))}" for g in governors.members
        #    ] or ["-"]
        # except exceptions.RoleNotFoundError:
        #    governors = ["-"]

        embed.add_field(
            name=f"Cabinet of Advisors",
            value="\n".join(mk13_min_value),
            inline=False,
        )

        # embed.add_field(
        #    name=f"{self.bot.mk.governor_term}s ({len(governors) if governors[0] != "-" else 0})",
        #    value="\n".join(governors),
        #    inline=False,
        # )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE}) *(try [laws.democraciv.com](https://laws.democraciv.com) too!)*\n"
            f"[Ministry Worksheet]({self.bot.mk.MINISTRY_WORKSHEET})\n[Ministry Procedures]({self.bot.mk.MINISTRY_PROCEDURES})",
            inline=False,
        )

        embed.add_field(
            name="Bills Awaiting Executive Action", value=pretty_bills, inline=False
        )
        await ctx.send(embed=embed)

    @ministry.command(name="bills", aliases=["b"])
    async def bills(self, ctx):
        """See all open bills from the Legislature to vote on"""

        pretty_bills = await self.get_pretty_vetoes()
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
        consumer = models.LegalConsumer(
            ctx=ctx, objects=bills, action=models.BillStatus.veto
        )
        await consumer.filter()

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

        await consumer.consume(scheduler=self.veto_scheduler)
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

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bills, action=models.BillStatus.pass_into_law
        )
        await consumer.filter()

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

        await consumer.consume(scheduler=self.pass_scheduler)
        await ctx.send(
            f"{config.YES} All bills were passed into law and can now be found in `{config.BOT_PREFIX}laws`."
            f"\n{config.HINT} If the Legal Code needs to "
            f"be updated, the {self.bot.mk.speaker_term} can use my "
            f"`{config.BOT_PREFIX}laws export` command to make me generate a Google Docs Legal Code. "
        )


async def setup(bot):
    await bot.add_cog(Ministry(bot))
