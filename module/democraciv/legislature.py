import typing
import asyncpg
import discord
import datetime

from util.flow import Flow
from util.paginator import Pages
from config import config, links
from discord.ext import commands
from discord.ext.commands import Greedy
from util import utils, mk, exceptions
from util.law_helper import AnnouncementQueue
from util.converter import Session, SessionStatus, Bill, Motion, Law


class PassScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = [f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the following bills were **passed by the Legislature**.\n"]

        for obj in self._objects:
            if obj.is_vetoable:
                message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")
            else:
                message.append(f"-  __**{obj.name}**__ (<{obj.tiny_link}>)")

        message.append("\nAll non-vetoable bills are now laws (marked as __underlined__),"
                       " the others were sent to the Ministry.")
        return '\n'.join(message)


class OverrideScheduler(AnnouncementQueue):

    def get_message(self) -> str:
        message = [f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the Ministry's **veto of the following bills were overridden** by the Legislature.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        message.append("\nAll of the above bills are now law.")
        return '\n'.join(message)


class Legislature(commands.Cog):
    """Allows the Cabinet to organize Legislative Sessions and their submitted bills and motions."""

    def __init__(self, bot):
        self.bot = bot
        self.scheduler = PassScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.override_scheduler = OverrideScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    @property
    def speaker(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.SPEAKER_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def speaker_role(self) -> typing.Optional[discord.Role]:
        return mk.get_democraciv_role(self.bot, mk.DemocracivRole.SPEAKER_ROLE)

    @property
    def vice_speaker(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.VICE_SPEAKER_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def vice_speaker_role(self) -> typing.Optional[discord.Role]:
        return mk.get_democraciv_role(self.bot, mk.DemocracivRole.VICE_SPEAKER_ROLE)

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    @property
    def legislator_role(self) -> typing.Optional[discord.Role]:
        return mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE)

    async def dm_legislators(self, message: str):
        for legislator in self.legislator_role.members:
            try:
                await legislator.send(message)
            except discord.Forbidden:
                await self.bot.owner.send(f"Failed to DM {legislator}.")

    def is_cabinet(self, member: discord.Member) -> bool:
        if self.speaker_role in member.roles or self.vice_speaker_role in member.roles:
            return True
        return False

    @commands.group(name='legislature', aliases=['leg'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legislature(self, ctx):
        """Dashboard for Legislators with important links and the status of the current session"""

        active_leg_session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            current_session_value = "There currently is no open session."
        else:
            current_session_value = f"Session #{active_leg_session.id} - {active_leg_session.status.value}"

        embed = self.bot.embeds.embed_builder(title=f"The Legislature of {mk.NATION_NAME}", description="")
        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(f"Speaker: {self.speaker.mention}")
        else:
            speaker_value.append("Speaker: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(f"Vice-Speaker: {self.vice_speaker.mention}")
        else:
            speaker_value.append("Vice-Speaker: -")

        embed.add_field(name="Legislative Cabinet", value='\n'.join(speaker_value))
        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Docket]({links.legislativedocket})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Legislative Procedures]({links.legislativeprocedures})", inline=True)
        embed.add_field(name="Current Session", value=current_session_value, inline=False)
        await ctx.send(embed=embed)

    @legislature.command(name='bill', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def bill(self, ctx, *, bill_id: Bill):
        """Details about a bill"""

        bill = bill_id

        embed = self.bot.embeds.embed_builder(title=f"Bill #{bill.id}", description="", has_footer=False)

        if bill.submitter is not None:
            embed.set_author(name=bill.submitter.name, icon_url=bill.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"During Session #{bill.session.id} by {bill.submitter.mention}"
        else:
            submitted_by_value = f"During Session #{bill.session.id} by *Person left Democraciv*"

        is_vetoable = "Yes" if bill.is_vetoable else "No"

        embed.add_field(name="Name", value=f"[{bill.name}]({bill.link})")
        embed.add_field(name="Description", value=bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        embed.add_field(name="Vetoable", value=is_vetoable, inline=False)
        embed.add_field(name="Status", value=await bill.get_emojified_status(verbose=True), inline=False)

        if await bill.is_law():
            law = await Law.from_bill(ctx, bill.id)
            embed.set_footer(text=f"Associated Law: #{law.id}", icon_url=config.BOT_ICON_URL)

        await ctx.send(embed=embed)

    @legislature.command(name='motion', aliases=['m'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def motion(self, ctx, motion_id: Motion):
        """Details about a motion"""

        motion = motion_id

        embed = self.bot.embeds.embed_builder(title=f"Motion #{motion.id}", description="", has_footer=False)

        if motion.submitter is not None:
            embed.set_author(name=motion.submitter.name, icon_url=motion.submitter.avatar_url_as(static_format='png'))
            submitted_by_value = f"{motion.submitter.mention} (during Session #{motion.session.id})"
        else:
            submitted_by_value = f"*Submitter left Democraciv* (during Session #{motion.session.id})"

        embed.add_field(name="Name", value=f"[{motion.title}]({motion.link})")
        embed.add_field(name="Content", value=motion.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        await ctx.send(embed=embed)

    @legislature.command(name='opensession', aliases=['os'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
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
                                                  f"#{new_session} has started! Everyone is allowed "
                                                  f"to submit bills with `-legislature submit`.")

        await self.dm_legislators(f":envelope_with_arrow: The **submission period** for Legislative Session"
                                  f" #{new_session} has started! Submit your bills and motions with "
                                  f"`-legislature submit` on the Democraciv server.")

    @legislature.command(name='updatesession', aliases=['us'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatesession(self, ctx, voting_form: str):
        """Changes the current session's status to be open for voting

        **Example:**
            `-leg updatesession https://forms.gle/asf8an3`

        """

        if not self.bot.laws.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session: Session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(":x: There is no open session!")

        if active_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(":x: You can only update a session to be in Voting Period that was previously in the"
                                  "Submission Period!")

        await active_leg_session.start_voting(voting_form)

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} is now in **voting period**.")

        await self.gov_announcements_channel.send(f"The **voting period** for Legislative "
                                                  f"Session #{active_leg_session.id}"
                                                  f" has started! Legislators can vote here: {voting_form}")

        await self.dm_legislators(f":ballot_box: The **voting period** for Legislative Session "
                                  f"#{active_leg_session.id} has started!\nVote here: {voting_form}")

    @legislature.command(name='closesession', aliases=['cs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(f":x: There is no open session!")

        await active_leg_session.close()

        #  Update all bills that did not pass
        await self.bot.db.execute("UPDATE legislature_bills SET has_passed_leg = false,"
                                  " voted_on_by_leg = true WHERE leg_session = $1 "
                                  "AND voted_on_by_leg = false", active_leg_session.id)

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} was closed. "
                       f"Check `-help legislature pass` on what to do next.")

        await self.gov_announcements_channel.send(f"{self.legislator_role.mention}, Legislative Session "
                                                  f"#{active_leg_session.id} has been **closed** by the Cabinet.")

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch("SELECT id, opened_on, closed_on FROM legislature_sessions ORDER BY id")
        pretty_sessions = []

        for record in all_sessions:
            opened_on = record['opened_on'].strftime("%b %d")

            if record['closed_on']:
                closed_on = record['closed_on'].strftime("%b %d %Y")
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on} to {closed_on}")
            else:
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on}")

        footer = f"Use {ctx.prefix}legislature session <number> to get more details about a session."

        pages = Pages(ctx=ctx, entries=pretty_sessions, show_entry_count=False,
                      title=f"All Sessions of the {mk.NATION_ADJECTIVE} Legislature",
                      show_index=False, footer_text=footer, show_amount_of_pages=True)
        await pages.paginate()

    @staticmethod
    def format_session_times(session: Session) -> str:
        formatted_time = [f"**Opened**: {session.opened_on.strftime('%A, %B %d %Y at %H:%M')}"]

        if session.status is not SessionStatus.SUBMISSION_PERIOD:
            # Session is either closed or in Voting Period
            if session.voting_started_on is not None:
                formatted_time.append(f"**Voting Started**: {session.voting_started_on.strftime('%A, %B %d %Y at %H:%M')}")

        if not session.is_active:
            # Session is closed
            formatted_time.append(f"**Ended**: {session.closed_on.strftime('%A, %B %d %Y at %H:%M')}")

        return '\n'.join(formatted_time)

    @legislature.command(name='session', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
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
                return await ctx.send(":x: There hasn't been any session yet.")

        if len(session.motions) > 0:
            pretty_motions = []
            for motion_id in session.motions:
                motion = await Motion.convert(ctx, motion_id)

                # If the motion's description is just a Google Docs link, use that link instead of the Hastebin
                is_google_docs = self.bot.laws.is_google_doc_link(motion.description) and len(motion.description) <= 100
                link = motion.description if is_google_docs else motion.link
                pretty_motions.append(f"Motion #{motion.id} - [{motion.short_name}]({link})")
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

        embed = self.bot.embeds.embed_builder(title=f"Legislative Session #{session.id}", description="")

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
            async with ctx.typing():
                haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_motions)
            too_long_motions = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
            embed.add_field(name="Submitted Motions", value=too_long_motions, inline=False)

        if len(pretty_bills) <= 1024:
            embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)
        else:
            async with ctx.typing():
                haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_bills)
            too_long_bills = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
            embed.add_field(name="Submitted Bills", value=too_long_bills, inline=False)

        embed.set_footer(text=f"Bills that are underlined are active laws. All times are in UTC.",
                         icon_url=config.BOT_ICON_URL)
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
            return None, None

        # Vetoable
        veto_question = await ctx.send(":information_source: Is the Ministry legally allowed to veto (or vote on) "
                                       "this bill?")
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
            embed.add_field(name="Ministry Veto Allowed", value="Yes" if is_vetoable else "No")
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
    @utils.is_democraciv_guild()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        if self.speaker is None:
            raise exceptions.NoOneHasRoleError(mk.DemocracivRole.SPEAKER_ROLE.printable_name)

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

        if not reaction:
            return

        if str(reaction.emoji) == config.LEG_SUBMIT_BILL:
            message, embed = await self.submit_bill(ctx, current_leg_session.id)

        elif str(reaction.emoji) == config.LEG_SUBMIT_MOTION:
            if self.legislator_role not in ctx.author.roles:
                return await ctx.send(":x: Only Legislators are allowed to submit motions!")
            message, embed = await self.submit_motion(ctx, current_leg_session.id)

        if message is None:
            return

        try:
            if self.speaker is not None:
                await self.speaker.send(content=message, embed=embed)
            if self.vice_speaker is not None:
                await self.vice_speaker.send(content=message, embed=embed)
        except discord.Forbidden:
            pass

    @legislature.command(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
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
                return f"You can only mark bills from the most recent session of the Legislature as passed."

            if last_session.status is not SessionStatus.CLOSED:
                return f"You cannot mark bills as passed while their session is still in Submission or Voting Period."

            if _bill.passed_leg:
                return f"You already voted on this bill!"

        error_messages = []

        # Check if every bill the Speaker gave us can be passed
        for bill in bills:
            error = await verify_bill(bill, last_leg_session)
            if error:
                error_messages.append((bill, error))

        if error_messages:
            # Remove bills that did not pass verify_bill from MultipleBills.bills list
            bills = [b for b in bills if b not in list(map(list, zip(*error_messages)))[0]]

            error_messages = '\n'.join([f"-  **{_bill.name}** (#{_bill.id}): _{reason}_" for _bill, reason in error_messages])
            await ctx.send(f":warning: The following bills can not be passed.\n{error_messages}")

        # If all bills failed verify_bills, return
        if not bills:
            return

        pretty_bills = '\n'.join([f"-  **{_bill.name}** (#{_bill.id})" for _bill in bills])
        are_you_sure = await ctx.send(f":information_source: Are you sure that you want"
                                      f" to mark the following bills as passed from the Legislature?"
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

                await ctx.send(":white_check_mark: All bills were marked as passed from the Legislature.")

    @legislature.group(name='withdraw', aliases=['w'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def withdraw(self, ctx):
        """Withdraw one or multiple bills or motions from the current session"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def withdraw_objects(self, ctx, objects: typing.List[typing.Union[Bill, Motion]]):

        if isinstance(objects[0], Bill):
            obj_name = "bill"
        else:
            obj_name = "motion"

        last_leg_session = await self.bot.laws.get_last_leg_session()

        def verify_object(to_verify) -> str:
            if last_leg_session.id != to_verify.session.id:
                return f"This {obj_name} was not submitted in the last session of the Legislature."

            if isinstance(to_verify, Bill) and to_verify.voted_on_by_leg:
                return f"This {obj_name} was already voted on by the Legislature."

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
                return f"Only the Cabinet and the original submitter of this {obj_name} can withdraw it."

        unverified_objects = []

        for obj in objects:
            error = verify_object(obj)
            if error:
                unverified_objects.append((obj, error))

        if unverified_objects:
            objects = [o for o in objects if o not in list(map(list, zip(*unverified_objects)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_object.name}** (#{_object.id}): _{reason}_" for _object, reason in unverified_objects])
            await ctx.send(f":warning: The following motions can not be withdrawn by you.\n{error_messages}")

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

    @withdraw.command(name='bill', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
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
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
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
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def override(self, ctx, bill_ids: Greedy[Bill]):
        """Override the veto of one or multiple bills to pass them into law

         **Examples:**
            `-legislature override 56`
            `-legislature override 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        bills = bill_ids

        async def verify_bill(bill_to_verify) -> str:
            if not bill_to_verify.passed_leg:
                return "This bill did not pass the Legislature."

            if not bill_to_verify.voted_on_by_ministry:
                return "The Ministry did not vote on this bill yet."

            if await bill_to_verify.is_law() or bill_to_verify.passed_ministry:
                return "This bill is already law."

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
        are_you_sure = await ctx.send(f":information_source: Are you sure that you want"
                                      f" to override the Ministry's veto of the following bills?\n{pretty_objects}")

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

    @legislature.command(name='stats')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def stats(self, ctx):
        """Statistics about the Legislature"""

        async with ctx.typing():
            stats = await self.bot.laws.generate_leg_statistics()

            embed = self.bot.embeds.embed_builder(title=f"Statistics for the {mk.NATION_ADJECTIVE} Legislature",
                                                  description="")

            general_value = f"Total Amount of Legislative Sessions: {stats[0]}\n" \
                            f"Total Amount of Submitted Bills: {stats[1]}\n" \
                            f"Total Amount of Submitted Motions: {stats[3]}\n" \
                            f"Total Amount of Laws: {stats[2]}"

            embed.add_field(name="General Statistics", value=general_value)
            embed.add_field(name="Top Speakers or Vice-Speakers of the Legislature ", value=stats[5], inline=False)
            embed.add_field(name="Top Bill Submitters", value=stats[4], inline=False)
            embed.add_field(name="Top Lawmakers", value=stats[6], inline=False)

        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            await ctx.send(":x: There has to be activity in the Legislature first.")


def setup(bot):
    bot.add_cog(Legislature(bot))
