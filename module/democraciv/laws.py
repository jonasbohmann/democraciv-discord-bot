import typing
import discord
import datetime

from config import config
from util import mk, utils
from util.flow import Flow
from discord.ext import commands
from discord.embeds import EmptyEmbed
from discord.ext.commands import Greedy
from util.paginator import AlternativePages
from util.law_helper import AnnouncementQueue
from util.exceptions import DemocracivBotException
from util.converter import Law, CaseInsensitiveMember, PoliticalParty


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
                pretty_laws.append(f"Law #{record['law_id']} - [{record['bill_name']}]({record['link']})")

            if not pretty_laws:
                embed = self.bot.embeds.embed_builder(title="There are no laws yet.",
                                                      description="",
                                                      has_footer=False)
                return await ctx.send(embed=embed)

        thumbnail = mk.NATION_FLAG_URL or self.bot.democraciv_guild_object.icon_url_as(static_format='png')

        pages = AlternativePages(ctx=ctx, entries=pretty_laws, show_entry_count=False,
                                 title=f"All Laws in {mk.NATION_NAME}", per_page=14,
                                 show_index=False, show_amount_of_pages=True,
                                 a_thumbnail=thumbnail)
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
            submitted_by_value = f"{law.bill.submitter.mention} (during Session #{law.bill.session.id})"
        else:
            submitted_by_value = f"*Person left Democraciv* (during Session #{law.bill.session.id})"

        if law.passed_on is None:
            law.passed_on = law.bill.session.closed_on

        embed.add_field(name="Name", value=f"[{law.bill.name}]({law.bill.link})")
        embed.add_field(name="Description", value=law.bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        embed.add_field(name="Law Since", value=law.passed_on.strftime("%A, %B %d %Y"), inline=False)
        embed.set_footer(text=f"All dates are in UTC. Associated Bill: #{law.bill.id}")
        await ctx.send(embed=embed)

    @law.command(name='export', aliases=['e', 'exp', 'ex', 'generate', 'generatelegalcode'])
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def exportlaws(self, ctx):
        """Generate a Legal Code as a Google Docs document from the list of active laws"""

        flow = Flow(self.bot, ctx)

        query = """SELECT legislature_laws.law_id, legislature_bills.bill_name, legislature_bills.link 
                   FROM legislature_laws JOIN legislature_bills
                   ON legislature_laws.bill_id = legislature_bills.id ORDER BY legislature_laws.law_id;
                """

        await ctx.send(":information_source: Reply with an **edit** link to a Google Docs "
                       "document you created. I will then fill that document to make it an up-to-date Legal Code.\n"
                       ":warning: Note that I will replace the entire content of your Google Docs document if it "
                       "isn't empty.")

        doc_url = await flow.get_private_text_input(120)

        if not doc_url:
            ctx.command.reset_cooldown(ctx)
            return

        if not self.bot.laws.is_google_doc_link(doc_url):
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        await ctx.send(f":white_check_mark: I will generate an up-to-date Legal Code."
                       f"\n:arrows_counterclockwise: This may take a few minutes...")

        async with ctx.typing():
            all_laws = await self.bot.db.fetch(query)
            ugly_laws = []

            for record in all_laws:
                ugly_laws.append({'id': record['law_id'], 'name': record['bill_name'], 'link': record['link']})

            date = datetime.datetime.utcnow().strftime("%B %d, %Y at %H:%M")

            result = await self.bot.google_api.run_apps_script(script_id="MMV-pGVACMhaf_DjTn8jfEGqnXKElby-M",
                                                               function="generate_legal_code",
                                                               parameters=[doc_url,
                                                                           {'name': mk.NATION_NAME, 'date': date},
                                                                           ugly_laws])

        if result is None or not result['done']:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(":x: There was an error while generating the document. Are you sure that you "
                                  "gave me an edit link?")

        if 'error' in result:
            ctx.command.reset_cooldown(ctx)

            error_msg = ("Exception: No item with the given ID could be found,"
                         " or you do not have permission to access it.", "Action not allowed")

            if result['error']['details'][0]['errorMessage'] in error_msg:
                return await ctx.send(":x: I cannot access that Google Docs document. Are you sure that you "
                                      "gave me an edit link?")
            else:
                return await ctx.send(":x: There was an error while generating the document. Are you sure that you "
                                      "gave me an edit link?")

        embed = self.bot.embeds.embed_builder(title=f"Generated Legal Code",
                                              description="This Legal Code is not guaranteed to be correct. Its "
                                                          f"content is based entirely on the list of Laws "
                                                          f"in `{config.BOT_PREFIX}laws`."
                                                          "\n\nRemember to change the edit link you "
                                                          "gave me earlier to not be public.")

        embed.add_field(name="Link to the Legal Code",
                        value=result['response']['result']['view'],
                        inline=False)

        await ctx.send(embed=embed)

    @law.command(name='from', aliases=['f', 'by'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def _from(self, ctx, *, member_or_party: typing.Union[
        discord.Member, CaseInsensitiveMember, discord.User, PoliticalParty] = None):
        """List the laws a specific person or Political Party authored"""

        member = member_or_party or ctx.author

        if isinstance(member, PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
        else:
            name = member.display_name
            members = [member.id]

        query = """SELECT legislature_laws.law_id, legislature_bills.bill_name, legislature_bills.link 
                   FROM legislature_laws JOIN legislature_bills
                   ON legislature_laws.bill_id = legislature_bills.id WHERE legislature_bills.submitter = ANY($1::bigint[])
                   ORDER BY legislature_laws.law_id;
                """

        laws_from_person = await self.bot.db.fetch(query, members)

        if not laws_from_person:
            if isinstance(member, PoliticalParty):
                title = f"No member of {name} has made a law yet."
            else:
                title = f"{name} hasn't made any laws yet."

            embed = self.bot.embeds.embed_builder(title=title, description="", has_footer=False)
            return await ctx.send(embed=embed)

        pretty_laws = []

        for record in laws_from_person:
            pretty_laws.append(f"Law #{record['law_id']} - [{record['bill_name']}]({record['link']})")

        if isinstance(member, PoliticalParty):
            a_title = f"Laws from members of {name}"
            a_icon = await member.get_logo() or EmptyEmbed
        else:
            a_title = f"Laws from {name}"
            a_icon = member.avatar_url_as(static_format='png')

        pages = AlternativePages(ctx=ctx, entries=pretty_laws, show_entry_count=False,
                                 a_title=a_title, show_index=False, show_amount_of_pages=True,
                                 a_icon=a_icon)
        await pages.paginate()

    @_from.error
    async def from_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

    @law.command(name='search', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def search(self, ctx, *query: str):
        """Search for laws by their name or description"""

        name = ' '.join(query)

        if len(name) < 3:
            return await ctx.send(":x: The query to search for must be at least 3 characters.")

        async with ctx.typing():

            # First, search by name similarity
            async with self.bot.db.acquire() as con:
                results = await self.bot.laws.search_law_by_name(name, connection=con)

                # Set word similarity threshold for search by tag
                await self.bot.laws.update_pg_trgm_similarity_threshold(0.4, connection=con)

                # Then, search by tag similarity
                for substring in query:
                    if len(substring) < 3 or substring in self.illegal_tags:
                        continue

                    result = await self.bot.laws.search_law_by_tag(substring, connection=con)
                    if result:
                        results.update(result)

                if not results:
                    results = ['Nothing found.']

        pages = AlternativePages(ctx=ctx, entries=list(results), show_entry_count=False,
                                 title=f"Laws matching '{name}'", show_index=False, show_amount_of_pages=True)
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

            law = await Law.convert(ctx, law.id)
            self.amend_scheduler.add(law)
            await ctx.send(f":white_check_mark: The link to `{law.bill.name}` was changed.")


def setup(bot):
    bot.add_cog(Laws(bot))
