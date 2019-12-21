from config import config
from util import utils, mk
from util.paginator import Pages

from discord.ext import commands


class Laws(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def search_by_name(self, name: str):
        bills = await self.bot.db.fetch("SELECT * FROM legislature_bills WHERE bill_name % $1", name.lower())

        found_bills = []

        for bill in bills:
            if bill['has_passed_leg']:
                if bill['is_vetoable'] and bill['has_passed_ministry']:
                    id = await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                    bill['id'])
                    found_bills.append(f"Law #{id} - [{bill['bill_name']}]({bill['link']})")
                elif not bill['is_vetoable']:
                    found_bills.append(f"Law #{id} - [{bill['bill_name']}]({bill['link']})")
                else:
                    continue
            else:
                continue

    async def search_by_tag(self, tag: str):
        found_bills = await self.bot.db.fetch("SELECT id FROM legislature_tags WHERE tag % $1", tag.lower())

        bills = []

        for bill in found_bills:
            bills.append(bill['id'])

        bills = list(set(bills))

        pretty_laws = []

        for bill in bills:
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 bill)
            pretty_laws.append(f"Law #{bill} - [{details['bill_name']}]({details['link']})")

        return pretty_laws

    @commands.group(name='laws', case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def laws(self, ctx):

        all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws")

        pretty_laws = []

        for law in all_laws:
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 law['bill_id'])
            pretty_laws.append(f"Law #{law['law_id']} - [{details['bill_name']}]({details['link']})\n")

        pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}"
                      , show_index=False, footer_text=f"Use {self.bot.commands_prefix}laws <id> to get more "
                                                      f"details about a law.")
        await pages.paginate()

    @laws.group(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):

        # First, search by name
        results = await self.search_by_name(' '.join(query))

        if results is None:
            results = []
            for substring in query:
                result = await self.search_by_tag(substring)
                if result:
                    results.append(result)

        pages_results = [item for sublist in results for item in sublist]

        if not pages_results or len(pages_results) == 0 or pages_results[0] == []:
            pages_results = ['Nothing found.']

        pages = Pages(ctx=ctx, entries=pages_results, show_entry_count=False, title=f"Search Results for '{' '.join(query)}'"
                      , show_index=False, footer_text=f"Use {self.bot.commands_prefix}laws <id> to get more "
                                                      f"details about a law.")
        await pages.paginate()


def setup(bot):
    bot.add_cog(Laws(bot))
