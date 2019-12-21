from util import mk
from config import config
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
                    id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                    bill['id']))['law_id']
                    found_bills.append(f"Law #{id} - [{bill['bill_name']}]({bill['link']})")
                elif not bill['is_vetoable']:
                    id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                    bill['id']))['law_id']
                    found_bills.append(f"Law #{id} - [{bill['bill_name']}]({bill['link']})")
                else:
                    continue
            else:
                continue

        return found_bills

    async def search_by_tag(self, tag: str):
        found_bills = await self.bot.db.fetch("SELECT id FROM legislature_tags WHERE tag % $1", tag.lower())

        bills = []

        for bill in found_bills:
            bills.append(bill['id'])

        bills = list(set(bills))

        pretty_laws = []

        for bill in bills:
            bill_id = (await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", bill))['bill_id']
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 bill_id)
            pretty_laws.append(f"Law #{bill} - [{details['bill_name']}]({details['link']})")

        return pretty_laws

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, law_id: str = None):

        if not law_id or law_id.lower() == 'all':
            all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws")

            pretty_laws = []

            for law in all_laws:
                details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                     law['bill_id'])
                pretty_laws.append(f"Law #{law['law_id']} - [{details['bill_name']}]({details['link']})\n")

            pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}"
                          , show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                          f"details about a law.")
            await pages.paginate()

        else:
            law_id = int(law_id)
            bill_id = (await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", law_id))['bill_id']

            if bill_id is None:
                return await ctx.send(f":x: Couldn't find any law with ID #{law_id}!")

            law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

            embed = self.bot.embeds.embed_builder(title=f"{law_details['bill_name']}", description="")
            embed.add_field(name="Link", value=law_details['link'])
            embed.add_field(name="Description", value=law_details['description'], inline=False)
            embed.add_field(name="Submitted By", value=self.bot.get_user(law_details['submitter']).mention)
            embed.add_field(name="Submitted During Legislative Session", value=law_details['leg_session'])
            await ctx.send(embed=embed)

    @law.group(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):

        # First, search by name
        results = await self.search_by_name(' '.join(query))

        if not results:
            results = []
            for substring in query:
                result = await self.search_by_tag(substring)
                if result:
                    results.append(result)

            results = [item for sublist in results for item in sublist]

        if not results or len(results) == 0 or results[0] == []:
            results = ['Nothing found.']

        pages = Pages(ctx=ctx, entries=results, show_entry_count=False, title=f"Search Results for '{' '.join(query)}'"
                      , show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                      f"details about a law.")
        await pages.paginate()


def setup(bot):
    bot.add_cog(Laws(bot))
