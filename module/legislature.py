import time
import asyncpg
import datetime

from util import utils, mk
from config import config, links
from discord.ext import commands
from bs4 import BeautifulSoup, SoupStrainer


class Legislature(commands.Cog):
    """Useful commands for Legislators"""

    def __init__(self, bot):
        self.bot = bot
        self.speaker = None
        self.vice_speaker = None

    def refresh_leg_discord_objects(self):
        self.speaker = mk.get_speaker_role(self.bot).members[0]
        self.vice_speaker = mk.get_vice_speaker_role(self.bot).members[0]

    @staticmethod
    def is_google_doc_link(link: str):

        valid_google_docs_url_strings = ['https://docs.google.com/', 'https://drive.google.com/', 'https://forms.gle/']

        if len(link) < 15 or not link.startswith(tuple(valid_google_docs_url_strings)):
            return False
        else:
            return True

    async def get_active_leg_session(self):
        active_leg_session_id = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE is_active = true")

        if active_leg_session_id is None:
            return None
        else:
            return active_leg_session_id['id']

    async def get_last_leg_session(self):
        last_session = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE id = "
                                                  "(SELECT MAX(id) FROM legislature_sessions)")

        if last_session is not None:
            return last_session['id']
        else:
            return None

    async def get_google_docs_title(self, link: str):
        try:
            async with self.bot.session.get(link) as response:
                text = await response.read()

            strainer = SoupStrainer(property="og:title")  # Only parse the title property HTMl to save time
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)  # Use lxml parser to speed things up

            bill_title = soup.find("meta")['content']  # Get title of Google Docs website

            if bill_title.endswith(' - Google Docs'):
                bill_title = bill_title[:-14]

            soup.decompose()  # Garbage collection

            return bill_title

        except Exception:
            return None

    @commands.group(name='legislature', aliases=['leg'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legislature(self, ctx):
        """Dashboard for Legislators"""

        self.refresh_leg_discord_objects()

        active_leg_session_id = await self.get_active_leg_session()

        if active_leg_session_id is None:
            active_leg_session = "There currently is no on-going session."
        else:
            status_record = await self.bot.db.fetchrow("SELECT status FROM legislature_sessions WHERE id = $1",
                                                       active_leg_session_id)
            if status_record is not None:
                status = status_record['status']
                active_leg_session = f"Session #{active_leg_session_id} - {status}"
            else:
                active_leg_session = f"Session #{active_leg_session_id}"

        embed = self.bot.embeds.embed_builder(title=f"The Legislature of {mk.NATION_NAME}",
                                              description=f"Use `{config.BOT_PREFIX}help legislature` to get a list of "
                                                          f"commands for the Legislature")
        embed.add_field(name="Current Legislative Cabinet", value=f"Speaker: {self.speaker.mention}\n"
                                                                  f"Vice-Speaker: {self.vice_speaker.mention}")

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

        active_leg_session_id = await self.get_active_leg_session()

        if active_leg_session_id is not None:
            return await ctx.send(f":x: There is still an open session, close Session #{active_leg_session_id} first!")

        last_session = await self.get_last_leg_session()

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

        await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_legislator_role(self.bot).mention}, the "
                                                              f"submission period for Legislative Session "
                                                              f"#{new_session} has started!\nSubmit your "
                                                              f"bills with `-legislature submit <link>`.")

        await ctx.send(f":white_check_mark: Successfully opened the submission period for session #{new_session}!")

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

        if not self.is_google_doc_link(voting_form):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        active_leg_session_id = await self.get_active_leg_session()

        if active_leg_session_id is None:
            return await ctx.send(f":x: There is no open session!")

        try:
            await self.bot.db.execute("UPDATE legislature_sessions SET status = 'Voting Period',"
                                      " voting_start_unixtime = $2"
                                      " WHERE id = $1", active_leg_session_id, time.time())
        except Exception:
            return await ctx.send(":x: Fatal database error.")

        await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_legislator_role(self.bot).mention},"
                                                              f" the voting period for Legislative Session "
                                                              f"#{active_leg_session_id} has started!\n:ballot_box:"
                                                              f" Vote here: {voting_form}")

        await ctx.send(f":white_check_mark: Successfully opened session #{active_leg_session_id} up for voting!")

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

        active_leg_session_id = await self.get_active_leg_session()

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

    @legislature.command(name='session')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def session(self, ctx, session: str = None):
        """Get details about a legislative session

        Usage:
        `-legislature session` to see details about the session that is currently open
        `-legislature session <number>` to see details about a specific session
        `-legislature session all` to see a list of all previous sessions."""

        self.refresh_leg_discord_objects()

        if not session or session is None:
            active_leg_session_id = await self.get_active_leg_session()

            if active_leg_session_id is None:
                msg = f":x: There currently is no on-going session.\n" \
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

                pretty_sessions = "Use `-legislature session <number>` to get more details about a session.\n\n"

                for record in all_session_ids:
                    pretty_sessions += f"**Session #{record[0][0]}**   - {record[0][1]}\n"

                embed = self.bot.embeds.embed_builder(title=f"All Sessions of the {mk.NATION_ADJECTIVE} Legislature",
                                                      description=pretty_sessions)
                await ctx.send(embed=embed)

            else:
                active_leg_session_id = int(session)

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

        bills = await self.bot.db.fetch(
            "SELECT (link, bill_name, submitter, is_law) FROM legislature_bills"
            " WHERE leg_session = $1", active_leg_session_id)

        pretty_bills = f""
        pretty_start_date = datetime.datetime.utcfromtimestamp(session_info[0][3]).strftime("%A, %B %d %Y"
                                                                                            " %H:%M:%S")
        if len(bills) > 0:
            for record in bills:
                pretty_bills += f"[{record[0][1]}]({record[0][0]}) by {self.bot.get_user(record[0][2]).mention}\n"

        else:
            pretty_bills = "No one submitted any bills during this session."

        embed = self.bot.embeds.embed_builder(title=f"Legislative Session #{str(active_leg_session_id)}",
                                              description="", time_stamp=True)
        embed.add_field(name="Opened by", value=self.bot.get_user(session_info[0][0]).mention)
        embed.add_field(name="Open", value=str(session_info[0][1]))
        embed.add_field(name="Opened on (UTC)", value=pretty_start_date, inline=False)

        if not session_info[0][1]:
            pretty_end_date = datetime.datetime.utcfromtimestamp(session_info[0][4]).strftime("%A, %B %d %Y"
                                                                                              " %H:%M:%S")
            embed.add_field(name="Ended on (UTC)", value=pretty_end_date, inline=False)

        embed.add_field(name="Status", value=session_info[0][5], inline=True)

        if session_info[0][5] != "Submission Period":
            pretty_voting_date = datetime.datetime.utcfromtimestamp(session_info[0][6]).strftime("%A, %B %d %Y"
                                                                                                 " %H:%M:%S")

            embed.add_field(name="Voting Started on (UTC)", value=pretty_voting_date, inline=True)
            embed.add_field(name="Vote Form", value=f"[Link]({session_info[0][2]})", inline=False)

        embed.add_field(name="Submitted Bills", value=pretty_bills, inline=False)

        await ctx.send(embed=embed)

    @legislature.command(name='submit')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Legislator", "Legislature")
    @utils.is_democraciv_guild()
    async def submit(self, ctx, google_docs_url: str):
        """Submit a new bill directly to the current Cabinet"""

        if not self.is_google_doc_link(google_docs_url):
            return await ctx.send(":x: That doesn't look like a Google Docs URL.")

        async with ctx.typing():

            self.refresh_leg_discord_objects()

            current_leg_session = await self.get_active_leg_session()

            if current_leg_session is None:
                await ctx.send(":x: There is no active session!")
                return

            bill_title = await self.get_google_docs_title(google_docs_url)

            if bill_title is None:
                await ctx.send(":x: Could not connect to Google Docs!")
                return

            embed = self.bot.embeds.embed_builder(title="New Bill Submitted", description="", time_stamp=True)
            embed.add_field(name="Title", value=bill_title, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name)
            embed.add_field(name="Session", value=current_leg_session)
            embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow())
            embed.add_field(name="URL", value=google_docs_url, inline=False)

            try:
                await self.bot.db.execute(
                    "INSERT INTO legislature_bills (leg_session, link, bill_name, submitter, is_law) "
                    "VALUES ($1, $2, $3, $4, false)", current_leg_session, google_docs_url,
                    bill_title, ctx.author.id)

            except asyncpg.UniqueViolationError:
                await ctx.send(":x: This bill was already submitted!")
                return
            except Exception:
                await ctx.send(":x: Database error!")
                return

            try:
                await self.speaker.send(embed=embed)
                await self.vice_speaker.send(embed=embed)

                await ctx.send(
                    f":white_check_mark: Successfully submitted '{bill_title}' for Session #{current_leg_session}!")
            except Exception:
                await ctx.send(":x: Unexpected error occurred during DMing the Speaker or Vice-Speaker!"
                               " Your bill was not submitted, please try again!")
                return

    @submit.error
    async def submiterror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only Legislators are allowed to use this command!")

        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'google_docs_url':
                await ctx.send(":x: You have to give me a valid Google Docs URL of the bill you want to submit!")


def setup(bot):
    bot.add_cog(Legislature(bot))
