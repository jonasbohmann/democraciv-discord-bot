from discord.ext import commands

from config import config
from util import mk, utils
from util.flow import Flow
from util.paginator import Pages


class Laws(commands.Cog, name='Law'):
    """Get all active laws in Arabia and search for them by name or keyword"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, law_id: str = None):
        """List all laws or get details about a specific law"""

        # If no ID was specified, list all existing laws
        if not law_id or law_id.lower() == 'all':
            async with ctx.typing():
                all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws ORDER BY law_id")

                pretty_laws = []

                for law in all_laws:
                    details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                         law['bill_id'])
                    pretty_laws.append(f"Law #{law['law_id']} - [{details['bill_name']}]({details['link']})\n")

                if not pretty_laws or len(pretty_laws) == 0:
                    pretty_laws = ['There are no laws yet.']

            pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}"
                          , show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                          f"details about a law.", show_amount_of_pages=False)
            await pages.paginate()

        # If the user did specify a law_id, send details about that law
        else:
            try:
                law_id = int(law_id)
            except ValueError:
                return await ctx.send(f":x: Couldn't find any law with ID `#{law_id}`!")

            bill_id = await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", law_id)

            if bill_id is None:
                return await ctx.send(f":x: Couldn't find any law with ID `#{law_id}`!")

            bill_id = bill_id['bill_id']

            law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

            if self.bot.get_user(law_details['submitter']) is not None:
                submitted_by_value = f"{self.bot.get_user(law_details['submitter']).mention} (during Session #" \
                                 f"{law_details['leg_session']})"
            else:
                submitted_by_value = f"*Submitter left the server* (during Session #" \
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
            results = await self.bot.laws.search_law_by_name(' '.join(query))

            # If the direct lookup by name didn't match anything, search for similar tag of each word of :param query
            if not results:
                results = []
                for substring in query:
                    result = await self.bot.laws.search_law_by_tag(substring)
                    if result:
                        results.append(result)

                # As LawUtils.search_by_tag() returns a list of matches, put all elements of all sublists
                # into the results list
                results = [item for sublist in results for item in sublist]

                # Eliminate duplicate results
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

    @law.command(name='remove', aliases=['r, repeal'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def removebill(self, ctx, law_id: int):
        """Remove a law from the laws of this nation"""

        law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", law_id)

        if law_details is None:
            return await ctx.send(f":x: There is no law with ID #{law_id}.")

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1",
                                                  law_details['bill_id'])

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{law_details['law_id']}) from the laws of {mk.NATION_NAME}?")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            await self.bot.db.execute("DELETE FROM legislature_laws WHERE law_id = $1", law_id)
            announcement_msg = f"Cabinet Member {ctx.author} has removed `{bill_details['bill_name']}`" \
                               f" from the laws of {mk.NATION_NAME}."
            await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL).send(announcement_msg)
            return await ctx.send(f":white_check_mark: `{bill_details['bill_name']}` was removed"
                                  f" from the laws of {mk.NATION_NAME}.")

    @removebill.error
    async def removebillerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'law_id':
                await ctx.send(':x: You have to give me the ID of the law to remove!\n\n**Usage**:\n'
                               '`-law remove <law_id>`')

    @law.command(name='updatelink', aliases=['ul'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatelink(self, ctx, law_id: int, new_link: str):
        """Update the link to a law"""

        law_details = await self.bot.db.fetchrow("SELECT * FROM legislature_laws WHERE law_id = $1", law_id)

        if law_details is None:
            return await ctx.send(f":x: There is no law with ID `#{law_id}`")

        if not self.bot.laws.is_google_doc_link(new_link):
            return await ctx.send(f":x: This does not look like a Google Docs link: `{new_link}`")

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1",
                                                  law_details['bill_id'])

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to change the link to "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{law_details['law_id']})?")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.session.get(f"https://tinyurl.com/api-create.php?url={new_link}") as response:
                tiny_url = await response.text()

            if tiny_url == "Error":
                return await ctx.send(":x: tinyurl.com returned an error, the link was not updated."
                                      " Try again in a few minutes.")

            await self.bot.db.execute("UPDATE legislature_bills SET link = $1, tiny_link = $2 WHERE id = $3",
                                      new_link, tiny_url, bill_details['id'])

            return await ctx.send(f":white_check_mark: Changed the link to '{bill_details['bill_name']}"
                                  f"' (#{bill_details['id']}).")


def setup(bot):
    bot.add_cog(Laws(bot))
