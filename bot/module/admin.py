from discord.ext import commands
from jishaku.cog import JishakuBase, jsk
from jishaku.metacog import GroupCogMeta

from bot.utils import models
from config import config


class Admin(
    JishakuBase,
    metaclass=GroupCogMeta,
    command_parent=jsk,
    command_attrs=dict(hidden=True),
):
    """Administrative commands to debug and monitor the bot."""

    hidden = True

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

    @commands.command(name="addbilltag", aliases=["lt", 'addlawtag', 'bt'])
    @commands.is_owner()
    async def billtag(self, ctx, bill: models.Bill, tag: str):
        """Add a search tag to a law to be used in `{PREFIX}bill/laws search`"""

        await self.bot.db.execute(
            "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2)",
            bill.id,
            tag.lower(),
        )
        await ctx.send(f"{config.YES} `{tag}` was added as a search tag to `{bill.name}` (#{bill.id})")


def setup(bot):
    bot.add_cog(Admin(bot))
