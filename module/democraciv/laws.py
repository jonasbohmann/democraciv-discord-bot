import typing
import discord

from config import config
from util import mk, utils
from util.flow import Flow
from util.converter import Law
from util.law_helper import MockContext, AnnouncementQueue
from util.paginator import Pages
from discord.ext import commands


class RepealScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = [f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the following laws were **repealed**.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.bill.name}** (<{obj.bill.tiny_link}>)")

        return '\n'.join(message)


class AmendScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = [f"The links to the following laws were changed by the Cabinet.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.bill.name}** (<{obj.bill.tiny_link}>)")

        return '\n'.join(message)


class Laws(commands.Cog, name='Law'):
    """List all active laws in Arabia and search for them by name or keyword"""

    def __init__(self, bot):
        self.bot = bot
        self.repeal_scheduler = RepealScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.amend_scheduler = AmendScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    async def paginate_all_laws(self, ctx):
        async with ctx.typing():
            all_laws = await self.bot.db.fetch("SELECT * FROM legislature_laws ORDER BY law_id")

            pretty_laws = []

            for record in all_laws:
                law = await Law.convert(MockContext(self.bot), record['law_id'])
                pretty_laws.append(f"Law #{law.id} - [{law.bill.name}]({law.bill.link})\n")

            if not pretty_laws:
                pretty_laws = ['There are no laws yet.']

        pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}",
                      show_index=False, show_amount_of_pages=True,
                      footer_text=f"Use {self.bot.commands_prefix}law <id> to get more details about a law.", )
        await pages.paginate()

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, law_id: Law = None):
        """List all laws or get details about a specific law

        **Usage:**
            `-law` will list every law in our nation
            `-law 48` will give you detailed information about Law #48"""

        # If no ID was specified, list all existing laws
        if not law_id:
            return await self.paginate_all_laws(ctx)

        # If the user did specify a law_id, send details about that law
        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        embed = self.bot.embeds.embed_builder(title="Law Details", description="")

        if law.bill.submitter is not None:
            embed.set_author(name=law.bill.submitter.name,
                             icon_url=law.bill.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"{law.bill.submitter.mention} (during Session #{law.bill.session.id})"
        else:
            submitted_by_value = f"*Submitter left Democraciv* (during Session #{law.bill.session.id})"

        if law.passed_on is None:
            law.passed_on = law.bill.session.closed_on

        embed.add_field(name="Name", value=f"[{law.bill.name}]({law.bill.link})")
        embed.add_field(name="Description", value=law.bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)
        embed.add_field(name="Law Since (UTC)", value=law.passed_on.strftime("%A, %B %d %Y"), inline=True)
        embed.add_field(name="Search Tags", value=', '.join(law.tags), inline=False)
        embed.set_footer(text=f"Associated Bill: #{law.bill.id}", icon_url=config.BOT_ICON_URL)
        await ctx.send(embed=embed)

    @law.command(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):
        """Search for laws by their name or description"""

        async with ctx.typing():
            # First, search by name
            name_lookup = await self.bot.laws.search_law_by_name(' '.join(query))

            # If the direct lookup by name didn't match anything, search for similar tag of each word of :param query

            results = [[name_lookup]]
            for substring in query:
                result = await self.bot.laws.search_law_by_tag(substring)
                if result:
                    results.append(result)

            # As LawUtils.search_by_tag() returns a list of matches, put all elements of all sublists
            # into the results list
            results = [item for sublist in results for item in sublist]

            # Eliminate duplicate results
            results = list(set(results))

            if not results or results[0] == []:
                results = ['Nothing found.']

        pages = Pages(ctx=ctx, entries=results, show_entry_count=False, title=f"Search Results for '{' '.join(query)}'",
                      show_index=False, footer_text=f"Use {self.bot.commands_prefix}law <id> to get more "
                                                    f"details about a law.")
        await pages.paginate()

    @law.command(name='repeal', aliases=['r, remove', 'delete'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def removelaw(self, ctx, law_id: Law):
        """Repeal a law to remove it from `-laws`

        **Example:**
            `-law removelaw 24`"""

        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to repeal `{law.bill.name}`"
                                      f" (#{law.id})?")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            await self.bot.db.execute("DELETE FROM legislature_laws WHERE law_id = $1", law.id)
            self.repeal_scheduler.add(law)
            return await ctx.send(f":white_check_mark: `{law.bill.name}` was repealed.")

    @law.command(name='updatelink', aliases=['ul', 'amend'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatelink(self, ctx, law_id: Law, new_link: str):
        """Update the link to a law.
        Useful for applying amendments to laws if the current Speaker does not own the law's Google Doc.

        **Example**:
            `-law updatelink 16 https://docs.google.com/1/d/ajgh3egfdjfnjdf`
        """

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
            self.amend_scheduler.add(law)
            return await ctx.send(f":white_check_mark: The link to `{law.bill.name}` was changed.")


def setup(bot):
    bot.add_cog(Laws(bot))
