from discord.ext import commands

from config import config
from util import mk, utils
from util.flow import Flow
from util.paginator import Pages


class Laws(commands.Cog):
    """Get all active laws in Arabia and search for them by name or keyword"""

    def __init__(self, bot):
        self.bot = bot

    async def search_by_name(self, name: str):
        bills = await self.bot.db.fetch("SELECT * FROM legislature_bills WHERE bill_name % $1", name.lower())

        found_bills = []

        for bill in bills:
            if bill['has_passed_leg']:
                if bill['is_vetoable'] and bill['has_passed_ministry']:
                    _id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                      bill['id']))['law_id']
                    found_bills.append(f"Law #{_id} - [{bill['bill_name']}]({bill['link']})")
                elif not bill['is_vetoable']:
                    _id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                      bill['id']))['law_id']
                    found_bills.append(f"Law #{_id} - [{bill['bill_name']}]({bill['link']})")
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
            bill_id = (await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", bill))[
                'bill_id']
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 bill_id)
            pretty_laws.append(f"Law #{bill} - [{details['bill_name']}]({details['link']})")

        return pretty_laws

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, law_id: str = None):
        """List all laws or get details about a specific law"""

        if not law_id or law_id.lower() == 'all':
            async with ctx.typing():
                all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws")

                pretty_laws = []

                for law in all_laws:
                    details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                         law['bill_id'])
                    pretty_laws.append(f"Law #{law['law_id']} - [{details['bill_name']}]({details['link']})\n")

                if not pretty_laws or len(pretty_laws) == 0:
                    pretty_laws = ['There are no laws yet.']

            pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}"
                          , show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                          f"details about a law.")
            await pages.paginate()

        else:
            try:
                law_id = int(law_id)
            except ValueError:
                return await ctx.send(f":x: Couldn't find any law with ID #{law_id}!")

            bill_id = await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", law_id)

            if bill_id is None:
                return await ctx.send(f":x: Couldn't find any law with ID #{law_id}!")

            bill_id = bill_id['bill_id']

            law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

            submitted_by_value = f"{self.bot.get_user(law_details['submitter']).mention} (during Session #" \
                                 f"{law_details['leg_session']})"

            embed = self.bot.embeds.embed_builder(title=f"{law_details['bill_name']}", description="")
            embed.add_field(name="Link", value=law_details['link'])
            embed.add_field(name="Description", value=law_details['description'], inline=False)
            embed.add_field(name="Submitter", value=submitted_by_value)
            await ctx.send(embed=embed)

    @law.command(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):
        """Search for laws by their name or description"""

        async with ctx.typing():
            # First, search by name
            results = await self.search_by_name(' '.join(query))

            if not results:
                results = []
                for substring in query:
                    result = await self.search_by_tag(substring)
                    if result:
                        results.append(result)

                results = [item for sublist in results for item in sublist]

                results = list(set(results))

            if not results or len(results) == 0 or results[0] == []:
                results = ['Nothing found.']

        pages = Pages(ctx=ctx, entries=results, show_entry_count=False, title=f"Search Results for '{' '.join(query)}'"
                      , show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                      f"details about a law.")
        await pages.paginate()

    @search.error
    async def searcherror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'query':
                await ctx.send(':x: You have to give me something to search for!\n\n**Usage**:\n'
                               '`-law search <query>`')

    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    @law.command(name='remove', aliases=['r'])
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    async def removebill(self, ctx, law_id: int):
        """Remove a law from the laws of this nation"""

        law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", law_id)

        if law_details is None:
            return await ctx.send(f":x: There is no law with ID #{law_id}")

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1",
                                                  law_details['bill_id'])

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{law_details['law_id']}) from the laws of {mk.NATION_NAME}?")

        flow = Flow(self.bot, ctx)

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if not reaction or reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            await self.bot.db.execute("DELETE FROM legislature_laws WHERE law_id = $1", law_id)
            return await ctx.send(f":white_check_mark: Successfully removed '{bill_details['bill_name']}"
                                  f"' (#{bill_details['id']}) from the laws of {mk.NATION_NAME}!")

    @removebill.error
    async def removebillerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'law_id':
                await ctx.send(':x: You have to give me the ID of the law to remove!\n\n**Usage**:\n'
                               '`-law remove <law_id>`')

        elif isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the cabinet is allowed to use this command!")


def setup(bot):
    bot.add_cog(Laws(bot))
