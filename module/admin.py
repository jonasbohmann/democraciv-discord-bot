import io
import discord

from util.converter import Law
from discord.ext import commands
from jishaku.cog import JishakuBase, jsk
from jishaku.metacog import GroupCogMeta


class Admin(JishakuBase, metaclass=GroupCogMeta, command_parent=jsk, command_attrs=dict(hidden=True)):
    """Administrative commands to debug and monitor the bot"""

    @commands.command(name='sql')
    @commands.is_owner()
    async def sql(self, ctx, *, query: str):
        """Debug the bot's database"""

        is_multistatement = query.count(';') > 1
        strategy = self.bot.db.execute if is_multistatement else self.bot.db.fetch

        try:
            result = await strategy(query)
        except Exception as e:
            return await ctx.send(f"```{e.__class__.__name__}: {e}```")

        result = f'```{result}```'

        if len(result) > 2000:
            fp = io.BytesIO(result.encode('utf-8'))
            await ctx.send('Output was too long!', file=discord.File(fp, 'results.txt'))
        else:
            await ctx.send(result)

    @commands.command(name='addlawtag', aliases=['lt', 'alt'])
    @commands.is_owner()
    async def lawtag(self, ctx, law: Law, tag: str):
        """Add a search tag to a law to be used in `-laws search`"""
        await self.bot.db.execute("INSERT INTO legislature_tags (id, tag) VALUES ($1, $2)", law.id, tag.lower())
        await ctx.send(f":white_check_mark: `{tag}` was added as a search tag to `{law.bill.name}` (#{law.id})")


def setup(bot):
    bot.add_cog(Admin(bot))
