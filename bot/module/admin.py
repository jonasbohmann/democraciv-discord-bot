import time
import typing

import discord.utils
from discord.ext import commands
from jishaku.cog import STANDARD_FEATURES
from jishaku.features.baseclass import Feature

from bot.utils import models, context, paginator
from bot.config import config, token
from config import mk


class Admin(*STANDARD_FEATURES, command_attrs=dict(hidden=True)):
    """Administrative commands to debug and monitor the bot."""

    hidden = True

    @Feature.Command(parent="jsk", name="restart", aliases=["stop"])
    async def jsk_restart(self, ctx):
        """Restarts the bot"""
        await ctx.send(":wave: Restarting...")
        await self.bot.close()

    @Feature.Command(parent="jsk", name="backup")
    async def jsk_backup(self, ctx):
        """Trigger a database backup"""
        await self.bot.do_db_backup(token.POSTGRESQL_DATABASE)
        await ctx.send(config.YES)

    @Feature.Command(parent="jsk", name="sql")
    async def jsk_sql(self, ctx, *, query: str):
        """Debug the bot's database"""

        is_multistatement = query.count(";") > 1
        strategy = self.bot.db.execute if is_multistatement else self.bot.db.fetch

        try:
            result = await strategy(query)
        except Exception as e:
            return await ctx.send(f"```{e.__class__.__name__}: {e}```")

        result = f"```{result}```"

        if len(result) > 2000:
            link = await self.bot.make_paste(result)
            await ctx.send(f"<{link}>")
        else:
            await ctx.send(result)

    @Feature.Command(parent="jsk", name="addbilltag", aliases=["bt", "lt", "addlawtag"])
    async def jsk_billtag(self, ctx, bill: models.Bill, tag: str):
        """Add a search tag to a law to be used in `{PREFIX}bill/laws search`"""

        await self.bot.db.execute(
            "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2)",
            bill.id,
            tag.lower(),
        )
        await ctx.send(
            f"{config.YES} `{tag}` was added as a search tag to `{bill.name}` (#{bill.id})"
        )

    @Feature.Command(parent="jsk", name="forceindex")
    async def jsk_ml_qa_force_index(self, ctx):
        """Force rebuilding the document index for BERTQuestionAnswering"""

        await self.bot.api_request("POST", "ml/question_answering/force_index")
        await ctx.send(config.YES)


class Experiments(context.CustomCog):
    """Test unfinished commands in beta & experimental features"""

    hidden = mk.MarkConfig.IS_MULTICIV

    def __init__(self, bot):
        super().__init__(bot)
        self.bot.loop.create_task(self._eject_self_if_no_experiments())

    async def _eject_self_if_no_experiments(self):
        # remove_cog can't be done in __init__
        await self.bot.wait_until_ready()

        public_cmds = filter(
            lambda cmd: cmd.enabled and not cmd.hidden and cmd.name != "experiments",
            self.walk_commands(),
        )

        if not any(public_cmds):
            # hide this cog if no public experiments
            self.bot.remove_cog(name=self.qualified_name)

    @commands.command(name="experiments", aliases=["beta", "test", "testing"])
    async def experiments(self, ctx):
        """What is this?"""
        await ctx.send(
            f"Any experimental commands or features that are still in beta and a "
            f"work-in-progress will be put in this `Experimental` category. See the list of "
            f"experimental commands below (if there are any right now), and "
            f"feel free to test them and share your feedback. Not every command here is guaranteed "
            f"to make it into a 'real' command, and some might even be scrapped entirely."
        )
        await ctx.send_help(self)

    @commands.command(name="ask")
    @commands.max_concurrency(1, wait=False)
    async def ask(self, ctx, batch_size: typing.Optional[int] = 1, *, question):
        """Get answers to a legal question with Deep (Machine) Learning:tm: and Neural Networks:tm:

        This is an experimental command and probably still a work-in-progress."""

        return await ctx.send(f"{config.NO} All AI features (`-ask` & `-extract`) are currently disabled.")

        if self.bot.mk.IS_MULTICIV:
            return await ctx.send(
                f"{config.NO} This command is disabled during Multiciv MKs."
            )

        wait = await ctx.send(
            f"{config.HINT} This might take 30 to 60 seconds. Should this feature make it out "
            f"of beta, the time it takes will *hopefully* be sped up to just a couple of seconds by "
            f"switching to more powerful server hardware.\n:arrows_counterclockwise: Thinking "
            f"really hard about your question..."
        )

        async with ctx.typing():
            start = time.time()
            response = await self.bot.api_request(
                "POST",
                "ml/question_answering",
                json={"question": question, "batch_size": batch_size},
            )
            end = time.time()

        duration = end - start

        await wait.delete()

        if not response:
            return await ctx.send(
                f"{config.NO} I couldn't find an answer to that question. Sorry!"
            )

        fmt = [
            "This uses deep learning, a particular machine learning method, with neural networks to try to "
            "find answers to a legal question you're asking. All currently existing bills & motions are taken into "
            "account to try to find the best answer. Google's BERT model in combination with Tensorflow Keras "
            "are used here.\n\nThis comes with no guarantees about the correctness of the answers. Do not expect "
            "this to be free of wrong, misleading or irrelevant answers.\n\n"
        ]

        for result in response:
            if result["score"] * 100 <= 1:
                continue

            if len(result["full_answer"]) - len(result["answer"]) <= 3:
                cntxt = []
            else:
                cntxt = [
                    f"__Context__",
                    f"```{discord.utils.escape_markdown(result['full_answer'])}```",
                ]

            thing, thing_id = result["document"].split("_")

            if thing == "bill":
                obj = await models.Bill.convert(ctx, thing_id)

            elif thing == "motion":
                obj = await models.Motion.convert(ctx, thing_id)

            else:
                continue

            fmt.append(
                f"**__Found answer in {obj.formatted} with a confidence of {result['score'] * 100:.2f}%__**"
            )
            fmt.append(f"```{discord.utils.escape_markdown(result['answer'])}```")
            fmt.extend(cntxt)

        pages = paginator.SimplePages(
            entries=fmt,
            author=f"[BETA] Results for '{question}'",
            icon=self.bot.mk.NATION_ICON_URL,
            reply=True,
        )

        await ctx.reply(
            f"{config.HINT} Keep in mind that this feature is still a work-in-progress in Beta. "
            f"Question answering took ~{duration:.2f} seconds with a batch size of {batch_size}."
        )
        await pages.start(ctx)

    @commands.command(name="extract")
    async def match(self, ctx, *, query):
        """Extract information from bills, laws & motions with Natural Language Processing:tm:

        This is an experimental command and probably still a work-in-progress."""

        return await ctx.send(f"{config.NO} All AI features (`-ask` & `-extract`) are currently disabled.")

        if self.bot.mk.IS_MULTICIV:
            return await ctx.send(
                f"{config.NO} This command is disabled during Multiciv MKs."
            )

        async with ctx.typing():
            response = await self.bot.api_request(
                "POST", "ml/information_extraction", json={"question": query}
            )

        if not response:
            return await ctx.send(
                f"{config.NO} I couldn't find anything that matches `{query}`. Sorry!"
            )

        fmt = [
            "This uses Natural Language Processing to topic match your query against all existing bills & motions "
            "and shows the most closely corresponding excerpts. Using full, grammatical expressions with "
            f"no spelling errors will improve the quality of your results.\n\nShould this feature come out of "
            f"beta, then it will probably be integrated into the `{config.BOT_PREFIX}laws search` and "
            f"`{config.BOT_PREFIX}legislature bills search` commands.\n\n"
        ]

        for result in response:
            thing, thing_id = result["document_label"].split("_")

            if thing == "bill":
                obj = await models.Bill.convert(ctx, thing_id)

            elif thing == "motion":
                obj = await models.Motion.convert(ctx, thing_id)

            else:
                continue

            txt = discord.utils.escape_markdown(result["text"])
            fmt.append(f"**__{obj.formatted}__**")
            fmt.append(f"```{txt}```\n")

        pages = paginator.SimplePages(
            entries=fmt,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"[BETA] Results for '{query}'",
        )

        await pages.start(ctx)


async def setup(bot):
    await bot.add_cog(Experiments(bot))
    await bot.add_cog(Admin(bot=bot))
