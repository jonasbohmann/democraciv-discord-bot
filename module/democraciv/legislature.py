import typing
import asyncpg
import discord
import datetime

from util.flow import Flow
from discord.ext import commands
from util.paginator import Pages
from config import config, links
from util import utils, mk, exceptions
from util.converter import Session, SessionStatus, Bill, Motion


# TODO - multiple bills in -leg pass, -m pass, -m veto
# TODO - queue new vetos & pass to not spam discord channels

class Legislature(commands.Cog):
    """Allows the Cabinet to organize Legislative Sessions and their submitted bills and motions."""

    def __init__(self, bot):
        self.bot = bot

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

        if bill.submitter is not None:
            submitted_by_value = f"{bill.submitter.mention} (during Session #{bill.session.id})"
        else:
            submitted_by_value = f"*Submitter left Democraciv* (during Session #{bill.session.id})"

        embed = self.bot.embeds.embed_builder(title=f"Bill Details", description="")
        embed.add_field(name="Name", value=f"[{bill.name}]({bill.link})")
        embed.add_field(name="Description", value=bill.description, inline=False)
        embed.add_field(name="Submitter", value=submitted_by_value, inline=False)
        embed.add_field(name="Vetoable", value=bill.is_vetoable, inline=False)
        embed.add_field(name="Status", value=await bill.get_emojified_status(verbose=True), inline=False)
        await ctx.send(embed=embed)

    @legislature.command(name='motion', aliases=['m'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def motion(self, ctx, motion_id: Motion):
        """Details about a motion"""

        motion = motion_id

        if motion.submitter is not None:
            submitted_by_value = f"{motion.submitter.mention} (during Session #{motion.session.id})"
        else:
            submitted_by_value = f"*Submitter left Democraciv* (during Session #{motion.session.id})"

        embed = self.bot.embeds.embed_builder(title=f"Motion Details", description="")
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
            'INSERT INTO legislature_sessions (speaker, is_active, status, opened_on)'
            'VALUES ($1, true, $2, $3) RETURNING id', ctx.author.id, 'Submission Period',
            datetime.datetime.utcnow())

        #  Update all bills that did not pass from last session
        if new_session > 1:
            await self.bot.db.execute("UPDATE legislature_bills SET has_passed_leg = false,"
                                      " voted_on_by_leg = true WHERE leg_session = %1 "
                                      "AND voted_on_by_leg = false", new_session - 1)

        await ctx.send(f":white_check_mark: The **submission period** for session #{new_session} was opened.")

        await self.gov_announcements_channel.send(f"The **submission period** for Legislative Session "
                                                  f"#{new_session} has started! Everyone is allowed "
                                                  f"to submit bills with `-legislature submit`.")

        await self.dm_legislators(f":envelope_with_arrow: The **submission period** for Legislative Session"
                                  f" #{new_session} has started! Submit your bills and motions with "
                                  f"`-legislature submit` on the Democraciv guild.")

    @legislature.command(name='updatesession', aliases=['us'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def updatesession(self, ctx, voting_form: str):
        """Changes the current session's status to be open for voting"""

        if not self.bot.laws.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session: Session = await self.bot.laws.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(":x: There is no open session!")

        if active_leg_session.status != SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(":x: You can only update a session to be in Voting Period that was previously in the"
                                  "Submission Period!")

        await self.bot.db.execute("UPDATE legislature_sessions SET status = 'Voting Period',"
                                  " voting_started_on = $2, vote_form = $3"
                                  " WHERE id = $1", active_leg_session.id, datetime.datetime.utcnow(), voting_form)

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} is now in **voting period**.")

        await self.gov_announcements_channel.send(f"The **voting period for Legislative "
                                                  f"Session #{active_leg_session.id}**"
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

        await self.bot.db.execute("UPDATE legislature_sessions SET is_active = false, closed_on = $2,"
                                  " status = 'Closed' WHERE id = $1", active_leg_session.id, datetime.datetime.utcnow())

        await ctx.send(f":white_check_mark: Session #{active_leg_session.id} was closed."
                       f" Add the bills that passed this session with `-legislature pass <bill_id>`. Get the "
                       f"bill ids from the list of submitted bills in `-legislature session {active_leg_session.id}`")

        await self.gov_announcements_channel.send(f"{self.legislator_role.mention}, **Legislative Session "
                                                  f"#{active_leg_session.id} has been closed** by the Cabinet.")

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch("SELECT id, status FROM legislature_sessions ORDER BY id")

        pretty_sessions = [f"**Session #{record['id']}**  - {record['status']}" for record in all_sessions]
        footer = f"Use {ctx.prefix}legislature session <number> to get more details about a session."

        pages = Pages(ctx=ctx, entries=pretty_sessions, show_entry_count=False,
                      title=f"All Sessions of the {mk.NATION_ADJECTIVE} Legislature",
                      show_index=False, footer_text=footer)
        await pages.paginate()

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

        if len(session.motions) > 0:
            pretty_motions = []
            for motion_id in session.motions:
                motion = await Motion.convert(ctx, motion_id)

                # If the motion's description is just a Google Docs link, use that link instead of the Hastebin
                is_google_docs = self.bot.laws.is_google_doc_link(motion.description) and len(motion.description) <= 100
                link = motion.description if is_google_docs else motion.link

                if motion.submitter is not None:
                    pretty_motions.append(f"Motion #{motion.id} - [{motion.title}]({link}) by "
                                          f"{motion.submitter.mention}")
                else:
                    pretty_motions.append(f"Motion #{motion.id} - [{motion.title}]({link})")
        else:
            pretty_motions = ["-"]

        if len(session.bills) > 0:
            pretty_bills = []

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                if bill.submitter is not None:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.name}]({bill.tiny_link}) by "
                                        f"{bill.submitter.mention} {await bill.get_emojified_status(verbose=False)}")
                else:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.name}]({bill.tiny_link}) "
                                        f"{await bill.get_emojified_status(verbose=False)}")
        else:
            pretty_bills = ["-"]

        embed = self.bot.embeds.embed_builder(title=f"Legislative Session #{session.id}", description="")

        if session.speaker is not None:
            embed.add_field(name="Opened by", value=session.speaker.mention)
        else:
            embed.add_field(name="Opened by", value="*Person left Democraciv*")

        embed.add_field(name="Status", value=session.status.value, inline=True)
        embed.add_field(name="Opened on (UTC)", value=session.opened_on.strftime("%A, %B %d %Y at %H:%M"), inline=False)

        if session.status != SessionStatus.SUBMISSION_PERIOD:
            # Session is either closed or in Voting Period
            if session.voting_started_on is not None:
                embed.add_field(name="Voting Started on (UTC)",
                                value=session.voting_started_on.strftime("%A, %B %d %Y at %H:%M"), inline=False)
                embed.add_field(name="Vote Form", value=f"[Link]({session.vote_form})", inline=False)

        if not session.is_active:
            # Session is closed
            embed.add_field(name="Ended on (UTC)",
                            value=session.closed_on.strftime("%A, %B %d %Y at %H:%M"), inline=False)

        pretty_motions = '\n'.join(pretty_motions)
        pretty_bills = '\n'.join(pretty_bills)

        if len(pretty_motions) <= 1024:
            embed.add_field(name="Submitted Motions", value=pretty_motions, inline=False)
        else:
            haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_motions)
            too_long_motions = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
            embed.add_field(name="Submitted Motions", value=too_long_motions, inline=False)

        if len(pretty_bills) <= 1024:
            embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)
        else:
            haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_bills)
            too_long_bills = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
            embed.add_field(name="Submitted Bills", value=too_long_bills, inline=False)

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
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

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
            bill_title = await self.bot.laws.get_google_docs_title(google_docs_url)

            if bill_title is None:
                await ctx.send(":x: Couldn't connect to Google Docs. Make sure that the document can be"
                               " read by anyone and that it's not a published version!")
                return None, None

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
                    "description, tiny_link) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    current_leg_session_id, google_docs_url, bill_title, ctx.author.id, is_vetoable,
                    bill_description, tiny_url)
            except asyncpg.UniqueViolationError:
                await ctx.send(":x: A bill with the same exact Google Docs Document was already submitted!")
                return None, None

            message = "Hey! A new **bill** was just submitted."
            embed = self.bot.embeds.embed_builder(title="Bill Submitted", description="", time_stamp=True)
            embed.add_field(name="Title", value=bill_title, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name, inline=False)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(name="Ministry Veto Allowed", value=is_vetoable)
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
                await ctx.send(":x: Your motion was not submitted, there was a problem with hastebin.com. "
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
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        if self.speaker is None:
            raise exceptions.NoOneHasRoleError(mk.DemocracivRole.SPEAKER_ROLE.printable_name)

        current_leg_session: Session = await self.bot.laws.get_active_leg_session()

        if current_leg_session is None:
            return await ctx.send(":x: There is no active session!")

        if current_leg_session.status != SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(f":x: The submission period for session #{current_leg_session.id} is already over!")

        flow = Flow(self.bot, ctx)

        bill_motion_question = await ctx.send(":information_source: Do you want to submit a motion or a bill?"
                                              " React with <:bill:683370062358642737> for bill, and with "
                                              "<:motion:683370053508399121> for a motion.")

        reaction, user = await flow.get_emoji_choice("<:bill:683370062358642737>", "<:motion:683370053508399121>",
                                                     bill_motion_question, 200)

        if not reaction:
            return

        if str(reaction.emoji) == "<:bill:683370062358642737>":
            message, embed = await self.submit_bill(ctx, current_leg_session.id)

        elif str(reaction.emoji) == "<:motion:683370053508399121>":
            if self.legislator_role not in ctx.author.roles:
                return await ctx.send(":x: Only Legislators are allowed to submit motions!")
            message, embed = await self.submit_motion(ctx, current_leg_session.id)

        if message is None:
            return

        # Send DM to Cabinet after everything is done
        if self.speaker_role not in ctx.author.roles and self.vice_speaker_role not in ctx.author.roles:
            try:
                await self.speaker.send(content=message, embed=embed)
                await self.vice_speaker.send(content=message, embed=embed)
            except discord.Forbidden:
                pass

    @legislature.command(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.SPEAKER_ROLE, mk.DemocracivRole.VICE_SPEAKER_ROLE)
    async def passbill(self, ctx, bill_id: Bill):
        """Mark a bill as passed from the Legislature.

        If the bill is vetoable, it sends the bill to the Ministry. If not, the bill automatically becomes law."""

        bill = bill_id  # At this point, bill_id is already a Bill object, so calling it ball_id makes no sense

        last_leg_session: Session = await self.bot.laws.get_last_leg_session()

        if last_leg_session.id != bill.session.id:
            return await ctx.send(f":x: You can only mark bills from the most recent "
                                  f"session of the Legislature as passed.")

        if last_leg_session.status == SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(f":x: You cannot mark bills as passed while the "
                                  f"session is still in submission period.")

        if bill.voted_on_by_leg:
            return await ctx.send(f":x: You already voted on this bill!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to mark "
                                      f"`{bill.name}` (#{bill.id}) as passed from the Legislature?")

        flow = Flow(self.bot, ctx)
        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with ctx.typing():
                await self.bot.db.execute("UPDATE legislature_bills SET has_passed_leg = true, voted_on_by_leg = true "
                                          "WHERE id = $1", bill.id)

                # Bill is vetoable
                if bill.is_vetoable:
                    await ctx.send(f":white_check_mark: The bill named `{bill.name}` was sent to the "
                                   f"Ministry for them to vote on it.")

                    await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.EXECUTIVE_CHANNEL).send(
                        f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.PRIME_MINISTER_ROLE).mention}, "
                        f"the Legislature has just passed `{bill.name}` (#{bill.id}) hat you need to vote on. "
                        f"Check `-ministry bills` to get the details.")

                # Bill is not vetoable
                else:
                    if await self.bot.laws.pass_into_law(ctx, bill):
                        # pass_into_law() returned True -> success
                        await ctx.send(f":white_check_mark: `{bill.name}` was passed into law."
                                       f" Remember to add it to the Legal Code, too!")

                        await self.gov_announcements_channel.send(
                            f"The `{bill.name}` ({bill.tiny_link}) was passed into law by the Legislature without "
                            f"requiring a prior vote on it by the Ministry. It was marked as non-vetoable by the "
                            f"original submitter {bill.submitter.name}.")

                    else:
                        # pass_into_law() returned False -> Database Error
                        await ctx.send(":x: Unexpected error occurred.")

    @legislature.group(name='withdraw', aliases=['w'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def withdraw(self, ctx):
        """Withdraw a bill or motion from the current session."""
        await ctx.send_help(ctx.command)

    @withdraw.command(name='bill', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def withdrawbill(self, ctx, bill_id: Bill):
        """Withdraw a bill from the current session"""

        bill = bill_id  # At this point, bill_id is already a Bill object, so calling it ball_id makes no sense

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session.id != bill.session.id:
            return await ctx.send(f":x: This bill was not submitted in the last session of the Legislature!")

        if bill.voted_on_by_leg:
            return await ctx.send(f":x: This bill was already voted on by the Legislature!")

        # The Speaker and Vice-Speaker can withdraw every submitted bill during both the Submission Period and the
        # Voting Period.
        # The original submitter of the bill can only withdraw their own bill during the Submission Period.

        is_cabinet = False

        if self.speaker_role not in ctx.author.roles and self.vice_speaker_role not in ctx.author.roles:
            if ctx.author.id == bill.submitter.id:
                if last_leg_session.status == SessionStatus.SUBMISSION_PERIOD:
                    allowed = True
                else:
                    return await ctx.send(f":x: The original submitter can only withdraw "
                                          f"bills during the Submission Period!")
            else:
                allowed = False
        else:
            is_cabinet = True
            allowed = True

        if not allowed:
            return await ctx.send(":x: Only the Cabinet and the original submitter of this bill can withdraw it!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to withdraw the **bill** "
                                      f"`{bill.name}` (#{bill.id}) from session #{last_leg_session.id}?")

        flow = Flow(self.bot, ctx)
        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            try:
                await self.bot.db.execute("DELETE FROM legislature_bills WHERE id = $1", bill.id)
            except asyncpg.ForeignKeyViolationError:
                return await ctx.send(":x: This bill is already a law and cannot be withdrawn.")

            await ctx.send(f":white_check_mark: `{bill.name}` (#{bill.id}) was withdrawn "
                           f"from session #{last_leg_session.id}.")

            if not is_cabinet:
                msg = f"**Bill Withdrawn**\n{ctx.author.name} has withdrawn their bill `{bill.name}` (#{bill.id}) " \
                      f"from the current session."

                try:
                    await self.speaker.send(msg)
                    await self.vice_speaker.send(msg)
                except discord.Forbidden:
                    pass

    @withdraw.command(name='motion', aliases=['m'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def withdrawmotion(self, ctx, motion_id: Motion):
        """Withdraw a motion from the current session"""

        motion = motion_id

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session.id != motion.session.id:
            return await ctx.send(f":x: This motion was not submitted in the last session of the Legislature!")

        # The Speaker and Vice-Speaker can withdraw every submitted motion during both the Submission Period and the
        # Voting Period.
        # The original submitter of the bill can only withdraw their own bill during the Submission Period.

        is_cabinet = False

        if self.speaker_role not in ctx.author.roles and self.vice_speaker_role not in ctx.author.roles:
            if ctx.author.id == motion.submitter.id:
                if last_leg_session.status == SessionStatus.SUBMISSION_PERIOD:
                    allowed = True
                else:
                    return await ctx.send(f":x: The original submitter can only withdraw "
                                          f"motions during the Submission Period!")
            else:
                allowed = False
        else:
            is_cabinet = True
            allowed = True

        if not allowed:
            return await ctx.send(":x: Only the Cabinet and the original submitter of this motion can withdraw it!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to withdraw the **motion**"
                                      f" `{motion.title}` (#{motion.id}) from session #{last_leg_session.id}?")

        flow = Flow(self.bot, ctx)
        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            await self.bot.db.execute("DELETE FROM legislature_motions WHERE id = $1", motion.id)
            await ctx.send(f":white_check_mark: `{motion.title}` (#{motion.id}) was withdrawn "
                           f"from session #{last_leg_session.id}.")

            if not is_cabinet:
                msg = f"**Motion Withdrawn**\n{ctx.author.name} has withdrawn their motion" \
                      f" `{motion.title}` (#{motion.id}) from the current session."

                try:
                    await self.speaker.send(msg)
                    await self.vice_speaker.send(msg)
                except discord.Forbidden:
                    pass

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
