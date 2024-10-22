import discord

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import config, mk
from bot.utils import text, checks, context, models, mixin, paginator
from bot.utils.converter import (
    CaseInsensitiveMember,
    PoliticalParty,
    CaseInsensitiveUser,
    Fuzzy,
    FuzzySettings,
)


class RepealScheduler(text.RedditAnnouncementScheduler):
    def get_reddit_post_title(self) -> str:
        return f"Laws repealed by the {self.bot.mk.LEGISLATURE_NAME} - {discord.utils.utcnow().strftime('%d %B %Y')}"

    def get_reddit_post_content(self) -> str:
        content = [
            f"The following laws were repealed by the {self.bot.mk.LEGISLATURE_NAME}."
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

        outro = f"""\n\n &nbsp; \n\n---\n\nThese laws were removed from the legal code.
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
                and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)

    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"{self.bot.mk.LEGISLATURE_NAME} repealed Bills",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        message = [f"The following laws were **repealed**.\n"]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Written by {submitter.mention}*\n{obj.description}\n"
            )

        message.append(f"\nThe laws were removed from `{config.BOT_PREFIX}laws`.")
        embed.description = "\n".join(message)
        return embed


class Laws(context.CustomCog, mixin.GovernmentMixin, name="Law"):
    """List all active laws in {NATION_NAME} and search for them by name or keyword."""

    def __init__(self, bot):
        super().__init__(bot)
        self.repeal_scheduler = RepealScheduler(
            bot,
            mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
            subreddit=config.DEMOCRACIV_SUBREDDIT,
        )

    @commands.group(
        name="law", aliases=["laws"], case_insensitive=True, invoke_without_command=True
    )
    async def law(self, ctx, *, law_id: Fuzzy[models.Law] = None):
        """List all laws in {NATION_NAME} or get details about a specific law

        **Usage**
            `{PREFIX}{COMMAND}` will list every law in our nation
            `{PREFIX}{COMMAND} 48` will give you detailed information about Law #48"""

        # If no ID was specified, list all existing laws
        if not law_id:
            return await self._paginate_all_(ctx, model=models.Law)

        return await self._detail_view(ctx, obj=law_id)

    @law.command(
        name="export", aliases=["e", "exp", "ex", "generate", "generatelegalcode"]
    )
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def exportlaws(self, ctx: context.CustomContext):
        """Generate a Legal Code as a Google Docs document from the list of active laws in {NATION_NAME}"""

        doc_url = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with an **edit** link to a Google Docs "
            "document you created. I will then fill that document to make it an up-to-date Legal Code.\n"
            ":warning: Note that I will replace the entire content of your Google Docs document if it "
            "isn't empty.",
            delete_after=True,
        )

        if not doc_url:
            ctx.command.reset_cooldown(ctx)
            return

        if not self.is_google_doc_link(doc_url):
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} That doesn't look like a Google Docs URL."
            )

        await ctx.send(
            f"{config.YES} I will generate an up-to-date Legal Code."
            f"\n:arrows_counterclockwise: This may take a few minutes..."
        )

        async with ctx.typing():
            all_laws = await self.bot.db.fetch(
                "SELECT id, name, link FROM bill WHERE status = $1 ORDER BY id;",
                models.BillIsLaw.flag.value,
            )
            ugly_laws = [dict(r) for r in all_laws]
            date = discord.utils.utcnow().strftime("%B %d, %Y at %H:%M")

            result = await self.bot.run_apps_script(
                script_id="MMV-pGVACMhaf_DjTn8jfEGqnXKElby-M",
                function="generate_legal_code",
                parameters=[
                    doc_url,
                    {"name": self.bot.mk.NATION_FULL_NAME, "date": date},
                    ugly_laws,
                ],
            )

        embed = text.SafeEmbed(
            title=f"Generated Legal Code",
            description="This Legal Code is not guaranteed to be correct. Its "
            f"content is based entirely on the list of Laws "
            f"in `{config.BOT_PREFIX}laws`."
            "\n\nRemember to change the edit link you "
            "gave me earlier to not be public.",
        )

        embed.add_field(
            name="Link to the Legal Code",
            value=result["response"]["result"]["view"],
            inline=False,
        )

        await ctx.send(embed=embed)

    @law.command(name="from", aliases=["f", "by"])
    async def _from(
        self,
        ctx,
        *,
        person_or_party: Fuzzy[
            CaseInsensitiveMember,
            CaseInsensitiveUser,
            PoliticalParty,
            FuzzySettings(weights=(5, 1, 2)),
        ] = None,
    ):
        """List the laws a specific person or Political Party authored"""
        return await self._from_person_model(
            ctx, model=models.Law, member_or_party=person_or_party
        )

    @law.command(name="read")
    async def read(self, ctx, *, law_id: Fuzzy[models.Law]):
        """Read the content of a law"""
        await self._show_bill_text(ctx, law_id)

    @law.command(name="search", aliases=["s"])
    async def search(self, ctx, *, query: str):
        """Search for laws"""
        results = await self._search_model(ctx, model=models.Law, query=query)

        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Laws matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)

    @law.command(name="repeal", aliases=["r"])
    @checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    async def removelaw(self, ctx: context.CustomContext, law_ids: Greedy[models.Law]):
        """Repeal one or multiple laws

        **Example**
            `{PREFIX}{COMMAND} 24` will repeal law #24
            `{PREFIX}{COMMAND} 56 57 58 12 13` will repeal all those laws"""

        if not law_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=law_ids, action=models.BillStatus.repeal
        )
        await consumer.filter()

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want repeal the following laws?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.repeal_scheduler)
        msg = (
            f"1 law was repealed."
            if len(law_ids) == 1
            else f"{len(law_ids)} laws were repealed."
        )
        return await ctx.send(
            f"{config.YES} {msg}\n{config.HINT} If the Legal Code needs to "
            f"be updated to remove the repealed law(s), the {self.bot.mk.speaker_term} can use my "
            f"`{config.BOT_PREFIX}laws export` command to make me generate a Google Docs Legal Code."
        )


async def setup(bot):
    await bot.add_cog(Laws(bot))
