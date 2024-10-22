import typing
import discord

from discord.ext import commands
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
            f"The following bills were **passed into law by the {self.bot.mk.MINISTRY_NAME}**.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description}\n"
            )

        message.append(
            f"\nAll new laws were added to `{config.BOT_PREFIX}laws` and can now be found with "
            f"`{config.BOT_PREFIX}laws search <query>`."
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
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{bill.description}\n\n &nbsp;"
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
            name=f"Bills vetoed by the {self.bot.mk.MINISTRY_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        message = [
            f"The following bills were **vetoed by the {self.bot.mk.MINISTRY_NAME}**.\n"
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
    """Allows the {MINISTRY_NAME} to pass and veto bills from the {LEGISLATURE_NAME}"""

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

    async def get_pretty_vetoes(self) -> typing.List[str]:
        """Gets all bills that passed the Legislature, are vetoable and were not yet voted on by the Ministry"""

        open_bills = await self.bot.db.fetch(
            "SELECT id, name, link FROM bill WHERE is_vetoable = true AND status = $1 ORDER BY id",
            models.BillPassedLegislature.flag.value,
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
            pretty_bills.append(
                f"Bill #{record['id']} - [{record['name']}]({record['link']})"
            )

        exported = [
            f"Export of Vetoable Bills -- {discord.utils.utcnow().strftime('%c')}\n\n\n",
            "----- Vetoable Bills -----\n",
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
            pretty_bills = "There are no new bills to vote on."
        else:
            pretty_bills = f"You can vote on new bills, check `{config.BOT_PREFIX}{mk.MarkConfig.MINISTRY_COMMAND} bills`."

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

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=False,
        )

        try:
            ministers = self.bot.get_democraciv_role(mk.DemocracivRole.MINISTER)
            ministers = [
                f"{m.mention} {escape_markdown(str(m))}" for m in ministers.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            ministers = ["-"]

        try:
            governors = self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNOR)
            governors = [
                f"{g.mention} {escape_markdown(str(g))}" for g in governors.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            governors = ["-"]

        embed.add_field(
            name=f"{self.bot.mk.minister_term}s ({len(ministers) if ministers[0] != "-" else 0})",
            value="\n".join(ministers),
            inline=False,
        )

        embed.add_field(
            name=f"{self.bot.mk.governor_term}s ({len(governors) if governors[0] != "-" else 0})",
            value="\n".join(governors),
            inline=False,
        )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})\n"
            f"[Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})",
            inline=False,
        )

        embed.add_field(name="Vetoable Bills", value=pretty_bills, inline=False)
        await ctx.send(embed=embed)

    @ministry.command(name="bills", aliases=["b"])
    async def bills(self, ctx):
        """See all open bills from the {LEGISLATURE_NAME} to vote on"""

        pretty_bills = await self.get_pretty_vetoes()
        pages = paginator.SimplePages(
            entries=pretty_bills,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Open Bills to Vote On",
            empty_message="There are no new bills to vote on.",
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
            f"{self.bot.mk.LEGISLATURE_NAME} wants to give these bills a second chance, a veto can be "
            f"overridden with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} override`, or, if the "
            f"votes to override are not enough, the bill can be "
            f"resubmitted to the next legislative session with "
            f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} resubmit`."
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
