import datetime
import difflib
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
from bot.utils import converter, exceptions, mixin, models, paginator, text

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


SESSION_TYPE_CHOICES = [
    app_commands.Choice(name="Regular", value=models.SessionKind.REGULAR.value),
    app_commands.Choice(name="Emergency", value=models.SessionKind.EMERGENCY.value),
]


def _session_kind_from_choice(value: str = None) -> typing.Optional[models.SessionKind]:
    if value is None:
        return None

    return models.SessionKind(value)


class SubmitBillModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        sessions: typing.Sequence[models.Session],
    ):
        super().__init__(title=f"Submit a Bill to {models.display_house_name(house)}")
        self.cog = cog
        self.house = house
        mixin.add_submit_session_choice(self, sessions)

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
        session, error = await self.cog.resolve_submit_session_from_modal(
            ctx,
            house=self.house,
            session_id=mixin.get_submit_session_choice_id(self),
        )
        if error:
            return await ctx.send(error, ephemeral=True)

        await self.cog.submit_bill(
            ctx,
            house=self.house,
            session=session,
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
        sessions: typing.Sequence[models.Session],
    ):
        super().__init__(title=f"Submit a Motion to {models.display_house_name(house)}")
        self.cog = cog
        self.house = house
        mixin.add_submit_session_choice(self, sessions)

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

        session, error = await self.cog.resolve_submit_session_from_modal(
            ctx,
            house=self.house,
            session_id=mixin.get_submit_session_choice_id(self),
        )
        if error:
            return await ctx.send(error, ephemeral=True)

        await self.cog.submit_motion(
            ctx,
            house=self.house,
            session=session,
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
        sessions: typing.Sequence[models.Session],
        disabled: bool = False,
    ):
        super().__init__(
            label="Submit Bill",
            style=discord.ButtonStyle.primary,
            emoji="\U0001f4dd",
            disabled=disabled,
        )
        self.cog = cog
        self.house = house
        self.sessions = list(sessions)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SubmitBillModal(self.cog, house=self.house, sessions=self.sessions)
        )


class SubmitMotionButton(discord.ui.Button):
    def __init__(
        self,
        cog: "LegislatureSlash",
        *,
        house: str,
        sessions: typing.Sequence[models.Session],
        disabled: bool = False,
    ):
        super().__init__(
            label="Submit Motion",
            style=discord.ButtonStyle.secondary,
            emoji="\U0001f5f3",
            disabled=disabled,
        )
        self.cog = cog
        self.house = house
        self.sessions = list(sessions)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SubmitMotionModal(self.cog, house=self.house, sessions=self.sessions)
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
            description=f"Hey! A new **bill** was just submitted to {session.display_name}.",
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
        embed = text.SafeEmbed(
            title=f"{title} (#{motion_id})",
            url=motion_url,
            description=f"Hey! A new **motion** was just submitted to {session.display_name}.",
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
            embed = text.SafeEmbed(
                title=f"Help for Bill #{item_id}",
                description=f"**{config.HINT} Help | Government System: Bill Submissions**",
            )
            embed.add_field(
                name="Sponsors",
                value=f"Supporters can sponsor this bill with `/bill sponsor`. "
                f"The sponsor list appears on `/bill show`.",
                inline=False,
            )
            embed.add_field(
                name="Editing",
                value="During the Submission Period, keep working in the Google Docs "
                "document. Use `/bill edit` if the document link or summary needs "
                "to change.",
                inline=False,
            )
            embed.add_field(
                name="Withdrawing",
                value=f"You can withdraw your own bill during Submission Period with "
                f"`/bill withdraw`. The {leader_term} can withdraw chamber bills "
                "while the session is open.",
                inline=False,
            )
            embed.add_field(
                name="More Commands",
                value=f"Use `/{command_name} session show`, `/bill show`, `/bill search`, "
                "and `/bill history` to track this bill.",
                inline=False,
            )
        else:
            embed = text.SafeEmbed(
                title=f"Help for Motion #{item_id}",
                description=f"**{config.HINT} Help | Government System: Motion Submissions**",
            )
            embed.add_field(
                name="Sponsors",
                value="Supporters can sponsor this motion with `/motion sponsor`.",
                inline=False,
            )
            embed.add_field(
                name="Editing and Withdrawing",
                value="Use `/motion edit` or `/motion withdraw` while the motion is still "
                "eligible to be changed.",
                inline=False,
            )
            embed.add_field(
                name="More Commands",
                value=f"Use `/{command_name} session show`, `/motion show`, and "
                "`/motion search` to track this motion.",
                inline=False,
            )

        await ctx.send(embed=embed, ephemeral=True)

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
        action: str = "view",
    ) -> typing.Optional[models.Session]:
        if session_id is None:
            ctx.session_prompt_cancelled = False
            open_sessions = await self.get_open_leg_sessions(house=house)
            if len(open_sessions) == 1:
                return open_sessions[0]
            if len(open_sessions) > 1:
                session = await self.prompt_for_leg_session(
                    ctx,
                    sessions=open_sessions,
                    action=action,
                    ephemeral=True,
                    silent=True,
                )
                if session is None:
                    ctx.session_prompt_cancelled = True
                return session
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

    async def _resolve_active_session_for_slash(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
        status: typing.Optional[models.SessionStatus] = None,
        option_name: str = "session_type",
        action: str = "use",
    ) -> typing.Tuple[bool, typing.Optional[models.Session]]:
        sessions = await self.get_open_leg_sessions(
            house=house, session_kind=session_kind, status=status
        )
        house_name = models.display_house_name(house)

        if len(sessions) == 1:
            return True, sessions[0]

        if session_kind is not None:
            await ctx.send(
                f"{config.NO} There is no open {session_kind.value.lower()} {house_name} session.",
                ephemeral=True,
            )
            return False, None

        if len(sessions) > 1:
            session = await self.prompt_for_leg_session(
                ctx,
                sessions=sessions,
                action=action,
                ephemeral=True,
                silent=True,
            )
            return session is not None, session

        return True, None

    async def _resolve_cross_house_target_for_slash(
        self,
        ctx: slash_context.InteractionContext,
        *,
        acting_house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ) -> typing.Tuple[bool, typing.Optional[models.Session]]:
        other_house = models.BillStatus.other_house(acting_house)
        return await self._resolve_active_session_for_slash(
            ctx,
            house=other_house,
            session_kind=session_kind,
            option_name="destination_session_type",
            action="send this bill to",
        )

    async def open_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: models.SessionKind,
        notify_legislators: bool = False,
    ):
        active_session = await self.get_active_leg_session(
            house=house, session_kind=session_kind
        )
        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is not None:
            return await ctx.send(
                f"{config.NO} There is still an open {active_session.display_name}. "
                "Close it first.",
                ephemeral=True,
            )

        sequence = (
            "mk13_senate_session_seq"
            if house == "senate"
            else "mk13_commons_session_seq"
        )
        new_session = await self.bot.db.fetchrow(
            f"INSERT INTO legislature_session (speaker, opened_on, house, mk13_house_id, session_kind) "
            f"VALUES ($1, $2, $3, nextval('{sequence}'), $4) RETURNING id, mk13_house_id",
            ctx.author.id,
            datetime.datetime.utcnow(),
            house,
            session_kind.value,
        )
        new_session_obj = await models.Session.convert(ctx, new_session["id"])
        queued_bill_count = await self.attach_pending_bills_to_session(
            house=house, session_id=new_session["id"]
        )
        display_name = new_session_obj.display_name

        new_session_name = f"{house_name} Session #{new_session['mk13_house_id']}"

        await ctx.send(
            f"{config.YES} The **submission period** for {new_session_name} was opened, "
            f"and bills & motions can now be submitted."
        )

        info = text.SafeEmbed()
        info.set_author(
            name=f"{config.HINT}  Help | Government System:  Legislative Sessions"
        )
        info.description = (
            f"You have several options on how to proceed with this {house_name} session.\n"
            f"- `/{command_name} session lock` — Lock submissions to start a debate period.\n"
            f"- `/{command_name} session unlock` — Unlock if you previously locked.\n"
            f"- `/{command_name} session vote` — Start the voting period (requires a voting form link).\n"
            f"- `/{command_name} session close` — Close the session."
        )
        info.add_field(
            name="Optional Voting Form",
            value=f"The `/{command_name} export form` can generate a voting form for you, but this has been disabled for security reasons.",
            inline=False,
        )
        info.add_field(
            name="Failed Bills from previous Sessions",
            value=f"Previous bills that failed can be resubmitted to the current submission period session with `/bill resubmit`.",
            inline=False,
        )
        await ctx.send(embed=info)

        if queued_bill_count > 0:
            await ctx.send(
                f"{config.HINT} I also attached {queued_bill_count} bill{'s' if queued_bill_count != 1 else ''} from the "
                f"{'Commons' if house == 'senate' else 'Senate'} that were waiting on the "
                f"{'Senate' if house == 'senate' else 'Commons'} to this new session."
            )

        announcement = text.SafeEmbed(
            description=f"The cabinet has opened the Submission Period for {display_name}."
        )
        announcement.set_author(
            name=f"Submission Period open for {display_name}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        announcement.add_field(
            name="Submissions",
            value=f"Bills and motions can be submitted with `/{command_name} submit`.\nYou can see all submissions with `/{command_name} session show`.",
            inline=False,
        )
        announcement.add_field(
            name="Sponsors",
            value=f"Bills and motions can be sponsored with `/bill sponsor` and `/motion sponsor`.\n\nThe list of submissions can be filtered by the amount of sponsors they have. For example, `/{command_name} session show >=1` will only show bills & motions with 1 or more sponsors.",
            inline=False,
        )
        await self.gov_announcements_channel.send(embed=announcement)

        if notify_legislators:
            await self.dm_legislators(
                reason="leg_session_open",
                message=(
                    f":envelope_with_arrow: The submission period for {house_name} "
                    f"{display_name} has started. Submit bills and motions "
                    f"with `/{command_name} submit` on the {self.bot.dciv.name} server."
                ),
            )

    async def lock_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ):
        ok, active_session = await self._resolve_active_session_for_slash(
            ctx, house=house, session_kind=session_kind, action="lock"
        )
        if not ok:
            return

        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.\n"
                f"{config.HINT} You can open a new session "
                f"at any time with `/{command_name} session open`.",
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

        await self.gov_announcements_channel.send(
            f"The {self.leader_term(house)} has locked submissions for {active_session.display_name}. Nothing can be submitted until the {self.leader_term(house)} decides to unlock the session again."
        )
        l = self.house_command(house)
        p = config.BOT_PREFIX
        await ctx.send(
            f"{config.YES} Submissions for {active_session.display_name} have been locked.\n"
            f"{config.HINT} Want to allow submissions again? Unlock the session with "
            f"`/{l} session unlock`.\n"
            f"{config.HINT} In case you intend to leave submissions locked until voting starts "
            f"in order to use this time as a **debate period**, you can make me post the current list "
            f"of submissions to **r/{config.DEMOCRACIV_SUBREDDIT}** with "
            f"`/{l} session export reddit`."
        )

    async def unlock_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ):
        ok, active_session = await self._resolve_active_session_for_slash(
            ctx, house=house, session_kind=session_kind, action="unlock"
        )
        if not ok:
            return

        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.\n"
                f"{config.HINT} You can open a new session "
                f"at any time with `/{command_name} session open`.",
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

        await self.gov_announcements_channel.send(
            f"The {self.leader_term(house)} has unlocked submissions for {active_session.display_name}, meaning you can now submit bills & motions with `/{command_name} submit` again."
        )
        await ctx.send(
            f"{config.YES} Submissions for {active_session.display_name} have been unlocked."
        )

    async def vote_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        voting_form: str,
        session_kind: typing.Optional[models.SessionKind] = None,
        notify_legislators: bool = False,
    ):
        ok, active_session = await self._resolve_active_session_for_slash(
            ctx, house=house, session_kind=session_kind, action="start voting for"
        )
        if not ok:
            return

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

        voters = f"{self.bot.mk.legislator_term}s" if house == "senate" else "Everyone"
        announcement = text.SafeEmbed(
            description=f"{voters} can vote here:\n{voting_form}"
        )
        announcement.set_author(
            name=f"Voting has started for {active_session.display_name}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        await self.gov_announcements_channel.send(embed=announcement)
        l = self.house_command(house)
        await ctx.send(
            f"{config.YES} {active_session.display_name} is now in **voting period**.\n"
            f"{config.HINT} You can post the list of submissions to "
            f"**r/{config.DEMOCRACIV_SUBREDDIT}** with `/{l} session export reddit`.\n"
            f"{config.HINT} Once enough time has passed for people to vote, close this session "
            f"with `/{l} session close`. I'll go over what happens after that once you close the session."
        )

        if notify_legislators:
            await self.dm_legislators(
                reason="leg_session_update",
                message=(
                    f":ballot_box: Voting for "
                    f"{active_session.display_name} has started.\nVote here: {voting_form}"
                ),
            )

    async def close_session(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ):
        ok, active_session = await self._resolve_active_session_for_slash(
            ctx, house=house, session_kind=session_kind, action="close"
        )
        if not ok:
            return

        house_name = models.display_house_name(house)
        command_name = self.house_command(house)

        if active_session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session.\n"
                f"{config.HINT} You can open a new session "
                f"at any time with `/{command_name} session open`.",
                ephemeral=True,
            )

        confirmed = await ui.confirm(
            ctx,
            title=f"Close {active_session.display_name}",
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

        announcement = text.SafeEmbed()
        announcement.set_author(
            name=f"{active_session.display_name} has been closed",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        await self.gov_announcements_channel.send(embed=announcement)
        l = self.house_command(house)
        await ctx.send(
            f"{config.YES} {active_session.display_name} was closed.\n"
            f"{config.HINT} Now tally the results and mark each passing bill with "
            f"`/{l} pass`."
        )

        info = text.SafeEmbed()
        info.set_author(
            name=f"{config.HINT}  Help | Government System:  Legislative Sessions"
        )
        info.description = (
            f"Now tally the results and use `/{l} pass <bill id>` to mark each bill as passed. "
            f"You will be prompted to confirm. You can mark multiple bills in "
            f"separate pass commands."
        )
        if house == "senate":
            info.add_field(
                name="What happens after a pass?",
                value="Bills passed by the Senate move to the Commons, unless they are Senate procedures which skip the Commons and the Ministry and become law once the Senate passes them.",
                inline=False,
            )
        else:
            info.add_field(
                name="What happens after a pass?",
                value="Bills passed by the Commons move to the Senate, unless they are Commons procedures which skip the Senate and the Ministry and become law once the Commons passes them.",
                inline=False,
            )
        info.add_field(
            name="Why can't I pass motions?",
            value="Motions are temporary chamber actions and cannot be passed into law.",
            inline=False,
        )
        info.add_field(
            name="Updating the Legal Code",
            value=f"The {self.bot.mk.speaker_term} can use `/law export` to generate a Google Docs Legal Code.",
            inline=False,
        )
        info.add_field(
            name="Keep it rolling",
            value=f"You can open the next {'Senate' if house == 'senate' else 'Commons'} session at any time with `/{l} session open`.",
            inline=False,
        )
        await ctx.send(embed=info)

    async def submit_entrypoint(
        self,
        interaction: discord.Interaction,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name=f"{house} submit"
        )
        house_name = models.display_house_name(house)
        open_sessions = await self.get_open_leg_sessions(
            house=house, session_kind=session_kind
        )
        eligible_sessions = [
            session
            for session in open_sessions
            if self.submission_session_rejection(
                ctx.author, house=house, session=session
            )
            is None
        ]

        if not eligible_sessions:
            return await ctx.send(
                self.submission_session_unavailable_message(
                    house=house,
                    member=ctx.author,
                    sessions=open_sessions,
                    session_kind=session_kind,
                ),
                ephemeral=True,
            )

        can_submit_bill = self._can_submit_kind(ctx, kind="bill")
        can_submit_motion = self._can_submit_kind(ctx, kind="motion")

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            if not can_submit_bill:
                return await ctx.send(
                    f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                    "are allowed to submit bills.",
                    ephemeral=True,
                )
            return await interaction.response.send_modal(
                SubmitBillModal(self, house=house, sessions=eligible_sessions)
            )

        if not (can_submit_bill or can_submit_motion):
            return await ctx.send(
                f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                "are allowed to submit bills or motions.",
                ephemeral=True,
            )

        title = f"Submit to {house_name}"
        links_session = None
        if len(eligible_sessions) == 1:
            title = f"Submit to {eligible_sessions[0].display_name}"
            links_session = eligible_sessions[0]

        embed = text.SafeEmbed(
            title=title,
            description="Choose the kind of proposal you want to submit.",
        )
        embed.add_field(
            name="Bills",
            value="Use bills for permanent law, procedures, and anything that belongs in the legal record.",
            inline=False,
        )
        embed.add_field(
            name="Motions",
            value="Use motions for temporary decisions or short-term chamber actions.",
            inline=False,
        )
        embed.set_footer(
            text=f"{config.HINT} In 80% of cases, you should use bills instead of motions!"
        )

        view = discord.ui.View()
        if can_submit_bill:
            view.add_item(
                SubmitBillButton(
                    self,
                    house=house,
                    sessions=eligible_sessions,
                    disabled=not can_submit_bill,
                )
            )
        if can_submit_motion:
            view.add_item(
                SubmitMotionButton(
                    self,
                    house=house,
                    sessions=eligible_sessions,
                    disabled=not can_submit_motion,
                )
            )
        await ctx.send(embed=embed, view=view, ephemeral=True)

    def _can_submit_kind(
        self,
        ctx: slash_context.InteractionContext,
        *,
        kind: str,
    ) -> bool:
        return self.can_member_submit_kind(ctx.author, kind=kind)

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
            note=f"Submitted to {session.display_name}",
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

        await ctx.send(
            f"{config.YES} Your bill `{name}` (#{bill_id}) was submitted for "
            f"{session.display_name}."
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

        await ctx.send(
            f"{config.YES} Your motion `{title}` (#{motion_id}) was submitted for "
            f"{session.display_name}.\n"
            f"{config.HINT} Tell your supporters to sponsor your motion with "
            f"`/motion sponsor {motion_id}`."
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
        destination_session_kind: typing.Optional[models.SessionKind] = None,
    ):
        house_name = models.display_house_name(house)

        def verify_bill(_ctx, target_bill, **_kwargs):
            if target_bill.session is None or target_bill.session.house != house:
                return f"You can only mark bills from a {house_name} session as passed here."

            if target_bill.session.status is not models.SessionStatus.CLOSED:
                return "You can only mark bills as passed if their session is closed."

        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.pass_from_legislature
        )
        await consumer.filter(
            filter_func=verify_bill,
            acting_house=house,
        )

        if consumer.failed:
            await ctx.send(
                f":warning: The following bill cannot be passed.\n{consumer.failed_formatted}",
                ephemeral=True,
            )

        if not consumer.passed:
            return

        target_session = None
        if self.bill_needs_cross_house_destination(bill, acting_house=house):
            ok, target_session = await self._resolve_cross_house_target_for_slash(
                ctx,
                acting_house=house,
                session_kind=destination_session_kind,
            )
            if not ok:
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
        await consumer.consume(
            scheduler=scheduler,
            acting_house=house,
            target_session=target_session,
        )

        await ctx.send(
            f"{config.YES} This bill was marked as passed from the {house_name}.\n"
            f"{config.HINT} Depending on the bill's path, it is now either waiting on the "
            f"{'Commons' if house == 'senate' else 'Senate'} or on the "
            f"{self.bot.mk.MINISTRY_NAME}, or it is already law if it was a "
            f"{house_name.lower()} procedure."
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

        await ctx.send(
            f"{config.YES} The veto was overridden. This bill is now an active law and appears "
            f"in `/law list`."
        )

    async def export_spreadsheet(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_id: int = None,
    ):
        session = await self._get_session(
            ctx, house=house, session_id=session_id, action="export"
        )
        house_name = models.display_house_name(house)
        if session is None:
            if getattr(ctx, "session_prompt_cancelled", False):
                return
            return await ctx.send(
                f"{config.NO} There has not been a {house_name} session yet.",
                ephemeral=True,
            )

        bills = [await models.Bill.convert(ctx, bill_id) for bill_id in session.bills]
        motions = [
            await models.Motion.convert(ctx, motion_id) for motion_id in session.motions
        ]
        exported = [
            f"Export of {session.display_name} -- "
            f"{discord.utils.utcnow().strftime('%c')}\n\n",
            f"{session.display_name} - "
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
        leader_term = self.leader_term(house)
        await ctx.send(
            f"__**Spreadsheet Export of {session.display_name}**__\n"
            f"This session's bills and motions were exported into a format that "
            f"you can easily copy & paste into Google Spreadsheets, for example for a "
            f"Legislative Docket: **<{paste_link}>**\n\n"
            f"See the video below to see how to speed up your "
            f"{leader_term} duties with this.\n"
            f"https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4"
        )

    async def export_form(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
    ):
        await ctx.send(
            f"{config.NO} This command is still disabled due to security concerns.",
            ephemeral=True,
        )

    async def export_reddit(
        self,
        ctx: slash_context.InteractionContext,
        *,
        house: str,
        session_kind: typing.Optional[models.SessionKind] = None,
    ):
        ok, session = await self._resolve_active_session_for_slash(
            ctx, house=house, session_kind=session_kind, action="post to Reddit"
        )
        if not ok:
            return

        house_name = models.display_house_name(house)

        if session is None:
            return await ctx.send(
                f"{config.NO} There is no open {house_name} session right now.",
                ephemeral=True,
            )

        confirmed = await ui.confirm(
            ctx,
            title=f"Post {session.display_name} to Reddit",
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
                "title": f"{session.display_name} - Docket & Submissions",
                "content": "\n\n".join(content),
            },
        )

        if "error" in result:
            raise exceptions.DemocracivBotAPIError()

        await ctx.send(f"A summary was posted to r/{config.DEMOCRACIV_SUBREDDIT}.")

    @senate.command(
        name="overview",
        description="Show the Senate dashboard with links, legislators, and session status.",
    )
    async def senate_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="senate overview"
        )
        await ctx.defer()
        embed = await self._build_legislature_overview_embed("senate")
        await ctx.send(embed=embed)

    @commons.command(
        name="overview",
        description="Show the Commons dashboard with links, legislators, and session status.",
    )
    async def commons_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons overview"
        )
        await ctx.defer()
        embed = await self._build_legislature_overview_embed("commons")
        await ctx.send(embed=embed)

    @senate.command(name="search", description="Search bills and motions together.")
    async def senate_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="senate search")
        await ctx.defer()
        results = await self._search_model(ctx, model=models.Bill, query=query)
        results += await self._search_model(ctx, model=models.Motion, query=query)
        if not results:
            return await ctx.send(f"Nothing found matching '{query}'.", ephemeral=True)
        unique = list(dict.fromkeys(results))
        unique.sort(
            key=lambda e: difflib.SequenceMatcher(
                None, query.lower(), e.lower()
            ).ratio(),
            reverse=True,
        )
        pages = paginator.SimplePages(
            entries=unique,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Bills & Motions matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)

    @commons.command(name="search", description="Search bills and motions together.")
    async def commons_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="commons search")
        await ctx.defer()
        results = await self._search_model(ctx, model=models.Bill, query=query)
        results += await self._search_model(ctx, model=models.Motion, query=query)
        if not results:
            return await ctx.send(f"Nothing found matching '{query}'.", ephemeral=True)
        unique = list(dict.fromkeys(results))
        unique.sort(
            key=lambda e: difflib.SequenceMatcher(
                None, query.lower(), e.lower()
            ).ratio(),
            reverse=True,
        )
        pages = paginator.SimplePages(
            entries=unique,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Bills & Motions matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)

    @senate.command(
        name="from",
        description="List bills and motions submitted by a person or party.",
    )
    @app_commands.describe(
        person="Person to list submissions for.",
        party="Political party to list submissions for.",
    )
    async def senate_from(
        self,
        interaction: discord.Interaction,
        person: discord.Member = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate from")
        await ctx.defer()

        member_or_party = person or party or ctx.author

        bills = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=models.Bill, paginate=False
        )
        motions = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=models.Motion, paginate=False
        )
        things = bills + motions

        if isinstance(member_or_party, converter.PoliticalParty):
            name = member_or_party.role.name
            empty = f"No member of {name} has submitted something yet."
            title = f"Bills & Motions from members of {name}"
            icon = (
                await member_or_party.get_logo() or self.bot.mk.NATION_ICON_URL or None
            )
        else:
            name = member_or_party.display_name
            empty = f"{name} hasn't submitted anything yet."
            title = f"Bills & Motions from {name}"
            icon = member_or_party.display_avatar.url

        pages = paginator.SimplePages(
            entries=things, author=title, icon=icon, empty_message=empty
        )
        await pages.start(ctx)

    @commons.command(
        name="from",
        description="List bills and motions submitted by a person or party.",
    )
    @app_commands.describe(
        person="Person to list submissions for.",
        party="Political party to list submissions for.",
    )
    async def commons_from(
        self,
        interaction: discord.Interaction,
        person: discord.Member = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="commons from")
        await ctx.defer()

        member_or_party = person or party or ctx.author

        bills = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=models.Bill, paginate=False
        )
        motions = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=models.Motion, paginate=False
        )
        things = bills + motions

        if isinstance(member_or_party, converter.PoliticalParty):
            name = member_or_party.role.name
            empty = f"No member of {name} has submitted something yet."
            title = f"Bills & Motions from members of {name}"
            icon = (
                await member_or_party.get_logo() or self.bot.mk.NATION_ICON_URL or None
            )
        else:
            name = member_or_party.display_name
            empty = f"{name} hasn't submitted anything yet."
            title = f"Bills & Motions from {name}"
            icon = member_or_party.display_avatar.url

        pages = paginator.SimplePages(
            entries=things, author=title, icon=icon, empty_message=empty
        )
        await pages.start(ctx)

    @senate_session.command(
        name="all",
        description="View a history of all previous Senate sessions.",
    )
    async def senate_session_all(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="senate session all"
        )
        await ctx.defer()
        await self._all_sessions(ctx, house="senate")

    @commons_session.command(
        name="all",
        description="View a history of all previous Commons sessions.",
    )
    async def commons_session_all(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session all"
        )
        await ctx.defer()
        await self._all_sessions(ctx, house="commons")

    async def _all_sessions(self, ctx: slash_context.InteractionContext, *, house: str):
        house_name = models.display_house_name(house)
        records = await self.bot.db.fetch(
            "SELECT id, mk13_house_id, opened_on, closed_on, session_kind "
            "FROM legislature_session WHERE house = $1 ORDER BY id",
            house,
        )
        entries = []
        for record in records:
            opened_on = f"<t:{int(record['opened_on'].timestamp())}:D>"
            label = (
                f"Emergency Session #{record['mk13_house_id']}"
                if record["session_kind"] == models.SessionKind.EMERGENCY.value
                else f"Session #{record['mk13_house_id']}"
            )
            if record["closed_on"]:
                closed_on = f"<t:{int(record['closed_on'].timestamp())}:D>"
                entries.append(f"* **{label}**  - {opened_on} to {closed_on}")
            else:
                entries.append(f"* **{label}**  - {opened_on}")

        pages = paginator.SimplePages(
            entries=entries,
            title=f"All Sessions of the {house_name}",
            per_page=12,
            empty_message="There hasn't been a session yet.",
        )
        await pages.start(ctx)

    @senate.command(name="submit", description="Submit a bill or motion to the Senate.")
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.checks.dynamic_cooldown(_submit_cooldown)
    @app_commands.describe(
        session_type="Preselect a regular or emergency target session."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_submit(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        await self.submit_entrypoint(
            interaction,
            house="senate",
            session_kind=_session_kind_from_choice(session_type),
        )

    @commons.command(
        name="submit", description="Submit a bill or motion to the Commons."
    )
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.checks.dynamic_cooldown(_submit_cooldown)
    @app_commands.describe(
        session_type="Preselect a regular or emergency target session."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_submit(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        await self.submit_entrypoint(
            interaction,
            house="commons",
            session_kind=_session_kind_from_choice(session_type),
        )

    @senate.command(name="pass", description="Mark one Senate bill as passed.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        bill="Bill ID or title",
        destination_session_type="Other-house target if both destination sessions are open.",
    )
    @app_commands.choices(destination_session_type=SESSION_TYPE_CHOICES)
    async def senate_pass(
        self,
        interaction: discord.Interaction,
        bill: BillOption,
        destination_session_type: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate pass")
        await ctx.defer()
        await self.pass_bill(
            ctx,
            house="senate",
            bill=bill,
            destination_session_kind=_session_kind_from_choice(
                destination_session_type
            ),
        )

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
        description="Show Senate statistics, optionally for one person or party.",
    )
    @app_commands.describe(
        person="Person to show statistics for.",
        party="Political party to show statistics for.",
    )
    async def senate_statistics(
        self,
        interaction: discord.Interaction,
        person: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="senate statistics"
        )
        await ctx.defer()
        embed = await self._build_statistics_embed(
            ctx=ctx, house="senate", target=person or party
        )
        await ctx.send(embed=embed)

    @commons.command(name="pass", description="Mark one Commons bill as passed.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        bill="Bill ID or title",
        destination_session_type="Other-house target if both destination sessions are open.",
    )
    @app_commands.choices(destination_session_type=SESSION_TYPE_CHOICES)
    async def commons_pass(
        self,
        interaction: discord.Interaction,
        bill: BillOption,
        destination_session_type: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="commons pass")
        await ctx.defer()
        await self.pass_bill(
            ctx,
            house="commons",
            bill=bill,
            destination_session_kind=_session_kind_from_choice(
                destination_session_type
            ),
        )

    @commons.command(
        name="statistics",
        description="Show Commons statistics, optionally for one person or party.",
    )
    @app_commands.describe(
        person="Person to show statistics for.",
        party="Political party to show statistics for.",
    )
    async def commons_statistics(
        self,
        interaction: discord.Interaction,
        person: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="commons statistics",
        )
        await ctx.defer()
        embed = await self._build_statistics_embed(
            ctx=ctx, house="commons", target=person or party
        )
        await ctx.send(embed=embed)

    @senate_session.command(name="show", description="Show a Senate session.")
    @app_commands.describe(
        session_id="Senate session number. Uses open session, prompts if needed, otherwise latest.",
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
        session = await self._get_session(ctx, house="senate", session_id=session_id)
        if session is None:
            if getattr(ctx, "session_prompt_cancelled", False):
                return
            return await ctx.send(
                f"{config.NO} There hasn't been a Senate session yet.",
                ephemeral=True,
            )
        if session.status is models.SessionStatus.CLOSED:
            entries = [":warning: This session is already closed."]
        else:
            entries = []
        if sponsor_filter:
            converted = await models.SessionSponsorFilter().convert(ctx, sponsor_filter)
            if converted is None:
                return await ctx.send(
                    f"{config.NO} `{sponsor_filter}` is not a valid sponsor filter.",
                    ephemeral=True,
                )
            sponsor_filter = converted
        else:
            sponsor_filter = None
        entries.extend(
            await self._build_session_entries(
                ctx=ctx,
                house="senate",
                session=session,
                sponsor_filter=sponsor_filter,
            )
        )
        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=session.display_name,
        )
        await pages.start(ctx)

    @commons_session.command(name="show", description="Show a Commons session.")
    @app_commands.describe(
        session_id="Commons session number. Uses open session, prompts if needed, otherwise latest.",
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
        session = await self._get_session(ctx, house="commons", session_id=session_id)
        if session is None:
            if getattr(ctx, "session_prompt_cancelled", False):
                return
            return await ctx.send(
                f"{config.NO} There hasn't been a Commons session yet.",
                ephemeral=True,
            )
        if session.status is models.SessionStatus.CLOSED:
            entries = [":warning: This session is already closed."]
        else:
            entries = []
        if sponsor_filter:
            converted = await models.SessionSponsorFilter().convert(ctx, sponsor_filter)
            if converted is None:
                return await ctx.send(
                    f"{config.NO} `{sponsor_filter}` is not a valid sponsor filter.",
                    ephemeral=True,
                )
            sponsor_filter = converted
        else:
            sponsor_filter = None
        entries.extend(
            await self._build_session_entries(
                ctx=ctx,
                house="commons",
                session=session,
                sponsor_filter=sponsor_filter,
            )
        )
        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=session.display_name,
        )
        await pages.start(ctx)

    @senate_session.command(name="open", description="Open a Senate submission period.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        session_type="Kind of session to open.",
        notify_legislators="DM legislators about the new session.",
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_session_open(
        self,
        interaction: discord.Interaction,
        session_type: str = models.SessionKind.REGULAR.value,
        notify_legislators: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.open_session(
            ctx,
            house="senate",
            session_kind=_session_kind_from_choice(session_type),
            notify_legislators=notify_legislators,
        )

    @commons_session.command(
        name="open", description="Open a Commons submission period."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        session_type="Kind of session to open.",
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_session_open(
        self,
        interaction: discord.Interaction,
        session_type: str = models.SessionKind.REGULAR.value,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.open_session(
            ctx,
            house="commons",
            session_kind=_session_kind_from_choice(session_type),
            notify_legislators=False,
        )

    @senate_session.command(name="lock", description="Lock Senate submissions.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        session_type="Session type to lock if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_session_lock(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.lock_session(
            ctx, house="senate", session_kind=_session_kind_from_choice(session_type)
        )

    @commons_session.command(name="lock", description="Lock Commons submissions.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        session_type="Session type to lock if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_session_lock(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.lock_session(
            ctx, house="commons", session_kind=_session_kind_from_choice(session_type)
        )

    @senate_session.command(name="unlock", description="Unlock Senate submissions.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        session_type="Session type to unlock if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_session_unlock(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.unlock_session(
            ctx, house="senate", session_kind=_session_kind_from_choice(session_type)
        )

    @commons_session.command(name="unlock", description="Unlock Commons submissions.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        session_type="Session type to unlock if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_session_unlock(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.unlock_session(
            ctx, house="commons", session_kind=_session_kind_from_choice(session_type)
        )

    @senate_session.command(name="vote", description="Start Senate voting period.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        voting_form="Google Forms, Sheets, or Docs voting link.",
        session_type="Session type to start voting for if multiple sessions are open.",
        notify_legislators="DM legislators the voting link.",
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_session_vote(
        self,
        interaction: discord.Interaction,
        voting_form: str,
        session_type: str = None,
        notify_legislators: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.vote_session(
            ctx,
            house="senate",
            voting_form=voting_form,
            session_kind=_session_kind_from_choice(session_type),
            notify_legislators=notify_legislators,
        )

    @commons_session.command(name="vote", description="Start Commons voting period.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        voting_form="Google Forms, Sheets, or Docs voting link.",
        session_type="Session type to start voting for if multiple sessions are open.",
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_session_vote(
        self,
        interaction: discord.Interaction,
        voting_form: str,
        session_type: str = None,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.vote_session(
            ctx,
            house="commons",
            voting_form=voting_form,
            session_kind=_session_kind_from_choice(session_type),
            notify_legislators=False,
        )

    @senate_session.command(
        name="close", description="Close the active Senate session."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    @app_commands.describe(
        session_type="Session type to close if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_session_close(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate session")
        await ctx.defer()
        await self.close_session(
            ctx, house="senate", session_kind=_session_kind_from_choice(session_type)
        )

    @commons_session.command(
        name="close", description="Close the active Commons session."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        session_type="Session type to close if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_session_close(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="commons session"
        )
        await ctx.defer()
        await self.close_session(
            ctx, house="commons", session_kind=_session_kind_from_choice(session_type)
        )

    @senate_export.command(
        name="spreadsheet", description="Export a Senate session for Google Sheets."
    )
    @app_commands.describe(
        session_id="Senate session number. Uses open session, prompts if needed, otherwise latest."
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
        session_id="Commons session number. Uses open session, prompts if needed, otherwise latest."
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
    @app_commands.describe(
        session_type="Session type to post if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def senate_export_reddit(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="senate export")
        await ctx.defer()
        await self.export_reddit(
            ctx, house="senate", session_kind=_session_kind_from_choice(session_type)
        )

    @commons_export.command(
        name="reddit", description="Post the active Commons docket to Reddit."
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER
    )
    @app_commands.describe(
        session_type="Session type to post if multiple sessions are open."
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def commons_export_reddit(
        self, interaction: discord.Interaction, session_type: str = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="commons export")
        await ctx.defer()
        await self.export_reddit(
            ctx, house="commons", session_kind=_session_kind_from_choice(session_type)
        )


async def setup(bot):
    await bot.add_cog(LegislatureSlash(bot))
