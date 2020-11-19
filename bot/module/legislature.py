import typing
import asyncpg
import discord
import datetime

import nltk

from bot import DemocracivBot
from bot.config import config, mk
from discord.ext import commands
from discord.embeds import EmptyEmbed
from bot.utils import exceptions, text, checks, context
from discord.ext.commands import Greedy

from bot.utils.mixin import GovernmentMixin
from bot.utils.text import AnnouncementScheduler
from bot.utils.converter import Session, SessionStatus, Bill, Motion, Law, CaseInsensitiveMember, PoliticalParty, \
    BillStatus


class PassScheduler(AnnouncementScheduler):

    def get_message(self) -> str:
        message = [f"{self.bot.get_democraciv_role(mk.DemocracivRole.MINISTER_ROLE).mention}, "
                   f"the following bills were **passed by the {self.bot.mk.LEGISLATURE_NAME}**.\n"]

        for obj in self._objects:
            if obj.is_vetoable:
                message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")
            else:
                message.append(f"-  __**{obj.name}**__ (<{obj.tiny_link}>)")

        message.append(f"\nAll non-vetoable bills are now laws (marked as __underlined__), "
                       f"the others were sent to the {self.bot.mk.MINISTRY_NAME}.")
        return '\n'.join(message)


class OverrideScheduler(AnnouncementScheduler):

    def get_message(self) -> str:
        message = [f"{self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the {self.bot.mk.MINISTRY_NAME}'s **veto of the following bills were overridden** "
                   f"by the {self.bot.mk.LEGISLATURE_NAME}.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        message.append("\nAll of the above bills are now law.")
        return '\n'.join(message)


class Legislature(context.CustomCog, GovernmentMixin):
    """Allows the {LEGISLATURE_CABINET_NAME} to organize {LEGISLATURE_ADJECTIVE} Sessions and their submitted bills and motions."""

    def __init__(self, bot):
        super().__init__(bot)
        self.pass_scheduler = PassScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.override_scheduler = OverrideScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.illegal_tags = ('act', 'the', 'author', 'authors', 'date',
                             'name', 'bill', 'law', 'and', 'd/m/y', 'type', 'description')

        nltk.download('punkt')
        nltk.download('averaged_perceptron_tagger')

    @commands.group(name='legislature', aliases=['leg'], case_insensitive=True, invoke_without_command=True)
    async def legislature(self, ctx):
        """Dashboard for {legislator_term}s with important links and the status of the current session"""

        active_leg_session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            current_session_value = "There currently is no open session."
        else:
            current_session_value = f"Session #{active_leg_session.id} - {active_leg_session.status.value}"

        embed = text.SafeEmbed(title=f"{self.bot.mk.NATION_EMOJI}  The {self.bot.mk.LEGISLATURE_NAME} "
                                     f"of {self.bot.mk.NATION_FULL_NAME}")
        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.speaker_term}: {self.speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.speaker_term}: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: {self.vice_speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: -")

        embed.add_field(name=self.bot.mk.LEGISLATURE_CABINET_NAME, value='\n'.join(speaker_value))
        embed.add_field(name="Links", value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
                                            f"[Legal Code]({self.bot.mk.LEGAL_CODE})\n"
                                            f"[Legislative Docket]({self.bot.mk.LEGISLATURE_DOCKET})\n"
                                            f"[Legislative Procedures]({self.bot.mk.LEGISLATURE_PROCEDURES})",
                        inline=True)
        embed.add_field(name="Current Session", value=current_session_value, inline=False)
        await ctx.send(embed=embed)

    async def paginate_all_bills(self, ctx):
        async with ctx.typing():
            query = """SELECT id FROM legislature_bills ORDER BY id;"""

            all_bills = await self.bot.db.fetch(query)

            if not all_bills:
                embed = self.bot.embeds.embed_builder(title="No one has submitted any bills yet.")
                return await ctx.send(embed=embed)

            pretty = []

            for record in all_bills:
                _bill = await Bill.convert(ctx, record['id'])
                pretty.append(f"Bill #{_bill.id} - [{_bill.name}]({_bill.link}) "
                              f"{await _bill.get_emojified_status(verbose=False)}")

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False, per_page=8,
                                 title=f"{self.bot.mk.NATION_EMOJI}  All Submitted Bills",
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @legislature.group(name='bill', aliases=['b', 'bills'], case_insensitive=True, invoke_without_command=True)
    async def bill(self, ctx, *, bill_id: Bill = None):
        """List all bills or get details about a single bill"""

        if bill_id is None:
            return await self.paginate_all_bills(ctx)

        bill = bill_id

        embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  Bill #{bill.id}")

        if bill.submitter is not None:
            embed.set_author(name=bill.submitter.name, icon_url=bill.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"{bill.submitter.mention} (during Session #{bill.session.id})"
        else:
            submitted_by_value = f"*Person left Democraciv* (during Session #{bill.session.id})"

        is_vetoable = "Yes" if bill.is_vetoable else "No"

        embed.add_field(name="Name", value=f"[{bill.name}]({bill.link})")
        embed.add_field(name="Description", value=bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        embed.add_field(name="Vetoable", value=is_vetoable, inline=False)
        embed.add_field(name="Status", value=await bill.get_emojified_status(verbose=True), inline=False)

        if bill.repealed_on:
            embed.add_field(name="Repealed On", value=bill.repealed_on.strftime("%A, %B %d %Y"), inline=True)

        if await bill.is_law():
            law = await Law.from_bill(ctx, bill.id)
            embed.set_footer(text=f"Associated Law: #{law.id}")

        await ctx.send(embed=embed)

    @bill.command(name='search', aliases=['s'])
    async def b_search(self, ctx, *, query: str):
        """Search for a bill"""

        if len(query) < 3:
            return await ctx.send(":x: The query to search for has to be at least 3 characters long.")

        sql_query = """SELECT id from legislature_bills
                   WHERE (lower(bill_name) LIKE '%' || $1 || '%') OR (lower(description) LIKE '%' || $1 || '%')
                   ORDER BY similarity(lower(bill_name), $1) DESC
                   LIMIT 20"""

        found_bills = await self.bot.db.fetch(sql_query, query.lower())
        pretty = []

        for record in found_bills:
            _bill = await Bill.convert(ctx, record['id'])
            pretty.append(f"Bill #{_bill.id} - [{_bill.name}]({_bill.link}) "
                          f"{await _bill.get_emojified_status(verbose=False)}")

        pretty = pretty or ["Nothing found."]

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False, per_page=8,
                                 title=f"{self.bot.mk.NATION_EMOJI}  Bills matching '{query}'",
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @bill.command(name='from', aliases=['f', 'by'])
    async def b_from(self, ctx, *, member_or_party: typing.Union[
        discord.Member, CaseInsensitiveMember, discord.User, PoliticalParty] = None):
        """List all bills that a specific person or Political Party submitted"""

        member = member_or_party or ctx.author

        if isinstance(member, PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
        else:
            name = member.display_name
            members = [member.id]

        bills_from_person = await self.bot.db.fetch("SELECT id FROM legislature_bills "
                                                    "WHERE submitter = ANY($1::bigint[]) ORDER BY id;", members)

        if not bills_from_person:
            if isinstance(member, PoliticalParty):
                title = f"No member of {name} has submitted a bill yet."
            else:
                title = f"{name} hasn't submitted any bills yet."

            embed = self.bot.embeds.embed_builder(title=title)
            return await ctx.send(embed=embed)

        pretty = []

        for record in bills_from_person:
            _bill = await Bill.convert(ctx, record['id'])
            pretty.append(f"Bill #{_bill.id} - [{_bill.name}]({_bill.link}) "
                          f"{await _bill.get_emojified_status(verbose=False)}")

        if isinstance(member, PoliticalParty):
            a_title = f"Bills from members of {name}"
            a_icon = await member.get_logo() or EmptyEmbed
        else:
            a_title = f"Bills from {name}"
            a_icon = member.avatar_url_as(static_format='png')

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False, per_page=8,
                                 a_title=a_title, show_index=False, show_amount_of_pages=True, a_icon=a_icon)
        await pages.paginate()

    @b_from.error
    async def bfrom_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

    async def paginate_all_motions(self, ctx):
        async with ctx.typing():
            query = """SELECT id, title, hastebin FROM legislature_motions ORDER BY id;"""

            all_motions = await self.bot.db.fetch(query)

            if not all_motions:
                embed = self.bot.embeds.embed_builder(title="No one has submitted any motions yet.")
                return await ctx.send(embed=embed)

            pretty = []

            for record in all_motions:
                pretty.append(f"Motion #{record['id']} - [{record['title']}]({record['hastebin']})")

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False, per_page=14,
                                 title=f"{self.bot.mk.NATION_EMOJI}  All Submitted Motions",
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @legislature.group(name='motion', aliases=['m', 'motions'], case_insensitive=True, invoke_without_command=True)
    async def motion(self, ctx, motion_id: Motion = None):
        """List all motions or get details about a single motion"""

        if motion_id is None:
            return await self.paginate_all_motions(ctx)

        motion = motion_id

        embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  Motion #{motion.id}")

        if motion.submitter is not None:
            embed.set_author(name=motion.submitter.name, icon_url=motion.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"{motion.submitter.mention} (during Session #{motion.session.id})"
        else:
            submitted_by_value = f"*Person left Democraciv* (during Session #{motion.session.id})"

        embed.add_field(name="Title", value=f"[{motion.title}]({motion.link})")
        embed.add_field(name="Content", value=motion.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        await ctx.send(embed=embed)

    @motion.command(name='from', aliases=['f', 'by'])
    async def m_from(self, ctx, *, member_or_party: typing.Union[
        discord.Member, CaseInsensitiveMember, discord.User, PoliticalParty] = None):
        """List all motions that a specific person or Political Party submitted"""

        member = member_or_party or ctx.author

        if isinstance(member, PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
        else:
            name = member.display_name
            members = [member.id]

        motions_from_person = await self.bot.db.fetch("SELECT id, title, hastebin FROM legislature_motions "
                                                      "WHERE submitter = ANY($1::bigint[]) ORDER BY id;", members)

        if not motions_from_person:
            if isinstance(member, PoliticalParty):
                title = f"No member of {name} has submitted a motion yet."
            else:
                title = f"{name} hasn't submitted any motions yet."

            embed = self.bot.embeds.embed_builder(title=title)
            return await ctx.send(embed=embed)

        pretty = []

        for record in motions_from_person:
            pretty.append(f"Motion #{record['id']} - [{record['title']}]({record['hastebin']})")

        if isinstance(member, PoliticalParty):
            a_title = f"Motions from members of {name}"
            a_icon = await member.get_logo() or EmptyEmbed
        else:
            a_title = f"Motions from {member.display_name}"
            a_icon = member.avatar_url_as(static_format='png')

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False,
                                 a_title=a_title, show_index=False, show_amount_of_pages=True, a_icon=a_icon)
        await pages.paginate()

    @m_from.error
    async def mfrom_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

    @motion.command(name='search', aliases=['s'])
    async def m_search(self, ctx, *, query: str):
        """Search for a motion"""

        if len(query) < 3:
            return await ctx.send(":x: The query to search for has to be at least 3 characters long.")

        sql_query = """SELECT id from legislature_motions
                       WHERE (lower(title) LIKE '%' || $1 || '%') OR (lower(description) LIKE '%' || $1 || '%')
                       ORDER BY similarity(lower(title), $1) DESC
                       LIMIT 20"""

        found_motions = await self.bot.db.fetch(sql_query, query.lower())
        pretty = []

        for record in found_motions:
            _motion = await Motion.convert(ctx, record['id'])
            pretty.append(f"Motion #{_motion.id} - [{_motion.title}]({_motion.link})")

        pretty = pretty or ["Nothing found."]

        pages = AlternativePages(ctx=ctx, entries=pretty, show_entry_count=False, per_page=8,
                                 title=f"{self.bot.mk.NATION_EMOJI}  Motions matching '{query}'",
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @legislature.command(name='opensession', aliases=['os'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def opensession(self, ctx):
        """Opens a session for the submission period to begin"""

        active_leg_session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is not None:
            return await ctx.send(f":x: There is still an open session, close session #{active_leg_session.id} first!")

        new_session = await self.bot.db.fetchval(
            'INSERT INTO legislature_sessions (speaker, is_active, opened_on)'
            'VALUES ($1, true, $2) RETURNING id', ctx.author.id, datetime.datetime.utcnow())

        await ctx.send(f":white_check_mark: The **submission period** for session #{new_session} was opened.")

        await self.gov_announcements_channel.send(f"The **submission period** for Legislative Session "
                                                  f"#{new_session} has started! Bills and motions can be "
                                                  f"submitted with `-legislature submit`.")

        await self.dm_legislators(reason="leg_session_open",
                                  message=f":envelope_with_arrow: The **submission period** for Legislative Session "
                                          f" #{new_session} has started! Submit your bills and motions with "
                                          f"`-legislature submit` on the Democraciv server.")

    @legislature.command(name='updatesession', aliases=['us'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def updatesession(self, ctx, voting_form: str):
        """Changes the current session's status to be open for voting

        **Example:**
            `-leg updatesession https://forms.gle/asf8an3`

        """

        if not self.bot.laws.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session: Session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(":x: There is no open session.")

        if active_leg_session.status is SessionStatus.VOTING_PERIOD:
            return await ctx.send(":x: This session is already in the Voting Period.")
        elif active_leg_session.status is SessionStatus.CLOSED:
            return await ctx.send(":x: This session is closed.")

        await active_leg_session.start_voting(voting_form)

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} is now in **voting period**.")

        await self.gov_announcements_channel.send(f"The **voting period** for Legislative "
                                                  f"Session #{active_leg_session.id} "
                                                  f"has started!\nVote Form: <{voting_form}>")

        await self.dm_legislators(reason="leg_session_update",
                                  message=f":ballot_box: The **voting period** for Legislative Session "
                                          f"#{active_leg_session.id} has started!\nVote here: {voting_form}")

    @legislature.command(name='closesession', aliases=['cs'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(f":x: There is no open session.")

        await active_leg_session.close()

        #  Update all bills that did not pass
        await self.bot.db.execute("UPDATE legislature_bills SET status = $1 WHERE leg_session = $2",
                                  BillStatus.LEG_FAILED.value,
                                  active_leg_session.id)

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} was closed. "
                       f"Check `-help legislature pass` on what to do next.")

        await self.gov_announcements_channel.send(f"{self.legislator_role.mention}, Legislative Session "
                                                  f"#{active_leg_session.id} has been **closed** by the "
                                                  f"{self.bot.mk.LEGISLATURE_CABINET_NAME}.")

    @legislature.command(name='exportsession', aliases=['es', 'ex', 'export'])
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def exportsession(self, ctx, session: Session = None):
        """Export a session's bills and motions for Google Spreadsheets and generate the Google Forms voting form"""
        if isinstance(session, str):
            return

        session = session or await self.bot.laws.get_last_leg_session()

        if session is None:
            return await ctx.send(":x: There hasn't been a session yet.")

        async with ctx.typing():
            b_ids = list()
            b_hyperlinks = list()

            m_ids = list()
            m_hyperlinks = list()

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                b_ids.append(f"Bill #{bill.id}")
                b_hyperlinks.append(f'=HYPERLINK("{bill.link}"; "{bill.name}")')

            for motion_id in session.motions:
                motion = await Motion.convert(ctx, motion_id)
                m_ids.append(f"Motion #{motion.id}")
                m_hyperlinks.append(f'=HYPERLINK("{motion.link}"; "{motion.name}")')

            exported = [
                f"Export of Legislative Session {session.id} -- {datetime.datetime.utcnow().strftime('%c')}\n\n\n",
                f"Xth Session - {session.opened_on.strftime('%B %d %Y')} (Bot Session {session.id})\n\n"
                "----- Submitted Bills -----\n"]

            exported.extend(b_ids)
            exported.append("\n")
            exported.extend(b_hyperlinks)
            exported.append("\n\n----- Submitted Motions -----\n")
            exported.extend(m_ids)
            exported.append("\n")
            exported.extend(m_hyperlinks)

            link = await self.bot.laws.post_to_hastebin('\n'.join(exported))
            text = f"**__Export of Legislative Session #{session.id}__**\nSee the video below to see how to speed up " \
                   f"your Speaker duties with this command.\n\n**Export:** <{link}>\n\n" \
                   "https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4"
            await ctx.send(text)

        flow = Flow(self.bot, ctx)

        question = await ctx.send(f":information_source: Do you want me to generate the Google Forms"
                                  f" voting form for Legislative Session #{session.id} as well?")

        reaction = await flow.get_continue_confirm(question, "\U00002705", 20)

        if not reaction:
            ctx.command.reset_cooldown(ctx)
            return

        elif reaction:
            await ctx.send(":information_source: Reply with an **edit** link to an **empty** Google Forms "
                           "form you created. I will then fill that form to make it the voting form. "
                           "Create a Form here: <https://forms.new>")

            form_url = await flow.get_private_text_input(120)

            if not form_url:
                ctx.command.reset_cooldown(ctx)
                return

            if not self.bot.laws.is_google_doc_link(form_url):
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(":x: That doesn't look like a Google Forms URL.")

            await ctx.send(f":white_check_mark: I will generate the voting form for Legislative Session #{session.id}."
                           f"\n:arrows_counterclockwise: This may take a few minutes...")

            async with ctx.typing():
                bills = {b.name: b.link for b in [await Bill.convert(ctx, _b) for _b in session.bills]}
                motions = {m.name: m.link for m in [await Motion.convert(ctx, _m) for _m in session.motions]}

                result = await self.bot.google_api.run_apps_script(script_id="MME1GytLY6YguX02rrXqPiGqnXKElby-M",
                                                                   function="generate_form",
                                                                   parameters=[form_url, session.id, bills, motions])

                if result is None or not result['done']:
                    ctx.command.reset_cooldown(ctx)
                    return await ctx.send(":x: There was an error while generating the form.")

                if 'error' in result:
                    ctx.command.reset_cooldown(ctx)

                    error_msg = "Exception: No item with the given ID could be found, or you do" \
                                " not have permission to access it."

                    if result['error']['details'][0]['errorMessage'] == error_msg:
                        return await ctx.send(":x: I cannot access that Google Forms form. Are you sure that you "
                                              "gave me an edit link?")
                    else:
                        return await ctx.send(":x: There was an error while generating the form.")

            embed = self.bot.embeds.embed_builder(title=f"Generated Voting Form for Legislative Session #{session.id}",
                                                  description="Remember to double check the form to make sure it's "
                                                              "correct.\n\nNote that you may have to adjust "
                                                              "the form to comply with this nation's laws.\n"
                                                              "This comes with no guarantees of a form's valid "
                                                              "legal status.\n\nRemember to change the edit link you "
                                                              "gave me earlier to not be public.")

            embed.add_field(name="Link to the Voting Form",
                            value=result['response']['result']['view'],
                            inline=False)

            embed.add_field(name="Shortened Link to the Voting Form",
                            value=result['response']['result']['short-view'],
                            inline=False)

            await ctx.send(embed=embed)

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch("SELECT id, opened_on, closed_on FROM legislature_sessions ORDER BY id")
        pretty_sessions = []

        if not all_sessions:
            embed = self.bot.embeds.embed_builder(title="There hasn't been a session yet.")
            return await ctx.send(embed=embed)

        for record in all_sessions:
            opened_on = record['opened_on'].strftime("%b %d")

            if record['closed_on']:
                closed_on = record['closed_on'].strftime("%b %d %Y")
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on} to {closed_on}")
            else:
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on}")

        pages = AlternativePages(ctx=ctx, entries=pretty_sessions, show_entry_count=False,
                                 title=f"{self.bot.mk.NATION_EMOJI}  All Sessions of the {self.bot.mk.NATION_ADJECTIVE}"
                                       f" {self.bot.mk.LEGISLATURE_NAME}",
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @staticmethod
    def format_session_times(session: Session) -> str:
        formatted_time = [f"**Opened**: {session.opened_on.strftime('%A, %B %d %Y at %H:%M')}"]

        if session.status is not SessionStatus.SUBMISSION_PERIOD:
            # Session is either closed or in Voting Period
            if session.voting_started_on is not None:
                formatted_time.append(
                    f"**Voting Started**: {session.voting_started_on.strftime('%A, %B %d %Y at %H:%M')}")

        if not session.is_active:
            # Session is closed
            formatted_time.append(f"**Ended**: {session.closed_on.strftime('%A, %B %d %Y at %H:%M')}")

        return '\n'.join(formatted_time)

    @staticmethod
    def split_embed_fields(things: str) -> typing.Dict[int, str]:
        lines = things.splitlines(keepends=True)
        split_into_1024 = dict()
        index = 0

        for paragraph in lines:
            try:
                split_into_1024[index]
            except KeyError:
                split_into_1024[index] = ""

            split_into_1024[index] = split_into_1024[index] + ''.join(paragraph)

            if (len(''.join(split_into_1024[index]))) > 924:
                index += 1

        return split_into_1024

    @legislature.command(name='session', aliases=['s'])
    async def session(self, ctx, session: Session = None):
        """Get details about a session from the Legislature

        **Usage:**
        `-legislature session` to see details about the last session
        `-legislature session <number>` to see details about a specific session
        `-legislature session all` to see a list of all previous sessions."""

        # Show all past sessions and their status
        if session == "all":
            return await self.paginate_all_sessions(ctx)

        # User invoked -legislature session without arguments
        elif session is None:
            session = await self.bot.laws.get_last_leg_session()

            if session is None:
                return await ctx.send(":x: There hasn't been a session yet.")

        if len(session.motions) > 0:
            pretty_motions = []
            for motion_id in session.motions:
                motion = await Motion.convert(ctx, motion_id)
                pretty_motions.append(f"Motion #{motion.id} - [{motion.short_name}]({motion.link})")
        else:
            pretty_motions = ["-"]

        if len(session.bills) > 0:
            pretty_bills = []

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                if await bill.is_law():
                    pretty_bills.append(f"__Bill #{bill.id}__ - [{bill.short_name}]({bill.tiny_link})")
                else:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.short_name}]({bill.tiny_link})")
        else:
            pretty_bills = ["-"]

        embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  Legislative Session #{session.id}")

        if session.speaker is not None:
            embed.add_field(name="Opened by", value=session.speaker.mention)
        else:
            embed.add_field(name="Opened by", value="*Person left Democraciv*")

        embed.add_field(name="Status", value=session.status.value, inline=True)
        embed.add_field(name="Date", value=self.format_session_times(session), inline=False)

        if session.vote_form:
            embed.add_field(name="Vote Form", value=f"[Link]({session.vote_form})", inline=False)

        pretty_motions = '\n'.join(pretty_motions)
        pretty_bills = '\n'.join(pretty_bills)

        if len(pretty_motions) <= 1024:
            embed.add_field(name="Submitted Motions", value=pretty_motions, inline=False)
        else:
            fields = self.split_embed_fields(pretty_motions)

            for index in fields:
                if index == 0:
                    embed.add_field(name="Submitted Motions", value=fields[index], inline=False)
                else:
                    embed.add_field(name="Submitted Motions (cont.)", value=fields[index], inline=False)

        if len(pretty_bills) <= 1024:
            embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)
        else:
            fields = self.split_embed_fields(pretty_bills)

            for index in fields:
                if index == 0:
                    embed.add_field(name="Submitted Bills", value=fields[index], inline=False)
                else:
                    embed.add_field(name="Submitted Bills (cont.)", value=fields[index], inline=False)

        if len(embed) > 6000:
            for _ in embed.fields:
                embed.remove_field(4)

            async with ctx.typing():
                haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_motions)
                too_long = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
                embed.add_field(name="Submitted Motions", value=too_long, inline=False)

                haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_bills)
                too_long_ = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
                embed.add_field(name="Submitted Bills", value=too_long_, inline=False)

        embed.set_footer(text="Bills that are underlined are active laws. All times are in UTC.")
        await ctx.send(embed=embed)

    async def submit_bill(self, ctx, current_leg_session_id: int) -> typing.Tuple[typing.Optional[str],
                                                                                  typing.Optional[discord.Embed]]:
        """Submits a bill to a session that is in Submission Period. Uses the Flow API to get the bill
         details via Discord. Returns the message and formatted Embed that will be sent to
          the Cabinet upon submission."""

        flow = Flow(self.bot, ctx)

        # Google Docs Link
        await ctx.send(":white_check_mark: You will submit a **bill**.\n"
                       ":information_source: Reply with the Google Docs link to the bill you want to submit.")
        google_docs_url = await flow.get_text_input(150)

        if not google_docs_url:
            return None, None

        if not self.bot.laws.is_google_doc_link(google_docs_url):
            await ctx.send(":x: That doesn't look like a Google Docs URL.")
            ctx.command.reset_cooldown(ctx)
            return None, None

        # Vetoable
        veto_question = await ctx.send(f":information_source: Is the {self.bot.mk.MINISTRY_NAME} legally allowed to "
                                       f"veto (or vote on) this bill?")

        reaction = await flow.get_yes_no_reaction_confirm(veto_question, 200)

        if reaction is None:
            return None, None

        is_vetoable = True if reaction else False

        # Description
        await ctx.send(
            ":information_source: Reply with a **short** (max. 2 sentences) description of what your "
            "bill does.")

        bill_description = await flow.get_text_input(620)

        if not bill_description:
            bill_description = "-"

        async with ctx.typing():
            google_meta_info = await self.bot.laws.get_google_docs_meta_data(google_docs_url)

            if google_meta_info is None:
                await ctx.send(":x: Couldn't connect to Google Docs. Make sure that the document can be"
                               " read by anyone and that it's not a published version.")
                ctx.command.reset_cooldown(ctx)
                return None, None

            bill_title = google_meta_info["title"]
            google_description = google_meta_info["description"]

            # Make the Google Docs link smaller to workaround the "embed value cannot be longer than 1024 characters
            # in -legislature session" issue
            tiny_url = await self.bot.laws.post_to_tinyurl(google_docs_url)

            if tiny_url is None:
                await ctx.send(":x: Your bill was not submitted since there was a problem with tinyurl.com. "
                               "Try again in a few minutes.")
                return None, None

            try:
                await self.bot.db.execute(
                    "INSERT INTO legislature_bills (leg_session, link, bill_name, submitter, is_vetoable, "
                    "description, tiny_link, google_docs_description) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    current_leg_session_id, google_docs_url, bill_title, ctx.author.id, is_vetoable,
                    bill_description, tiny_url, google_description)
            except asyncpg.UniqueViolationError:
                await ctx.send(":x: A bill with the same exact Google Docs Document was already submitted!")
                return None, None

            message = "Hey! A new **bill** was just submitted."
            embed = self.bot.embeds.embed_builder(title="Bill Submitted", description="", time_stamp=True)
            embed.add_field(name="Title", value=bill_title, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name, inline=False)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(name=f"{self.bot.mk.MINISTRY_NAME} Veto Allowed", value="Yes" if is_vetoable else "No")
            embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)
            embed.add_field(name="URL", value=google_docs_url, inline=False)

        await ctx.send(
            f":white_check_mark: Your bill `{bill_title}` was submitted for session #{current_leg_session_id}.")

        return message, embed

    async def submit_motion(self, ctx, current_leg_session_id: int) -> typing.Tuple[typing.Optional[str],
                                                                                    typing.Optional[discord.Embed]]:
        """Submits a motion to a session that is in Submission Period. Uses the Flow API to get the bill
           details via Discord. Returns the message and formatted Embed that will be sent to
           the Cabinet upon submission."""

        flow = Flow(self.bot, ctx)

        await ctx.send(":white_check_mark: You will submit a **motion**.\n"
                       ":information_source: Reply with the title of your motion.")

        title = await flow.get_text_input(300)

        if not title:
            return None, None

        await ctx.send(":information_source: Reply with the content of your motion. If your motion is"
                       " inside a Google Docs document, just use a link to that for this.")

        description = await flow.get_text_input(600)

        if not description:
            return None, None

        async with ctx.typing():
            haste_bin_url = await self.bot.laws.post_to_hastebin(description)

            if not haste_bin_url:
                await ctx.send(":x: Your motion was not submitted, there was a problem with mystb.in. "
                               "Try again in a few minutes.")
                return None, None

            await self.bot.db.execute(
                "INSERT INTO legislature_motions (leg_session, title, description, submitter, hastebin) "
                "VALUES ($1, $2, $3, $4, $5)",
                current_leg_session_id, title, description, ctx.author.id, haste_bin_url)

            message = "Hey! A new **motion** was just submitted."
            embed = self.bot.embeds.embed_builder(title="Motion Submitted", description="", time_stamp=True)
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Content", value=description, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)

        await ctx.send(
            f":white_check_mark: Your motion `{title}` was submitted for session #{current_leg_session_id}.")

        return message, embed

    @legislature.command(name='submit')
    @commands.cooldown(1, 180, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    @checks.is_democraciv_guild()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        if self.is_cabinet(ctx.author):
            ctx.command.reset_cooldown(ctx)

        if self.speaker is None:
            raise exceptions.NoOneHasRoleError(mk.DemocracivRole.SPEAKER.printable_name)

        current_leg_session: Session = await self.bot.laws.get_active_leg_session()

        if current_leg_session is None:
            return await ctx.send(":x: There is no active session.")

        if current_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(f":x: The submission period for session #{current_leg_session.id} is already over.")

        flow = Flow(self.bot, ctx)

        bill_motion_question = await ctx.send(f":information_source: Do you want to submit a motion or a bill?"
                                              f" React with {config.LEG_SUBMIT_BILL} for bill, and with "
                                              f"{config.LEG_SUBMIT_MOTION} for a motion.")

        reaction, user = await flow.get_emoji_choice(config.LEG_SUBMIT_BILL, config.LEG_SUBMIT_MOTION,
                                                     bill_motion_question, 200)

        message = embed = None

        if not reaction:
            return

        if str(reaction.emoji) == config.LEG_SUBMIT_BILL:

            if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
                if self.legislator_role not in ctx.author.roles:
                    return await ctx.send(f":x: Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} are allowed to "
                                          f"submit bills!")

            message, embed = await self.submit_bill(ctx, current_leg_session.id)

        elif str(reaction.emoji) == config.LEG_SUBMIT_MOTION:
            ctx.command.reset_cooldown(ctx)

            if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS:
                if self.legislator_role not in ctx.author.roles:
                    return await ctx.send(f":x: Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} are allowed to "
                                          f"submit motions!")

            message, embed = await self.submit_motion(ctx, current_leg_session.id)

        if message is None:
            return

        if not self.is_cabinet(ctx.author):
            if self.speaker is not None:
                await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_submit", message=message,
                                            embed=embed)
            if self.vice_speaker is not None:
                await self.bot.safe_send_dm(target=self.vice_speaker, reason="leg_session_submit", message=message,
                                            embed=embed)

    @legislature.command(name='pass', aliases=['p'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def pass_bill(self, ctx, bill_ids: Greedy[Bill]):
        """Mark one or multiple bills as passed from the Legislature

        If the bill is vetoable, it sends the bill to the Ministry. If not, the bill automatically becomes law.

        **Example:**
            `-leg pass 12` will mark Bill #12 as passed from the Legislature
            `-leg pass 45 46 49 51 52` will mark all those bills as passed"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        bills = bill_ids
        last_leg_session: Session = await self.bot.laws.get_last_leg_session()
        flow = Flow(self.bot, ctx)

        async def verify_bill(_bill: Bill, last_session: Session) -> typing.Optional[str]:
            if last_session.id != _bill.session.id:
                return "You can only mark bills from the most recent session as passed."

            if last_session.status is not SessionStatus.CLOSED:
                return "You cannot mark bills as passed while their session is still in Submission or Voting Period."

            if _bill.status is not BillStatus.SUBMITTED or _bill.status is not BillStatus.LEG_FAILED:
                return "You already voted on this bill."

        error_messages = []

        # Check if every bill the Speaker gave us can be passed
        for bill in bills:
            error = await verify_bill(bill, last_leg_session)
            if error:
                error_messages.append((bill, error))

        if error_messages:
            # Remove bills that did not pass verify_bill from MultipleBills.bills list
            bills = [b for b in bills if b not in list(map(list, zip(*error_messages)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_bill.name}** (#{_bill.id}): _{reason}_" for _bill, reason in error_messages])
            await ctx.send(f":warning: The following bills can not be passed.\n{error_messages}")

        # If all bills failed verify_bills, return
        if not bills:
            return

        pretty_bills = '\n'.join([f"-  **{_bill.name}** (#{_bill.id})" for _bill in bills])
        are_you_sure = await ctx.send(f":information_source: Are you sure that you want "
                                      f"to mark the following bills as passed from the {self.bot.mk.LEGISLATURE_NAME}?"
                                      f"\n{pretty_bills}")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with ctx.typing():
                for _bill in bills:
                    await _bill.pass_from_legislature()

                    if not _bill.is_vetoable:
                        await _bill.pass_into_law()

                    self.scheduler.add(_bill)

                await ctx.send(f":white_check_mark: All bills were marked as passed from "
                               f"the {self.bot.mk.LEGISLATURE_NAME}.")

    @legislature.group(name='withdraw', aliases=['w'], group_show_parent_in_help=False)
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx):
        """Withdraw one or multiple bills or motions from the current session"""
        if ctx.invoked_subcommand is None:
            await ctx.send(":x: You have to tell me whether you want to withdraw motions or bills!"
                           " Take a look at the help page:")
            await ctx.send_help(ctx.command)

    async def withdraw_objects(self, ctx, objects: typing.List[typing.Union[Bill, Motion]]):

        if isinstance(objects[0], Bill):
            obj_name = "bill"
        else:
            obj_name = "motion"

        last_leg_session = await self.bot.laws.get_last_leg_session()

        def verify_object(to_verify) -> str:
            if not to_verify.session.is_active:
                return f"The session during which this {obj_name} was submitted is not open anymore."

            if isinstance(to_verify, Bill) and to_verify.status is not BillStatus.SUBMITTED:
                return f"This {obj_name} was already voted on by the {self.bot.mk.LEGISLATURE_NAME}."

            if not self.is_cabinet(ctx.author):
                if to_verify.submitter is not None and ctx.author.id == to_verify.submitter.id:
                    if last_leg_session.status is SessionStatus.SUBMISSION_PERIOD:
                        allowed = True
                    else:
                        return f"The original submitter can only withdraw {obj_name}s during the Submission Period."
                else:
                    allowed = False
            else:
                allowed = True

            if not allowed:
                return f"Only the {self.bot.mk.LEGISLATURE_CABINET_NAME} and the original submitter " \
                       f"of this {obj_name} can withdraw it."

        unverified_objects = []

        for obj in objects:
            error = verify_object(obj)
            if error:
                unverified_objects.append((obj, error))

        if unverified_objects:
            objects = [o for o in objects if o not in list(map(list, zip(*unverified_objects)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_object.name}** (#{_object.id}): _{reason}_" for _object, reason in unverified_objects])
            await ctx.send(f":warning: The following {obj_name}s can not be withdrawn by you.\n{error_messages}")

        if not objects:
            return

        pretty_objects = '\n'.join([f"-  **{_object.name}** (#{_object.id})" for _object in objects])
        are_you_sure = await ctx.send(f":information_source: Are you sure that you want"
                                      f" to withdraw the following {obj_name}s from Session #{last_leg_session.id}?"
                                      f"\n{pretty_objects}")

        flow = Flow(self.bot, ctx)
        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            for obj in objects:
                try:
                    await obj.withdraw()
                except asyncpg.ForeignKeyViolationError:
                    await ctx.send(f":warning: Bill #{obj.id} is already a law and cannot be withdrawn.")

            await ctx.send(f":white_check_mark: All {obj_name}s were withdrawn.")

            message = f"The following {obj_name}s were withdrawn by {ctx.author}.\n{pretty_objects}"

            if not self.is_cabinet(ctx.author):
                if self.speaker is not None:
                    await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_withdraw",
                                                message=message)
                if self.vice_speaker is not None:
                    await self.bot.safe_send_dm(target=self.vice_speaker, reason="leg_session_withdraw",
                                                message=message)

    @withdraw.command(name='bill', aliases=['b'])
    @checks.is_democraciv_guild()
    async def withdrawbill(self, ctx, bill_ids: Greedy[Bill]):
        """Withdraw one or multiple bills from the current session

        The Speaker and Vice-Speaker can withdraw every submitted bill during both the Submission Period and the Voting Period.
           The original submitter of the bill can only withdraw their own bill during the Submission Period.

        **Examples:**
            `-legislature withdraw bill 56` will withdraw bill #56
            `-legislature withdraw bill 12 13 14 15 16` will withdraw all those bills"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, bill_ids)

    @withdraw.command(name='motion', aliases=['m'])
    @checks.is_democraciv_guild()
    async def withdrawmotion(self, ctx, motion_ids: Greedy[Motion]):
        """Withdraw one or multiple motions from the current session

        The Speaker and Vice-Speaker can withdraw every submitted motion during both the Submission Period and the Voting Period.
           The original submitter of the motion can only withdraw their own motio during the Submission Period.

        **Examples:**
            `-legislature withdraw motion 56` will withdraw motion #56
            `-legislature withdraw motion 12 13 14 15 16` will withdraw all those motions"""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, motion_ids)

    @legislature.command(name='override', aliases=['ov'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def override(self, ctx, bill_ids: Greedy[Bill]):
        """Override the veto of one or multiple bills to pass them into law

         **Examples:**
            `-legislature override 56`
            `-legislature override 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        bills = bill_ids

        async def verify_bill(bill_to_verify: Bill) -> str:
            if bill_to_verify.status is not BillStatus.MIN_FAILED:
                return "This bill is not currently vetoed."

        unverified_bills = []

        for bill in bills:
            error = await verify_bill(bill)
            if error:
                unverified_bills.append((bill, error))

        if unverified_bills:
            bills = [b for b in bills if b not in list(map(list, zip(*unverified_bills)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_bill.name}** (#{_bill.id}): _{reason}_" for _bill, reason in unverified_bills])
            await ctx.send(f":warning: The vetos of the following bills can not be overridden.\n{error_messages}")

        if not bills:
            return

        pretty_objects = '\n'.join([f"-  **{_bill.name}** (#{_bill.id})" for _bill in bills])
        are_you_sure = await ctx.send(f":information_source: Are you sure that you want "
                                      f"to override the {self.bot.mk.MINISTRY_NAME}'s veto of the following "
                                      f"bills?\n{pretty_objects}")

        flow = Flow(self.bot, ctx)
        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            for bill in bills:
                await bill.pass_into_law(override=True)
                self.override_scheduler.add(bill)

            await ctx.send(f":white_check_mark: The vetos of all bills were overridden.")

    @legislature.command(name='stats', aliases=['stat', 'statistics', 'statistic'])
    async def stats(self, ctx):
        """Statistics about the Legislature"""

        async with ctx.typing():
            stats = await self.bot.laws.generate_leg_statistics()

            embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  Statistics for the "
                                                        f"{self.bot.mk.NATION_ADJECTIVE} "
                                                        f"{self.bot.mk.LEGISLATURE_NAME}")

            general_value = f"Sessions: {stats[0]}\n" \
                            f"Submitted Bills: {stats[1]}\n" \
                            f"Submitted Motions: {stats[3]}\n" \
                            f"Active Laws: {stats[2]}"

            embed.add_field(name="General Statistics", value=general_value)
            embed.add_field(name=f"Top {self.bot.mk.speaker_term}s or {self.bot.mk.vice_speaker_term}s of "
                                 f"the {self.bot.mk.LEGISLATURE_NAME}",
                            value=stats[5], inline=False)
            embed.add_field(name="Top Bill Submitters", value=stats[4], inline=False)
            embed.add_field(name="Top Lawmakers", value=stats[6], inline=False)

        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            await ctx.send(":x: There has to be activity in the Legislature first.")


def setup(bot):
    bot.add_cog(Legislature(bot))
