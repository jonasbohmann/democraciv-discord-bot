import typing
import discord

from config import config
from util import mk, utils
from util.converter import Law
from util.flow import Flow
from util.law_helper import MockContext
from util.paginator import Pages
from discord.ext import commands


class Laws(commands.Cog, name='Law'):
    """Get all active laws in Arabia and search for them by name or keyword"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    async def paginate_all_laws(self, ctx):
        async with ctx.typing():
            all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws ORDER BY law_id")

            pretty_laws = []

            for record in all_laws:
                law = await Law.convert(MockContext(self.bot), record['law_id'])
                pretty_laws.append(f"Law #{law.id} - [{law.bill.name}]({law.bill.tiny_link})\n")

            if not pretty_laws:
                pretty_laws = ['There are no laws yet.']

        pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}",
                      show_index=False, show_amount_of_pages=False,
                      footer_text=f"Use {self.bot.commands_prefix}law <id> to get more details about a law.", )
        await pages.paginate()

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, law_id: Law = None):
        """List all laws or get details about a specific law"""

        # If no ID was specified, list all existing laws
        if not law_id:
            return await self.paginate_all_laws(ctx)

        # If the user did specify a law_id, send details about that law
        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        if law.bill.submitter is not None:
            submitted_by_value = f"{law.bill.submitter.mention} (during Session #{law.bill.session.id})"
        else:
            submitted_by_value = f"*Submitter left Democraciv* (during Session #{law.bill.session.id})"

        embed = self.bot.embeds.embed_builder(title="Law Details", description=f"Associated Bill: #{law.bill.id}")
        embed.add_field(name="Name", value=f"[{law.bill.name}]({law.bill.link})")
        embed.add_field(name="Description", value=law.bill.description, inline=False)
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

        pages = Pages(ctx=ctx, entries=results, show_entry_count=False, title=f"Search Results for '{' '.join(query)}'",
                      show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                    f"details about a law.")
        await pages.paginate()

    @law.command(name='remove', aliases=['r, repeal'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def removelaw(self, ctx, law_id: Law):
        """Remove a law from the laws of this nation"""

        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove `{law.bill.name}`"
                                      f" (#{law.id}) from the laws of {mk.NATION_NAME}?")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            await self.bot.db.execute("DELETE FROM legislature_laws WHERE law_id = $1", law.id)

            await self.gov_announcements_channel.send(f"Cabinet Member {ctx.author} has removed `{law.bill.name}`"
                                                      f" from the laws of {mk.NATION_NAME}.")

            return await ctx.send(f":white_check_mark: `{law.bill.name}` was removed from "
                                  f"the laws of {mk.NATION_NAME}.")

    @law.command(name='updatelink', aliases=['ul', 'amend'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatelink(self, ctx, law_id: Law, new_link: str):
        """Update the link to a law. Useful for applying amendments to laws."""

        if not self.bot.laws.is_google_doc_link(new_link):
            return await ctx.send(f":x: This does not look like a Google Docs link: `{new_link}`")

        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to change the link to "
                                      f"`{law.bill.name}` (#{law.id})?")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            tiny_url = await self.bot.laws.post_to_tinyurl(new_link)

            if tiny_url is None:
                return await ctx.send(":x: tinyurl.com returned an error, the link was not updated."
                                      " Try again in a few minutes.")

            await self.bot.db.execute("UPDATE legislature_bills SET link = $1, tiny_link = $2 WHERE id = $3",
                                      new_link, tiny_url, law.bill.id)

            await self.gov_announcements_channel.send(f"Cabinet Member {ctx.author} has amended `{law.bill.name}`. The"
                                                      f"new link for this law is: {tiny_url}")

            return await ctx.send(f":white_check_mark: Changed the link to `{law.bill.id}` #{law.id}).")


def setup(bot):
    bot.add_cog(Laws(bot))
