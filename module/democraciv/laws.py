import typing
import discord

from config import config
from util import mk, utils
from discord.ext.commands import Greedy
from util.flow import Flow
from util.converter import Law
from util.paginator import Pages
from discord.ext import commands
from util.exceptions import DemocracivBotException
from util.law_helper import AnnouncementQueue


class RepealScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = [f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the following laws were **repealed**.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.bill.name}** (<{obj.bill.tiny_link}>)")

        return '\n'.join(message)


class AmendScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = ["The links to the following laws were changed by the Cabinet.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.bill.name}** (<{obj.bill.tiny_link}>)")

        return '\n'.join(message)


class Laws(commands.Cog, name='Law'):
    """List all active laws in Arabia and search for them by name or keyword."""

    def __init__(self, bot):
        self.bot = bot
        self.repeal_scheduler = RepealScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.amend_scheduler = AmendScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.illegal_tags = ('act', 'the', 'author', 'authors', 'date',
                             'name', 'bill', 'law', 'and', 'd/m/y', 'type', 'description')

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    async def paginate_all_laws(self, ctx):
        async with ctx.typing():
            query = """SELECT legislature_laws.law_id, legislature_bills.bill_name, legislature_bills.link 
                       FROM legislature_laws JOIN legislature_bills
                       ON legislature_laws.bill_id = legislature_bills.id ORDER BY legislature_laws.law_id;
                    """

            all_laws = await self.bot.db.fetch(query)

            pretty_laws = []

            for record in all_laws:
                pretty_laws.append(f"Law #{record['law_id']} - [{record['bill_name']}]({record['link']})\n")

            if not pretty_laws:
                pretty_laws = ['There are no laws yet.']

        pages = Pages(ctx=ctx, entries=pretty_laws, show_entry_count=False, title=f"All Laws in {mk.NATION_NAME}",
                      show_index=False, show_amount_of_pages=True,
                      footer_text=f"Use {self.bot.commands_prefix}law <id> to get more details about a law.", )
        await pages.paginate()

    @commands.group(name='law', aliases=['laws'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def law(self, ctx, *, law_id: Law = None):
        """List all laws or get details about a specific law

        **Usage:**
            `-law` will list every law in our nation
            `-law 48` will give you detailed information about Law #48"""

        # If no ID was specified, list all existing laws
        if not law_id:
            return await self.paginate_all_laws(ctx)

        # If the user did specify a law_id, send details about that law
        law = law_id  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        embed = self.bot.embeds.embed_builder(title=f"Law #{law.id}", description="")

        if law.bill.submitter is not None:
            embed.set_author(name=law.bill.submitter.name,
                             icon_url=law.bill.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"During Session #{law.bill.session.id} by {law.bill.submitter.mention}"
        else:
            submitted_by_value = f"During Session #{law.bill.session.id} by *Person left Democraciv*"

        if law.passed_on is None:
            law.passed_on = law.bill.session.closed_on

        embed.add_field(name="Name", value=f"[{law.bill.name}]({law.bill.link})")
        embed.add_field(name="Description", value=law.bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)
        embed.add_field(name="Law Since", value=law.passed_on.strftime("%A, %B %d %Y"), inline=True)
        embed.add_field(name="Search Tags", value=', '.join(law.tags), inline=False)
        embed.set_footer(text=f"All dates are in UTC. Associated Bill: #{law.bill.id}", icon_url=config.BOT_ICON_URL)
        await ctx.send(embed=embed)

    @law.command(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):
        """Search for laws by their name or description"""

        name = ' '.join(query)

        async with ctx.typing():

            # First, search by name similarity
            results = await self.bot.laws.search_law_by_name(name)

            # Then, search by tag similarity
            for substring in query:
                if len(substring) < 3 or substring in self.illegal_tags:
                    continue

                result = await self.bot.laws.search_law_by_tag(substring)
                if result:
                    results.update(result)

            if not results:
                results = ['Nothing found.']

        pages = Pages(ctx=ctx, entries=list(results), show_entry_count=False,
                      title=f"Search Results for '{name}'", show_index=False, show_amount_of_pages=True,
                      footer_text=f"Use {self.bot.commands_prefix}law <id> to get more details about a law.")
        if pages.maximum_pages == 1:
            pages.show_amount_of_pages = False
        await pages.paginate()

    @law.command(name='repeal', aliases=['r, remove', 'delete'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def removelaw(self, ctx, law_ids: Greedy[Law]):
        """Repeal one or multiple laws

        **Example:**
            `-law repeal 24` will repeal law #24
            `-law repeal 56 57 58 12 13` will repeal all those laws"""

        if not law_ids:
            return await ctx.send_help(ctx.command)

        laws = law_ids  # At this point, law_id is already a Law object, so calling it law_id makes no sense

        pretty_laws = '\n'.join([f"-  **{_law.bill.name}** (#{_law.id})" for _law in laws])

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want repeal the following laws?"
                                      f"\n{pretty_laws}")

        flow = Flow(self.bot, ctx)

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            for law in laws:
                await law.repeal()
                self.repeal_scheduler.add(law)

            return await ctx.send(f":white_check_mark: All laws were repealed.")

    @law.command(name='updatelink', aliases=['ul', 'amend'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatelink(self, ctx, law_id: Law, new_link: str):
        """Update the link to a law

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
            try:
                await law.amend(new_link)
            except DemocracivBotException as e:
                return await ctx.send(e.message)

            self.amend_scheduler.add(law)
            await ctx.send(f":white_check_mark: The link to `{law.bill.name}` was changed.")


def setup(bot):
    bot.add_cog(Laws(bot))
