import datetime
import textwrap
import typing

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import config, mk
from bot.utils import text, checks, context, models, mixin, paginator
from bot.utils.converter import (
    CaseInsensitiveMember,
    PoliticalParty,
    CaseInsensitiveUser,
    FuzzyCIMember,
)


class RepealScheduler(text.AnnouncementScheduler):
    def get_message(self) -> str:
        message = [f"The following laws were **repealed**.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        message.append(f"\nThe laws were removed from `{config.BOT_PREFIX}laws`.")

        return "\n".join(message)


class AmendScheduler(text.AnnouncementScheduler):
    def get_message(self) -> str:
        message = [f"The links to the following laws were changed by the {self.bot.mk.LEGISLATURE_CABINET_NAME}.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        return "\n".join(message)


class Laws(context.CustomCog, mixin.GovernmentMixin, name="Law"):
    """List all active laws in {NATION_NAME} and search for them by name or keyword."""

    def __init__(self, bot):
        super().__init__(bot)
        self.repeal_scheduler = RepealScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.amend_scheduler = AmendScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    @commands.group(name="law", aliases=["laws"], case_insensitive=True, invoke_without_command=True)
    async def law(self, ctx, *, law_id: models.Law = None):
        """List all laws in {NATION_NAME} or get details about a specific law

        **Usage**
            `{PREFIX}{COMMAND}` will list every law in our nation
            `{PREFIX}{COMMAND} 48` will give you detailed information about Law #48"""

        # If no ID was specified, list all existing laws
        if not law_id:
            return await self._paginate_all_(ctx, model=models.Law)

        # If the user did specify a law_id, send details about that law
        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        embed = text.SafeEmbed(title=f"{law.name} (#{law.id})", description=law.description, url=law.link)

        if law.submitter is not None:
            embed.set_author(
                name=f"Written by {law.submitter.name}",
                icon_url=law.submitter.avatar_url_as(static_format="png"),
            )
            submitted_by_value = f"{law.submitter.mention} (during Session #{law.session.id})"
        else:
            submitted_by_value = f"*Person left {self.bot.dciv.name}* (during Session #{law.session.id})"

        embed.add_field(name="Author", value=submitted_by_value, inline=False)

        history = [f"{entry.date.strftime('%d %b %y')} - {entry.after}" for entry in law.history[:3]]

        if history:
            embed.add_field(name="History", value="\n".join(history))

        embed.set_footer(text=f"All dates are in UTC. Associated Bill: #{law.id}")
        await ctx.send(embed=embed)

    @law.command(name="export", aliases=["e", "exp", "ex", "generate", "generatelegalcode"])
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
            return await ctx.send(f"{config.NO} That doesn't look like a Google Docs URL.")

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
            date = datetime.datetime.utcnow().strftime("%B %d, %Y at %H:%M")

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
            member_or_party: typing.Union[
                CaseInsensitiveMember, CaseInsensitiveUser, PoliticalParty, FuzzyCIMember] = None,
    ):
        """List the laws a specific person or Political Party authored"""
        return await self._from_person_model(ctx, model=models.Law, member_or_party=member_or_party)

    @law.command(name="search", aliases=["s"])
    async def search(self, ctx, *, query: str):
        """Search for laws by their name or description"""
        return await self._search_model(ctx, model=models.Law, query=query)

    @law.command(name="repeal", aliases=["r, remove", "delete"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def removelaw(self, ctx: context.CustomContext, law_ids: Greedy[models.Law]):
        """Repeal one or multiple laws

        **Example**
            `{PREFIX}{COMMAND} 24` will repeal law #24
            `{PREFIX}{COMMAND} 56 57 58 12 13` will repeal all those laws"""

        if not law_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=law_ids, action=models.BillStatus.repeal)
        await consumer.filter()

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want repeal the following laws?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.repeal_scheduler)
        msg = f"1 law was repealed." if len(law_ids) == 1 else f"{len(law_ids)} laws were repealed."
        return await ctx.send(
            f"{config.YES} {msg}\n{config.HINT} If the Legal Code needs to "
            f"be updated to remove the repealed law(s), the {self.bot.mk.speaker_term} can use my "
            f"`{config.BOT_PREFIX}laws export` command to make me generate a Google Docs Legal Code."
        )

    @law.command(name="updatelink", aliases=["ul", "amend"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def updatelink(self, ctx, law_id: models.Law, new_link: str):
        """Update the link to a law

        Useful for applying amendments to laws if the current Speaker does not own the law's Google Doc.

        **Example**
            `{PREFIX}{COMMAND} 16 https://docs.google.com/1/d/ajgh3egfdjfnjdf`
        """

        if not self.is_google_doc_link(new_link):
            return await ctx.send(f"{config.NO} This does not look like a Google Docs link: `{new_link}`")

        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense
        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to change the link to "
            f"`{law.name}` (#{law.id})?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await law.status.amend(new_link=new_link)
        law = await models.Law.convert(ctx, law.id)
        # self.amend_scheduler.add(law)
        await ctx.send(f"{config.YES} The link to `{law.name}` was changed.")

    @law.command(name="ask", hidden=True)
    @commands.max_concurrency(1, wait=False)
    async def ask(self, ctx, *, question):
        """Beta"""
        wait = await ctx.send(f"{config.HINT} This might take a bit longer...")

        async with ctx.typing():
            response = await self.bot.api_request("POST", "ml/question_answering", json={'question': question})

        await wait.delete()

        if not response:
            return await ctx.send(f"{config.NO} I couldn't find an answer to that question.")

        embed = text.SafeEmbed()
        embed.set_author(icon_url=self.bot.mk.NATION_ICON_URL, name=f"Results for '{question}'")

        fmt = ["This uses deep learning, a particular machine learning method, with neural networks to try to "
               "find answers to a legal question you're asking. All currently existing bills are taken into account "
               "to try to find the best answer. Google's BERT model in combination with Tensorflow Keras "
               "are used here."]

        for result in response:
            if result['score'] * 100 <= 1:
                continue

            if len(result['full_answer']) - len(result['answer']) <= 3:
                cntxt = ""
            else:
                cntxt = f"\n__Context__\n```{result['full_answer']}```"

            bill = await models.Bill.convert(ctx, result['bill'])
            fmt.append(f"**__Found answer in {bill.formatted} with a confidence of {result['score'] * 100:.2f}%__**"
                       f"\n```{result['answer']}```{cntxt}")

        embed.description = "\n\n".join(fmt)
        embed.set_footer(text="This feature is a work in progress and might change in the future.")
        await ctx.send(embed=embed)

    @law.command(name="nlpsearch", hidden=True)
    async def match(self, ctx, *, query):
        """Beta"""

        async with ctx.typing():
            response = await self.bot.api_request("POST", "ml/information_extraction", json={'question': query})

        if not response:
            return await ctx.send(f"{config.NO} I couldn't find anything that matches `{query}`.")

        fmt = ["This uses Natural Language Processing to topic match your query against all existing bills "
               "and shows the most closely corresponding excerpts. Using full, grammatical expressions with "
               "no spelling errors will improve the quality of your results.\n"]

        for result in response[:3]:
            bill = await models.Bill.convert(ctx, result['document_label'])

            txt = result['text']

            if len(txt) > 450:
                txt = f"{txt[:447]}..."

            fmt.append(f"**__{bill.formatted}__**")
            fmt.append(f"```{txt}```\n")

        pages = paginator.SimplePages(entries=fmt,
                                      icon=self.bot.mk.NATION_ICON_URL,
                                      author=f"Results for '{query}'")

        pages.embed.set_footer(text="This feature is a work in progress and might change in the future.")
        await pages.start(ctx)


def setup(bot):
    bot.add_cog(Laws(bot))
