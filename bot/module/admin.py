from discord.ext import commands
from jishaku.cog import JishakuBase, jsk
from jishaku.metacog import GroupCogMeta

from bot.utils import models, context, text, paginator
from bot.config import config, token


class Admin(
    JishakuBase,
    metaclass=GroupCogMeta,
    command_parent=jsk,
    command_attrs=dict(hidden=True),
):
    """Administrative commands to debug and monitor the bot."""

    hidden = True

    @commands.command(name="restart", aliases=["stop"])
    @commands.is_owner()
    async def restart(self, ctx):
        """Restarts the bot"""
        await ctx.send(":wave: Restarting...")
        await self.bot.close()

    @commands.command(name="backup")
    @commands.is_owner()
    async def backup(self, ctx):
        """Trigger a database backup"""
        await self.bot.do_db_backup(token.POSTGRESQL_DATABASE)
        await ctx.send(config.YES)

    @commands.command(name="sql")
    @commands.is_owner()
    async def sql(self, ctx, *, query: str):
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

    @commands.command(name="addbilltag", aliases=["lt", "addlawtag", "bt"])
    @commands.is_owner()
    async def billtag(self, ctx, bill: models.Bill, tag: str):
        """Add a search tag to a law to be used in `{PREFIX}bill/laws search`"""

        await self.bot.db.execute(
            "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2)",
            bill.id,
            tag.lower(),
        )
        await ctx.send(f"{config.YES} `{tag}` was added as a search tag to `{bill.name}` (#{bill.id})")

    @commands.command(name="forceindex", aliases=["force-index"])
    @commands.is_owner()
    async def ml_qa_force_index(self, ctx):
        """Force rebuilding the document index for BERTQuestionAnswering"""

        await self.bot.api_request("POST", "ml/question_answering/force_index")
        await ctx.send(f"{config.YES}")

    @commands.command(name="syncbill", aliases=["sb", "synclaw", "sl"])
    @commands.is_owner()
    async def syncbill(self, ctx, bills: commands.Greedy[models.Bill]):
        """Refresh bill name, content and keywords from Google Docs"""
        errs = []

        for bill in bills:
            name, keywords, content = await bill.fetch_name_and_keywords()

            if not name:
                errs.append(f"Error syncing Bill #{bill.id} - {bill.name}. Skipping update..")
                continue

            await self.bot.db.execute("UPDATE bill SET name = $1, content = $3 WHERE id = $2", name, bill.id, content)
            await self.bot.db.execute("DELETE FROM bill_lookup_tag WHERE bill_id = $1", bill.id)
            await self.bot.api_request("POST", "bill/update", json={"id": bill.id})

            id_with_kws = [(bill.id, keyword) for keyword in keywords]
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES " "($1, $2) ON CONFLICT DO NOTHING ", id_with_kws
                )
            )

        msg = f"{config.YES} Synced {len(bills) - len(errs)}/{len(bills)} bills with Google Docs."

        if errs:
            fmt = "\n".join(errs)
            msg = f"{fmt}\n\n{msg}"

        await ctx.send(msg)


class Experiments(context.CustomCog):
    """Test unfinished commands in beta & experimental features"""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot.loop.create_task(self._eject_self_if_no_experiments())

    async def _eject_self_if_no_experiments(self):
        # remove_cog can't be done in __init__ for some reason
        await self.bot.wait_until_ready()

        public_cmds = filter(lambda cmd: cmd.enabled and not cmd.hidden and cmd.name != "experiments",
                             self.walk_commands())

        if not any(public_cmds):
            # hide this cog if no public experiments
            self.bot.remove_cog(name=self.qualified_name)

    @commands.command(name="experiments", aliases=['beta', 'test', 'testing'])
    async def experiments(self, ctx):
        """What is this?"""
        await ctx.send(f"Any experimental commands or features that are still in beta and a "
                       f"work-in-progress will be put in this `Experimental` category. See the list of "
                       f"experimental commands below (if there are any right now), and "
                       f"feel free to test them and share your feedback. Not every command here is guaranteed "
                       f"to make it into a 'real' command, and some might even be scrapped entirely.")
        await ctx.send_help(self)

    @commands.command(name="ask")
    @commands.max_concurrency(1, wait=False)
    async def ask(self, ctx, *, question):
        """Get answers to a legal question with Deep (Machine) Learning:tm: and Neural Networks:tm:

        This is an experimental command and probably still a work-in-progress."""

        wait = await ctx.send(f"{config.HINT} This might take 30 to 60 seconds. Should this feature make it out "
                              f"of beta, the time it takes will *hopefully* be sped up to just a couple of seconds by "
                              f"switching to more powerful server hardware.\n:arrows_counterclockwise: Thinking "
                              f"really hard about your question...")

        async with ctx.typing():
            response = await self.bot.api_request("POST", "ml/question_answering", json={'question': question})

        await wait.delete()

        if not response:
            return await ctx.send(f"{config.NO} I couldn't find an answer to that question. Sorry!")

        embed = text.SafeEmbed()
        embed.set_author(icon_url=self.bot.mk.NATION_ICON_URL, name=f"[BETA] Results for '{question}'")

        fmt = ["This uses deep learning, a particular machine learning method, with neural networks to try to "
               "find answers to a legal question you're asking. All currently existing bills are taken into account "
               "to try to find the best answer. Google's BERT model in combination with Tensorflow Keras "
               "are used here.\n\nThis comes with no guarantees about the correctness of the answers. Do not expect "
               "this to be free of wrong, misleading or irrelevant answers."]

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
        embed.set_footer(icon_url="https://cdn.onlinewebfonts.com/svg/img_1326.png",
                         text="This experimental feature is a work in progress and will probably change in the future.")
        await ctx.reply(embed=embed)

    @commands.command(name="extract")
    async def match(self, ctx, *, query):
        """Extract information from bills & laws with Natural Language Processing:tm:

        This is an experimental command and probably still a work-in-progress."""

        async with ctx.typing():
            response = await self.bot.api_request("POST", "ml/information_extraction", json={'question': query})

        if not response:
            return await ctx.send(f"{config.NO} I couldn't find anything that matches `{query}`. Sorry!")

        fmt = ["This uses Natural Language Processing to topic match your query against all existing bills "
               "and shows the most closely corresponding excerpts. Using full, grammatical expressions with "
               f"no spelling errors will improve the quality of your results.\n\nShould this feature come out of "
               f"beta, then it will probably be integrated into the `{config.BOT_PREFIX}laws search` and "
               f"`{config.BOT_PREFIX}legislature bills search` commands.\n\n"]

        for result in response[:3]:
            bill = await models.Bill.convert(ctx, result['document_label'])

            txt = result['text']

            if len(txt) > 450:
                txt = f"{txt[:447]}..."

            fmt.append(f"**__{bill.formatted}__**")
            fmt.append(f"```{txt}```\n")

        pages = paginator.SimplePages(entries=fmt,
                                      icon=self.bot.mk.NATION_ICON_URL,
                                      author=f"[BETA] Results for '{query}'")

        pages.embed.set_footer(icon_url="https://cdn.onlinewebfonts.com/svg/img_1326.png",
                               text="This experimental feature is a work in progress and will probably "
                                    "change in the future.")
        await pages.start(ctx)


def setup(bot):
    bot.add_cog(Experiments(bot))
    bot.add_cog(Admin(bot))
