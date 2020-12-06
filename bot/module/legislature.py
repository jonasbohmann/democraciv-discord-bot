import collections
import datetime
import asyncpg
import discord

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import *
from bot.utils import models, text, paginator, context, mixin, checks, converter
from bot.utils.models import Bill, Session, Motion, SessionStatus


class PassScheduler(text.AnnouncementScheduler):
    def get_message(self) -> str:
        message = [
            f"{self.bot.get_democraciv_role(DemocracivRole.MINISTER).mention}, "
            f"the following bills were **passed by the {self.bot.mk.LEGISLATURE_NAME}**.\n"
        ]

        for obj in self._objects:
            if obj.is_vetoable:
                message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")
            else:
                message.append(f"-  __**{obj.name}**__ (<{obj.tiny_link}>)")

        message.append(
            f"\nAll non veto-able bills are now laws (marked as __underlined__), "
            f"the others were sent to the {self.bot.mk.MINISTRY_NAME}."
        )
        return "\n".join(message)


class OverrideScheduler(text.AnnouncementScheduler):
    def get_message(self) -> str:
        message = [
            f"{self.bot.get_democraciv_role(DemocracivRole.GOVERNMENT).mention}, "
            f"the {self.bot.mk.MINISTRY_NAME}'s **veto of the following bills were overridden** "
            f"by the {self.bot.mk.LEGISLATURE_NAME}.\n"
        ]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        message.append("\nAll of the above bills are now law.")
        return "\n".join(message)


class Legislature(context.CustomCog, mixin.GovernmentMixin, name=MarkConfig.LEGISLATURE_NAME):
    """Allows the Government to organize {LEGISLATURE_ADJECTIVE} sessions and their submitted bills"""

    def __init__(self, bot):
        super().__init__(bot)
        self.pass_scheduler = PassScheduler(bot, DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.override_scheduler = OverrideScheduler(bot, DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.illegal_tags = (
            "act",
            "the",
            "author",
            "authors",
            "date",
            "name",
            "bill",
            "law",
            "and",
            "d/m/y",
            "type",
            "description",
        )

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            self.bot.get_command(self.bot.mk.LEGISLATURE_COMMAND).remove_command("motion")
            self.bot.get_command(f"{self.bot.mk.LEGISLATURE_COMMAND} withdraw").remove_command("motion")

    @commands.group(
        name=MarkConfig.LEGISLATURE_NAME.lower(),
        aliases=["leg"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def legislature(self, ctx):
        """Dashboard for {legislator_term}s with important links and the status of the current session"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is None:
            current_session_value = "There currently is no open session."
        else:
            current_session_value = f"Session #{active_leg_session.id} - {active_leg_session.status.value}"

        embed = text.SafeEmbed(
            title=f"{self.bot.mk.NATION_EMOJI}  The {self.bot.mk.LEGISLATURE_NAME} "
                  f"of {self.bot.mk.NATION_FULL_NAME}"
        )
        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.speaker_term}: {self.speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.speaker_term}: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: {self.vice_speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: -")

        embed.add_field(name=self.bot.mk.LEGISLATURE_CABINET_NAME, value="\n".join(speaker_value))
        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n" f"[Legal Code]({self.bot.mk.LEGAL_CODE})\n",
            inline=True,
        )
        embed.add_field(name="Current Session", value=current_session_value, inline=False)
        await ctx.send(embed=embed)

    @legislature.group(
        name="bill",
        aliases=["b", "bills"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def bill(self, ctx: context.CustomContext, *, bill_id: models.Bill = None):
        """List all bills or get details about a single bill"""

        if bill_id is None:
            return await self._paginate_all_(ctx, model=models.Bill)

        return await self._detail_view(ctx, obj=bill_id)

    @bill.command(name="history", aliases=['h'])
    async def b_history(self, ctx: context.CustomContext, *, bill_id: models.Bill):
        """See when a bill was first introduced, passed into Law, vetoed, etc."""
        fmt_history = [f"**{entry.date.strftime('%d %B %Y')}** - {entry.after}   " 
                       f"({entry.after.emojified_status(verbose=False)})" for entry in bill_id.history]
        fmt_history.insert(0, "All dates are in UTC.\n")

        pages = paginator.SimplePages(entries=fmt_history, title=f"{bill_id.name} (#{bill_id.id})",
                                      title_url=bill_id.link)
        await pages.start(ctx)

    @bill.command(name="search", aliases=["s"])
    async def b_search(self, ctx: context.CustomContext, *, query: str):
        """Search for a bill"""
        return await self._search_model(ctx, model=models.Bill, query=query)

    @bill.command(name="from", aliases=["f", "by"])
    async def b_from(
            self,
            ctx: context.CustomContext,
            *,
            member_or_party: typing.Union[converter.CaseInsensitiveMember, converter.CaseInsensitiveUser, converter.PoliticalParty] = None,
    ):
        """List all bills that a specific person or Political Party submitted"""
        return await self._from_person_model(ctx, member_or_party=member_or_party, model=models.Bill)

    @legislature.group(
        name="motion",
        aliases=["m", "motions"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def motion(self, ctx: context.CustomContext, motion_id: Motion = None):
        """List all motions or get details about a single motion"""

        if motion_id is None:
            return await self._paginate_all_(ctx, model=models.Motion)

        return await self._detail_view(ctx, obj=motion_id)

    @motion.command(name="from", aliases=["f", "by"])
    async def m_from(
            self,
            ctx: context.CustomContext,
            *,
            member_or_party: typing.Union[converter.CaseInsensitiveMember, converter.CaseInsensitiveUser, converter.PoliticalParty] = None,
    ):
        """List all motions that a specific person or Political Party submitted"""
        return await self._from_person_model(ctx, model=models.Motion, member_or_party=member_or_party)

    @motion.command(name="search", aliases=["s"])
    async def m_search(self, ctx: context.CustomContext, *, query: str):
        """Search for a motion"""
        return await self._search_model(ctx, model=models.Motion, query=query)

    @legislature.group(
        name="session",
        aliases=["s"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def leg_session(self, ctx: context.CustomContext, session: Session = None):
        """Get details about a session from the Legislature

        **Usage**
        `{PREFIX}{COMMAND}` to see details about the last session
        `{PREFIX}{COMMAND} <number>` to see details about a specific session"""

        # User invoked -legislature session without arguments
        if session is None:
            session = await self.get_last_leg_session()

            if session is None:
                return await ctx.send(embed=text.SafeEmbed(title="There hasn't been a session yet."))

        if len(session.bills) > 0:
            pretty_bills = []

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                if bill.status.is_law:
                    pretty_bills.append(f"__Bill #{bill.id}__ - [{bill.short_name}]({bill.tiny_link})")
                else:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.short_name}]({bill.tiny_link})")
        else:
            pretty_bills = ["-"]

        embed = text.SafeEmbed(title=f"{self.bot.mk.NATION_EMOJI}  Legislative Session #{session.id}")

        if session.speaker is not None:
            embed.add_field(name="Opened by", value=session.speaker.mention)
        else:
            embed.add_field(name="Opened by", value="*Person left Democraciv*")

        embed.add_field(name="Status", value=session.status.value, inline=True)
        embed.add_field(name="Date", value=self.format_session_times(session), inline=False)

        if session.vote_form:
            embed.add_field(name="Vote Form", value=f"[Link]({session.vote_form})", inline=False)

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            if len(session.motions) > 0:
                pretty_motions = []
                for motion_id in session.motions:
                    motion = await Motion.convert(ctx, motion_id)
                    pretty_motions.append(f"Motion #{motion.id} - [{motion.short_name}]({motion.link})")
            else:
                pretty_motions = ["-"]

            pretty_motions = "\n".join(pretty_motions)
            too_long = (
                f"This text was too long for Discord, so I put it on "
                f"[here.]({await self.bot.make_paste(pretty_motions)})"
            )
            embed.add_field(
                name="Submitted Motions",
                value=pretty_motions,
                inline=False,
                too_long_value=too_long,
            )

        pretty_bills = "\n".join(pretty_bills)
        too_long_ = (
            f"This text was too long for Discord, so I put it on " f"[here.]({await self.bot.make_paste(pretty_bills)})"
        )
        embed.add_field(
            name="Submitted Bills",
            value=pretty_bills,
            inline=False,
            too_long_value=too_long_,
        )

        embed.set_footer(text="Bills that are underlined are active laws. All times are in UTC.")
        await ctx.send(embed=embed)

    @leg_session.command(name="open", aliases=["o"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def opensession(self, ctx):
        """Opens a session for the submission period to begin"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is not None:
            return await ctx.send(
                f"{config.NO} There is still an open session, close session #{active_leg_session.id} first!")

        new_session = await self.bot.db.fetchval(
            "INSERT INTO legislature_session (speaker, is_active, opened_on)" "VALUES ($1, true, $2) RETURNING id",
            ctx.author.id,
            datetime.datetime.utcnow(),
        )

        await ctx.send(f"{config.YES} The **submission period** for session #{new_session} was opened.")

        await self.gov_announcements_channel.send(
            f"The **submission period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
            f"#{new_session} has started! Bills can be "
            f"submitted with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit`."
        )

        await self.dm_legislators(
            reason="leg_session_open",
            message=f":envelope_with_arrow: The **submission period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
                    f" #{new_session} has started! Submit your bills with "
                    f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit` on the {self.bot.dciv.name} server.",
        )

    @leg_session.command(name="vote", aliases=["u", "v", "update"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def updatesession(self, ctx: context.CustomContext):
        """Changes the current session's status to be open for voting"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(f"{config.NO} There is no open session.")

        if active_leg_session.status is SessionStatus.VOTING_PERIOD:
            return await ctx.send(f"{config.NO} This session is already in the Voting Period.")
        elif active_leg_session.status is SessionStatus.CLOSED:
            return await ctx.send(f"{config.NO} This session is closed.")

        voting_form = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the link to this session' Google Forms voting "
            "form.\n\nHint: You can make me generate that form for you, "
            f"with the `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session export` command."
        )

        if not self.is_google_doc_link(voting_form):
            return await ctx.send(f"{config.NO} That doesn't look like a Google Docs URL.")

        await active_leg_session.start_voting(voting_form)

        await ctx.send(f"{config.YES} Session #{active_leg_session.id} is now in **voting period**.")

        await self.gov_announcements_channel.send(
            f"The **voting period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
            f"Session #{active_leg_session.id} "
            f"has started!\n{self.bot.mk.legislator_term}s can vote here: <{voting_form}>"
        )

        await self.dm_legislators(
            reason="leg_session_update",
            message=f":ballot_box: The **voting period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
                    f"#{active_leg_session.id} has started!\nVote here: {voting_form}",
        )

    @leg_session.command(name="close", aliases=["c"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is None:
            return await ctx.send(f"{config.NO} There is no open session.")

        await active_leg_session.close()

        #  Update all bills that did not pass
        await self.bot.db.execute(
            "UPDATE bill SET status = $1 WHERE leg_session = $2",
            models.BillFailedLegislature.flag.value,
            active_leg_session.id,
        )

        await ctx.send(
            f"{config.YES} Session #{active_leg_session.id} was closed. "
            f"Check `{config.BOT_PREFIX}help {self.bot.mk.LEGISLATURE_COMMAND} pass` on what to do next."
        )

        await self.gov_announcements_channel.send(
            f"{self.legislator_role.mention}, {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
            f"#{active_leg_session.id} has been **closed** by the "
            f"{self.bot.mk.LEGISLATURE_CABINET_NAME}.", allowed_mentions=discord.AllowedMentions(roles=True)
        )

    @leg_session.command(name="export", aliases=["es", "ex", "e"])
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def exportsession(self, ctx: context.CustomContext, session: Session = None):
        """Export a session's submissions for Google Spreadsheets and generate the Google Forms voting form"""
        if isinstance(session, str):
            return

        session = session or await self.get_last_leg_session()

        if session is None:
            return await ctx.send(f"{config.NO} There hasn't been a session yet.")

        async with ctx.typing():
            b_ids = []
            b_hyperlinks = []

            m_ids = []
            m_hyperlinks = []

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                b_ids.append(f"Bill #{bill.id}")
                b_hyperlinks.append(f'=HYPERLINK("{bill.link}"; "{bill.name}")')

            for motion_id in session.motions:
                motion = await Motion.convert(ctx, motion_id)
                m_ids.append(f"Motion #{motion.id}")
                m_hyperlinks.append(f'=HYPERLINK("{motion.link}"; "{motion.name}")')

            exported = [
                f"Export of {self.bot.mk.LEGISLATURE_ADJECTIVE} Session {session.id} -- {datetime.datetime.utcnow().strftime('%c')}\n\n\n",
                f"Xth Session - {session.opened_on.strftime('%B %d %Y')} (Bot Session {session.id})\n\n"
                "----- Submitted Bills -----\n",
            ]

            exported.extend(b_ids)
            exported.append("\n")
            exported.extend(b_hyperlinks)
            exported.append("\n\n----- Submitted Motions -----\n")
            exported.extend(m_ids)
            exported.append("\n")
            exported.extend(m_hyperlinks)

            link = await self.bot.make_paste("\n".join(exported))
            txt = (
                f"**__Export of {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}__**\nSee the video below to see how to speed up "
                f"your Speaker duties with this command.\n\n**Export:** <{link}>\n\n"
                "https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4"
            )
            await ctx.send(txt)

        question = await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Do you want me to generate the Google Forms"
            f" voting form for Legislative Session #{session.id} as well?"
        )

        reaction = await ctx.ask_to_continue(message=question, emoji=config.YES, timeout=30)

        if not reaction:
            ctx.command.reset_cooldown(ctx)
            return

        elif reaction:
            form_url = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with an **edit** link to an **empty** Google Forms "
                "form you created. I will then fill that form to make it the voting form. "
                "Create a Form here: <https://forms.new>",
                delete_after=True,
            )

            if not form_url:
                ctx.command.reset_cooldown(ctx)
                return

            if not self.is_google_doc_link(form_url):
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(f"{config.NO} That doesn't look like a Google Forms URL.")

            await ctx.send(
                f"{config.YES} I will generate the voting form for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}."
                f"\n:arrows_counterclockwise: This may take a few minutes..."
            )

            async with ctx.typing():
                bills = {b.name: b.link for b in [await Bill.convert(ctx, _b) for _b in session.bills]}
                motions = {m.name: m.link for m in [await Motion.convert(ctx, _m) for _m in session.motions]}

                result = await self.bot.run_apps_script(
                    script_id="MME1GytLY6YguX02rrXqPiGqnXKElby-M",
                    function="generate_form",
                    parameters=[form_url, session.id, bills, motions],
                )

            embed = text.SafeEmbed(
                title=f"Generated Voting Form for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}",
                description="Remember to double check the form to make sure it's "
                            "correct.\n\nNote that you may have to adjust "
                            "the form to comply with this nation's laws.\n"
                            "This comes with no guarantees of a form's valid "
                            "legal status.\n\nRemember to change the edit link you "
                            "gave me earlier to not be public.",
            )

            embed.add_field(
                name="Link to the Voting Form",
                value=result["response"]["result"]["view"],
                inline=False,
            )
            embed.add_field(
                name="Shortened Link to the Voting Form",
                value=result["response"]["result"]["short-view"],
                inline=False,
            )
            await ctx.send(embed=embed)

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch("SELECT id, opened_on, closed_on FROM legislature_session ORDER BY id")
        pretty_sessions = []

        for record in all_sessions:
            opened_on = record["opened_on"].strftime("%B %d")

            if record["closed_on"]:
                closed_on = record["closed_on"].strftime("%B %d %Y")
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on} to {closed_on}")
            else:
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on}")

        pages = paginator.SimplePages(
            entries=pretty_sessions,
            title=f"{self.bot.mk.NATION_EMOJI}  All Sessions of the {self.bot.mk.NATION_ADJECTIVE}"
                  f" {self.bot.mk.LEGISLATURE_NAME}",
            empty_message="There hasn't been a session yet.",
        )
        await pages.start(ctx)

    @staticmethod
    def format_session_times(session: Session) -> str:
        formatted_time = [f"**Opened**: {session.opened_on.strftime('%A, %B %d %Y at %H:%M')}"]

        if session.status is not SessionStatus.SUBMISSION_PERIOD:
            # Session is either closed or in Voting Period
            if session.voting_started_on is not None:
                formatted_time.append(
                    f"**Voting Started**: {session.voting_started_on.strftime('%A, %B %d %Y at %H:%M')}"
                )

        if not session.is_active:
            # Session is closed
            formatted_time.append(f"**Ended**: {session.closed_on.strftime('%A, %B %d %Y at %H:%M')}")

        return "\n".join(formatted_time)

    @leg_session.command(name="all", aliases=["a"])
    async def leg_session_all(self, ctx: context.CustomContext):
        """View a history of all previous sessions of the {LEGISLATURE_NAME}"""
        return await self.paginate_all_sessions(ctx)

    async def submit_bill(
            self, ctx: context.CustomContext, current_leg_session_id: int
    ) -> typing.Optional[discord.Embed]:
        """Submits a bill to a session that is in Submission Period. Uses the Flow API to get the bill
        details via Discord. Returns the message and formatted Embed that will be sent to
         the Cabinet upon submission."""

        # Google Docs Link
        google_docs_url = await ctx.input(
            f"{config.YES} You will submit a **bill**.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with the Google Docs link to the bill you want to submit."
        )

        if not self.is_google_doc_link(google_docs_url):
            await ctx.send("{config.NO} That doesn't look like a Google Docs URL.")
            ctx.command.reset_cooldown(ctx)
            return

        # Vetoable
        is_vetoable = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Is the {self.bot.mk.MINISTRY_NAME} legally allowed to vote on (veto) this bill?"
        )

        bill_description = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with a **short** description of what your bill does.",
            timeout=400,
        )

        if not bill_description:
            bill_description = "-"

        async with ctx.typing():
            tiny_url = await self.bot.tinyurl(google_docs_url)

            if tiny_url is None:
                await ctx.send(
                    f"{config.NO} Your bill was not submitted since there was a problem with tinyurl.com. "
                    "Try again in a few minutes."
                )
                return

            bill = models.Bill(bot=self.bot, link=google_docs_url, submitter_description=bill_description)
            name, tags = await bill.fetch_name_and_keywords()

            bill_id = await self.bot.db.fetchval(
                "INSERT INTO bill (leg_session, name, link, submitter, is_vetoable, "
                "submitter_description, tiny_link) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                current_leg_session_id,
                name,
                google_docs_url,
                ctx.author.id,
                is_vetoable,
                bill_description,
                tiny_url
            )

            bill.id = bill_id
            await bill.status.log_history(old_status=models.BillSubmitted.flag, new_status=models.BillSubmitted.flag)

            id_with_tags = [(bill_id, tag) for tag in tags]
            self.bot.loop.create_task(self.bot.db.executemany("INSERT INTO bill_lookup_tag (bill_id, tag) VALUES "
                                                              "($1, $2) ON CONFLICT DO NOTHING ", id_with_tags))

            embed = text.SafeEmbed(
                title="Bill Submitted",
                description="Hey! A new **bill** was just submitted.",
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Title", value=name, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name, inline=False)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(
                name=f"{self.bot.mk.MINISTRY_NAME} Veto Allowed",
                value="Yes" if is_vetoable else "No",
            )
            embed.add_field(
                name="Time of Submission (UTC)",
                value=datetime.datetime.utcnow(),
                inline=False,
            )
            embed.add_field(name="URL", value=google_docs_url, inline=False)

        await ctx.send(
            f"{config.YES} Your bill `{name}` was submitted for session #{current_leg_session_id}."
        )

        return embed

    async def submit_motion(
            self, ctx: context.CustomContext, current_leg_session_id: int
    ) -> typing.Optional[discord.Embed]:
        """Submits a motion to a session that is in Submission Period. Uses the Flow API to get the bill
        details via Discord. Returns the message and formatted Embed that will be sent to
        the Cabinet upon submission."""

        title = await ctx.input(
            f"{config.YES} You will submit a **motion**.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with the title of your motion."
        )

        if not title:
            return

        description = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the content of your motion. If your motion is"
            " inside a Google Docs document, just use a link to that for this."
        )

        if not description:
            return

        async with ctx.typing():
            haste_bin_url = await self.bot.make_paste(description)

            if not haste_bin_url:
                await ctx.send(
                    f"{config.NO} Your motion was not submitted, there was a problem with mystb.in. "
                    "Try again in a few minutes."
                )
                return

            await self.bot.db.execute(
                "INSERT INTO motion (leg_session, title, description, submitter, paste_link) "
                "VALUES ($1, $2, $3, $4, $5)",
                current_leg_session_id,
                title,
                description,
                ctx.author.id,
                haste_bin_url,
            )

            embed = text.SafeEmbed(
                title="Motion Submitted",
                description="Hey! A new **motion** was just submitted.",
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Content", value=description, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(
                name="Time of Submission (UTC)",
                value=datetime.datetime.utcnow(),
                inline=False,
            )

        await ctx.send(f"{config.YES} Your motion `{title}` was submitted for session #{current_leg_session_id}.")
        return embed

    @legislature.command(name="submit")
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    @checks.is_democraciv_guild()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        try:
            if self.is_cabinet(ctx.author):
                ctx.command.reset_cooldown(ctx)
        except exceptions.RoleNotFoundError:
            pass

        current_leg_session = await self.get_active_leg_session()

        if current_leg_session is None:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(f"{config.NO} There is no active session.")

        if current_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} The submission period for session #{current_leg_session.id} is already over.")

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            reaction = await ctx.choose(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to submit a motion or a bill?"
                f" React with {config.LEG_SUBMIT_BILL} for bill, and with "
                f"{config.LEG_SUBMIT_MOTION} for a motion."
                f"\n\n{config.HINT} *Motions lack a lot of features that bills have, "
                f"for example they cannot be passed into Law by the Government. They will not "
                f"show up in `{config.BOT_PREFIX}laws`, nor will they make it on the Legal Code. "
                f"If you want to submit something small "
                f"that results in some __temporary__ action, use a motion, otherwise use a bill. "
                f"\nCommon examples for motions: `Motion to repeal Law #12`, or "
                f"`Motion to recall {self.bot.mk.legislator_term} XY`.*",
                reactions=[config.LEG_SUBMIT_BILL, config.LEG_SUBMIT_MOTION],
            )

            embed = None

            if not reaction:
                return

            if str(reaction.emoji) == config.LEG_SUBMIT_BILL:
                if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
                    if self.legislator_role not in ctx.author.roles:
                        return await ctx.send(
                            f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} are allowed to " f"submit bills."
                        )

                embed = await self.submit_bill(ctx, current_leg_session.id)

            elif str(reaction.emoji) == config.LEG_SUBMIT_MOTION:
                ctx.command.reset_cooldown(ctx)

                if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS:
                    if self.legislator_role not in ctx.author.roles:
                        return await ctx.send(
                            f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} are allowed to " f"submit motions."
                        )

                embed = await self.submit_motion(ctx, current_leg_session.id)
        else:
            if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
                if self.legislator_role not in ctx.author.roles:
                    return await ctx.send(
                        f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} are allowed to " f"submit bills."
                    )

            embed = await self.submit_bill(ctx, current_leg_session.id)

        if embed is None:
            return

        if not self.is_cabinet(ctx.author):
            if self.speaker is not None:
                await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_submit", embed=embed)
            if self.vice_speaker is not None:
                await self.bot.safe_send_dm(target=self.vice_speaker, reason="leg_session_submit", embed=embed)

    @legislature.command(name="pass", aliases=["p"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def pass_bill(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Mark one or multiple bills as passed from the {LEGISLATURE_NAME}

        If the bill is veto-able, it sends the bill to the {MINISTRY_NAME}. If not, the bill automatically becomes law.

        **Example**
            `{PREFIX}{COMMAND} 12` will mark Bill #12 as passed from the {LEGISLATURE_NAME}
            `{PREFIX}{COMMAND} 45 46 49 51 52` will mark all those bills as passed"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        def verify_bill(_ctx, b: Bill, last_session: Session):
            if last_session.id != b.session.id:
                return "You can only mark bills from the most recent session as passed."

            if last_session.status is not SessionStatus.CLOSED:
                return "You cannot mark bills as passed while their session is still in Submission or Voting Period."

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.pass_from_legislature)
        await consumer.filter(filter_func=verify_bill, last_session=await self.get_last_leg_session())

        if consumer.failed:
            await ctx.send(f":warning: The following bills can not be passed.\n{consumer.failed_formatted}")

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to mark the following bills as passed from the {self.bot.mk.LEGISLATURE_NAME}?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.pass_scheduler)
        await ctx.send(f"{config.YES} All bills were marked as passed from the {self.bot.mk.LEGISLATURE_NAME}.")

    @legislature.group(name="withdraw", aliases=["w"], hidden=True)
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx):
        """Withdraw one or multiple bills or motions from the current session"""
        if ctx.invoked_subcommand is None:
            await ctx.send(
                f"{config.NO} You have to tell me whether you want to withdraw motions or bills!"
                " Take a look at the help page:"
            )
            await ctx.send_help(ctx.command)

    async def withdraw_objects(
            self,
            ctx: context.CustomContext,
            objects: typing.List[typing.Union[Bill, Motion]],
    ):
        if isinstance(objects[0], Bill):
            obj_name = "bill"
        else:
            obj_name = "motion"

        last_leg_session = await self.get_last_leg_session()

        def verify_object(_ctx, to_verify) -> str:
            if not to_verify.session.is_active:
                return f"The session during which this {obj_name} was submitted is not open anymore."

            if not self.is_cabinet(_ctx.author):
                if to_verify.submitter is not None and _ctx.author.id == to_verify.submitter.id:
                    if last_leg_session.status is SessionStatus.SUBMISSION_PERIOD:
                        allowed = True
                    else:
                        return f"The original submitter can only withdraw {obj_name}s during the Submission Period."
                else:
                    allowed = False
            else:
                allowed = True

            if not allowed:
                return (
                    f"Only the {_ctx.bot.mk.LEGISLATURE_CABINET_NAME} and the original submitter "
                    f"of this {obj_name} can withdraw it."
                )

        consumer = models.LegalConsumer(ctx=ctx, objects=objects, action=models.BillStatus.withdraw)
        await consumer.filter(filter_func=verify_object)

        if consumer.failed:
            await ctx.send(
                f":warning: The following {obj_name}s can not be withdrawn by you.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want"
            f" to withdraw the following {obj_name}s from Session #{last_leg_session.id}?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume()
        await ctx.send(f"{config.YES} All {obj_name}s were withdrawn.")
        message = f"The following {obj_name}s were withdrawn by {ctx.author}.\n{consumer.passed_formatted}"

        if not self.is_cabinet(ctx.author):
            if self.speaker is not None:
                await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_withdraw", message=message)
            if self.vice_speaker is not None:
                await self.bot.safe_send_dm(
                    target=self.vice_speaker,
                    reason="leg_session_withdraw",
                    message=message,
                )

    @withdraw.command(name="bill", aliases=["b"])
    @checks.is_democraciv_guild()
    async def withdrawbill(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Withdraw one or multiple bills from the current session

        The {speaker_term} and {vice_speaker_term} can withdraw every submitted bill during both the Submission Period and the Voting Period.
           The original submitter of the bill can only withdraw their own bill during the Submission Period.

        **Example**
            `{PREFIX}{COMMAND} 56` will withdraw bill #56
            `{PREFIX}{COMMAND} 12 13 14 15 16` will withdraw all those bills"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, bill_ids)

    @withdraw.command(name="motion", aliases=["m"])
    @checks.is_democraciv_guild()
    async def withdrawmotion(self, ctx: context.CustomContext, motion_ids: Greedy[Motion]):
        """Withdraw one or multiple motions from the current session

        The {speaker_term} and {vice_speaker_term} can withdraw every submitted motion during both the Submission Period and the Voting Period.
           The original submitter of the motion can only withdraw their own motion during the Submission Period.

        **Example**
            `{PREFIX}{COMMAND} 56` will withdraw motion #56
            `{PREFIX}{COMMAND} 12 13 14 15 16` will withdraw all those motions"""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, motion_ids)

    @legislature.command(name="override", aliases=["ov"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def override(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Override the veto of one or multiple bills to pass them into law

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.override_veto)
        await consumer.filter()

        if consumer.failed:
            await ctx.send(
                f":warning: The vetoes of the following bills can not be overridden.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to override the {self.bot.mk.MINISTRY_NAME}'s veto of the following "
            f"bills?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.override_scheduler)
        await ctx.send(f"{config.YES} The vetoes of all bills were overridden.")

    @legislature.command(name="resubmit", aliases=["rs"])
    @checks.has_any_democraciv_role(DemocracivRole.SPEAKER, DemocracivRole.VICE_SPEAKER)
    async def resubmit(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Resubmit any bills that failed in the {LEGISLATURE_NAME} or {MINISTRY_NAME} to the currently active session

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.resubmit)
        await consumer.filter()

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills cannot be resubmitted.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to resubmit the following bills to?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume()
        await ctx.send(f"{config.YES} All bills were resubmitted to the current session.")

    def _format_stats(self, *, record: asyncpg.Record, record_key: str, stats_name: str) -> str:
        """Prettifies the dicts used in generate_leg_statistics() to strings"""

        record_as_list = [r[record_key] for r in record]
        counter = dict(collections.Counter(record_as_list))
        sorted_dict = {k: v for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)}
        fmt = []

        for i, key, value in enumerate(sorted_dict.items(), start=1):
            if self.bot.get_user(key) is not None:
                if i > 5:
                    break

                if value == 1:
                    sts_name = stats_name[:-1]
                else:
                    sts_name = stats_name

                fmt.append(f"{i}. {self.bot.get_user(key).mention} with {value} {sts_name}")

        return "\n".join(fmt)

    async def _generate_leg_statistics(self):
        """Generates statistics for the -legislature stats command"""

        # todo fix this

        query = """SELECT COUNT(id) AS sessions FROM legislature_session
                UNION
                SELECT COUNT(id) AS bills FROM bill
                UNION
                SELECT COUNT(id) AS laws FROM bill WHERE status = $1
                UNION
                SELECT COUNT(id) AS motions FROM motion
                UNION 
                SELECT submitter AS b_submitters from bill
                UNION 
                SELECT speaker AS speakers from legislature_session
                UNION 
                SELECT submitter AS l_submitters from bill WHERE status = $1;"""

        amounts = await self.bot.db.fetchrow(query, models.BillIsLaw.flag.value)

        pretty_top_submitter = self._format_stats(
            record=amounts["b_submitters"], record_key="submitter", stats_name="bills"
        )

        pretty_top_speaker = self._format_stats(record=amounts["speakers"], record_key="speaker", stats_name="sessions")

        pretty_top_lawmaker = self._format_stats(
            record=amounts["l_submitters"], record_key="submitter", stats_name="laws"
        )

        return {
            "sessions": amounts["sessions"],
            "bills": amounts["bills"],
            "motions": amounts["motions"],
            "laws": amounts["laws"],
            "top_bills": pretty_top_submitter,
            "top_speaker": pretty_top_speaker,
            "top_laws": pretty_top_lawmaker,
        }

    @legislature.command(name="stats", aliases=["stat", "statistics", "statistic"])
    async def stats(self, ctx):
        """Statistics about the {LEGISLATURE_NAME}"""

        stats = await self._generate_leg_statistics()

        embed = text.SafeEmbed(
            title=f"{self.bot.mk.NATION_EMOJI}  Statistics for the "
                  f"{self.bot.mk.NATION_ADJECTIVE} "
                  f"{self.bot.mk.LEGISLATURE_NAME}"
        )

        general_value = (
            f"Sessions: {stats['sessions']}\nSubmitted Bills: {stats['bills']}\n"
            f"Submitted Motions: {stats['motions']}\nActive Laws: {stats['laws']}"
        )

        embed.add_field(name="General Statistics", value=general_value)
        embed.add_field(
            name=f"Top {self.bot.mk.speaker_term}s or {self.bot.mk.vice_speaker_term}s of "
                 f"the {self.bot.mk.LEGISLATURE_NAME}",
            value=stats["top_speaker"],
            inline=False,
        )
        embed.add_field(name="Top Bill Submitters", value=stats["top_bills"], inline=False)
        embed.add_field(name="Top Lawmakers", value=stats["top_laws"], inline=False)

        try:
            await ctx.send(embed=embed)
        except discord.HTTPException:
            await ctx.send(f"{config.NO} There has to be activity in the {self.bot.mk.LEGISLATURE_NAME} first.")


def setup(bot):
    bot.add_cog(Legislature(bot))
