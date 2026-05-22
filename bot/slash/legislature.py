import collections
import datetime
import traceback
import typing

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config, mk
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import transformers, ui
from bot.utils import context as legacy_context
from bot.utils import converter, exceptions, mixin, models, text

BillOption = app_commands.Transform[models.Bill, transformers.BillTransformer]
PartyOption = app_commands.Transform[
    converter.PoliticalParty, transformers.PoliticalPartyTransformer
]

SENATE_COMMAND_NAME = mk.MarkConfig.LEGISLATURE_COMMAND.lower()
COMMONS_COMMAND_NAME = "commons"


def _submit_cooldown(interaction: discord.Interaction):
    if isinstance(interaction.user, discord.Member):
        bypass_roles = {
            mk.DemocracivRole.SPEAKER.value,
            mk.DemocracivRole.VICE_SPEAKER.value,
            mk.DemocracivRole.MK13_SENATOR_PRESIDING.value,
        }
        if any(role.id in bypass_roles for role in interaction.user.roles):
            return None

    return app_commands.Cooldown(1, 15)


def _utc_timestamp(value: datetime.datetime) -> str:
    return f"<t:{int(value.timestamp())}:F>"


class SubmitBillModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        session: models.Session,
    ):
        super().__init__(title=f"Submit a Bill to {models.display_house_name(house)}")
        self.cog = cog
        self.house = house
        self.session = session

        self.google_docs_url = discord.ui.Label(
            text="Link to Google Docs",
            description="Bills are submitted as public Google Docs documents.",
            component=discord.ui.TextInput(
                style=discord.TextStyle.short,
                max_length=512,
                placeholder="https://docs.google.com/document/d/...",
            ),
        )
        self.bill_description = discord.ui.Label(
            text="Summary",
            description="What does your bill do? Write a short summary.",
            component=discord.ui.TextInput(
                style=discord.TextStyle.short,
                max_length=500,
            ),
        )
        self.is_procedure = discord.ui.Label(
            text=f"Bill or {models.display_house_name(house)} Procedure",
            description=(
                "Procedures only apply to this chamber. Bills continue through the "
                "normal bicameral process."
            ),
            component=discord.ui.Select(
                options=[
                    discord.SelectOption(
                        emoji="\U0001f4dd",
                        label="Bill. Other branches may be able to vote on this.",
                        value="false",
                        default=True,
                    ),
                    discord.SelectOption(
                        emoji="\U0001f512",
                        label=f"{models.display_house_name(house)} procedure only.",
                        value="true",
                    ),
                ],
            ),
        )

        self.add_item(self.google_docs_url)
        self.add_item(self.bill_description)
        self.add_item(self.is_procedure)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=f"{self.house} submit",
        )
        await ctx.defer()
        await self.cog.submit_bill(
            ctx,
            house=self.house,
            session=self.session,
            google_docs_url=self.google_docs_url.component.value,
            bill_description=self.bill_description.component.value,
            is_procedure=self.is_procedure.component.values[0] == "true",
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"{config.NO} Something went wrong.", ephemeral=True
            )
        traceback.print_exception(type(error), error, error.__traceback__)


class SubmitMotionModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        session: models.Session,
    ):
        super().__init__(title=f"Submit a Motion to {models.display_house_name(house)}")
        self.cog = cog
        self.house = house
        self.session = session

        self.intro = discord.ui.TextDisplay(
            content=(
                "Motions are best for temporary or one-off chamber decisions. "
                "Use a bill for permanent law or anything that belongs in the Legal Code."
            )
        )
        self.motion_title = discord.ui.Label(
            text="Title",
            description="What is the title of your motion?",
            component=discord.ui.TextInput(
                style=discord.TextStyle.short,
                max_length=200,
            ),
        )
        self.motion_description = discord.ui.Label(
            text="Content",
            description="Write the motion text, or paste a Google Docs link.",
            component=discord.ui.TextInput(style=discord.TextStyle.long),
        )
        self.understand_description = discord.ui.Label(
            text="Motions are temporary",
            description="I understand that motions are not added to the Legal Code.",
            component=discord.ui.Checkbox(),
        )

        self.add_item(self.intro)
        self.add_item(self.motion_title)
        self.add_item(self.motion_description)
        self.add_item(self.understand_description)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=f"{self.house} submit",
        )
        await ctx.defer()

        if not self.understand_description.component.value:
            return await ctx.send(
                f"{config.NO} Please confirm that you understand how motions work.",
                ephemeral=True,
            )

        await self.cog.submit_motion(
            ctx,
            house=self.house,
            session=self.session,
            title=self.motion_title.component.value,
            description=self.motion_description.component.value,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"{config.NO} Something went wrong.", ephemeral=True
            )
        traceback.print_exception(type(error), error, error.__traceback__)


class SubmitBillButton(discord.ui.Button):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        session: models.Session,
    ):
        super().__init__(
            label="Submit Bill",
            style=discord.ButtonStyle.primary,
            emoji="\U0001f4dd",
        )
        self.cog = cog
        self.house = house
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SubmitBillModal(self.cog, house=self.house, session=self.session)
        )


class SubmitMotionButton(discord.ui.Button):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        session: models.Session,
    ):
        super().__init__(
            label="Submit Motion",
            style=discord.ButtonStyle.secondary,
            emoji="\U0001f5f3",
        )
        self.cog = cog
        self.house = house
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SubmitMotionModal(self.cog, house=self.house, session=self.session)
        )


class LegislatureSlash(commands.Cog, mixin.GovernmentMixin):
    senate = app_commands.Group(
        name=SENATE_COMMAND_NAME,
        description="Senate session, submission, and export commands.",
        guild_only=True,
    )
    senate_session = app_commands.Group(
        name="session",
        description="Show and manage Senate sessions.",
        parent=senate,
    )
    senate_export = app_commands.Group(
        name="export",
        description="Export Senate session data.",
        parent=senate,
    )

    commons = app_commands.Group(
        name=COMMONS_COMMAND_NAME,
        description="Commons session, submission, and export commands.",
        guild_only=True,
    )
    commons_session = app_commands.Group(
        name="session",
        description="Show and manage Commons sessions.",
        parent=commons,
    )
    commons_export = app_commands.Group(
        name="export",
        description="Export Commons session data.",
        parent=commons,
    )

    def __init__(self, bot):
        self.bot = bot

    def house_command(self, house: str) -> str:
        return SENATE_COMMAND_NAME if house == "senate" else COMMONS_COMMAND_NAME

    def leader_term(self, house: str) -> str:
        if house == "senate":
            return self.bot.mk.senator_presiding_term

        return self.bot.mk.speaker_term

    def house_links(
        self,
        house: str,
        *,
        session: models.Session = None,
        extra: typing.Sequence[ui.LayoutLink] = (),
    ) -> list[ui.LayoutLink]:
        links = [
            ui.LayoutLink("Docket", self.bot.mk.LEGISLATURE_DOCKET, "\U0001f4ca"),
            ui.LayoutLink(
                "Procedures", self.bot.mk.LEGISLATURE_PROCEDURES, "\U0001f4d6"
            ),
            ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
            ui.LayoutLink("Laws Site", "https://laws.democraciv.com", "\U0001f517"),
        ]

        if session and session.vote_form:
            links.insert(
                0, ui.LayoutLink("Voting Form", session.vote_form, "\U0001f5f3")
            )

        return list(extra) + links

    def _format_stats(self, *, record, record_key: str, stats_name: str) -> str:
        counter = collections.Counter(r[record_key] for r in record if r[record_key])
        lines = []

        for user_id, amount in counter.most_common():
            user = self.bot.get_user(user_id)
            if user is None:
                continue

            label = stats_name[:-1] if amount == 1 else stats_name
            lines.append(f"{len(lines) + 1}. {user.mention} with {amount} {label}")

            if len(lines) >= 5:
                break

        return "\n".join(lines) or "None"

    async def _send_general_statistics(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        amounts = await self.bot.db.fetch(
            """SELECT COUNT(id) FROM legislature_session WHERE house = $2
               UNION ALL
               SELECT COUNT(id) FROM bill
               UNION ALL
               SELECT COUNT(id) FROM bill WHERE status = $1
               UNION ALL
               SELECT COUNT(id) FROM motion""",
            models.BillIsLaw.flag.value,
            house,
        )

        submitter = await self.bot.db.fetch("SELECT submitter FROM bill")
        speaker = await self.bot.db.fetch(
            "SELECT speaker FROM legislature_session WHERE house = $1",
            house,
        )
        lawmaker = await self.bot.db.fetch(
            "SELECT submitter FROM bill WHERE status = $1",
            models.BillIsLaw.flag.value,
        )

        if house == "senate":
            title = (
                f"Statistics for the {self.bot.mk.NATION_ADJECTIVE} "
                f"{self.bot.mk.LEGISLATURE_NAME}"
            )
            leader_title = (
                f"Top {self.bot.mk.senator_presiding_term}s of "
                f"the {self.bot.mk.LEGISLATURE_NAME}"
            )
        else:
            title = "Statistics for the Commons"
            leader_title = f"Top {self.bot.mk.speaker_term}s of the Commons"

        await ui.send_static(
            ctx,
            title=title,
            sections=[
                ui.LayoutSection(
                    "General Statistics",
                    f"Sessions: {amounts[0]['count']}\n"
                    f"Submitted Bills: {amounts[1]['count']}\n"
                    f"Submitted Motions: {amounts[3]['count']}\n"
                    f"Active Laws: {amounts[2]['count']}",
                ),
                ui.LayoutSection(
                    leader_title,
                    self._format_stats(
                        record=speaker,
                        record_key="speaker",
                        stats_name="sessions",
                    ),
                ),
                ui.LayoutSection(
                    "Top Bill Submitters",
                    self._format_stats(
                        record=submitter,
                        record_key="submitter",
                        stats_name="bills",
                    ),
                ),
                ui.LayoutSection(
                    "Top Lawmakers",
                    self._format_stats(
                        record=lawmaker,
                        record_key="submitter",
                        stats_name="laws",
                    ),
                ),
            ],
            links=self.house_links(house),
        )

    async def _send_target_statistics(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        member: discord.User = None,
        party: converter.PoliticalParty = None,
    ):
        if member is not None and party is not None:
            return await ctx.send(
                f"{config.NO} Choose either a member or a party, not both.",
                ephemeral=True,
            )

        if member is None and party is None:
            return await self._send_general_statistics(ctx, house=house)

        if party is not None:
            ids = [person.id for person in party.role.members]
            if house == "senate":
                title = (
                    f"Members of {party.role.name} in the "
                    f"{self.bot.mk.NATION_ADJECTIVE} {self.bot.mk.LEGISLATURE_NAME}"
                )
            else:
                title = f"Members of {party.role.name} in the Commons"
        else:
            ids = [member.id]
            member_name = getattr(member, "display_name", member.name)
            if house == "senate":
                title = (
                    f"{member_name} in the {self.bot.mk.NATION_ADJECTIVE} "
                    f"{self.bot.mk.LEGISLATURE_NAME}"
                )
            else:
                title = f"{member_name} in the Commons"

        stats = await self.bot.db.fetch(
            """SELECT COUNT(*) FROM bill WHERE submitter = ANY($1::bigint[])
               UNION ALL
               SELECT COUNT(*) FROM bill WHERE submitter = ANY($1::bigint[]) AND status = $2
               UNION ALL
               SELECT COUNT(*) FROM motion WHERE submitter = ANY($1::bigint[])
               UNION ALL
               SELECT COUNT(id) FROM bill_sponsor WHERE sponsor = ANY($1::bigint[])
               UNION ALL
               SELECT COUNT(bill_sponsor.sponsor) FROM bill_sponsor JOIN bill
               ON bill_sponsor.bill_id = bill.id WHERE bill.submitter = ANY($1::bigint[])""",
            ids,
            models.BillIsLaw.flag.value,
        )

        await ui.send_static(
            ctx,
            title=title,
            sections=[
                ui.LayoutSection(
                    "Submissions",
                    f"Bill Submissions: {stats[0]['count']}\n"
                    f"Motion Submissions: {stats[2]['count']}",
                ),
                ui.LayoutSection("Laws Written", str(stats[1]["count"])),
                ui.LayoutSection("Bills Sponsored", str(stats[3]["count"])),
                ui.LayoutSection("Sponsors for Own Bills", str(stats[4]["count"])),
            ],
            links=self.house_links(house),
        )

    def _bill_submission_embed(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session: models.Session,
        bill_id: int,
        name: str,
        google_docs_url: str,
        bill_description: str,
        is_procedure: bool,
    ):
        house_name = models.display_house_name(house)
        embed = text.SafeEmbed(
            title=f"{name} (#{bill_id})",
            url=google_docs_url,
            description=(
                f"Hey! A new **bill** was just submitted to {house_name} "
                f"Session #{session.mk13_house_id}."
            ),
        )
        embed.add_field(
            name="Type",
            value=f"{house_name} Procedure" if is_procedure else "Bill",
            inline=False,
        )
        embed.add_field(name="Description", value=bill_description, inline=False)
        embed.add_field(
            name="Author", value=f"{ctx.author.mention} {ctx.author}", inline=False
        )
        embed.add_field(
            name="Google Docs Document", value=google_docs_url, inline=False
        )
        embed.add_field(
            name="Exact Time of Submission",
            value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>",
            inline=False,
        )
        embed.set_author(
            icon_url=ctx.author_icon,
            name=f"Submitted by {ctx.author.display_name}",
        )
        return embed

    def _motion_submission_embed(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session: models.Session,
        motion_id: int,
        title: str,
        description: str,
        motion_url: str,
    ):
        house_name = models.display_house_name(house)
        embed = text.SafeEmbed(
            title=f"{title} (#{motion_id})",
            url=motion_url,
            description=(
                f"Hey! A new **motion** was just submitted to {house_name} "
                f"Session #{session.mk13_house_id}."
            ),
        )
        embed.add_field(name="Content", value=description or "-", inline=False)
        embed.add_field(name="Author", value=f"{ctx.author.mention} {ctx.author}")
        embed.add_field(
            name="Exact Time of Submission",
            value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>",
            inline=False,
        )
        embed.set_author(
            icon_url=ctx.author_icon,
            name=f"Submitted by {ctx.author.display_name}",
        )
        return embed

    async def _send_submission_help(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        item_type: str,
        item_id: int,
    ):
        command_name = self.house_command(house)
        leader_term = self.leader_term(house)

        if item_type == "bill":
            sections = [
                ui.LayoutSection(
                    "Sponsors",
                    f"Supporters can sponsor this bill with `/bill sponsor`. "
                    f"The sponsor list appears on `/bill show`.",
                ),
                ui.LayoutSection(
                    "Editing",
                    "During the Submission Period, keep working in the Google Docs "
                    "document. Use `/bill edit` if the document link or summary needs "
                    "to change.",
                ),
                ui.LayoutSection(
                    "Withdrawing",
                    f"You can withdraw your own bill during Submission Period with "
                    f"`/bill withdraw`. The {leader_term} can withdraw chamber bills "
                    "while the session is open.",
                ),
                ui.LayoutSection(
                    "More Commands",
                    f"Use `/{command_name} session show`, `/bill show`, `/bill search`, "
                    "and `/bill history` to track this bill.",
                ),
            ]
        else:
            sections = [
                ui.LayoutSection(
                    "Sponsors",
                    "Supporters can sponsor this motion with `/motion sponsor`.",
                ),
                ui.LayoutSection(
                    "Editing and Withdrawing",
                    "Use `/motion edit` or `/motion withdraw` while the motion is still "
                    "eligible to be changed.",
                ),
                ui.LayoutSection(
                    "More Commands",
                    f"Use `/{command_name} session show`, `/motion show`, and "
                    "`/motion search` to track this motion.",
                ),
            ]

        await ui.send_static(
            ctx,
            title=f"Help for {item_type.title()} #{item_id}",
            sections=sections,
            links=self.house_links(house),
            ephemeral=True,
        )

    async def _send_channel_layout(
        self,
        channel: discord.abc.Messageable,
        *,
        title: str,
        body: str = None,
        sections: typing.Sequence[ui.LayoutSection] = (),
        links: typing.Sequence[ui.LayoutLink] = (),
    ):
        await channel.send(
            view=ui.RichLayout(
                title=title,
                body=body,
                sections=sections,
                links=links,
            )
        )

    async def _get_session_by_display_id(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_id: int,
    ) -> typing.Optional[models.Session]:
        record = await self.bot.db.fetchrow(
            "SELECT id FROM legislature_session WHERE house = $1 AND mk13_house_id = $2",
            house,
            session_id,
        )

        if record is None:
            record = await self.bot.db.fetchrow(
                "SELECT id FROM legislature_session WHERE house = $1 AND id = $2",
                house,
                session_id,
            )

        if record is None:
            return None

        return await models.Session.convert(ctx, record["id"])

    async def _get_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_id: int = None,
    ) -> typing.Optional[models.Session]:
        if session_id is None:
            return await self.get_last_leg_session(house=house)

        return await self._get_session_by_display_id(
            ctx, house=house, session_id=session_id
        )

    def _bill_has_minimum_senate_support(self, bill: models.Bill) -> bool:
        if bill.status.flag is not models._BillStatusFlag.SUBMITTED:
            return True

        if not bill.submitter or not isinstance(bill.submitter, discord.Member):
            return False

        if self.legislator_role and self.legislator_role in bill.submitter.roles:
            return True

        return bool(bill.sponsors)

    async def _session_entries(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session: models.Session,
        sponsor_filter: str = None,
    ) -> typing.Optional[list[str]]:
        filter_info = None
        sponsors_needed = ""
        if sponsor_filter:
            filter_info = await models.SessionSponsorFilter().convert(
                ctx, sponsor_filter
            )

            if filter_info is None:
                await ctx.send(
                    f"{config.NO} `{sponsor_filter}` is not a valid sponsor filter.",
                    ephemeral=True,
                )
                return None

        bills = [await models.Bill.convert(ctx, bill_id) for bill_id in session.bills]
        amount_of_all_bills = len(bills)

        if filter_info:
            filter_func, sponsors_needed = filter_info
            bills = list(filter(filter_func, bills))

        pretty_bills = []
        for bill in bills:
            warning = ""
            if house == "senate" and not self._bill_has_minimum_senate_support(bill):
                warning = " :warning:"

            sponsor_label = "sponsor" if len(bill.sponsors) == 1 else "sponsors"
            pretty_bills.append(
                f"* {bill.formatted} ({len(bill.sponsors)} {sponsor_label}){warning}"
            )
        pretty_bills = pretty_bills or ["-"]

        presider = session.speaker or legacy_context.MockUser()
        leader_label = (
            self.bot.mk.senator_presiding_term
            if house == "senate"
            else "Presiding Speaker"
        )

        entries = [
            f"### {leader_label}\n{presider.mention}\n"
            f"### Opened\n{_utc_timestamp(session.opened_on)}"
        ]

        if session.voting_started_on:
            entries.append(
                f"### Voting Started\n{_utc_timestamp(session.voting_started_on)}"
            )

        if session.closed_on:
            entries.append(f"### Closed\n{_utc_timestamp(session.closed_on)}")

        if session.status is models.SessionStatus.SUBMISSION_PERIOD:
            entries.append(
                "### Submissions\n"
                f"Bills and motions can be submitted with `/{self.house_command(house)} submit`."
            )

        entries.append(f"### Status\n{session.status.value}")

        if session.vote_form:
            entries.append(f"### Voting Form\n{session.vote_form}")

        amount = (
            f"{len(bills)}/{amount_of_all_bills}"
            if filter_info
            else str(amount_of_all_bills)
        )
        sponsor_title = (
            ""
            if not filter_info
            else f" ({sponsors_needed} sponsor{'s' if sponsors_needed != '=1' else ''})"
        )
        entries.append(f"### Submitted Bills{sponsor_title} ({amount})")

        if not filter_info:
            entries.append(
                "Use the sponsor filter option to show only submissions matching "
                "`>=2`, `=1`, `<3`, and similar filters."
            )

        entries.extend(pretty_bills)

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            motions = [
                await models.Motion.convert(ctx, motion_id)
                for motion_id in session.motions
            ]
            amount_of_all_motions = len(motions)

            if filter_info:
                motions = list(filter(filter_func, motions))

            pretty_motions = [
                f"* {motion.formatted} ({len(motion.sponsors)} sponsor"
                f"{'s' if len(motion.sponsors) != 1 else ''})"
                for motion in motions
            ] or ["-"]
            motion_amount = (
                f"{len(motions)}/{amount_of_all_motions}"
                if filter_info
                else str(amount_of_all_motions)
            )
            entries.append(f"### Submitted Motions{sponsor_title} ({motion_amount})")
            entries.extend(pretty_motions)

        return entries

    async def show_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_id: int = None,
        sponsor_filter: str = None,
    ):
        session = await self._get_session(ctx, house=house, session_id=session_id)
        if session is None:
            return await ctx.send(
                f"{config.NO} There hasn't been a {models.display_house_name(house)} session yet.",
                ephemeral=True,
            )

        entries = await self._session_entries(
            ctx, house=house, session=session, sponsor_filter=sponsor_filter
        )
        if entries is None:
            return

        if session.status is models.SessionStatus.CLOSED:
            entries.insert(0, ":warning: This session is already closed.")

        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"{models.display_house_name(house)} Session #{session.mk13_house_id}",
            links=self.house_links(house, session=session),
            empty_message="There are no session details.",
        )

    async def open_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        notify_legislators: bool = False,
    ):
        active_session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is not None:
            return await ctx.send(
                f"{config.NO} There is still an open {house_name} session. "
                f"Close session #{active_session.mk13_house_id} first.",
                ephemeral=True,
            )

        sequence = (
            "mk13_senate_session_seq"
            if house == "senate"
            else "mk13_commons_session_seq"
        )
        new_session = await self.bot.db.fetchrow(
            f"INSERT INTO legislature_session (speaker, opened_on, house, mk13_house_id) "
            f"VALUES ($1, $2, $3, nextval('{sequence}')) RETURNING id, mk13_house_id",
            ctx.author.id,
            datetime.datetime.utcnow(),
            house,
        )
        queued_bill_count = await self.attach_pending_bills_to_session(
            house=house, session_id=new_session["id"]
        )
        display_id = new_session["mk13_house_id"]

        sections = [
            ui.LayoutSection(
                "Submission Period",
                f"Bills and motions can now be submitted with `/{command_name} submit`.",
            ),
            ui.LayoutSection(
                "Next Controls",
                f"Lock submissions with `/{command_name} session lock`, start voting with "
                f"`/{command_name} session vote`, or close the session with "
                f"`/{command_name} session close`.",
            ),
        ]

        if queued_bill_count:
            sections.append(
                ui.LayoutSection(
                    "Attached Pending Bills",
                    f"{queued_bill_count} bill{'s' if queued_bill_count != 1 else ''} "
                    "from the other chamber were attached to this session.",
                )
            )

        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{display_id} Opened",
            body="The submission period is now open.",
            sections=sections,
            links=self.house_links(house),
        )

        await self._send_channel_layout(
            self.gov_announcements_channel,
            title=f"Submission Period Open for {house_name} Session #{display_id}",
            body=(
                f"The cabinet has opened the submission period for {house_name} "
                f"Session #{display_id}."
            ),
            sections=[
                ui.LayoutSection(
                    "Submissions",
                    f"Bills and motions can be submitted with `/{command_name} submit`.",
                ),
                ui.LayoutSection(
                    "Sponsors",
                    "Bills and motions can be sponsored with `/bill sponsor` and "
                    "`/motion sponsor`.",
                ),
            ],
            links=self.house_links(house),
        )

        if notify_legislators:
            await self.dm_legislators(
                reason="leg_session_open",
                message=(
                    f":envelope_with_arrow: The submission period for {house_name} "
                    f"Session #{display_id} has started. Submit bills and motions "
                    f"with `/{command_name} submit` on the {self.bot.dciv.name} server."
                ),
            )

    async def lock_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        active_session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.",
                ephemeral=True,
            )

        if active_session.status is not models.SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(
                f"{config.NO} You can only lock sessions that are in Submission Period.",
                ephemeral=True,
            )

        await self.bot.db.execute(
            "UPDATE legislature_session SET status = $1 WHERE id = $2",
            models.SessionStatus.LOCKED.value,
            active_session.id,
        )

        await self._send_channel_layout(
            self.gov_announcements_channel,
            title=f"{house_name} Session #{active_session.mk13_house_id} Locked",
            body=(
                f"{self.leader_term(house)} has locked submissions. Nothing can be "
                "submitted until the session is unlocked again."
            ),
            links=self.house_links(house, session=active_session),
        )
        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{active_session.mk13_house_id} Locked",
            body=(
                f"Submissions have been locked. Unlock them again with "
                f"`/{command_name} session unlock`."
            ),
            links=self.house_links(house, session=active_session),
        )

    async def unlock_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        active_session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.",
                ephemeral=True,
            )

        if active_session.status is not models.SessionStatus.LOCKED:
            return await ctx.send(
                f"{config.NO} You can only unlock sessions that are already locked.",
                ephemeral=True,
            )

        await self.bot.db.execute(
            "UPDATE legislature_session SET status = $1 WHERE id = $2",
            models.SessionStatus.SUBMISSION_PERIOD.value,
            active_session.id,
        )

        await self._send_channel_layout(
            self.gov_announcements_channel,
            title=f"{house_name} Session #{active_session.mk13_house_id} Unlocked",
            body="Submissions are open again.",
            links=self.house_links(house, session=active_session),
        )
        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{active_session.mk13_house_id} Unlocked",
            body="Submissions are open again.",
            links=self.house_links(house, session=active_session),
        )

    async def vote_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        voting_form: str,
        notify_legislators: bool = False,
    ):
        active_session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.",
                ephemeral=True,
            )

        if active_session.status is models.SessionStatus.VOTING_PERIOD:
            return await ctx.send(
                f"{config.NO} This session is already in the Voting Period.",
                ephemeral=True,
            )

        if not self.is_google_doc_link(voting_form):
            return await ctx.send(
                f"{config.NO} That does not look like a Google Forms or Google Sheets link.\n"
                f"{config.HINT} `/{command_name} export form` is still disabled for security reasons.",
                ephemeral=True,
            )

        await active_session.start_voting(voting_form)

        await self._send_channel_layout(
            self.gov_announcements_channel,
            title=f"Voting Started for {house_name} Session #{active_session.mk13_house_id}",
            body=f"Voting is open here:\n{voting_form}",
            links=self.house_links(
                house,
                session=active_session,
                extra=[ui.LayoutLink("Voting Form", voting_form, "\U0001f5f3")],
            ),
        )
        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{active_session.mk13_house_id} Voting Period",
            body=(
                "The session is now in voting period. Once voting is complete, close "
                f"the session with `/{command_name} session close`."
            ),
            links=self.house_links(
                house,
                session=active_session,
                extra=[ui.LayoutLink("Voting Form", voting_form, "\U0001f5f3")],
            ),
        )

        if notify_legislators:
            await self.dm_legislators(
                reason="leg_session_update",
                message=(
                    f":ballot_box: Voting for {house_name} Session "
                    f"#{active_session.mk13_house_id} has started.\nVote here: {voting_form}"
                ),
            )

    async def close_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        active_session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.",
                ephemeral=True,
            )

        confirmed = await ui.confirm(
            ctx,
            title=f"Close {house_name} Session #{active_session.mk13_house_id}",
            body=(
                "This closes the session and marks every bill from this chamber that "
                "is not explicitly passed afterwards as failed."
            ),
            confirm_label="Close Session",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await active_session.close()

        consumer = models.LegalConsumer(
            ctx=ctx,
            objects=[
                await models.Bill.convert(ctx, bill) for bill in active_session.bills
            ],
            action=models.BillStatus.fail_in_legislature,
        )
        await consumer.filter(acting_house=house)
        await consumer.consume(acting_house=house)

        await self._send_channel_layout(
            self.gov_announcements_channel,
            title=f"{house_name} Session #{active_session.mk13_house_id} Closed",
            links=self.house_links(house, session=active_session),
        )
        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{active_session.mk13_house_id} Closed",
            body=(
                "Now tally the results and mark each passing bill with "
                f"`/{command_name} pass`."
            ),
            sections=[
                ui.LayoutSection(
                    "Bills",
                    "Bills not marked as passed from this chamber have been failed "
                    "for this session.",
                ),
                ui.LayoutSection(
                    "Motions",
                    "Motions are temporary chamber actions and are not passed into law.",
                ),
            ],
            links=self.house_links(house, session=active_session),
        )

    async def submit_entrypoint(
        self,
        interaction: discord.Interaction,
        *,
        house: str,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name=f"{house} submit"
        )
        session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)

        if session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.\n"
                f"{config.HINT} The {self.leader_term(house)} can open the next "
                f"session with `/{self.house_command(house)} session open`.",
                ephemeral=True,
            )

        if session.status is not models.SessionStatus.SUBMISSION_PERIOD:
            if (
                session.status is models.SessionStatus.LOCKED
                and self.is_cabinet_for_house(ctx.author, house)
            ):
                pass
            elif session.status is models.SessionStatus.LOCKED:
                return await ctx.send(
                    f"{config.NO} The {self.leader_term(house)} has locked "
                    f"submissions for Session #{session.mk13_house_id}.",
                    ephemeral=True,
                )
            elif session.status is models.SessionStatus.VOTING_PERIOD:
                return await ctx.send(
                    f"{config.NO} Voting for Session #{session.mk13_house_id} has already started.",
                    ephemeral=True,
                )

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            return await interaction.response.send_modal(
                SubmitBillModal(self, house=house, session=session)
            )

        await ui.send_static(
            ctx,
            title=f"Submit to {house_name} Session #{session.mk13_house_id}",
            body="Choose the kind of proposal you want to submit.",
            sections=[
                ui.LayoutSection(
                    "Bills",
                    "Use bills for permanent law, procedures, and anything that belongs "
                    "in the legal record.",
                ),
                ui.LayoutSection(
                    "Motions",
                    "Use motions for temporary decisions or short-term chamber actions.",
                ),
            ],
            links=self.house_links(house, session=session),
            action_items=[
                SubmitBillButton(self, house=house, session=session),
                SubmitMotionButton(self, house=house, session=session),
            ],
            ephemeral=True,
        )

    def _can_submit_kind(
        self,
        ctx: slash_context.InteractionContext,
        *,
        kind: str,
    ) -> bool:
        if kind == "bill" and self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
            return True

        if (
            kind == "motion"
            and self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS
        ):
            return True

        return bool(
            isinstance(ctx.author, discord.Member)
            and self.legislator_role
            and self.legislator_role in ctx.author.roles
        )

    async def submit_bill(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session: models.Session,
        google_docs_url: str,
        bill_description: str,
        is_procedure: bool,
    ):
        if not self._can_submit_kind(ctx, kind="bill"):
            return await ctx.send(
                f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                "are allowed to submit bills.",
                ephemeral=True,
            )

        if not google_docs_url:
            return await ctx.send(
                f"{config.NO} Missing Google Docs URL.", ephemeral=True
            )

        bill_description = bill_description or "*No summary provided by submitter.*"
        is_vetoable = not is_procedure
        house_name = models.display_house_name(house)

        bill = models.Bill(
            bot=self.bot,
            link=google_docs_url,
            submitter_description=bill_description,
        )
        name, tags, content = await bill.fetch_name_and_keywords()

        if not name:
            return await ctx.send(
                f"{config.NO} Something went wrong. Are you sure the Google Docs "
                "document is public?\n"
                f"{config.HINT} Word (.docx) documents on Google Docs are not supported.",
                ephemeral=True,
            )

        bill_id = await self.bot.db.fetchval(
            "INSERT INTO bill (leg_session, name, link, submitter, is_vetoable, "
            "is_procedure, submitter_description, content, origin_house) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
            session.id,
            name,
            google_docs_url,
            ctx.author.id,
            is_vetoable,
            is_procedure,
            bill_description,
            content,
            house,
        )
        bill.id = bill_id
        await self.bot.db.execute(
            "INSERT INTO bill_session (bill_id, leg_session) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            bill_id,
            session.id,
        )
        await bill.status.log_history(
            old_status=models.BillSubmitted.flag,
            new_status=models.BillSubmitted.flag,
            note=f"Submitted to {house_name} Session #{session.mk13_house_id}",
        )

        if tags:
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    [(bill_id, tag) for tag in tags],
                )
            )

        await self.bot.api_request(
            "POST", "document/add", silent=True, json={"id": bill_id, "type": "bill"}
        )

        submission_embed = self._bill_submission_embed(
            ctx,
            house=house,
            session=session,
            bill_id=bill_id,
            name=name,
            google_docs_url=google_docs_url,
            bill_description=bill_description,
            is_procedure=is_procedure,
        )

        await ui.send_static(
            ctx,
            title=f"{name} (#{bill_id})",
            body=f"Your bill was submitted to {house_name} Session #{session.mk13_house_id}.",
            sections=[
                ui.LayoutSection(
                    "Type",
                    f"{house_name} Procedure" if is_procedure else "Bill",
                ),
                ui.LayoutSection("Summary", bill_description),
                ui.LayoutSection("Author", f"{ctx.author.mention} {ctx.author}"),
                ui.LayoutSection(
                    "Next Steps",
                    f"Supporters can sponsor this bill with `/bill sponsor`. "
                    f"The submission appears on `/{self.house_command(house)} session show`.",
                ),
            ],
            links=self.house_links(
                house,
                session=session,
                extra=[
                    ui.LayoutLink("Read Document", google_docs_url, "\U0001f4c3"),
                    ui.LayoutLink(
                        "laws.democraciv.com",
                        f"https://laws.democraciv.com/bill/{bill_id}",
                        "\U0001f517",
                    ),
                ],
            ),
        )
        await self._send_submission_help(
            ctx,
            house=house,
            item_type="bill",
            item_id=bill_id,
        )

        if not self.is_cabinet_for_house(ctx.author, house):
            for leader in self.get_cabinet_members_for_house(house):
                await self.bot.safe_send_dm(
                    target=leader,
                    reason="leg_session_submit",
                    embed=submission_embed,
                )

    async def submit_motion(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session: models.Session,
        title: str,
        description: str,
    ):
        if not self._can_submit_kind(ctx, kind="motion"):
            return await ctx.send(
                f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                "are allowed to submit motions.",
                ephemeral=True,
            )

        if not title:
            return await ctx.send(f"{config.NO} Missing motion title.", ephemeral=True)

        house_name = models.display_house_name(house)
        motion_url = "https://laws.democraciv.com/motion/<id>"
        motion_id = await self.bot.db.fetchval(
            "INSERT INTO motion (leg_session, title, description, submitter, paste_link) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            session.id,
            title,
            description,
            ctx.author.id,
            motion_url,
        )
        motion_url = f"https://laws.democraciv.com/motion/{motion_id}"
        await self.bot.db.execute(
            "UPDATE motion SET paste_link = $1 WHERE id = $2",
            motion_url,
            motion_id,
        )
        await self.bot.api_request(
            "POST",
            "document/add",
            silent=True,
            json={"id": motion_id, "type": "motion"},
        )

        submission_embed = self._motion_submission_embed(
            ctx,
            house=house,
            session=session,
            motion_id=motion_id,
            title=title,
            description=description,
            motion_url=motion_url,
        )

        await ui.send_static(
            ctx,
            title=f"{title} (#{motion_id})",
            body=f"Your motion was submitted to {house_name} Session #{session.mk13_house_id}.",
            sections=[
                ui.LayoutSection("Content", description or "*No content provided.*"),
                ui.LayoutSection("Author", f"{ctx.author.mention} {ctx.author}"),
                ui.LayoutSection(
                    "Next Steps",
                    f"Supporters can sponsor this motion with `/motion sponsor`. "
                    f"The motion appears on `/{self.house_command(house)} session show`.",
                ),
            ],
            links=self.house_links(
                house,
                session=session,
                extra=[
                    ui.LayoutLink("Motion Page", motion_url, "\U0001f517"),
                ],
            ),
        )
        await self._send_submission_help(
            ctx,
            house=house,
            item_type="motion",
            item_id=motion_id,
        )

        if not self.is_cabinet_for_house(ctx.author, house):
            for leader in self.get_cabinet_members_for_house(house):
                await self.bot.safe_send_dm(
                    target=leader,
                    reason="leg_session_submit",
                    embed=submission_embed,
                )

    async def pass_bill(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        bill: models.Bill,
    ):
        last_session = await self.get_last_leg_session(house=house)
        house_name = models.display_house_name(house)

        if last_session is None:
            return await ctx.send(
                f"{config.NO} There has not been a {house_name} session yet.",
                ephemeral=True,
            )

        def verify_bill(_ctx, target_bill, *, last_session, **_kwargs):
            if last_session.id != target_bill.session.id:
                return "You can only mark bills from the most recent session as passed."

            if last_session.status is not models.SessionStatus.CLOSED:
                return "You can only mark bills as passed if their session is closed."

        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.pass_from_legislature
        )
        await consumer.filter(
            filter_func=verify_bill,
            last_session=last_session,
            acting_house=house,
        )

        if consumer.failed:
            await ctx.send(
                f":warning: The following bill cannot be passed.\n{consumer.failed_formatted}",
                ephemeral=True,
            )

        if not consumer.passed:
            return

        confirmed = await ui.confirm(
            ctx,
            title=f"Pass Bill from {house_name}",
            body=consumer.passed_formatted,
            confirm_label="Pass Bill",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        scheduler = getattr(self.bot.get_cog(house_name), "pass_scheduler", None)
        await consumer.consume(scheduler=scheduler, acting_house=house)

        await ui.send_static(
            ctx,
            title=f"Bill #{bill.id} Passed from {house_name}",
            body="The bill's next legal destination has been recorded.",
            sections=[
                ui.LayoutSection("Bill", f"[{bill.name}]({bill.link})"),
                ui.LayoutSection(
                    "Status",
                    bill.status.emojified_status(verbose=True),
                ),
            ],
            links=self.house_links(
                house,
                extra=[
                    ui.LayoutLink("Read Document", bill.link, "\U0001f4c3"),
                    ui.LayoutLink(
                        "laws.democraciv.com",
                        f"https://laws.democraciv.com/bill/{bill.id}",
                        "\U0001f517",
                    ),
                ],
            ),
        )

        if bill.status.is_law and bill.content and "repeal" in bill.content.lower():
            await ctx.send(
                f"{config.HINT} {ctx.author.mention}, I found the word `repeal` in "
                f"this new law. You may need `/law repeal`.",
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )

    async def override_veto(
        self,
        ctx: slash_context.InteractionContext,
        *,
        bill: models.Bill,
    ):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.override_veto
        )
        await consumer.filter(acting_house="senate")

        if consumer.failed:
            await ctx.send(
                f":warning: This bill's veto cannot be overridden.\n{consumer.failed_formatted}",
                ephemeral=True,
            )

        if not consumer.passed:
            return

        confirmed = await ui.confirm(
            ctx,
            title="Override Executive Veto",
            body=(
                f"Override the {self.bot.mk.MINISTRY_NAME}'s veto of this bill?\n\n"
                f"{consumer.passed_formatted}"
            ),
            confirm_label="Override Veto",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        scheduler = getattr(self.bot.get_cog("Senate"), "override_scheduler", None)
        await consumer.consume(scheduler=scheduler, acting_house="senate")

        await ui.send_static(
            ctx,
            title=f"Veto Overridden for Bill #{bill.id}",
            body=(
                f"The veto was overridden. This bill is now an active law and appears "
                "in `/law list`."
            ),
            sections=[
                ui.LayoutSection("Bill", f"[{bill.name}]({bill.link})"),
                ui.LayoutSection(
                    "Status",
                    bill.status.emojified_status(verbose=True),
                ),
            ],
            links=self.house_links(
                "senate",
                extra=[
                    ui.LayoutLink("Read Document", bill.link, "\U0001f4c3"),
                    ui.LayoutLink(
                        "laws.democraciv.com",
                        f"https://laws.democraciv.com/bill/{bill.id}",
                        "\U0001f517",
                    ),
                ],
            ),
        )

    async def export_spreadsheet(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_id: int = None,
    ):
        session = await self._get_session(ctx, house=house, session_id=session_id)
        house_name = models.display_house_name(house)
        if session is None:
            return await ctx.send(
                f"{config.NO} There has not been a {house_name} session yet.",
                ephemeral=True,
            )

        bills = [await models.Bill.convert(ctx, bill_id) for bill_id in session.bills]
        motions = [
            await models.Motion.convert(ctx, motion_id) for motion_id in session.motions
        ]
        exported = [
            f"Export of {house_name} Session {session.mk13_house_id} -- "
            f"{discord.utils.utcnow().strftime('%c')}\n\n",
            f"{house_name} Session #{session.mk13_house_id} - "
            f"{session.opened_on.strftime('%B %d %Y')}\n\n"
            "----- Submitted Bills -----\n",
        ]
        exported.extend(
            f"Bill #{bill.id} ({len(bill.sponsors)} sponsors)" for bill in bills
        )
        exported.append("\n")
        exported.extend(f'=HYPERLINK("{bill.link}"; "{bill.name}")' for bill in bills)
        exported.append("\n\n----- Submitted Motions -----\n")
        exported.extend(f"Motion #{motion.id}" for motion in motions)
        exported.append("\n")
        exported.extend(
            f'=HYPERLINK("{motion.link}"; "{motion.name}")' for motion in motions
        )

        paste_link = await self.bot.make_paste("\n".join(exported))
        await ui.send_static(
            ctx,
            title=f"Spreadsheet Export of {house_name} Session #{session.mk13_house_id}",
            body=(
                "This session's bills and motions were exported into copy-and-paste "
                "formatting for Google Sheets."
            ),
            links=self.house_links(
                house,
                session=session,
                extra=[
                    ui.LayoutLink("Spreadsheet Export", paste_link, "\U0001f4cb"),
                    ui.LayoutLink(
                        "How-To Video",
                        "https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4",
                        "\U000025b6",
                    ),
                ],
            ),
        )

    async def export_form(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        await ui.send_static(
            ctx,
            title=f"{models.display_house_name(house)} Voting Form Export",
            body=(
                f"{config.NO} This command is still disabled due to security concerns."
            ),
            links=self.house_links(house),
            ephemeral=True,
        )

    async def export_reddit(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        session = await self.get_active_leg_session(house=house)
        house_name = models.display_house_name(house)

        if session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session right now.",
                ephemeral=True,
            )

        confirmed = await ui.confirm(
            ctx,
            title=f"Post {house_name} Session #{session.mk13_house_id} to Reddit",
            body=f"This will post the current docket to r/{config.DEMOCRACIV_SUBREDDIT}.",
            confirm_label="Post to Reddit",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        bills = [await models.Bill.convert(ctx, bill_id) for bill_id in session.bills]
        motions = [
            await models.Motion.convert(ctx, motion_id) for motion_id in session.motions
        ]

        presider = session.speaker or legacy_context.MockUser()
        content = [
            f"{self.leader_term(house)} {presider.display_name} ({presider}) opened "
            f"the Submission Period for this session on "
            f"{session.opened_on.strftime('%B %d, %Y at %H:%M')} UTC."
        ]

        if session.voting_started_on:
            content.append(
                f"Voting started on "
                f"{session.voting_started_on.strftime('%B %d, %Y at %H:%M')} UTC "
                f"[here]({session.vote_form})."
            )

        content.append(
            "\n\nFeel free to use this thread to debate and propose feedback on "
            "bills and motions, in case voting has not started yet.\n\n"
            "###Relevant Links\n\n"
            f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
            "* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE})\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n"
        )

        if bills:
            content.append("\n\n###Submitted Bills\n---\n")
        for bill in bills:
            submitter = bill.submitter or legacy_context.MockUser()
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n"
                f"*Submitted by {submitter.display_name} ({submitter}) with "
                f"{len(bill.sponsors)} sponsor(s)*\n\n{bill.description}\n\n"
            )

        if motions:
            content.append("\n\n###Submitted Motions\n---\n")
        for motion in motions:
            submitter = motion.submitter or legacy_context.MockUser()
            content.append(
                f"__**Motion #{motion.id} - [{motion.name}]({motion.link})**__\n\n"
                f"*Submitted by {submitter.display_name} ({submitter})*\n\n"
                f"{motion.description}\n\n"
            )

        content.append(
            "\n\n---\n\n*I am a bot, and this is an automated service. Contact "
            "u/Jovanos (DerJonas on Discord) for further questions or bug reports.*"
        )

        result = await self.bot.api_request(
            "POST",
            "reddit/post",
            json={
                "subreddit": config.DEMOCRACIV_SUBREDDIT,
                "title": f"{house_name} Session #{session.mk13_house_id} - Docket & Submissions",
                "content": "\n\n".join(content),
            },
        )

        if "error" in result:
            raise exceptions.DemocracivBotAPIError()

        await ui.send_static(
            ctx,
            title=f"{house_name} Session #{session.mk13_house_id} Posted",
            body=f"A summary was posted to r/{config.DEMOCRACIV_SUBREDDIT}.",
            links=self.house_links(house, session=session),
        )

    @senate.command(name="submit", description="Submit a bill or motion to the Senate.")
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.checks.dynamic_cooldown(_submit_cooldown)
    async def senate_submit(self, interaction: discord.Interaction):
        await self.submit_entrypoint(interaction, house="senate")

    @commons.command(
        name="submit", description="Submit a bill or motion to the Commons."
    )
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.checks.dynamic_cooldown(_submit_cooldown)
    async def commons_submit(self, interaction: discord.Interaction):
        await self.submit_entrypoint(interaction, house="commons")

    @senate.command(name="pass", description="Mark one Senate bill as passed.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(bill="Bill ID or title")
    async def senate_pass(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="senate pass")
        await ctx.defer()
        await self.pass_bill(ctx, house="senate", bill=bill)

    @senate.command(
        name="override", description="Override the Executive veto of one bill."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(bill="Bill ID or title")
    async def senate_override(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(
            interaction, command_name="senate override"
        )
        await ctx.defer()
        await self.override_veto(ctx, bill=bill)

    @senate.command(
        name="statistics",
        description="Show Senate statistics, optionally for one member or party.",
    )
    @app_commands.describe(
        member="Member or user to show statistics for.",
        party="Political party to show statistics for.",
    )
    async def senate_statistics(
        self,
        interaction: discord.Interaction,
        member: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="senate statistics"
        )
        await ctx.defer()
        await self._send_target_statistics(
            ctx,
            house="senate",
            member=member,
            party=party,
        )

    @commons.command(name="pass", description="Mark one Commons bill as passed.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(bill="Bill ID or title")
    async def commons_pass(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="commons pass")
        await ctx.defer()
        await self.pass_bill(ctx, house="commons", bill=bill)

    @commons.command(
        name="statistics",
        description="Show Commons statistics, optionally for one member or party.",
    )
    @app_commands.describe(
        member="Member or user to show statistics for.",
        party="Political party to show statistics for.",
    )
    async def commons_statistics(
        self,
        interaction: discord.Interaction,
        member: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="commons statistics",
        )
        await ctx.defer()
        await self._send_target_statistics(
            ctx,
            house="commons",
            member=member,
            party=party,
        )

    @senate_session.command(name="show", description="Show a Senate session.")
    @app_commands.describe(
        session_id="Senate session number. Defaults to the latest session.",
        sponsor_filter="Optional sponsor filter such as >=2, =1, or <3.",
    )
    async def senate_session_show(
        self,
        interaction: discord.Interaction,
        session_id: int = None,
        sponsor_filter: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.show_session(
            ctx, house="senate", session_id=session_id, sponsor_filter=sponsor_filter
        )

    @commons_session.command(name="show", description="Show a Commons session.")
    @app_commands.describe(
        session_id="Commons session number. Defaults to the latest session.",
        sponsor_filter="Optional sponsor filter such as >=2, =1, or <3.",
    )
    async def commons_session_show(
        self,
        interaction: discord.Interaction,
        session_id: int = None,
        sponsor_filter: str = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.show_session(
            ctx, house="commons", session_id=session_id, sponsor_filter=sponsor_filter
        )

    @senate_session.command(name="open", description="Open a Senate submission period.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(notify_legislators="DM legislators about the new session.")
    async def senate_session_open(
        self, interaction: discord.Interaction, notify_legislators: bool = False
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.open_session(
            ctx, house="senate", notify_legislators=notify_legislators
        )

    @commons_session.command(
        name="open", description="Open a Commons submission period."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(notify_legislators="DM legislators about the new session.")
    async def commons_session_open(
        self, interaction: discord.Interaction, notify_legislators: bool = False
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.open_session(
            ctx, house="commons", notify_legislators=notify_legislators
        )

    @senate_session.command(name="lock", description="Lock Senate submissions.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def senate_session_lock(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.lock_session(ctx, house="senate")

    @commons_session.command(name="lock", description="Lock Commons submissions.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    async def commons_session_lock(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.lock_session(ctx, house="commons")

    @senate_session.command(name="unlock", description="Unlock Senate submissions.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def senate_session_unlock(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.unlock_session(ctx, house="senate")

    @commons_session.command(name="unlock", description="Unlock Commons submissions.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    async def commons_session_unlock(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.unlock_session(ctx, house="commons")

    @senate_session.command(name="vote", description="Start Senate voting period.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        voting_form="Google Forms, Sheets, or Docs voting link.",
        notify_legislators="DM legislators the voting link.",
    )
    async def senate_session_vote(
        self,
        interaction: discord.Interaction,
        voting_form: str,
        notify_legislators: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.vote_session(
            ctx,
            house="senate",
            voting_form=voting_form,
            notify_legislators=notify_legislators,
        )

    @commons_session.command(name="vote", description="Start Commons voting period.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        voting_form="Google Forms, Sheets, or Docs voting link.",
        notify_legislators="DM legislators the voting link.",
    )
    async def commons_session_vote(
        self,
        interaction: discord.Interaction,
        voting_form: str,
        notify_legislators: bool = False,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.vote_session(
            ctx,
            house="commons",
            voting_form=voting_form,
            notify_legislators=notify_legislators,
        )

    @senate_session.command(
        name="close", description="Close the active Senate session."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def senate_session_close(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.close_session(ctx, house="senate")

    @commons_session.command(
        name="close", description="Close the active Commons session."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    async def commons_session_close(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.close_session(ctx, house="commons")

    @senate_export.command(
        name="spreadsheet", description="Export a Senate session for Google Sheets."
    )
    @app_commands.describe(
        session_id="Senate session number. Defaults to the latest session."
    )
    async def senate_export_spreadsheet(
        self, interaction: discord.Interaction, session_id: int = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate export")
        await ctx.defer(ephemeral=True)
        await self.export_spreadsheet(ctx, house="senate", session_id=session_id)

    @commons_export.command(
        name="spreadsheet", description="Export a Commons session for Google Sheets."
    )
    @app_commands.describe(
        session_id="Commons session number. Defaults to the latest session."
    )
    async def commons_export_spreadsheet(
        self, interaction: discord.Interaction, session_id: int = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="commons export")
        await ctx.defer(ephemeral=True)
        await self.export_spreadsheet(ctx, house="commons", session_id=session_id)

    @senate_export.command(
        name="form", description="Explain Senate form export status."
    )
    async def senate_export_form(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="senate export")
        await ctx.defer(ephemeral=True)
        await self.export_form(ctx, house="senate")

    @commons_export.command(
        name="form", description="Explain Commons form export status."
    )
    async def commons_export_form(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="commons export")
        await ctx.defer(ephemeral=True)
        await self.export_form(ctx, house="commons")

    @senate_export.command(
        name="reddit", description="Post the active Senate docket to Reddit."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def senate_export_reddit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="senate export")
        await ctx.defer()
        await self.export_reddit(ctx, house="senate")

    @commons_export.command(
        name="reddit", description="Post the active Commons docket to Reddit."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    async def commons_export_reddit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="commons export")
        await ctx.defer()
        await self.export_reddit(ctx, house="commons")


async def setup(bot):
    await bot.add_cog(LegislatureSlash(bot))
