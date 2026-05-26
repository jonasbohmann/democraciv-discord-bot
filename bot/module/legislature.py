import asyncio
import collections
import datetime
import difflib
import logging
import traceback
import asyncpg
import discord
import typing
import re

from discord.ext import commands
from discord.ext.commands import Greedy
from discord.utils import escape_markdown

from bot.config import config, mk
from bot.utils import (
    models,
    text,
    paginator,
    context,
    mixin,
    checks,
    converter,
    exceptions,
)
from bot.utils.models import (
    Bill,
    Session,
    Motion,
    SessionStatus,
    SenateSessionConverter,
)
from bot.utils.converter import Fuzzy, FuzzySettings


class SubmitChooserView(text.PromptView):

    def __init__(self, *args, **kwargs):
        self.bill_modal: SubmitBillModal = kwargs.pop("bill_modal")
        self.motion_modal: SubmitMotionModal = kwargs.pop("motion_modal")
        self.can_submit_bill: bool = kwargs.pop("can_submit_bill", True)
        self.can_submit_motion: bool = kwargs.pop("can_submit_motion", True)
        super().__init__(*args, **kwargs)
        for item in self.children:
            if getattr(item, "label", None) == "Submit a Bill":
                item.disabled = not self.can_submit_bill
            elif getattr(item, "label", None) == "Submit a Motion":
                item.disabled = not self.can_submit_motion

    @discord.ui.button(label="Submit a Bill", style=discord.ButtonStyle.primary)
    async def bill(self, interaction: discord.Interaction, button):
        self.result = "bill"
        await interaction.response.send_modal(self.bill_modal)
        await self.bill_modal.wait()
        self.stop()

    @discord.ui.button(label="Submit a Motion", style=discord.ButtonStyle.grey)
    async def motion(self, interaction, button):
        self.result = "motion"
        await interaction.response.send_modal(self.motion_modal)
        await self.motion_modal.wait()
        self.stop()


class SubmitBillOnlyView(text.PromptView):
    def __init__(self, *args, **kwargs):
        self.bill_modal: SubmitBillModal = kwargs.pop("bill_modal")
        super().__init__(*args, **kwargs)

    @discord.ui.button(label="Submit a Bill", style=discord.ButtonStyle.primary)
    async def bill(self, interaction: discord.Interaction, button):
        self.result = "bill"
        await interaction.response.send_modal(self.bill_modal)
        await self.bill_modal.wait()
        self.stop()


class ModelChooseView(text.PromptView):
    @discord.ui.button(label="Bills", style=discord.ButtonStyle.grey)
    async def bill(self, interaction, button):
        await interaction.response.defer()
        self.result = "bill"
        self.stop()

    @discord.ui.button(label="Motions", style=discord.ButtonStyle.grey)
    async def motion(self, interaction, button):
        await interaction.response.defer()
        self.result = "motion"
        self.stop()


class SuperPassScheduler(text.RedditAnnouncementScheduler):
    def get_reddit_post_title(self) -> str:
        return f"New Bills passed into law with a super-majority by the Senate - {discord.utils.utcnow().strftime('%d %B %Y')}"

    def get_reddit_post_content(self) -> str:
        content = [
            f"The following bills were passed into law with a super-majority by the Senate."
            f"\n\n###Relevant Links\n\n"
            f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
            f"* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `{config.BOT_PREFIX}laws` in #bot on our "
            f"[Discord Server](https://discord.gg/tVmHVcZPVs)\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n---\n  &nbsp; \n\n"
        ]

        for bill in self._objects:
            submitter = bill.submitter or context.MockUser()
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{bill.description}\n\n &nbsp;"
            )

        outro = f"""\n\n &nbsp; \n\n---\n\nAll these bills are now laws.
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
                and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)

    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Supermajority Pass",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )

        message = [
            f"The following bills were **passed into law** with a supermajority by the Senate.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description}\n"
            )

        embed.description = "\n".join(message)
        return embed


class PassScheduler(text.RedditAnnouncementScheduler):
    def _destination_text(self, obj: Bill) -> str:
        if isinstance(obj.status, models.BillPassedSenatePendingCommons):
            return "Next stop: Commons"
        if isinstance(obj.status, models.BillAwaitingExecutive):
            return f"Next stop: {self.bot.mk.MINISTRY_NAME}"
        if isinstance(obj.status, models.BillPassedLegislature):
            return f"Next stop: {self.bot.mk.MINISTRY_NAME}"
        if obj.status.is_law:
            return "This bill is now law"
        return "Next step recorded by the bot"

    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Bills passed by the {self.bot.mk.LEGISLATURE_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        message = [
            f"The following bills were **passed** by the {self.bot.mk.LEGISLATURE_NAME}.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description} — {self._destination_text(obj)}\n"
            )

        embed.description = "\n".join(message)
        return embed

    def get_reddit_post_title(self) -> str:
        return f"New Bills passed by the {self.bot.mk.LEGISLATURE_NAME} - {discord.utils.utcnow().strftime('%d %B %Y')}"

    def get_reddit_post_content(self) -> str:
        content = [
            f"The following bills were passed by the {self.bot.mk.LEGISLATURE_NAME}."
            f"\n\n###Relevant Links\n\n"
            f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
            f"* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `{config.BOT_PREFIX}laws` in #bot on our "
            f"[Discord Server](https://discord.gg/tVmHVcZPVs)\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n---\n  &nbsp; \n\n"
        ]

        for bill in self._objects:
            submitter = bill.submitter or context.MockUser()
            content.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{bill.description}\n\n*{self._destination_text(bill)}*\n\n &nbsp;"
            )

        outro = f"""\n\n &nbsp; \n\n---\n\nThe bot recorded the next legislative destination for each bill above.
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
                and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)


class OverrideScheduler(text.AnnouncementScheduler):
    def get_embed(self):
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Veto overridden by the {self.bot.mk.LEGISLATURE_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )

        message = [
            f"The {self.bot.mk.MINISTRY_NAME}'s **veto of the following bills was overridden** "
            f"by the {self.bot.mk.LEGISLATURE_NAME}.\n"
        ]

        for obj in self._objects:
            submitter = obj.submitter or context.MockUser()

            message.append(
                f"__Bill #{obj.id} - **[{obj.name}]({obj.link})**__"
                f"\n*Submitted by {submitter.mention}*\n{obj.description}\n"
            )

        message.append(
            f"\nAll of the above bills are now law and can be found in `{config.BOT_PREFIX}laws`, "
            f"as well with `{config.BOT_PREFIX}laws search`."
        )
        embed.description = "\n".join(message)
        return embed


class SubmitBillModal(discord.ui.Modal, title=f"Submit a Bill to the Senate"):

    def __init__(self, sessions: typing.Sequence[Session]):
        super().__init__()
        mixin.add_submit_session_choice(self, sessions)

    google_docs_url = discord.ui.Label(
        text="Link to Google Docs",
        description="Bills are submitted as Google Docs documents. Make sure to copy the public link.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=512,
            placeholder="https://docs.google.com/document/d/...",
        ),
    )

    bill_description = discord.ui.Label(
        text="Summary",
        description="What does your bill do? Write a short summary.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=500,
        ),
    )

    is_procedure = discord.ui.Label(
        text="Bill or Senate-only Procedure",
        description=(
            "Are you submitting a bill, or procedure that only pertains to the Senate?"
        ),
        component=discord.ui.Select(
            options=[
                discord.SelectOption(
                    emoji="\U0001f4dd",
                    label=f"Bill. The Commons & Executive will be able vote on this too.",
                    value="false",
                    default=True,
                ),
                discord.SelectOption(
                    emoji="\U0001f512",
                    label="Procedure. Only the Senate will be able to vote on this.",
                    value="true",
                ),
            ],
        ),
    )

    """ is_vetoable = discord.ui.Label(
        text="Veto",
        description=f"Is the {mk.MarkConfig.MINISTRY_NAME} legally allowed to vote on and veto this bill?",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(
                    emoji="\U00002705",
                    label=f"Yes, the {mk.MarkConfig.MINISTRY_NAME} should be able vote on this bill",
                    value="true",
                    default=True,
                ),
                discord.SelectOption(emoji="\U0000274c", label="No", value="false"),
            ],
        ),
    ) """

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.stop()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            f"{config.NO} Something went wrong.", ephemeral=True
        )
        traceback.print_exception(type(error), error, error.__traceback__)


class SubmitMotionModal(discord.ui.Modal, title=f"Submit a Motion to the Senate"):

    def __init__(self, sessions: typing.Sequence[Session]):
        super().__init__()
        mixin.add_submit_session_choice(self, sessions)

    intro = discord.ui.TextDisplay(
        content=f"Motions lack a lot of features that bills have, "
        f"for example they cannot be passed into Law by the Government. They will not "
        f"show up in `{config.BOT_PREFIX}laws`, nor will they make it on the Legal Code.\n\nIf you want to submit "
        f"something small that results in some __temporary__ action and where it's not important to track if it passed, "
        f"use a motion, otherwise use a bill.\n\n"
        f"Common examples for motions: `Motion to repeal Law #12`, or `Motion to recall person XY`."
    )

    motion_title = discord.ui.Label(
        text="Title",
        description="What's the title of your motion?",
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            max_length=200,
        ),
    )

    motion_description = discord.ui.Label(
        text="Content",
        description="Write your motion here. If your motion is inside a Google Docs document, just paste the link here.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.long,
        ),
    )

    understand_description = discord.ui.Label(
        description="I understand that motions are intended for short-term, temporary actions.",
        text="Motions won't show up in -laws",
        component=discord.ui.Checkbox(),
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.stop()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            f"{config.NO} Something went wrong.", ephemeral=True
        )
        traceback.print_exception(type(error), error, error.__traceback__)


LEG_COMMAND_ALIASES = ["s", "sen", "senate"]

try:
    LEG_COMMAND_ALIASES.remove(mk.MarkConfig.LEGISLATURE_COMMAND.lower())
except ValueError:
    pass


# Allows the Government to organize legislative sessions and bill & motion submissions
class Legislature(context.CustomCog, mixin.GovernmentMixin, name="Senate"):
    """The Senate of the Celtic Nation."""

    def __init__(self, bot):
        super().__init__(bot)
        self.email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
        self.pass_scheduler = PassScheduler(
            bot,
            mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
            subreddit=config.DEMOCRACIV_SUBREDDIT,
        )
        self.override_scheduler = OverrideScheduler(
            bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL
        )
        self.superpass_scheduler = SuperPassScheduler(
            bot,
            mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
            subreddit=config.DEMOCRACIV_SUBREDDIT,
        )

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            logging.warning("motion commands still visible")
            # todo oct-24
            # self.bot.get_command(self.bot.mk.LEGISLATURE_COMMAND).remove_command(
            #     "motion"
            # )
            # self.bot.get_command(
            #     f"{self.bot.mk.LEGISLATURE_COMMAND} withdraw"
            # ).remove_command("motion")

    def is_cabinet(self, member: discord.Member) -> bool:
        return self.senator_presiding_role in member.roles

    async def _redirect_to_root_command(
        self, ctx: context.CustomContext, command_name: str, rest: str = ""
    ):
        ctx.message.content = (
            f"{ctx.prefix}{command_name}"
            if not rest
            else f"{ctx.prefix}{command_name} {rest}"
        )
        new_ctx = await self.bot.get_context(ctx.message)
        return await self.bot.invoke(new_ctx)

    @commands.command(name="session", aliases=["sessions", "ses"], hidden=True)
    async def _session(self, ctx: context.CustomContext):
        """This only exists to serve as an alias to `{PREFIX}{LEGISLATURE_COMMAND} session`

        Use `{PREFIX}help {LEGISLATURE_COMMAND} session` for the help page of the actual command.
        """
        ctx.message.content = ctx.message.content.replace(
            f"{ctx.prefix}{ctx.invoked_with}",
            f"{ctx.prefix}{self.bot.mk.LEGISLATURE_COMMAND.lower()} "
            f"{ctx.invoked_with}",
        )
        new_ctx = await self.bot.get_context(ctx.message)
        return await self.bot.invoke(new_ctx)

    @commands.group(
        name=mk.MarkConfig.LEGISLATURE_COMMAND.lower(),
        aliases=LEG_COMMAND_ALIASES,
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def legislature(self, ctx):
        """Dashboard for {LEGISLATURE_LEGISLATOR_NAME_PLURAL} with important links and the status of the current session"""
        embed = await self._build_legislature_overview_embed("senate")
        await ctx.send(embed=embed)

    @legislature.command(name="search")
    async def search(self, ctx: context.CustomContext, *, query: str):
        """Search for both bills & motions at once

        If you want to limit your search to either just bills or just motions, consider
        the `{PREFIX}bill search` and `{PREFIX}motion search` commands.
        """

        matches = await self._search_model(
            ctx, model=models.Bill, query=query, return_model=True
        )
        matches.extend(
            await self._search_model(
                ctx, model=models.Motion, query=query, return_model=True
            )
        )

        matches.sort(
            key=lambda elm: difflib.SequenceMatcher(None, elm.name, query).ratio(),
            reverse=True,
        )
        matches = list(map(lambda elm: f"* {elm.formatted}", matches))

        if matches:
            matches.insert(
                0,
                f"This searches for both bills and motions. You can search for just bills with "
                f"`{config.BOT_PREFIX}bill search`, and for just motions with "
                f"`{config.BOT_PREFIX}motion search`.\n",
            )

        pages = paginator.SimplePages(
            entries=matches,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Bills & Motions matching '{query}'",
            empty_message="Nothing found.",
        )

        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com>) as well!"
        )
        await pages.start(ctx)
        fts_pages = None

        try:
            fts_pages = await self.prepare_full_text_search_paginator(ctx, query)
        except Exception:
            pass

        if fts_pages:
            view = mixin.FullTextSearchView(ctx)
            delete_after = await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to perform a full-text search across all bills too? This feature is a work-in-progress.\n{config.HINT} Known issue: This only shows 1 search result per bill, even if there were more occurrences found.",
                view=view,
            )
            yes = await view.prompt(silent=True)

            if yes:
                await fts_pages.start(ctx)
                await delete_after.delete()

    @legislature.command(name="from", aliases=["f", "by"])
    async def _from(
        self,
        ctx: context.CustomContext,
        *,
        person_or_party: Fuzzy[
            converter.CaseInsensitiveMember,
            converter.CaseInsensitiveUser,
            converter.PoliticalParty,
            FuzzySettings(weights=(5, 0, 2)),
        ] = None,
    ):
        """List all bills and motions that a specific person or Political Party submitted"""
        member_or_party = person_or_party or ctx.author

        bills = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=Bill, paginate=False
        )
        motions = await self._from_person_model(
            ctx, member_or_party=member_or_party, model=Motion, paginate=False
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

        if things:
            things.insert(
                0,
                f"This lists both bills and motions. You can limit this to just bills by using "
                f"`{config.BOT_PREFIX}bill from`, and to just motions by using "
                f"`{config.BOT_PREFIX}motion from`.\n",
            )

        pages = paginator.SimplePages(
            entries=things, author=title, icon=icon, empty_message=empty
        )
        await pages.start(ctx)

    @legislature.command(name="bill", aliases=["b", "bills"], hidden=True)
    async def bill_redirect(self, ctx: context.CustomContext, *, rest: str = ""):
        return await self._redirect_to_root_command(ctx, "bill", rest)

    @legislature.command(name="motion", aliases=["m", "motions", "mo"], hidden=True)
    async def motion_redirect(self, ctx: context.CustomContext, *, rest: str = ""):
        return await self._redirect_to_root_command(ctx, "motion", rest)

    def _mk12_bill_from_citizen_has_enough_sponsors(self, bill: Bill) -> bool:
        if not bill.submitter:
            return False

        # only care about fresh bills
        if bill.status.flag is not models._BillStatusFlag.SUBMITTED:
            return True

        if self.legislator_role in bill.submitter.roles:
            return True

        # this assumes only Senators can sponsor
        if bill.sponsors:
            return True

        return False

    @legislature.group(
        name="session",
        aliases=["s", "ses"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def session(
        self,
        ctx: context.CustomContext,
        session: typing.Optional[SenateSessionConverter] = None,
        *,
        sponsor_filter: models.SessionSponsorFilter = None,
    ):
        """Get details about a session from the {LEGISLATURE_NAME}

        You can filter the list of bills & motions by their amount of sponsors. Support notation: `<`, `<=`, `=`, `==`, `!=`, `!`, `>`, `>=` followed by a number.

        **Example**
        `{PREFIX}{COMMAND}` to see details about the most recent session
        `{PREFIX}{COMMAND} 9` to see details about Session #9

        **Example with sponsor filter**
        `{PREFIX}{COMMAND} >1` to see details about the most recent session, but only show bills & motions that have more than 1 sponsor
        `{PREFIX}{COMMAND} >=2` to see details about the most recent session, but only show bills & motions that have more than or exactly 2 sponsors
        `{PREFIX}{COMMAND} =5` to see details about the most recent session, but only show bills & motions that have exactly 5 sponsors

        `{PREFIX}{COMMAND} 9 =1` to see details about Session #9, but only show bills & motions that have exactly 1 sponsor
        `{PREFIX}{COMMAND} 21 >=1` to see details about Session #21, but only show bills & motions that have more than or exactly 1 sponsor

        """

        if session is None:
            open_sessions = await self.get_open_leg_sessions(house="senate")
            if len(open_sessions) == 1:
                session = open_sessions[0]
            elif len(open_sessions) > 1:
                session = await self.prompt_for_leg_session(
                    ctx, sessions=open_sessions, action="view"
                )
                if session is None:
                    return
            else:
                session = await self.get_last_leg_session(house="senate")

        if session is None:
            return await ctx.send(
                f"{config.NO} There hasn't been a session yet.\n{config.HINT} The "
                f"{self.bot.mk.senator_presiding_term} can open one at any time with "
                f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session open`."
            )

        entries = await self._build_session_entries(
            ctx=ctx, house="senate", session=session, sponsor_filter=sponsor_filter
        )

        if session.status is SessionStatus.CLOSED:
            await ctx.send(f":warning: This session is already closed.")

        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=session.display_name,
        )
        await pages.start(ctx)

    @session.command(name="open", aliases=["o"])
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def opensession(self, ctx):
        """Opens a session for the submission period to begin"""

        session_kind = await self.prompt_for_session_kind(
            ctx, house="senate", action="open"
        )
        if session_kind is None:
            return

        active_leg_session = await self.get_active_leg_session(
            house="senate", session_kind=session_kind
        )
        if active_leg_session is not None:
            return await ctx.send(
                f"{config.NO} There is still an open {active_leg_session.display_name}, close it "
                f"first with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session close`."
            )

        new_session = await self.bot.db.fetchrow(
            "INSERT INTO legislature_session (speaker, opened_on, house, mk13_house_id, session_kind) VALUES ($1, $2, $3, nextval('mk13_senate_session_seq'), $4) RETURNING id, mk13_house_id",
            ctx.author.id,
            datetime.datetime.utcnow(),
            "senate",
            session_kind.value,
        )
        new_session_obj = await Session.convert(ctx, new_session["id"])
        queued_bill_count = await self.attach_pending_bills_to_session(
            house="senate", session_id=new_session["id"]
        )
        new_session_name = new_session_obj.display_name

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND
        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Legislative Sessions",
            description=f"Once you feel like enough time has passed for people to "
            f"submit their bills and motions, you can lock submissions by doing either "
            f"one of these options:\n\n1. If you want to stop submissions coming in, but aren't ready "
            f"yet to start voting, you can **lock the session** with `{p}{l} session lock`. You "
            f"can allow submissions to be submitted again by unlocking the session with "
            f"`{p}{l} session unlock`.\n\n2.  "
            f"*(Optional)* Set the session into *Voting Period* with "
            f"`{p}{l} session vote`. The only advantage of setting a session into Voting "
            f"Period before directly closing it, is that I will DM every legislator "
            f"a reminder to vote and the link to the voting form, and the voting form "
            f"will be displayed in `{p}{l} session`. After enough time has passed for "
            f"everyone to vote, you would close the session as described in the "
            f"next step.\n\n"
            f"3. Close the session entirely with "
            f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session close`.",
        )

        info.add_field(
            name="Optional: Voting Form",
            value="If you want to use Google Forms to vote, "
            "I can generate that Google Form for you and fill "
            f"it with all the bills and motions that were submitted. "
            f"Take a look at `{p}{l} session export form`. You can use my generated Google Form "
            f"for the `{p}{l} session vote` command.",
            inline=False,
        )

        info.add_field(
            name="Bill & Motion Submissions",
            value=f"As {self.bot.mk.senator_presiding_term}, you can remove any bill or "
            f"motion from this session with `{p}{l} withdraw`. Everyone else can use that command "
            f"too, but they're only allowed to withdraw the bills/motions that they "
            f"themselves also submitted.",
            inline=False,
        )

        info.add_field(
            name="Failed Bills from previous Sessions",
            value="Are there any bills from last session that "
            f"failed, that you want to give a second chance in this session? Don't bother "
            f"doing `{p}{l} submit` all over again, instead use `{p}bill resubmit <bill_ids>` to "
            f"move any old, failed bills back into the current submission-period session in their "
            f"origin house.",
            inline=False,
        )

        should_dm_legislators = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Do you want me to DM all "
            f"{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} to notify them "
            f"about a new session "
            f"being opened?"
        )

        await ctx.send(
            f"{config.YES} The **submission period** for {new_session_name} was opened, and bills & "
            f"motions can now be submitted."
        )
        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))
        if queued_bill_count:
            await ctx.send(
                f"{config.HINT} I also attached {queued_bill_count} bill{'s' if queued_bill_count != 1 else ''} from the Commons "
                f"that were waiting on the Senate to this new session."
            )

        announcement = text.SafeEmbed()
        announcement.description = (
            f"The cabinet has opened the Submission Period for {new_session_name}."
        )
        announcement.set_author(
            name=f"Submission Period open for {new_session_name}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )
        announcement.add_field(
            name="Submissions",
            value="Bills and motions can be "
            f"submitted with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit`.\nYou can see all submissions with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session`.",
            inline=False,
        )
        announcement.add_field(
            name="Sponsors",
            value="Bills and motions can be "
            f"sponsored with `{config.BOT_PREFIX}bill sponsor` and `{config.BOT_PREFIX}motion sponsor`.\n\nThe list of submissions can be filtered by the amount of sponsors they have. For example, `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session >=1` will only show bills & motions with 1 or more sponsors.",
            inline=False,
        )

        await self.gov_announcements_channel.send(embed=announcement)

        if should_dm_legislators:
            await self.dm_legislators(
                reason="leg_session_open",
                message=f":envelope_with_arrow: The **submission period** for {new_session_name} "
                f"has started! Submit your bills and motions with "
                f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit` "
                f"on the {self.bot.dciv.name} server.",
            )

    @session.command(name="lock")
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def locksession(self, ctx):
        """Lock (deny) submissions for the currently active session"""

        active_leg_session = await self.resolve_active_leg_session_for_text_command(
            ctx, house="senate", action="lock"
        )
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(
                f"{config.NO} You can only lock sessions that are in Submission Period."
            )

        await self.bot.db.execute(
            "UPDATE legislature_session SET status = $1 WHERE id = $2",
            SessionStatus.LOCKED.value,
            active_leg_session.id,
        )

        await self.gov_announcements_channel.send(
            f"The {self.bot.mk.senator_presiding_term} has locked submissions for "
            f"{active_leg_session.display_name}. Nothing can be submitted until the {self.bot.mk.senator_presiding_term} decides "
            f"to unlock the session again."
        )

        await ctx.send(
            f"{config.YES} Submissions for "
            f"{active_leg_session.display_name} have been locked.\n{config.HINT} Want to allow "
            f"submissions again? Unlock the session with `{p}{l} session unlock`.\n"
            f"{config.HINT} In case you intend to leave submissions locked until voting starts "
            f"in order to use this time as a **debate period**, you can make me post the current list "
            f"of submission to **r/{config.DEMOCRACIV_SUBREDDIT}** with `{p}{l} session export reddit`. "
            f"That reddit post may help with more focused debates & feedback on bills & motions."
        )

    @session.command(name="unlock")
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def unlocksession(self, ctx):
        """Unlock (allow) submissions for the currently active session again"""

        active_leg_session = await self.resolve_active_leg_session_for_text_command(
            ctx, house="senate", action="unlock"
        )
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is not SessionStatus.LOCKED:
            return await ctx.send(
                f"{config.NO} You can only unlock sessions that are already locked."
            )

        await self.bot.db.execute(
            "UPDATE legislature_session SET status = $1 WHERE id = $2",
            SessionStatus.SUBMISSION_PERIOD.value,
            active_leg_session.id,
        )

        await self.gov_announcements_channel.send(
            f"The {self.bot.mk.senator_presiding_term} has unlocked submissions for "
            f"{active_leg_session.display_name}, meaning you can now submit bills & motions with "
            f"`{p}{l} submit` again."
        )

        await ctx.send(
            f"{config.YES} Submissions for "
            f"{active_leg_session.display_name} have been unlocked."
        )

    @session.command(name="vote", aliases=["u", "v", "update"])
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def updatesession(self, ctx: context.CustomContext):
        """Changes the current session's status to be open for voting"""

        active_leg_session = await self.resolve_active_leg_session_for_text_command(
            ctx, house="senate", action="start voting for"
        )
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is SessionStatus.VOTING_PERIOD:
            return await ctx.send(
                f"{config.NO} This session is already in the Voting Period."
            )

        voting_form = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the link to this session's Google Forms voting "
            f"form or to the Google Sheets voting spreadsheet.\n{config.HINT} Reply with gibberish if you want me to generate that form for you."
        )

        if not self.is_google_doc_link(voting_form):
            return await ctx.send(
                f"{config.HINT} Use the "
                f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session export form` "
                f"command to make me generate the form for you, then use this command "
                f"again once you're all set."
            )

        should_dm_legislators = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Do you want me to DM the link "
            f"to the Voting Form/Spreadsheet to all "
            f"{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL}?"
        )

        await active_leg_session.start_voting(voting_form)

        await ctx.send(
            f"{config.YES} {active_leg_session.display_name} is now in **voting period**.\n{config.HINT} You can make "
            f"me post the list of bill & motion submissions to **r/{config.DEMOCRACIV_SUBREDDIT}** with "
            f"`{p}{l} session export reddit`.\n{config.HINT} Once you feel "
            f"like enough time has passed for people to vote, close this session with `{p}{l} session close`. "
            f"I'll go over what happens after that once you close the session."
        )

        announcement = text.SafeEmbed()
        announcement.description = f"{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} can vote here:\n{voting_form}"
        announcement.set_author(
            name=f"Voting has started for {active_leg_session.display_name}",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )

        await self.gov_announcements_channel.send(embed=announcement)

        if should_dm_legislators:
            await self.dm_legislators(
                reason="leg_session_update",
                message=f":ballot_box: The **voting period** for "
                f"{active_leg_session.display_name} has started!\nVote here: {voting_form}",
            )

    @session.command(name="close", aliases=["c"])
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session = await self.resolve_active_leg_session_for_text_command(
            ctx, house="senate", action="close"
        )

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new "
                f"session with `{p}{l} session open` at any time."
            )

        await active_leg_session.close()

        consumer = models.LegalConsumer(
            ctx=ctx,
            objects=[await Bill.convert(ctx, b) for b in active_leg_session.bills],
            action=models.BillStatus.fail_in_legislature,
        )

        await consumer.filter(acting_house="senate")
        await consumer.consume(acting_house="senate")

        for bill_id in active_leg_session.bills:
            try:
                bill = await Bill.convert(ctx, bill_id)
                self.bot.loop.create_task(self._synchronize_bill(bill))
            except Exception:
                pass

        #  Update all bills that did not pass
        # await self.bot.db.execute(
        #    "UPDATE bill SET status = $1 WHERE leg_session = $2",
        #    models.BillFailedLegislature.flag.value,
        #    active_leg_session.id,
        # )

        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Legislative Sessions",
            description=f"Now, tally the results and tell me which bills passed with "
            f"`{p}{l} pass <bill_ids>`.\n\nYou do not have to tell me which bills "
            f"failed in the vote, I will "
            f"automatically set every bill from this session that you do not "
            f"explicitly pass with `{p}{l} pass <bill_ids>` as failed.",
        )

        info.add_field(
            name="What happens after a pass?",
            value="Bills passed by the Senate move to the Commons. If the Commons also pass them, "
            f"they are sent to the {self.bot.mk.MINISTRY_NAME} for approval or veto.\n\n"
            f"Senate procedures skip the Commons and the {self.bot.mk.MINISTRY_NAME} and become law "
            f"once the Senate passes them.",
            inline=False,
        )

        info.add_field(
            name="Why can't I pass motions?",
            value="Motions are intended for short-term, temporary actions that do not "
            f"require to be kept as record in `{p}laws`. As such, they lack some features that bills "
            f"have, "
            "such as passing them into law.\n\nAn example for a use case for motions could be a "
            "'Motion to recall Person XY' motion, because if that motion to recall passes, "
            "why would we need to keep that motion as a record on our Legal Code, it's a "
            "one-and-done thing.",
            inline=False,
        )

        info.add_field(
            name="Updating the Legal Code",
            value=f"As {self.bot.mk.senator_presiding_term}, one of your obligations is "
            f"probably to make sure our Legal Code is up-to-date. "
            f"While my `{p}laws` command is an always up-to-date legal code, some people might "
            f"prefer one as an old-fashioned document.\n\nYou can use my `{p}laws export` command to "
            f"make me generate that for you! Just give me the link to a Google Docs document "
            f"and I will make that an up-to-date Legal Code.",
            inline=False,
        )

        info.add_field(
            name="Keep it rolling",
            value=f"Now that you've closed the last session, you can keep your "
            f"{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} busy by opening the next session "
            f"with `{p}{l} session open` right away. It doesn't matter how long the "
            f"Submission Period is, and it doesn't hurt anyone that they can submit bills "
            f"around the clock.\n\nJust sit back, let submissions come in and once you're ready to "
            f"'start' the session 'for real', tell your {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} that "
            f"submissions will be locked soon, and schedule a few debates. Now that everyone already "
            f"had days to write and submit their bills, more time is left for debate, discussion and "
            f"collective brainstorming once the session really 'starts'.",
        )

        await ctx.send(f"{config.YES} {active_leg_session.display_name} was closed.")

        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))

        announcement = text.SafeEmbed()
        announcement.set_author(
            name=f"{active_leg_session.display_name} has been closed",
            icon_url=self.bot.mk.NATION_ICON_URL or self.bot.dciv.icon.url or None,
        )

        await self.gov_announcements_channel.send(embed=announcement)

    @session.group(
        name="export",
        aliases=["es", "ex", "e"],
        hidden=True,
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def export(self, ctx: context.CustomContext):
        """Automate the most time consuming Senator Presiding responsibilities with these commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send(
                f"{config.NO} You have to tell me how you would like this session to be exported."
            )
            await ctx.send_help(ctx.command)

    @export.command(name="spreadsheet", aliases=["sheet", "sheets", "s"])
    async def export_spreadsheet(self, ctx, session: SenateSessionConverter = None):
        """Export a session's submissions into copy & paste-able formatting for Google Spreadsheets"""

        if session is None:
            open_sessions = await self.get_open_leg_sessions(house="senate")
            if len(open_sessions) == 1:
                session = open_sessions[0]
            elif len(open_sessions) > 1:
                session = await self.prompt_for_leg_session(
                    ctx, sessions=open_sessions, action="export"
                )
                if session is None:
                    return
            else:
                session = await self.get_last_leg_session(house="senate")

        if session is None:
            return await ctx.send(f"{config.NO} There hasn't been a session yet.")

        async with ctx.typing():
            bills = [await Bill.convert(ctx, bill_id) for bill_id in session.bills]
            motions = [
                await Motion.convert(ctx, motion_id) for motion_id in session.motions
            ]

            b_ids = [
                f"Bill #{bill.id} ({len(bill.sponsors)} sponsors)" for bill in bills
            ]
            b_hyperlinks = [
                f'=HYPERLINK("{bill.link}"; "{bill.name}")' for bill in bills
            ]
            m_ids = [f"Motion #{motion.id}" for motion in motions]
            m_hyperlinks = [
                f'=HYPERLINK("{motion.link}"; "{motion.name}")' for motion in motions
            ]

            exported = [
                f"Export of {session.display_name} -- {discord.utils.utcnow().strftime('%c')}\n\n\n",
                f"Xth Session - {session.opened_on.strftime('%B %d %Y')} (Bot Session {session.mk13_house_id})\n\n"
                "----- Submitted Bills -----\n",
            ]

            exported.extend(b_ids)
            exported.append("\n")
            exported.extend(b_hyperlinks)
            exported.append("\n\n----- Submitted Motions -----\n")
            exported.extend(m_ids)
            exported.append("\n")
            exported.extend(m_hyperlinks)

            spreadsheet_formatting_link = await self.bot.make_paste("\n".join(exported))

        await ctx.send(
            f"__**Spreadsheet Export of {session.display_name}**__\n"
            f"This session's bills and motions were exported into a format that "
            f"you can easily copy & paste into Google Spreadsheets, for example for a "
            f"Legislative Docket: **<{spreadsheet_formatting_link}>**\n\nSee the video below to see how to "
            f"speed up your {self.bot.mk.senator_presiding_term} duties with this.\n"
            f"https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4"
        )

    @export.command(name="form", aliases=["forms", "voting", "f"])
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def export_form(self, ctx, session: SenateSessionConverter = None):
        """Generate the Google Forms voting form with all the submitted bills & motions for a session"""

        return await ctx.send(
            f"{config.NO} This command has been disabled due to security concerns. Sorry! Please DM @ Jonas for further information."
        )

        session = session or await self.get_last_leg_session(house="senate")

        if session is None:
            return await ctx.send(f"{config.NO} There hasn't been a session yet.")

        form_url = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with an **edit** link to an **empty** Google Forms "
            f"form you created. I will then fill that form to make it the voting form.\n{config.HINT} "
            "*Create a new Google Form here: <https://forms.new>, then click on the three dots in the upper right, "
            "then on 'Add collaborators', after which a new window should pop up. "
            "Click on 'Change' on the bottom left, and change the link from 'Restricted' to the other option. "
            "Then copy the link from your browser's address bar (do not click on 'Copy link' button on the pop-up!) and send it here.*",
            delete_after=True,
            timeout=400,
        )

        if not form_url:
            ctx.command.reset_cooldown(ctx)
            return

        if not self.is_google_doc_link(form_url):
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} That doesn't look like a Google Forms URL. This process was cancelled."
            )

        bill_min_sponsors = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the minimum amount of "
            f"sponsors a **bill** needs to have to be included on the "
            f"Voting Form.\n{config.HINT} If you "
            f"reply with `0`, every bill will be included, "
            f"regardless the amount of sponsors it has."
        )

        try:
            bill_min_sponsors = int(bill_min_sponsors)
        except ValueError:
            return await ctx.send(f"{config.NO} You didn't reply with a number.")

        motion_min_sponsors = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the minimum amount of "
            f"sponsors a **motion** needs to have to be included on the "
            f"Voting Form.\n{config.HINT} If you "
            f"reply with `0`, every motion will be included, "
            f"regardless the amount of sponsors it has."
        )

        try:
            motion_min_sponsors = int(motion_min_sponsors)
        except ValueError:
            return await ctx.send(f"{config.NO} You didn't reply with a number.")

        generating = await ctx.send(
            f"{config.YES} I will generate the voting form for Senate "
            f"Session #{session.mk13_house_id}. \n:arrows_counterclockwise: This may take a few minutes..."
        )

        def safe_get_submitter(thing) -> str:
            return (
                thing.submitter.display_name if thing.submitter else "*Unknown Person*"
            )

        async with ctx.typing():
            bills = [await Bill.convert(ctx, bill_id) for bill_id in session.bills]
            motions = [
                await Motion.convert(ctx, motion_id) for motion_id in session.motions
            ]

            bills = list(filter(lambda b: len(b.sponsors) >= bill_min_sponsors, bills))
            motions = list(
                filter(lambda m: len(m.sponsors) >= motion_min_sponsors, motions)
            )

            bills_info = {
                f"{b.name} (#{b.id})": f"Submitted by {safe_get_submitter(b)} with "
                f"{len(b.sponsors)} sponsor(s)\n"
                f"{b.link}\n\n{b.description}"
                for b in bills
            }

            motions_info = {
                f"{m.name} (#{m.id})": f"Submitted by {safe_get_submitter(m)}\n{m.link}"
                for m in motions
            }

            result = await self.bot.run_apps_script(
                script_id="MME1GytLY6YguX02rrXqPiGqnXKElby-M",
                function="generate_form",
                parameters=[form_url, session.id, bills_info, motions_info],
            )

        embed = text.SafeEmbed(
            title=f"Export of Senate Session #{session.mk13_house_id}",
            description="Make sure to double check the form to make sure it's "
            "correct.\n\nNote that you may have to adjust "
            "the form to comply with this nation's laws as this comes with no guarantees of a form's valid "
            "legal status.\n\n:warning: Remember to change the edit link you "
            f"gave me earlier to be **'Restricted'** again.",
        )

        embed.add_field(
            name="Voting Form",
            value=f"Link: {result['response']['result']['view']}\n\n"
            f"Shortened: {result['response']['result']['short-view']}",
            inline=False,
        )

        await ctx.send(
            f"{config.HINT} You can use this voting form to start the Voting Period of a session with "
            f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session vote`.",
            embed=embed,
        )
        self.bot.loop.create_task(generating.delete())

    @export.command(name="reddit")
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def export_reddit(self, ctx):
        """Make me post an overview of the current session and its submissions to our subreddit"""

        session = await self.resolve_active_leg_session_for_text_command(
            ctx, house="senate", action="post to Reddit"
        )

        if session is None:
            return await ctx.send(
                f"{config.NO} There is no open session in either Submission Period or "
                f"Voting Period right now."
            )

        bills = [await Bill.convert(ctx, i) for i in session.bills]
        motions = [await Motion.convert(ctx, i) for i in session.motions]

        speaker = session.speaker or context.MockUser()
        cntnt = []

        intro = (
            f"{self.bot.mk.senator_presiding_term} {speaker.display_name} ({speaker}) opened the Submission Period for this session on "
            f"{session.opened_on.strftime('%B %d, %Y at %H:%M')} UTC. "
        )

        if session.voting_started_on:
            intro += (
                f"Voting started on {session.voting_started_on.strftime('%B %d, %Y at %H:%M')} UTC "
                f"[here]({session.vote_form}). "
            )

        intro += (
            f"\n\nFeel free to use this thread to debate and propose feedback on bills & motions, "
            f"in case voting has not started yet.\n\n###Relevant Links\n\n* "
            f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
            f"* [laws.democraciv.com](https://laws.democraciv.com)\n"
            f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `-laws` in #bot on our "
            f"[Discord Server](https://discord.gg/tVmHVcZPVs)\n"
            f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n  &nbsp; \n\n"
        )

        cntnt.append(intro)

        if bills:
            cntnt.append("\n\n###Submitted Bills\n---\n &nbsp;")

        for bill in bills:
            submitter = bill.submitter or context.MockUser()
            cntnt.append(
                f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Submitted by "
                f"{submitter.display_name} ({submitter}) with {len(bill.sponsors)} sponsor(s)*"
                f"\n\n{bill.description}\n\n &nbsp;"
            )

        if motions:
            cntnt.append("\n\n###Submitted Motions\n---\n &nbsp;")

        for motion in motions:
            submitter = motion.submitter or context.MockUser()
            cntnt.append(
                f"__**Motion #{motion.id} - [{motion.name}]({motion.link})**__\n\n*Submitted by "
                f"{submitter.display_name} ({submitter})*"
                f"\n\n{motion.description}\n\n &nbsp;"
            )

        outro = f"""\n\n &nbsp; \n\n--- \n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/)
        and this is an automated service. Contact u/Jovanos (DerJonas on Discord) for further questions or bug
        reports.*"""

        cntnt.append(outro)

        content = "\n\n".join(cntnt)

        js = {
            "subreddit": config.DEMOCRACIV_SUBREDDIT,
            "title": f"{session.display_name} - Docket & Submissions",
            "content": content,
        }

        result = await self.bot.api_request("POST", "reddit/post", json=js)

        if "error" in result:
            raise exceptions.DemocracivBotAPIError()

        await ctx.send(
            f"{config.YES} A summary of {session.display_name} was posted "
            f"to r/{config.DEMOCRACIV_SUBREDDIT}."
        )

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch(
            "SELECT id, mk13_house_id, opened_on, closed_on, session_kind FROM legislature_session WHERE house = 'senate' ORDER BY id"
        )
        pretty_sessions = []

        for record in all_sessions:
            opened_on = f"<t:{int(record["opened_on"].timestamp())}:D>"

            if record["closed_on"]:
                closed_on = f"<t:{int(record["closed_on"].timestamp())}:D>"
                label = (
                    f"Emergency Session #{record['mk13_house_id']}"
                    if record["session_kind"] == models.SessionKind.EMERGENCY.value
                    else f"Session #{record['mk13_house_id']}"
                )
                pretty_sessions.append(f"* **{label}**  - {opened_on} to {closed_on}")
            else:
                label = (
                    f"Emergency Session #{record['mk13_house_id']}"
                    if record["session_kind"] == models.SessionKind.EMERGENCY.value
                    else f"Session #{record['mk13_house_id']}"
                )
                pretty_sessions.append(f"* **{label}**  - {opened_on}")

        pages = paginator.SimplePages(
            entries=pretty_sessions,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"All Sessions of the Senate",
            empty_message="There hasn't been a session yet.",
            per_page=12,
        )
        await pages.start(ctx)

    @session.command(name="all", aliases=["a"])
    async def all_sessions(self, ctx: context.CustomContext):
        """View a history of all previous sessions of the {LEGISLATURE_NAME}"""
        return await self.paginate_all_sessions(ctx)

    async def make_google_docs_bill(self, ctx) -> typing.Optional[str]:
        name = await ctx.input(
            f"{config.YES} I will make a Google Docs document for you instead.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **name** of the bill you want to submit."
        )

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **text** of your bill.\n"
            f"{config.HINT} You can reply with as many messages as you need for this. Once you're done, reply with "
            f"just the word `stop` and we will continue with the process."
        )

        messages = []
        start = discord.utils.utcnow()

        while True:
            try:
                _message = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                    timeout=180,
                )

                _ctx = await self.bot.get_context(_message)

                if _ctx.valid:
                    continue

                if _message.content.lower() == "stop":
                    break

                messages.append(_message)
                await ctx.send(
                    f"{config.YES} That message was added to the text of your bill.\n{config.HINT} You can "
                    f"write more messages if you want. If not, reply with just the word `stop` to stop "
                    f"and continue with the submission process.\n"
                    f"{config.HINT} If you edit or delete any of your messages, I will also "
                    f"reflect that change in the text of your bill."
                )
            except asyncio.TimeoutError:
                if discord.utils.utcnow() - start >= datetime.timedelta(minutes=15):
                    break
                else:
                    continue

        if not messages:
            await ctx.send(
                f"{config.HINT} You didn't write any text for your bill. The bill submission "
                f"process was cancelled."
            )
            return

        # check if messages were deleted
        messages = [
            discord.utils.get(self.bot.cached_messages, id=mes.id) for mes in messages
        ]

        if not any(messages):
            await ctx.send(
                f"{config.HINT} You deleted all your messages. The bill submission process was cancelled."
            )
            return

        messages = list(filter(None, messages))

        email = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **email address** "
            f"of your Google Account if you want me to add you as an editor to the document. If not, just reply with gibberish.",
            delete_after=True,
        )

        if not self.email_regex.fullmatch(email):
            email = "No Email"

        author = f"{ctx.author.display_name} ({ctx.author})"

        bill_text = []

        for mes in messages:
            # get message again in case it was edited
            mes = discord.utils.get(self.bot.cached_messages, id=mes.id)

            # message was deleted
            if not mes:
                continue

            if mes.content:
                bill_text.append(mes.clean_content)

        bill_text = "\n\n".join(bill_text)

        async with ctx.typing():
            result = await self.bot.run_apps_script(
                script_id="M_fLh3UOUzLzW873Z7VZ1emqnXKElby-M",
                function="make_google_doc",
                parameters=[name, bill_text, email, author],
            )

            link = result["response"]["result"]["view"]
            fixed_link = link.replace("open?id=", "document/d/")
            fixed_link = f"{fixed_link}/edit"

        if "share_error" in result["response"]["result"]:
            await ctx.send(
                f"{config.NO} While generating the Google Doc for your bill was successful, there was an error while "
                f"setting the link of your Google Docs document to public. Unfortunately this error just sometimes "
                f"happens on Google's side, and there is nothing I can do to circumvent it. "
                f"Please set the link to public by yourself, or otherwise no one else can "
                f"view your bill: <{fixed_link}>"
            )

        return fixed_link

    async def submit_bill(
        self,
        ctx: context.CustomContext,
        current_leg_session_id: int,
        current_leg_session_display_id: int,
        bill_modal: SubmitBillModal,
        current_leg_session_name: str = None,
    ) -> typing.Optional[discord.Embed]:
        current_leg_session_name = (
            current_leg_session_name
            or f"Senate Session #{current_leg_session_display_id}"
        )

        google_docs_url = bill_modal.google_docs_url.component.value

        if not google_docs_url:
            await ctx.send(f"{config.NO} Something went wrong.")
            return

        is_procedure = (
            True if bill_modal.is_procedure.component.values[0] == "true" else False
        )
        is_vetoable = not is_procedure
        bill_description = (
            bill_modal.bill_description.component.value
            or "*No summary provided by submitter.*"
        )

        async with ctx.typing():
            bill = models.Bill(
                bot=self.bot,
                link=google_docs_url,
                submitter_description=bill_description,
            )
            name, tags, content = await bill.fetch_name_and_keywords()

            if not name:
                await ctx.send(
                    f"{config.NO} Something went wrong. Are you sure you made your "
                    f"Google Docs document public for everyone to view?\n"
                    f"{config.HINT} Word (.docx) documents on Google Docs are not supported."
                )
                return

            bill_id = await self.bot.db.fetchval(
                "INSERT INTO bill (leg_session, name, link, submitter, is_vetoable, is_procedure, submitter_description, content, origin_house) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                current_leg_session_id,
                name,
                google_docs_url,
                ctx.author.id,
                is_vetoable,
                is_procedure,
                bill_description,
                content,
                "senate",
            )

            bill.id = bill_id
            await self.bot.db.execute(
                "INSERT INTO bill_session (bill_id, leg_session) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                bill_id,
                current_leg_session_id,
            )
            await bill.status.log_history(
                old_status=models.BillSubmitted.flag,
                new_status=models.BillSubmitted.flag,
                note=f"Submitted to {current_leg_session_name}",
            )

            id_with_tags = [(bill_id, tag) for tag in tags]
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES "
                    "($1, $2) ON CONFLICT DO NOTHING ",
                    id_with_tags,
                )
            )

        embed = text.SafeEmbed(
            title=f"{name} (#{bill_id})",
            url=google_docs_url,
            description=f"Hey! A new **bill** was just submitted to {current_leg_session_name}.",
        )
        embed.add_field(
            name="Type",
            value="Senate Procedure" if is_procedure else "Bill",
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
        )

        embed.set_author(
            icon_url=ctx.author_icon, name=f"Submitted by {ctx.author.display_name}"
        )

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND
        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Bill Submissions",
            description=f"The {self.bot.mk.senator_presiding_term} has been informed about your "
            f"bill submission.",
        )

        info.add_field(
            name="Sponsors",
            value="Depending on current legislative procedures or laws, your bill might need a specific "
            f"amount of sponsors before the {self.bot.mk.senator_presiding_term} allows a vote on it. "
            f"Tell your supporters to sponsor your bill with `{p}bill sponsor {bill_id}`. The list "
            f"of sponsors will be displayed on your bill's detail page, `{p}bill {bill_id}`.",
            inline=False,
        )

        info.add_field(
            name="I want to change something in my bill",
            value=f"During the Submission Period, you __do not__ have to withdraw your bill and submit it "
            f"as a new bill again if you want to keep working on your bill and do some changes, "
            f"based on feedback for example.\n\nUntil the Voting Period, just make your changes in "
            f"the Google Docs document. It would be fair to your colleagues to inform them on any "
            f"changes to your bill, though.\n\nDo __not__ edit your bill if the session is already in "
            f"Voting Period and people are already voting on it, as a way to mislead them or "
            f"to sneak anything secret in.",
            inline=False,
        )

        info.add_field(
            name="Withdrawing a Bill",
            value=f"If, for whatever reason, you want to withdraw your bill from this "
            f"session, use the `{p}{l} withdraw {bill_id}` or `{p}bill withdraw {bill_id}` command.\n\n"
            f"You can only withdraw your bills during the Submission Period of a legislative session, "
            f"while the {self.bot.mk.senator_presiding_term} can withdraw _every_ bill, at any time.",
            inline=False,
        )

        info.add_field(
            name="Additional Commands",
            value=f"Congratulations! Your submitted bill will now show up in the detail page "
            f"for the current session `{p}{l} session`, in `{p}{l} bills`, "
            f"`{p}{l} bills from {ctx.author.name}` and "
            f"`{p}{l} bills from <your_party>` if you belong to a political party, and "
            f"everyone can search for it based on matching keywords "
            f"with `{p}bill search <keyword>`.",
        )
        await ctx.send(
            f"{config.YES} Your bill `{name}` (#{bill_id}) was submitted for {current_leg_session_name}.",
        )

        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))
        await self.bot.api_request(
            "POST", "document/add", silent=True, json={"id": bill_id, "type": "bill"}
        )
        return embed

    async def submit_motion(
        self,
        ctx: context.CustomContext,
        current_leg_session_id: int,
        current_leg_session_display_id: int,
        motion_modal: SubmitMotionModal,
        current_leg_session_name: str = None,
    ) -> typing.Optional[discord.Embed]:
        current_leg_session_name = (
            current_leg_session_name
            or f"Senate Session #{current_leg_session_display_id}"
        )

        title = motion_modal.motion_title.component.value

        if not title:
            await ctx.send(f"{config.NO} Something went wrong.")
            return

        description = motion_modal.motion_description.component.value

        haste_bin_url = f"https://laws.democraciv.com/motion/<id>"

        motion_id = await self.bot.db.fetchval(
            "INSERT INTO motion (leg_session, title, description, submitter, paste_link) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            current_leg_session_id,
            title,
            description,
            ctx.author.id,
            haste_bin_url,
        )

        haste_bin_url = f"https://laws.democraciv.com/motion/{motion_id}"

        # this is not a good way of doing it. should just edit schema but oh well
        await self.bot.db.execute(
            "UPDATE motion SET paste_link = $1 WHERE id = $2", haste_bin_url, motion_id
        )

        embed = text.SafeEmbed(
            title=f"{title} (#{motion_id})",
            description=f"Hey! A new **motion** was just submitted to {current_leg_session_name}.",
            url=haste_bin_url,
        )

        embed.add_field(name="Content", value=description, inline=False)
        embed.add_field(name="Author", value=f"{ctx.author.mention} {ctx.author}")
        embed.add_field(
            name="Exact Time of Submission",
            value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>",
            inline=False,
        )
        embed.set_author(
            icon_url=ctx.author_icon, name=f"Submitted by {ctx.author.display_name}"
        )

        await ctx.send(
            f"{config.YES} Your motion `{title}` (#{motion_id}) was submitted for {current_leg_session_name}.\n"
            f"{config.HINT} Tell your supporters to sponsor your motion with "
            f"`{config.BOT_PREFIX}motion sponsor {motion_id}`."
        )
        await self.bot.api_request(
            "POST",
            "document/add",
            silent=True,
            json={"id": motion_id, "type": "motion"},
        )
        return embed

    @legislature.command(name="submit")
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.max_concurrency(3, per=commands.BucketType.guild, wait=False)
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        try:
            if self.is_cabinet(ctx.author):
                ctx.command.reset_cooldown(ctx)
        except exceptions.RoleNotFoundError:
            pass

        open_sessions = await self.get_open_leg_sessions(house="senate")
        eligible_sessions = [
            session
            for session in open_sessions
            if self.submission_session_rejection(
                ctx.author, house="senate", session=session
            )
            is None
        ]

        if not eligible_sessions:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                self.submission_session_unavailable_message(
                    house="senate",
                    member=ctx.author,
                    sessions=open_sessions,
                )
            )

        can_submit_bill = self.can_member_submit_kind(ctx.author, kind="bill")
        can_submit_motion = self.can_member_submit_kind(ctx.author, kind="motion")

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST and not can_submit_bill:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                "are allowed to submit bills."
            )

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST and not (
            can_submit_bill or can_submit_motion
        ):
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} "
                "are allowed to submit bills or motions."
            )

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            bill_modal = SubmitBillModal(eligible_sessions)
            motion_modal = SubmitMotionModal(eligible_sessions)
            view = SubmitChooserView(
                ctx,
                bill_modal=bill_modal,
                motion_modal=motion_modal,
                can_submit_bill=can_submit_bill,
                can_submit_motion=can_submit_motion,
            )

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to submit a bill or a motion?"
                f"\n\n{config.HINT} *Motions lack a lot of features that bills have, "
                f"for example they cannot be passed into Law by the Government. They will not "
                f"show up in `{config.BOT_PREFIX}laws`, nor will they make it on the Legal Code. If you want to submit "
                f"something small that results in some __temporary__ action and where it's not important to track if it passed, "
                f"use a motion, otherwise use a bill. __In most cases you should probably use bills.__ "
                f"Common examples for motions: `Motion to repeal Law #12`, or "
                f"`Motion to recall {self.bot.mk.legislator_term} XY`.*\n\n### {config.HINT} In 80% of cases, you should use bills instead of motions!",
                view=view,
            )

            result = await view.prompt()
            embed = None

            if not result:
                return

            if result == "bill":
                current_leg_session, error = (
                    await self.resolve_submit_session_from_modal(
                        ctx,
                        house="senate",
                        session_id=mixin.get_submit_session_choice_id(bill_modal),
                    )
                )
                if error:
                    ctx.command.reset_cooldown(ctx)
                    return await ctx.send(error)

                embed = await self.submit_bill(
                    ctx,
                    current_leg_session.id,
                    current_leg_session.display_id,
                    bill_modal,
                    current_leg_session.display_name,
                )

            elif result == "motion":
                ctx.command.reset_cooldown(ctx)

                current_leg_session, error = (
                    await self.resolve_submit_session_from_modal(
                        ctx,
                        house="senate",
                        session_id=mixin.get_submit_session_choice_id(motion_modal),
                    )
                )
                if error:
                    return await ctx.send(error)

                embed = await self.submit_motion(
                    ctx,
                    current_leg_session.id,
                    current_leg_session.display_id,
                    motion_modal,
                    current_leg_session.display_name,
                )
        else:
            bill_modal = SubmitBillModal(eligible_sessions)
            view = SubmitBillOnlyView(ctx, bill_modal=bill_modal)

            await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Submit a bill to the Senate.",
                view=view,
            )

            result = await view.prompt()
            embed = None

            if not result:
                return

            current_leg_session, error = await self.resolve_submit_session_from_modal(
                ctx,
                house="senate",
                session_id=mixin.get_submit_session_choice_id(bill_modal),
            )
            if error:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(error)

            embed = await self.submit_bill(
                ctx,
                current_leg_session.id,
                current_leg_session.display_id,
                bill_modal,
                current_leg_session.display_name,
            )

        if embed is None:
            return

        if not self.is_cabinet(ctx.author):
            if self.senator_presiding is not None:
                await self.bot.safe_send_dm(
                    target=self.senator_presiding,
                    reason="leg_session_submit",
                    embed=embed,
                )

    @legislature.command(name="pass", aliases=["p"])
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def pass_bill(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Mark one or multiple bills as passed from the {LEGISLATURE_NAME}

        **Example**
            `{PREFIX}{COMMAND} 12` will mark Bill #12 as passed from the {LEGISLATURE_NAME}
            `{PREFIX}{COMMAND} 45 46 49 51 52` will mark all those bills as passed"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        def verify_bill(_ctx, b: Bill, **_kwargs):
            if b.session is None or b.session.house != "senate":
                return "You can only mark bills from a Senate session as passed here."

            if b.session.status is not SessionStatus.CLOSED:
                return "You can only mark bills as passed if their session is closed."

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.pass_from_legislature
        )

        await consumer.filter(
            filter_func=verify_bill,
            acting_house="senate",
        )

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills can not be passed.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        target_session = None
        if any(
            self.bill_needs_cross_house_destination(bill, acting_house="senate")
            for bill in consumer.passed
        ):
            open_commons_sessions = await self.get_open_leg_sessions(house="commons")
            if len(open_commons_sessions) == 1:
                target_session = open_commons_sessions[0]
            elif len(open_commons_sessions) > 1:
                target_session = await self.prompt_for_leg_session(
                    ctx,
                    sessions=open_commons_sessions,
                    action="send these bills to",
                )
                if target_session is None:
                    return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to mark the following bills as passed from the {self.bot.mk.LEGISLATURE_NAME}?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(
            scheduler=self.pass_scheduler,
            acting_house="senate",
            target_session=target_session,
        )
        await ctx.send(
            f"{config.YES} All bills were marked as passed from the {self.bot.mk.LEGISLATURE_NAME}.\n"
            f"{config.HINT} Depending on each bill's path, it is now either waiting on the Commons "
            f"or on the {self.bot.mk.MINISTRY_NAME}, or it is already law if it was a Senate procedure."
        )

        bills_that_might_repeal_something = [
            f" - Law #{bill.id} - **{bill.name}**"
            for bill in consumer.passed
            if bill.status.is_law and "repeal" in bill.content.lower()
        ]

        if bills_that_might_repeal_something:
            fmt = "\n".join(bills_that_might_repeal_something)

            await ctx.send(
                f"{config.HINT} {ctx.author.mention}, I found the word `repeal` in the following laws that "
                f"you just passed into law. Maybe you have to repeal some laws?\n\n{fmt}\n\n"
                f"You can repeal laws with `{config.BOT_PREFIX}law repeal`.",
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )

    @legislature.command(name="superpass", aliases=["sp"], hidden=True)
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def superpass(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        return await ctx.send(
            f"{config.NO} `superpass` is a legacy-only admin path and is not part of the MK13 bicameral process."
        )

    @legislature.command(name="withdraw", aliases=["w"], hidden=True)
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx, *, bill_or_motion_ids):
        """Withdraw one or multiple bills or motions."""

        view = ModelChooseView(ctx)

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Do you want to withdraw bills or motions? "
            f"You can use the `{config.BOT_PREFIX}bill withdraw` and `{config.BOT_PREFIX}motion withdraw` commands "
            f"to skip this step.",
            view=view,
        )

        result = await view.prompt()

        if not result:
            return

        if result == "bill":
            return await self._redirect_to_root_command(
                ctx, "bill", f"withdraw {bill_or_motion_ids}"
            )

        return await self._redirect_to_root_command(
            ctx, "motion", f"withdraw {bill_or_motion_ids}"
        )

    @legislature.command(name="override", aliases=["ov"], hidden=True)
    @checks.has_democraciv_role(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    async def override(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Override the veto of one or multiple bills to pass them into law

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.override_veto
        )
        await consumer.filter(acting_house="senate")

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

        await consumer.consume(scheduler=self.override_scheduler, acting_house="senate")
        await ctx.send(
            f"{config.YES} The vetoes of all bills were overridden, and all bills are active laws and in "
            f"`{config.BOT_PREFIX}laws` now."
        )

    @legislature.command(name="sponsor", aliases=["second", "cosponsor"], hidden=True)
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def sponsor(self, ctx, *, bill_or_motion_ids):
        """Show your support for one or multiple bills or motions by sponsoring them

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        view = ModelChooseView(ctx)

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Do you want to sponsor bills or motions?\n"
            f"{config.HINT} You can use the `{config.BOT_PREFIX}bill sponsor` and `{config.BOT_PREFIX}motion sponsor` commands "
            f"to skip this step.",
            view=view,
        )

        result = await view.prompt()

        if not result:
            return

        if result == "bill":
            return await self._redirect_to_root_command(
                ctx, "bill", f"sponsor {bill_or_motion_ids}"
            )

        return await self._redirect_to_root_command(
            ctx, "motion", f"sponsor {bill_or_motion_ids}"
        )

    @legislature.command(name="unsponsor", aliases=["usp"], hidden=True)
    @checks.is_democraciv_guild()
    async def unsponsor(self, ctx, *, bill_or_motion_ids):
        """Remove yourself from the list of sponsors of one or multiple bills or motions

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        view = ModelChooseView(ctx)

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Do you want to unsponsor bills or motions?\n"
            f"{config.HINT} You can use the `{config.BOT_PREFIX}bill unsponsor` and `{config.BOT_PREFIX}motion unsponsor` commands "
            f"to skip this step.",
            view=view,
        )

        result = await view.prompt()

        if not result:
            return

        if result == "bill":
            return await self._redirect_to_root_command(
                ctx, "bill", f"unsponsor {bill_or_motion_ids}"
            )

        return await self._redirect_to_root_command(
            ctx, "motion", f"unsponsor {bill_or_motion_ids}"
        )

    @legislature.command(name="statistics", aliases=["stat", "stats", "statistic"])
    async def stats(
        self,
        ctx,
        *,
        person_or_political_party: Fuzzy[
            converter.CaseInsensitiveMember,
            converter.CaseInsensitiveUser,
            converter.PoliticalParty,
            FuzzySettings(weights=(5, 0, 2)),
        ] = None,
    ):
        """Legislative statistics about the overall Legislature, a specific person or a political party

        **Example**
        `{PREFIX}{COMMAND}` to get the overall statistics about the {LEGISLATURE_NAME}
        `{PREFIX}{COMMAND} DerJonas` to get personalized statistics for that person
        `{PREFIX}{COMMAND} Ecological Democratic Union` to get statistics for a political party
        """

        embed = await self._build_statistics_embed(
            ctx=ctx, house="senate", target=person_or_political_party
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Legislature(bot))
