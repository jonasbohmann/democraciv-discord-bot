import time
import asyncpg
import discord
import datetime

from util.flow import Flow
from config import config, links
from discord.ext import commands
from util import utils, mk, exceptions


class Legislature(commands.Cog):
    """Useful commands for Legislators"""

    def __init__(self, bot):
        self.bot = bot
        self.speaker = None
        self.vice_speaker = None

    def refresh_leg_discord_objects(self):
        try:
            self.speaker = mk.get_speaker_role(self.bot).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Speaker of the Legislature")

        try:
            self.vice_speaker = mk.get_vice_speaker_role(self.bot).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Vice-Speaker of the Legislature")

    @commands.group(name='legislature', aliases=['leg'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legislature(self, ctx):
        """Dashboard for Legislators"""

        try:
            self.refresh_leg_discord_objects()
        except exceptions.DemocracivBotException as e:
            # We're raising the same exception again because discord.ext.commands.Exceptions only "work" (i.e. get sent
            # to events/error_handler.py) if they get raised in an actual command
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
                                              description=f"")
        speaker_value = f""

        if isinstance(self.speaker, discord.Member):
            speaker_value += f"Speaker: {self.speaker.mention}\n"
        else:
            speaker_value += f"Speaker: -\n"

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value += f"Vice-Speaker: {self.vice_speaker.mention}"
        else:
            speaker_value += f"Vice-Speaker: -"

        embed.add_field(name="Current Legislative Cabinet", value=speaker_value)

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
            return await ctx.send(f":x: There is still an open session, close Session #{active_leg_session_id} first!")

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

        await ctx.send(f":white_check_mark: Successfully opened the submission period for Session #{new_session}!")

        await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_legislator_role(self.bot).mention}, the "
                                                              f"submission period for Legislative Session "
                                                              f"#{new_session} has started!\nSubmit your "
                                                              f"bills with `-legislature submit`.")

        for legislator in mk.get_legislator_role(self.bot).members:
            try:
                await legislator.send(f":envelope_with_arrow: The **submission period for Legislative Session"
                                      f" #{new_session}** has started!"
                                      f"\nSubmit your bills with `-legislature submit` on the"
                                      f" Democraciv guild.")
            except discord.Forbidden:
                pass

    @opensession.error
    async def opensessionerror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the cabinet is allowed to use this command!")

    @legislature.command(name='updatesession', aliases=['us'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def updatesession(self, ctx, voting_form: str):
        """Changes the current session's status to be open for voting"""

        if not self.bot.laws.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is None:
            return await ctx.send(f":x: There is no open session!")

        try:
            await self.bot.db.execute("UPDATE legislature_sessions SET status = 'Voting Period',"
                                      " voting_start_unixtime = $2"
                                      " WHERE id = $1", active_leg_session_id, time.time())
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await ctx.send(f":white_check_mark: Successfully opened session #{active_leg_session_id} up for voting!")

        await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_legislator_role(self.bot).mention},"
                                                              f" the voting period for Legislative Session "
                                                              f"#{active_leg_session_id} has started!\n:ballot_box:"
                                                              f" Vote here: {voting_form}")

        for legislator in mk.get_legislator_role(self.bot).members:
            try:
                await legislator.send(f":ballot_box: The **voting period for Legislative Session "
                                      f"#{active_leg_session_id}** has "
                                      f"started!\nVote here: {voting_form}")
            except Exception:
                pass

    @updatesession.error
    async def updatesessionerror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the cabinet is allowed to use this command!")

        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'voting_form':
                await ctx.send(":x: You have to give me a valid Google Forms URL for the voting period to begin!")

    @legislature.command(name='closesession', aliases=['cs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def closesession(self, ctx):
        """Closes the current session"""

        status = await self.bot.laws.get_status_of_active_leg_session()

        if status == "Submission Period":
            return await ctx.send(f":x: You can only close sessions that are in Voting Period!")

        active_leg_session_id = await self.bot.laws.get_active_leg_session()

        if active_leg_session_id is None:
            return await ctx.send(f":x: There is no open session!")

        try:
            await self.bot.db.execute("UPDATE legislature_sessions SET is_active = false, end_unixtime = $2,"
                                      " status = 'Closed'"
                                      " WHERE id = $1", active_leg_session_id, time.time())
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await ctx.send(f":white_check_mark: Successfully closed Session #{active_leg_session_id}!")

    @closesession.error
    async def closesessionerror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the cabinet is allowed to use this command!")

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
            # We're raising the same exception again because discord.ext.commands.Exceptions only "work" (i.e. get sent
            # to events/error_handler.py) if they get raised in an actual command
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
                await ctx.send(msg)
                return

        elif session:
            if session.lower() == "all":

                all_session_ids = await self.bot.db.fetch("SELECT (id, status) FROM legislature_sessions")

                pretty_sessions = ""

                for record in all_session_ids:
                    pretty_sessions += f"**Session #{record[0][0]}**   - {record[0][1]}\n"

                embed = self.bot.embeds.embed_builder(title=f"All Sessions of the {mk.NATION_ADJECTIVE} Legislature",
                                                      description=pretty_sessions, footer=f"Use "
                                                                                          f"{self.bot.commands_prefix}l"
                                                                                          f"egislature session <number>"
                                                                                          f" to get more details about"
                                                                                          f" a session.")
                return await ctx.send(embed=embed)

            else:
                active_leg_session_id = int(session)

        async with ctx.typing():
            session_info = await self.bot.db.fetchrow(
                "SELECT (speaker, is_active, vote_form, start_unixtime, end_unixtime, status, voting_start_unixtime) "
                "FROM legislature_sessions WHERE id = $1", active_leg_session_id)

            if session_info is None:
                msg = f":x: I couldn't find that session.\n\n" \
                      f"**Usage**:\n  `{config.BOT_PREFIX}legislature session` to see details about the session that is" \
                      f" currently open,\n  " \
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
            pretty_start_date = datetime.datetime.utcfromtimestamp(session_info[0][3]).strftime("%A, %B %d %Y"
                                                                                                " %H:%M:%S")
            if len(bills) > 0:
                for record in bills:
                    pretty_bills += f"Bill #{record[0][0]} - [{record[0][2]}]({record[0][1]}) by " \
                                    f"{self.bot.get_user(record[0][3]).mention}\n"

            else:
                pretty_bills = "No one submitted any bills during this session."

            embed = self.bot.embeds.embed_builder(title=f"Legislative Session #{str(active_leg_session_id)}",
                                                  description="", time_stamp=True)
            embed.add_field(name="Opened by", value=self.bot.get_user(session_info[0][0]).mention)
            embed.add_field(name="Status", value=session_info[0][5], inline=True)
            embed.add_field(name="Opened on (UTC)", value=pretty_start_date, inline=False)

            if session_info[0][5] != "Submission Period":
                pretty_voting_date = datetime.datetime.utcfromtimestamp(session_info[0][6]).strftime("%A, %B %d %Y"
                                                                                                     " %H:%M:%S")

                embed.add_field(name="Voting Started on (UTC)", value=pretty_voting_date, inline=False)
                embed.add_field(name="Vote Form", value=f"[Link]({session_info[0][2]})", inline=False)

            if not session_info[0][1]:
                pretty_end_date = datetime.datetime.utcfromtimestamp(session_info[0][4]).strftime("%A, %B %d %Y"
                                                                                                  " %H:%M:%S")
                embed.add_field(name="Ended on (UTC)", value=pretty_end_date, inline=False)

            embed.add_field(name="Submitted Motions", value=pretty_motions, inline=False)
            embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)

            try:
                await ctx.send(embed=embed)
            except discord.HTTPException:
                await ctx.send(
                    f":x: {self.bot.DerJonas_object.mention}, the embed value is > 1024 as there were too many"
                    f"bills submitted. Did you figure out a solution for this yet?")

    @legislature.command(name='submit')
    @utils.is_democraciv_guild()
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def submit(self, ctx):
        """Submit a new bill or motion for the currently active session"""

        try:
            self.refresh_leg_discord_objects()
        except exceptions.DemocracivBotException as e:
            # We're raising the same exception again because discord.ext.commands.Exceptions only "work"
            # (i.e. get sent to events/error_handler.py) if they get raised in an actual command
            raise e

        current_leg_session = await self.bot.laws.get_active_leg_session()

        if current_leg_session is None:
            await ctx.send(":x: There is no active session!")
            return

        current_leg_session_status = await self.bot.laws.get_status_of_active_leg_session()

        if current_leg_session_status is None or current_leg_session_status != "Submission Period":
            await ctx.send(f":x: The submission period for session #{current_leg_session} is already over!")
            return

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

            else:
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
                    await ctx.send(":x: Could not connect to Google Docs!")
                    return

                # -- Submit Bill --
                new_id = await self.bot.laws.generate_new_bill_id()

                async with self.bot.session.get(
                        f"https://tinyurl.com/api-create.php?url={google_docs_url}") as response:
                    tiny_url = await response.text()

                try:
                    await self.bot.db.execute(
                        "INSERT INTO legislature_bills (id, leg_session, link, bill_name, submitter, is_vetoable, "
                        " has_passed_leg, has_passed_ministry, description, tiny_link, voted_on_by_leg, "
                        "voted_on_by_ministry) "
                        "VALUES ($1, $2, $3, $4, $5, $6, false, false, $7, $8, false, false)", new_id, current_leg_session,
                        google_docs_url
                        , bill_title, ctx.author.id, is_vetoable, bill_description, tiny_url)

                except asyncpg.UniqueViolationError:
                    await ctx.send(":x: This bill was already submitted!")
                    return
                except Exception:
                    await ctx.send(":x: Database error!")
                    return

                message = "Hey! A new **bill** was just submitted."
                embed = self.bot.embeds.embed_builder(title="Bill Submitted", description="", time_stamp=True)
                embed.add_field(name="Title", value=bill_title, inline=False)
                embed.add_field(name="Author", value=ctx.message.author.name)
                embed.add_field(name="Session", value=current_leg_session)
                embed.add_field(name="Ministry Veto Allowed", value=is_vetoable)
                embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)
                embed.add_field(name="URL", value=google_docs_url, inline=False)

            await ctx.send(
                f":white_check_mark: Successfully submitted bill '{bill_title}' for session #{current_leg_session}!")

        elif str(reaction.emoji) == "\U0001f1f2":
            # -- Motion --

            if mk.get_legislator_role(self.bot) not in ctx.author.roles:
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
                    await ctx.send(":x: This motion was already submitted!")
                    return
                except Exception:
                    await ctx.send(":x: Database error!")
                    return

                message = "Hey! A new **motion** was just submitted."
                embed = self.bot.embeds.embed_builder(title="Motion Submitted", description="", time_stamp=True)
                embed.add_field(name="Title", value=title, inline=False)
                embed.add_field(name="Content", value=description, inline=False)
                embed.add_field(name="Author", value=ctx.message.author.name)
                embed.add_field(name="Session", value=current_leg_session)
                embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow(), inline=False)

            await ctx.send(
                f":white_check_mark: Successfully submitted motion titled '{title}'"
                f" for session #{current_leg_session}!")
        try:
            await self.speaker.send(message)
            await self.speaker.send(embed=embed)
            await self.vice_speaker.send(message)
            await self.vice_speaker.send(embed=embed)
        except Exception:
            await ctx.send(f":x: Unexpected error occurred while DMing the Speaker or Vice-Speaker."
                           f" Your bill was still submitted for session #{current_leg_session}, though!")
            return

    @legislature.command(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Speaker of the Legislature", "Vice-Speaker of the Legislature")
    @utils.is_democraciv_guild()
    async def passbill(self, ctx, bill_id: int):
        """Mark a bill as passed from the Legislature"""

        if bill_id <= 0:
            return await ctx.send(":x: The bill ID has to be greater than 0!")

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

        if bill_details is None:
            return await ctx.send(f":x: There is no submitted bill with ID #{bill_id}")

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session != bill_details['leg_session']:
            return await ctx.send(f":x: This bill was not submitted in the last session of the Legislature!")

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

        if str(reaction.emoji) == "\U00002705":  # yes

            async with ctx.typing():

                await self.bot.db.execute("UPDATE legislature_bills SET has_passed_leg = true, voted_on_by_leg = true "
                                          "WHERE id = $1", bill_id)

                # Bill is vetoable
                if bill_details['is_vetoable']:
                    await ctx.send(f":white_check_mark: The bill titled '{bill_details['bill_name']}' was sent to the "
                                   f"Ministry for"
                                   f" them to vote on it.")

                    await mk.get_executive_channel(self.bot).send(
                        f"{mk.get_minister_role(self.bot).mention}, the Legislature"
                        f" has just passed bill #{bill_id} that you need to vote on. "
                        f"Check `-ministry bills` to get the details.")

                # Bill is not vetoable
                else:

                    if await self.bot.laws.pass_into_law(ctx, bill_id, bill_details):
                        await ctx.send(":white_check_mark: Successfully passed this bill into law!"
                                       " Remember to also add it to "
                                       "the Legal Code!")
                    else:
                        await ctx.send(":x: Unexpected error occurred.")

    @passbill.error
    async def passbillerror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the cabinet is allowed to use this command!")

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
            return await ctx.send(f":x: There is no submitted bill with ID #{bill_id}")

        last_leg_session = await self.bot.laws.get_last_leg_session()

        if last_leg_session != bill_details['leg_session']:
            return await ctx.send(f":x: This bill was not submitted in the last session of the Legislature!")

        last_leg_session_status = await self.bot.laws.get_status_of_active_leg_session()

        if mk.get_speaker_role(self.bot) not in ctx.author.roles or mk.get_vice_speaker_role(self.bot) not in ctx.author.roles:
            if ctx.author.id == bill_details['submitter']:
                if last_leg_session_status != "Submission Period":
                    return await ctx.send(f":x: The original submitter can only withdraw bills during "
                                          f"the Submission Period!")
                else:
                    allowed = True
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

        else:
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


def setup(bot):
    bot.add_cog(Legislature(bot))
