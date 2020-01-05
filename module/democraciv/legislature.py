import time
import asyncpg
import discord
import datetime

from discord.ext import commands

from util.flow import Flow
from util.paginator import Pages
from config import config, links
from util import utils, mk, exceptions


class Legislature(commands.Cog):
    """Organize and get details about Legislative Sessions and submit bills or motions"""

    def __init__(self, bot):
        self.bot = bot
        self.speaker = None
        self.vice_speaker = None

    def refresh_leg_discord_objects(self):
        """Refreshes class attributes with current Speaker and Vice Speaker discord.Member objects"""

        try:
            self.speaker = mk.get_democraciv_role(self.bot, mk.DemocracivRole.SPEAKER_ROLE).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Speaker of the Legislature")

        try:
            self.vice_speaker =mk.get_democraciv_role(self.bot, mk.DemocracivRole.VICE_SPEAKER_ROLE).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Vice-Speaker of the Legislature")

    @commands.group(name='legislature', aliases=['leg'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legislature(self, ctx):
        """Dashboard for Legislators"""

        try:
            self.refresh_leg_discord_objects()
        except exceptions.DemocracivBotException as e:
            await ctx.send(e.message)

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is None:
            active_leg_session = "There currently is no open session."
        else:
            status_record = await self.bot.db.fetchrow("SELECT status FROM legislature_sessions WHERE id = $1",
                                                       active_leg_session_id)
            if status_record is not None:
                status = status_record['status']
                active_leg_session = f"Session #{active_leg_session_id} - {status}"
            else:
                active_leg_session = f"Session #{active_leg_session_id}"

        embed = self.bot.embeds.embed_builder(title=f"The Legislature of {mk.NATION_NAME}",
                                              description="")
        speaker_value = f""

        if isinstance(self.speaker, discord.Member):
            speaker_value += f"Speaker: {self.speaker.mention}\n"
        else:
            speaker_value += f"Speaker: -\n"

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value += f"Vice-Speaker: {self.vice_speaker.mention}"
        else:
            speaker_value += f"Vice-Speaker: -"

        embed.add_field(name="Legislative Cabinet", value=speaker_value)
        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Docket]({links.legislativedocket})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Legislative Procedures]({links.legislativeprocedures})", inline=True)
        embed.add_field(name="Current Session", value=f"{active_leg_session}", inline=False)

        await ctx.send(embed=embed)

    @legislature.command(name='opensession', aliases=['os'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def opensession(self, ctx):
        """Opens a session for the submission period to begin"""

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is not None:
            return await ctx.send(f":x: There is still an open session, close session #{active_leg_session_id} first!")

        last_session = await self.bot.laws.get_last_leg_session()

        if last_session is None:
            last_session = 0

        new_session = last_session + 1

        try:
            await self.bot.db.execute('INSERT INTO legislature_sessions (id, speaker, is_active, status, '
                                      'start_unixtime)'
                                      'VALUES ($1, $2, true, $3, $4)', int(new_session), ctx.author.id,
                                      'Submission Period', time.time())

        except asyncpg.UniqueViolationError:
            return await ctx.send(":x: This session already exists!")
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await ctx.send(f":white_check_mark: Successfully opened the submission period for session #{new_session}!")

        await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL).send(f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE).mention}, the "
                                                              f"submission period for Legislative Session "
                                                              f"#{new_session} has started!\nSubmit your "
                                                              f"bills with `-legislature submit`.")

        for legislator in mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE).members:
            try:
                await legislator.send(f":envelope_with_arrow: The **submission period for Legislative Session"
                                      f" #{new_session}** has started!"
                                      f"\nSubmit your bills with `-legislature submit` on the"
                                      f" Democraciv guild.")
            except discord.Forbidden:
                pass

    @legislature.command(name='updatesession', aliases=['us'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def updatesession(self, ctx, voting_form: str):
        """Changes the current session's status to be open for voting. Needs a Google Forms link as argument."""

        if not self.bot.laws.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is None:
            return await ctx.send(":x: There is no open session!")

        status_of_active_session = await self.bot.laws.get_status_of_active_leg_session()

        if status_of_active_session != "Submission Period":
            return await ctx.send(":x: You can only update a session to the Voting Period that was previously in the"
                                  "Submission Period!")

        try:
            await self.bot.db.execute("UPDATE legislature_sessions SET status = 'Voting Period',"
                                      " voting_start_unixtime = $2, vote_form = $3"
                                      " WHERE id = $1", active_leg_session_id, time.time(), voting_form)
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await ctx.send(f":white_check_mark: Successfully opened session #{active_leg_session_id} up for voting!")

        await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL).send(f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE).mention},"
                                                              f" the voting period for Legislative Session "
                                                              f"#{active_leg_session_id} has started!\n:ballot_box:"
                                                              f" Vote here: {voting_form}")

        for legislator in mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE).members:
            try:
                await legislator.send(f":ballot_box: The **voting period for Legislative Session "
                                      f"#{active_leg_session_id}** has "
                                      f"started!\nVote here: {voting_form}")
            except discord.Forbidden:
                continue

    @updatesession.error
    async def updatesessionerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'voting_form':
                await ctx.send(":x: You have to give me a valid Google Forms URL for the voting period to begin!")

    @legislature.command(name='closesession', aliases=['cs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is None:
            return await ctx.send(f":x: There is no open session!")

        try:
            await self.bot.db.execute("UPDATE legislature_sessions SET is_active = false, end_unixtime = $2,"
                                      " status = 'Closed'"
                                      " WHERE id = $1", active_leg_session_id, time.time())
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await ctx.send(f":white_check_mark: Successfully closed Session #{active_leg_session_id}!\n"
                       f"Add the bills that passed this session with `-legislature pass <bill_id>`. You can get the "
                       f"bill ids from the list of submitted bills in `-legislature session {active_leg_session_id}`")

        await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL).send(f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE).mention},"
                                                              f" Legislative Session "
                                                              f"#{active_leg_session_id} has been closed by "
                                                              f"the Cabinet.")

    @legislature.command(name='session', aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def session(self, ctx, session: str = None):
        """Get details about a legislative session

        Usage:
        `-legislature session` to see details about the session that is currently open
        `-legislature session <number>` to see details about a specific session
        `-legislature session all` to see a list of all previous sessions."""

        try:
            self.refresh_leg_discord_objects()
        except exceptions.DemocracivBotException as e:
            await ctx.send(e.message)

        if not session or session is None:
            active_leg_session_id = await self.bot.laws.get_active_leg_session()

            if active_leg_session_id is None:
                msg = f":x: There currently is no open session.\n" \
                      f"**Usage**:\n  `{config.BOT_PREFIX}legislature session` to see details about the session that is" \
                      f" currently open,\n  " \
                      f"`{config.BOT_PREFIX}legislature session <number>` to see details about a specific " \
                      f"session or\n  " \
                      f"`{config.BOT_PREFIX}legislature session all` to see a list of all previous sessions."
                return await ctx.send(msg)

        elif session:
            if session.lower() == "all":

                all_session_ids = await self.bot.db.fetch("SELECT (id, status) FROM legislature_sessions")

                pretty_sessions = []

                for record in all_session_ids:
                    pretty_sessions.append(f"**Session #{record[0][0]}**   - {record[0][1]}")

                footer = f"Use {self.bot.commands_prefix}legislature session <number> to get more details about" \
                         f" a session."

                pages = Pages(ctx=ctx, entries=pretty_sessions, show_entry_count=False,
                              title=f"All Sessions of the {mk.NATION_ADJECTIVE} Legislature"
                              , show_index=False, footer_text=footer)
                await pages.paginate()
                return

            else:
                try:
                    active_leg_session_id = int(session)
                except ValueError:
                    msg = f":x: You typed neither 'all', nor a number of a session." \
                          f"**Usage**:\n  `{config.BOT_PREFIX}legislature session` to see details about the session" \
                          f" that is currently open,\n  " \
                          f"`{config.BOT_PREFIX}legislature session <number>` to see details about a specific " \
                          f"session or\n  " \
                          f"`{config.BOT_PREFIX}legislature session all` to see a list of all previous sessions."
                    return await ctx.send(msg)

        async with ctx.typing():
            session_info = await self.bot.db.fetchrow(
                "SELECT (speaker, is_active, vote_form, start_unixtime, end_unixtime, status, voting_start_unixtime) "
                "FROM legislature_sessions WHERE id = $1", active_leg_session_id)

            if session_info is None:
                msg = f":x: I couldn't find that session.\n\n" \
                      f"**Usage**:\n  `{config.BOT_PREFIX}legislature session` to see details about the session that" \
                      f" is currently open,\n  " \
                      f"`{config.BOT_PREFIX}legislature session <number>` to see details about a specific " \
                      f"session or\n  " \
                      f"`{config.BOT_PREFIX}legislature session all` to see a list of all previous sessions."
                await ctx.send(msg)
                return

            motions = await self.bot.db.fetch(
                "SELECT (id, title, description, submitter) FROM legislature_motions"
                " WHERE leg_session = $1", active_leg_session_id)

            pretty_motions = f""

            if len(motions) > 0:
                for record in motions:
                    pretty_motions += f"Motion #{record[0][0]} - {record[0][1]} by " \
                                      f"{self.bot.get_user(record[0][3]).mention}\n"

            else:
                pretty_motions = "No one submitted any motions during this session."

            bills = await self.bot.db.fetch(
                "SELECT (id, tiny_link, bill_name, submitter) FROM legislature_bills"
                " WHERE leg_session = $1", active_leg_session_id)

            pretty_bills = f""

            if len(bills) > 0:
                for record in bills:
                    pretty_bills += f"Bill #{record[0][0]} - [{record[0][2]}]({record[0][1]}) by " \
                                    f"{self.bot.get_user(record[0][3]).mention}\n"

            else:
                pretty_bills = "No one submitted any bills during this session."

            pretty_start_date = datetime.datetime.utcfromtimestamp(session_info[0][3]).strftime("%A, %B %d %Y"
                                                                                                " %H:%M:%S")

            embed = self.bot.embeds.embed_builder(title=f"Legislative Session #{str(active_leg_session_id)}",
                                                  description="", time_stamp=True)
            embed.add_field(name="Opened by", value=self.bot.get_user(session_info[0][0]).mention)
            embed.add_field(name="Status", value=session_info[0][5], inline=True)
            embed.add_field(name="Opened on (UTC)", value=pretty_start_date, inline=False)

            if session_info[0][5] != "Submission Period":
                # Session is either closed or in Voting Period
                pretty_voting_date = datetime.datetime.utcfromtimestamp(session_info[0][6]).strftime("%A, %B %d %Y"
                                                                                                     " %H:%M:%S")

                embed.add_field(name="Voting Started on (UTC)", value=pretty_voting_date, inline=False)
                embed.add_field(name="Vote Form", value=f"[Link]({session_info[0][2]})", inline=False)

            if not session_info[0][1]:
                # Session is closed
                pretty_end_date = datetime.datetime.utcfromtimestamp(session_info[0][4]).strftime("%A, %B %d %Y"
                                                                                                  " %H:%M:%S")
                embed.add_field(name="Ended on (UTC)", value=pretty_end_date, inline=False)

            embed.add_field(name="Submitted Motions", value=pretty_motions, inline=False)

            # If the submitted bills text is longer than 1024 characters, the Discord API returns a 403.
            # To combat this, we upload the raw Markdown to Hastebin if it's too long.
            if len(pretty_bills) < 1024:
                embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)
            elif len(pretty_bills) > 1024:
                haste_bin_url = await self.bot.laws.post_to_hastebin(pretty_bills)
                too_long_bills = f"This text was too long for Discord, so I put it on [here.]({haste_bin_url})"
                embed.add_field(name="Submitted Bills", value=too_long_bills, inline=False)

            try:
                await ctx.send(embed=embed)
            except discord.HTTPException:
                await ctx.send(
                    f":x: The embed value is > 1024 as there were too many "
                    f"bills or motions submitted. Jonas is working on this.")

    @legislature.command(name='submit')
    @utils.is_democraciv_guild()
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def submit(self, ctx):
        """Submit a new bill or motion for the currently active session"""

        try:
            self.refresh_leg_discord_objects()
        except exceptions.DemocracivBotException as e:
            raise e

        current_leg_session = await self.bot.laws.get_active_leg_session()

        if current_leg_session is None:
            return await ctx.send(":x: There is no active session!")

        current_leg_session_status = await self.bot.laws.get_status_of_active_leg_session()

        if current_leg_session_status is None or current_leg_session_status != "Submission Period":
            return await ctx.send(f":x: The submission period for session #{current_leg_session} is already over!")

        # -- Interactive Flow Session --
        flow = Flow(self.bot, ctx)

        bill_motion_question = await ctx.send(":information_source: Do you want to submit a motion or a bill?"
                                              " React with :regional_indicator_b: for bill, and with "
                                              ":regional_indicator_m: for a motion.")

        reaction, user = await flow.get_emoji_choice("\U0001f1e7", "\U0001f1f2", bill_motion_question, 200)

        if not reaction:
            return

        if str(reaction.emoji) == "\U0001f1e7":
            # -- Bill --

            await ctx.send(":white_check_mark: You will submit a **bill**.")

            # Vetoable?
            veto_question = await ctx.send(":information_source: Is the Ministry legally allowed to veto (or vote on) "
                                           "this bill?")

            reaction, user = await flow.yes_no_reaction_confirm(veto_question, 200)

            if not reaction:
                return

            if str(reaction.emoji) == "\U00002705":
                is_vetoable = True

            elif str(reaction.emoji) == "\U0000274c":
                is_vetoable = False

            # Description?
            await ctx.send(
                ":information_source: Reply with a **short** (max. 2 sentences) description of what your "
                "bill does.")

            bill_description = await flow.get_text_input(620)

            if not bill_description:
                bill_description = "-"

            # Link?
            await ctx.send(":information_source: Reply with the Google Docs link to the bill"
                           " you want to submit.")

            google_docs_url = await flow.get_text_input(150)

            if not google_docs_url:
                return

            if not self.bot.laws.is_google_doc_link(google_docs_url):
                return await ctx.send(
                    ":x: That doesn't look like a Google Docs URL.")

            async with ctx.typing():
                bill_title = await self.bot.laws.get_google_docs_title(google_docs_url)

                if bill_title is None:
                    return await ctx.send(":x: Could not connect to Google Docs!")

                # -- Submit Bill --
                new_id = await self.bot.laws.generate_new_bill_id()

                # Make the Google Docs link smaller to workaround the "embed value cannot be longer than 1024 characters
                # in -legislature session" issue
                async with self.bot.session.get(
                        f"https://tinyurl.com/api-create.php?url={google_docs_url}") as response:
                    tiny_url = await response.text()

                try:
                    await self.bot.db.execute(
                        "INSERT INTO legislature_bills (id, leg_session, link, bill_name, submitter, is_vetoable, "
                        " has_passed_leg, has_passed_ministry, description, tiny_link, voted_on_by_leg, "
                        "voted_on_by_ministry) "
                        "VALUES ($1, $2, $3, $4, $5, $6, false, false, $7, $8, false, false)", new_id,
                        current_leg_session,
                        google_docs_url
                        , bill_title, ctx.author.id, is_vetoable, bill_description, tiny_url)

                except asyncpg.UniqueViolationError:
                    return await ctx.send(":x: This bill was already submitted!")
                except Exception:
                    return await ctx.send(":x: Database error!")

                message = "Hey! A new **bill** was just submitted."
                embed = self.bot.embeds.embed_builder(title="Bill Submitted", description="", time_stamp=True)
                embed.add_field(name="Title", value=bill_title, inline=False)
                embed.add_field(name="Author", value=ctx.message.author.name)
                embed.add_field(name="Session", value=current_leg_session)
                embed.add_field(name="Ministry Veto Allowed", value=is_vetoable)
                embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)
                embed.add_field(name="URL", value=google_docs_url, inline=False)

            await ctx.send(
                f":white_check_mark: Successfully submitted bill `{bill_title}` for session #{current_leg_session}!")

        elif str(reaction.emoji) == "\U0001f1f2":
            # -- Motion --

            if mk.get_democraciv_role(self.bot, mk.DemocracivRole.LEGISLATOR_ROLE) not in ctx.author.roles:
                return await ctx.send(":x: Only Legislators are allowed to submit motions!")

            await ctx.send(":white_check_mark: You will submit a **motion**.")

            await ctx.send(":information_source: Reply with the title of your motion.")

            title = await flow.get_text_input(300)

            if not title:
                return

            await ctx.send(":information_source: Reply with a short description or the content of your motion.")

            description = await flow.get_text_input(600)

            if not description:
                return

            async with ctx.typing():
                _new_id = await self.bot.laws.generate_new_motion_id()

                try:
                    await self.bot.db.execute(
                        "INSERT INTO legislature_motions (id, leg_session, title, description, submitter) "
                        "VALUES ($1, $2, $3, $4, $5)", _new_id, current_leg_session, title, description, ctx.author.id)

                except asyncpg.UniqueViolationError:
                    return await ctx.send(":x: This motion was already submitted!")
                except Exception:
                    return await ctx.send(":x: Database error!")

                message = "Hey! A new **motion** was just submitted."
                embed = self.bot.embeds.embed_builder(title="Motion Submitted", description="", time_stamp=True)
                embed.add_field(name="Title", value=title, inline=False)
                embed.add_field(name="Content", value=description, inline=False)
                embed.add_field(name="Author", value=ctx.message.author.name)
                embed.add_field(name="Session", value=current_leg_session)
                embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)

            await ctx.send(
                f":white_check_mark: Successfully submitted motion titled `{title}`"
                f" for session #{current_leg_session}!")

        # -- Send DM to Cabinet after everything is done and succeed --

        try:
            await self.speaker.send(contet=message, embed=embed)
            await self.vice_speaker.send(content=message, embed=embed)
        except discord.Forbidden:
            return await ctx.send(f":x: Unexpected error occurred while DMing the Speaker or Vice-Speaker."
                                  f" Your bill was still submitted for session #{current_leg_session}, though!")

    @legislature.command(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def passbill(self, ctx, bill_id: int):
        """Mark a bill as passed from the Legislature"""

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

        if bill_details is None:
            return await ctx.send(f":x: There is no submitted bill with ID `#{bill_id}`!")

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session != bill_details['leg_session']:
            return await ctx.send(f":x: You can only mark bills from the most recent session of the "
                                  f"Legislature as passed!")

        last_leg_session_status = await self.bot.laws.get_status_of_active_leg_session()

        if last_leg_session_status == "Submission Period":
            return await ctx.send(f":x: You cannot mark bills as passed in the Submission Period!")

        if bill_details['voted_on_by_leg']:
            return await ctx.send(f":x: You already passed this bill!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to mark "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{bill_details['id']}) as passed from the Legislature?")

        flow = Flow(self.bot, ctx)

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if not reaction or reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":  # yes

            async with ctx.typing():

                await self.bot.db.execute("UPDATE legislature_bills SET has_passed_leg = true, voted_on_by_leg = true "
                                          "WHERE id = $1", bill_id)

                # Bill is vetoable
                if bill_details['is_vetoable']:
                    await ctx.send(f":white_check_mark: The bill titled '{bill_details['bill_name']}' was sent to the "
                                   f"Ministry for them to vote on it.")

                    await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.EXECUTIVE_CHANNEL).send(
                        f"{mk.get_democraciv_role(self.bot, mk.DemocracivRole.PRIME_MINISTER_ROLE).mention}, the Legislature"
                        f" has just passed '{bill_details['bill_name']}' (#{bill_id}) that you need to vote on. "
                        f"Check `-ministry bills` to get the details.")

                # Bill is not vetoable
                else:
                    if await self.bot.laws.pass_into_law(ctx, bill_id, bill_details):
                        # pass_into_law() returned True -> success
                        await ctx.send(f":white_check_mark: Successfully passed '{bill_details['bill_name']}' into law!"
                                       f" Remember to add it to the Legal Code, too!")

                        await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL).send(
                            f"'{bill_details['bill_name']}' was passed "
                            f"into law by the Legislature without requiring a prior vote on it by the Ministry. It was"
                            f" marked as non-vetoable by the original submitter "
                            f"{self.bot.get_user(bill_details['submitter']).name}.")

                    else:
                        # pass_into_law() returned False -> Database Error
                        await ctx.send(":x: Unexpected error occurred.")

    @passbill.error
    async def passbillerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'bill_id':
                await ctx.send(':x: You have to give me the ID of the bill you want to pass!\n\n**Usage**:\n'
                               '`-legislature pass <bill_id>`')

    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    @legislature.command(name='withdraw', aliases=['w'])
    async def withdrawbill(self, ctx, bill_id: int):
        """Withdraw a bill from the current session"""

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

        if bill_details is None:
            return await ctx.send(f":x: There is no submitted bill with ID `#{bill_id}`!")

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session != bill_details['leg_session']:
            return await ctx.send(f":x: This bill was not submitted in the last session of the Legislature!")

        last_leg_session_status = await self.bot.laws.get_status_of_active_leg_session()

        if last_leg_session_status is None:
            return await ctx.send(":x: The session is already closed!")

        # The Speaker and Vice-Speaker can withdraw every submitted bill during both the Submission Period and the
        # Voting Period.
        # The original submitter of the bill can only withdraw their own bill during the Submission Period.

        if mk.get_democraciv_role(self.bot, mk.DemocracivRole.SPEAKER_ROLE) not in ctx.author.roles and mk.get_democraciv_role(
                self.bot, mk.DemocracivRole.VICE_SPEAKER_ROLE) not in ctx.author.roles:
            if ctx.author.id == bill_details['submitter']:
                if last_leg_session_status == "Submission Period":
                    allowed = True
                else:
                    return await ctx.send(f":x: The original submitter can only withdraw bills during "
                                          f"the Submission Period!")
            else:
                allowed = False
        else:
            allowed = True

        if not allowed:
            return await ctx.send(":x: Only the Cabinet and the original submitter of this bill can withdraw it!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to withdraw "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{bill_details['id']}) from session #{last_leg_session}?")

        flow = Flow(self.bot, ctx)

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if not reaction or reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            try:
                await self.bot.db.execute("DELETE FROM legislature_bills WHERE id = $1", bill_id)
            except asyncpg.ForeignKeyViolationError:
                return await ctx.send(":x: This bill is already a law and cannot be withdrawn.")

            return await ctx.send(f":white_check_mark: Successfully withdrew '{bill_details['bill_name']}"
                                  f"' (#{bill_details['id']}) from session #{last_leg_session}!")

    @withdrawbill.error
    async def wberror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'bill_id':
                await ctx.send(':x: You have to give me the ID of the bill to withdraw!\n\n**Usage**:\n'
                               '`-legislature withdraw <bill_id>`')

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

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Legislature(bot))
