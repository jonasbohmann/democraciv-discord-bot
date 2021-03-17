from discord.ext import commands
from jishaku.cog import JishakuBase, jsk
from jishaku.metacog import GroupCogMeta

from bot.utils import models
from config import config, token


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

    @commands.command(name="syncbill", aliases=["sb", "synclaw", "sl"])
    @commands.is_owner()
    async def syncbill(self, ctx, bills: commands.Greedy[models.Bill]):
        """Refresh bill name, content and keywords from Google Docs"""

        for bill in bills:
            name, keywords, content = await bill.fetch_name_and_keywords()

            await self.bot.db.execute("UPDATE bill SET name = $1, content = $3 WHERE id = $2", name, bill.id, content)
            await self.bot.db.execute("DELETE FROM bill_lookup_tag WHERE bill_id = $1", bill.id)
            await self.bot.api_request("POST", "bill/update", json={"id": bill.id})

            id_with_kws = [(bill.id, keyword) for keyword in keywords]
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES " "($1, $2) ON CONFLICT DO NOTHING ", id_with_kws
                )
            )

        await ctx.send(f"{config.YES} Synced {len(bills)} bills with Google Docs.")


def setup(bot):
    bot.add_cog(Admin(bot))
