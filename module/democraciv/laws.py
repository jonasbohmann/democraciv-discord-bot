
from discord.ext import commands

from config import config
from module.help import HelpPaginator
from util import utils, mk


class Laws(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def search_by_name(self, name: str):
        bill = await self.bot.db.fetchrow()

    @commands.group(name='laws', case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def laws(self, ctx):

        all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws")

        pretty_laws = ""

        for law in all_laws:
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 law['bill_id'])
            pretty_laws += f"Law #{law['law_id']} - [{details['bill_name']}]({details['link']})\n"

        embed = self.bot.embeds.embed_builder(title=f"All Laws in {mk.NATION_NAME}", description=pretty_laws)

        await ctx.send(embed=embed)

    @laws.group(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, query: str):
        pass


def setup(bot):
    bot.add_cog(Laws(bot))
