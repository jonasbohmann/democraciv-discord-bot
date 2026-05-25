import asyncio
import collections
import datetime

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config, mk
from bot.slash import forms
from bot.slash import context as slash_context
from bot.slash import checks as slash_checks
from bot.slash import transformers, ui
from bot.utils import converter, exceptions, mixin, models, paginator, text

LawOption = app_commands.Transform[models.Law, transformers.LawTransformer]
BillOption = app_commands.Transform[models.Bill, transformers.BillTransformer]
MotionOption = app_commands.Transform[models.Motion, transformers.MotionTransformer]
PartyOption = app_commands.Transform[
    converter.PoliticalParty, transformers.PoliticalPartyTransformer
]

SESSION_TYPE_CHOICES = [
    app_commands.Choice(name="Regular", value=models.SessionKind.REGULAR.value),
    app_commands.Choice(name="Emergency", value=models.SessionKind.EMERGENCY.value),
]


def _session_kind_from_choice(value: str = None) -> models.SessionKind | None:
    if value is None:
        return None

    return models.SessionKind(value)


class BillBulkEditModal(forms.ErrorHandledModal):
    def __init__(self, cog: "LegalSlash"):
        super().__init__(title="Bulk Edit Bill Links")
        self.cog = cog
        self.bill_links = forms.text_label(
            label="Bills and new links",
            description="One bill per line: bill_id space Google Docs link.",
            placeholder="12 https://docs.google.com/document/d/...\n45 https://docs.google.com/document/d/...",
            style=discord.TextStyle.long,
            max_length=4000,
        )
        self.add_item(self.bill_links)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="bill bulkedit")
        await ctx.defer()
        await self.cog._bulkedit_bills(ctx, self.bill_links.component.value)


class BillEditModal(forms.ErrorHandledModal):
    def __init__(self, cog: "LegalSlash", *, bill: models.Bill):
        super().__init__(title=f"Edit Bill #{bill.id}")
        self.cog = cog
        self.bill = bill
        self.link = forms.text_label(
            label="New Google Docs link",
            description="Leave empty to keep the current link.",
            placeholder=bill.link,
            required=False,
            max_length=512,
        )
        self.description = forms.text_label(
            label="New short summary",
            description="Leave empty to keep the current summary.",
            placeholder=(bill.description or "")[:100],
            required=False,
            max_length=500,
            style=discord.TextStyle.long,
        )
        self.add_item(self.link)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="bill edit")
        await ctx.defer()
        await self.cog._edit_bill(
            ctx,
            self.bill,
            link=self.link.component.value,
            description=self.description.component.value,
        )


class MotionEditModal(forms.ErrorHandledModal):
    def __init__(self, cog: "LegalSlash", *, motion: models.Motion):
        super().__init__(title=f"Edit Motion #{motion.id}")
        self.cog = cog
        self.motion = motion
        self.title_input = forms.text_label(
            label="Title",
            default=(motion.title or "")[:200],
            required=False,
            max_length=200,
        )
        self.content = forms.text_label(
            label="Content",
            description="Leave empty to keep the current content.",
            placeholder=(motion.description or "")[:100],
            required=False,
            max_length=4000,
            style=discord.TextStyle.long,
        )
        self.add_item(self.title_input)
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="motion edit")
        await ctx.defer()
        await self.cog._edit_motion(
            ctx,
            self.motion,
            title=self.title_input.component.value,
            content=self.content.component.value,
        )


class LegalSlash(commands.Cog, mixin.GovernmentMixin):
    law = app_commands.Group(
        name="law",
        description="List, search, show, and read laws.",
        guild_only=True,
    )
    bill = app_commands.Group(
        name="bill",
        description="List, search, and show bills.",
        guild_only=True,
    )
    motion = app_commands.Group(
        name="motion",
        description="List, search, and show motions.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    async def _confirm_consumer(
        self,
        ctx: slash_context.InteractionContext,
        *,
        consumer: models.LegalConsumer,
        title: str,
        body: str,
        confirm_label: str,
    ) -> bool | None:
        if consumer.failed:
            await ctx.send(
                f":warning: Some items cannot be changed.\n{consumer.failed_formatted}",
                ephemeral=True,
            )

        if not consumer.passed:
            return None

        return await ui.confirm(
            ctx,
            title=title,
            body=f"{body}\n\n{consumer.passed_formatted}",
            confirm_label=confirm_label,
        )

    async def _sponsor_bill(self, ctx, bill: models.Bill):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.sponsor
        )

        def filter_sponsor(_ctx, target_bill, **kwargs):
            if _ctx.author.id == target_bill.submitter_id:
                return "The bill's author cannot sponsor their own bill."

            if _ctx.author in target_bill.sponsors:
                return "You already sponsored this bill."

            house = self.get_house_for_object(target_bill)
            if not self.can_member_sponsor_in_house(_ctx.author, house):
                if house == "senate":
                    return "Only Senators can sponsor Senate bills."

                return "Only Senators can sponsor this bill."

        await consumer.filter(filter_func=filter_sponsor, sponsor=ctx.author)

        confirmed = await self._confirm_consumer(
            ctx,
            consumer=consumer,
            title="Sponsor Bill",
            body="Are you sure that you want to sponsor this bill?",
            confirm_label="Sponsor",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(f"{config.YES} Bill #{bill.id} was sponsored by you.")

    async def _unsponsor_bill(self, ctx, bill: models.Bill):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.unsponsor
        )

        def filter_unsponsor(_ctx, target_bill, **kwargs):
            if _ctx.author not in target_bill.sponsors:
                return "You are not a sponsor of this bill."

        await consumer.filter(filter_func=filter_unsponsor, sponsor=ctx.author)

        confirmed = await self._confirm_consumer(
            ctx,
            consumer=consumer,
            title="Unsponsor Bill",
            body="Remove yourself from the sponsors of this bill?",
            confirm_label="Unsponsor",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(
            f"{config.YES} You were removed as a sponsor of Bill #{bill.id}."
        )

    async def _withdraw_bill(self, ctx, bill: models.Bill):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.withdraw
        )

        def verify_object(_ctx, target_bill, **kwargs):
            house = self.get_house_for_object(target_bill)

            if target_bill.session.closed_on:
                return "The session during which this bill was submitted is not open anymore."

            if self.is_cabinet_for_house(_ctx.author, house):
                return

            if _ctx.author.id != target_bill.submitter_id:
                return "Only chamber leadership and the original submitter of this bill can withdraw it."

            if target_bill.session.status is not models.SessionStatus.SUBMISSION_PERIOD:
                return "The original submitter can only withdraw bills during the Submission Period."

        await consumer.filter(filter_func=verify_object)

        confirmed = await self._confirm_consumer(
            ctx,
            consumer=consumer,
            title="Withdraw Bill",
            body="Are you sure that you want to withdraw this bill?",
            confirm_label="Withdraw",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await consumer.consume()
        await ctx.send(f"{config.YES} Bill #{bill.id} was withdrawn.")

        withdrawn_by_house = collections.defaultdict(list)
        for passed_bill in consumer.passed:
            house = self.get_house_for_object(passed_bill)
            if self.is_cabinet_for_house(ctx.author, house):
                continue

            withdrawn_by_house[house].append(
                f"-  **{passed_bill.name}** (#{passed_bill.id})"
            )

        for house, formatted_bills in withdrawn_by_house.items():
            message = (
                f"The following bills were withdrawn by {ctx.author}.\n"
                f"{chr(10).join(formatted_bills)}"
            )

            for leader in self.get_cabinet_members_for_house(house):
                await self.bot.safe_send_dm(
                    target=leader,
                    reason="leg_session_withdraw",
                    message=message,
                )

    async def _resubmit_bill(
        self,
        ctx,
        bill: models.Bill,
        *,
        session_kind: models.SessionKind = None,
    ):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.resubmit
        )
        await consumer.filter(resubmitter=ctx.author)

        if not consumer.passed:
            await self._confirm_consumer(
                ctx,
                consumer=consumer,
                title="Resubmit Bill",
                body="Resubmit this bill to the current submission-period session in its origin house?",
                confirm_label="Resubmit",
            )
            return

        sessions = await self.get_open_leg_sessions(
            house=bill.origin_house,
            session_kind=session_kind,
            status=models.SessionStatus.SUBMISSION_PERIOD,
        )

        if len(sessions) == 0:
            suffix = (
                f" {session_kind.value.lower()}" if session_kind is not None else ""
            )
            return await ctx.send(
                f"{config.NO} There is no open{suffix} {bill.origin_house_name} session in Submission Period.",
                ephemeral=True,
            )

        if len(sessions) > 1:
            target_session = await self.prompt_for_leg_session(
                ctx,
                sessions=sessions,
                action="resubmit this bill to",
                ephemeral=True,
                silent=True,
            )
            if target_session is None:
                return
        else:
            target_session = sessions[0]

        confirmed = await self._confirm_consumer(
            ctx,
            consumer=consumer,
            title="Resubmit Bill",
            body="Resubmit this bill to the current submission-period session in its origin house?",
            confirm_label="Resubmit",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await consumer.consume(resubmitter=ctx.author, target_session=target_session)
        await ctx.send(
            f"{config.YES} Bill #{bill.id} was resubmitted to its origin-house submission session."
        )

    async def _sponsor_motion(self, ctx, motion: models.Motion):
        house = self.get_house_for_object(motion)
        failed = None

        if ctx.author.id == motion.submitter_id:
            failed = "The motion's author cannot sponsor their own motion."
        elif ctx.author in motion.sponsors:
            failed = "You already sponsored this motion."
        elif not self.can_member_sponsor_in_house(ctx.author, house):
            failed = "Only Senators can sponsor Senate motions."
        elif motion.session.closed_on:
            failed = "You can only sponsor motions if the session they were submitted in is still open."

        if failed:
            return await ctx.send(f"{config.NO} {failed}", ephemeral=True)

        if not await ui.confirm(
            ctx,
            title="Sponsor Motion",
            body=f"Are you sure that you want to sponsor **{motion.name}** (#{motion.id})?",
            confirm_label="Sponsor",
        ):
            return await ctx.send("Cancelled.", ephemeral=True)

        await self.bot.db.execute(
            "INSERT INTO motion_sponsor (motion_id, sponsor) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            motion.id,
            ctx.author.id,
        )
        await ctx.send(f"{config.YES} Motion #{motion.id} was sponsored by you.")

    async def _unsponsor_motion(self, ctx, motion: models.Motion):
        failed = None

        if ctx.author not in motion.sponsors:
            failed = "You are not a sponsor of this motion."
        elif motion.session.closed_on:
            failed = "You can only unsponsor motions if the session they were submitted in is still open."

        if failed:
            return await ctx.send(f"{config.NO} {failed}", ephemeral=True)

        if not await ui.confirm(
            ctx,
            title="Unsponsor Motion",
            body=f"Remove yourself from the sponsors of **{motion.name}** (#{motion.id})?",
            confirm_label="Unsponsor",
        ):
            return await ctx.send("Cancelled.", ephemeral=True)

        await self.bot.db.execute(
            "DELETE FROM motion_sponsor WHERE motion_id = $1 and sponsor = $2",
            motion.id,
            ctx.author.id,
        )
        await ctx.send(
            f"{config.YES} You were removed as a sponsor of Motion #{motion.id}."
        )

    async def _withdraw_motion(self, ctx, motion: models.Motion):
        house = self.get_house_for_object(motion)
        failed = None

        if motion.session.closed_on:
            failed = "The session during which this motion was submitted is not open anymore."
        elif not self.is_cabinet_for_house(ctx.author, house):
            if ctx.author.id != motion.submitter_id:
                failed = "Only chamber leadership and the original submitter of this motion can withdraw it."
            elif motion.session.status is not models.SessionStatus.SUBMISSION_PERIOD:
                failed = "The original submitter can only withdraw motions during the Submission Period."

        if failed:
            return await ctx.send(f"{config.NO} {failed}", ephemeral=True)

        if not await ui.confirm(
            ctx,
            title="Withdraw Motion",
            body=f"Are you sure that you want to withdraw **{motion.name}** (#{motion.id})?",
            confirm_label="Withdraw",
        ):
            return await ctx.send("Cancelled.", ephemeral=True)

        await motion.withdraw()
        await ctx.send(f"{config.YES} Motion #{motion.id} was withdrawn.")

    async def _repeal_law(self, ctx, law: models.Law):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[law], action=models.BillStatus.repeal
        )
        await consumer.filter()

        confirmed = await self._confirm_consumer(
            ctx,
            consumer=consumer,
            title="Repeal Law",
            body="Are you sure that you want to repeal this law?",
            confirm_label="Repeal",
        )
        if confirmed is None:
            return
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        scheduler = getattr(self.bot.get_cog("Law"), "repeal_scheduler", None)
        await consumer.consume(scheduler=scheduler)
        await ctx.send(f"{config.YES} Law #{law.id} was repealed.")

    async def _synchronize_bill(
        self,
        ctx: slash_context.InteractionContext,
        bill: models.Bill,
    ):
        house = self.get_house_for_object(bill)
        if not self.is_cabinet_for_house(ctx.author, house):
            return await ctx.send(
                f"{config.NO} Only chamber leadership can synchronize this bill.",
                ephemeral=True,
            )

        name, keywords, content = await bill.fetch_name_and_keywords()
        if not name:
            return await ctx.send(
                f"{config.NO} Error synchronizing Bill #{bill.id} - {bill.name}. "
                "Are you sure the Google Docs document is public?",
                ephemeral=True,
            )

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE bill SET name = $1, content = $2 WHERE id = $3",
                    name,
                    content,
                    bill.id,
                )
                await connection.execute(
                    "DELETE FROM bill_lookup_tag WHERE bill_id = $1",
                    bill.id,
                )
                if keywords:
                    await connection.executemany(
                        "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) "
                        "ON CONFLICT DO NOTHING",
                        [(bill.id, keyword) for keyword in keywords],
                    )

        await self.bot.api_request(
            "POST", "document/update", json={"id": bill.id, "type": "bill"}
        )
        await ctx.send(f"{config.YES} Synchronized Bill #{bill.id} with Google Docs.")

    async def _bulkedit_bills(
        self,
        ctx: slash_context.InteractionContext,
        raw_bill_links: str,
    ):
        lines = forms.split_lines(raw_bill_links)
        if not lines:
            return await ctx.send(
                f"{config.NO} No bill/link pairs were provided.",
                ephemeral=True,
            )

        skipped = []
        changed = 0

        for line_number, line in enumerate(lines, start=1):
            try:
                bill_id, link = line.split(maxsplit=1)
            except ValueError:
                skipped.append(f"  - Incorrect input formatting on line {line_number}.")
                continue

            try:
                bill = await models.Bill.convert(ctx, bill_id)
            except exceptions.NotFoundError:
                skipped.append(f"  - There is no Bill #{bill_id}.")
                continue

            house = self.get_house_for_object(bill)
            if not self.is_cabinet_for_house(ctx.author, house):
                skipped.append(
                    f"  - You are not part of the leadership that can edit Bill #{bill.id}."
                )
                continue

            if not self.is_google_doc_link(link):
                skipped.append(
                    f"  - The new link for Bill #{bill_id} is not a valid Google Docs link."
                )
                continue

            try:
                await bill.update_link(link)
            except exceptions.DemocracivBotException as error:
                skipped.append(f"  - {error.message}")
                continue

            changed += 1

        message = f"{config.YES} Changed the link of {changed}/{len(lines)} bills."
        if skipped:
            message = (
                ":warning: I skipped changing the link of some bills:\n\n"
                f"{chr(10).join(skipped)}\n\n{message}"
            )

        await ctx.send(message)

    async def _edit_bill(
        self,
        ctx: slash_context.InteractionContext,
        bill: models.Bill,
        *,
        link: str,
        description: str,
    ):
        house = self.get_house_for_object(bill)
        is_house_leadership = self.is_cabinet_for_house(ctx.author, house)

        if not is_house_leadership and bill.submitter_id != ctx.author.id:
            return await ctx.send(
                f"{config.NO} Only chamber leadership and the original submitter of a bill can edit it.",
                ephemeral=True,
            )

        link = (link or "").strip()
        description = (description or "").strip()
        current_description = bill.description or ""
        description_changed = bool(description) and description != current_description

        if not link and not description_changed:
            return await ctx.send(f"{config.NO} Nothing changed.", ephemeral=True)

        if link:
            if (
                not is_house_leadership
                and bill.session.status is not models.SessionStatus.SUBMISSION_PERIOD
            ):
                return await ctx.send(
                    f"{config.NO} You can only change the link to your bill if the "
                    "session it was submitted in is still in Submission Period.",
                    ephemeral=True,
                )

            if not self.is_google_doc_link(link):
                return await ctx.send(
                    f"{config.NO} That does not look like a Google Docs URL.",
                    ephemeral=True,
                )

            changed_bill = models.Bill(
                id=bill.id,
                bot=self.bot,
                link=link,
                submitter_description=description or bill.description,
            )
            await changed_bill.update_link(link)

        if description_changed:
            await self.bot.db.execute(
                "UPDATE bill SET submitter_description = $1 WHERE id = $2",
                description or "*No summary provided by submitter.*",
                bill.id,
            )

        await ctx.send(f"{config.YES} Bill #{bill.id} `{bill.name}` was updated.")

    async def _edit_motion(
        self,
        ctx: slash_context.InteractionContext,
        motion: models.Motion,
        *,
        title: str,
        content: str,
    ):
        house = self.get_house_for_object(motion)
        is_house_leadership = self.is_cabinet_for_house(ctx.author, house)

        if not is_house_leadership:
            if motion.submitter_id != ctx.author.id:
                return await ctx.send(
                    f"{config.NO} Only chamber leadership and the original submitter of a motion can edit it.",
                    ephemeral=True,
                )

            if motion.session.status is not models.SessionStatus.SUBMISSION_PERIOD:
                return await ctx.send(
                    f"{config.NO} You can only edit your motion if the session it was submitted in "
                    "is still in Submission Period.",
                    ephemeral=True,
                )

        title = (title or "").strip() or motion.title
        content = (content or "").strip()
        title_changed = title != motion.title
        content_changed = bool(content) and content != (motion.description or "")

        if not title_changed and not content_changed:
            return await ctx.send(f"{config.NO} Nothing changed.", ephemeral=True)

        if content_changed:
            paste = await self.bot.make_paste(content)
            if not paste:
                return await ctx.send(
                    f"{config.NO} The motion will not be updated; there was a problem creating the paste.",
                    ephemeral=True,
                )
        else:
            content = motion.description
            paste = motion._link

        await self.bot.db.execute(
            "UPDATE motion SET title = $1, description = $2, paste_link = $3 WHERE id = $4",
            title,
            content,
            paste,
            motion.id,
        )
        await self.bot.api_request(
            "POST", "document/update", json={"id": motion.id, "type": "motion"}
        )
        await ctx.send(f"{config.YES} Motion #{motion.id} `{motion.name}` was updated.")

    @law.command(name="list", description="List all active laws.")
    async def law_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        await self._paginate_all_(ctx, model=models.Law)

    @law.command(name="from", description="List laws submitted by a member or party.")
    @app_commands.describe(
        person="Person to list laws from.",
        party="Political party to list laws from.",
    )
    async def law_from(
        self,
        interaction: discord.Interaction,
        person: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        target = party or person or ctx.author
        await self._from_person_model(ctx, model=models.Law, member_or_party=target)

    @law.command(name="show", description="Show details about one law.")
    @app_commands.describe(law="Law ID or title")
    async def law_show(self, interaction: discord.Interaction, law: LawOption):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        await self._show_detail(ctx, obj=law)

    @law.command(name="search", description="Search laws.")
    @app_commands.describe(query="At least 3 characters to search for")
    async def law_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        results = await self._search_model(ctx, model=models.Law, query=query)
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/law>) as well!"
        )
        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Laws matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)
        fts_view = mixin.FullTextSearchView(ctx)
        index_map = {"law": "bill", "bill": "bill", "motion": "motion"}
        index = index_map.get(models.Law.model.lower(), "bill")
        await ctx.send(
            "Do you want to perform a full-text search via Meilisearch?",
            view=fts_view,
        )
        result = await fts_view.prompt(silent=True)
        if result:
            api_result = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": index, "semantic_ratio": 0.0},
            )
            if api_result and "result" in api_result and api_result["result"]:
                fts_entries = api_result["result"]
                fts_pages = paginator.SimplePages(
                    entries=fts_entries,
                    icon=self.bot.mk.NATION_ICON_URL,
                    author=f"Full-text search results for '{query}'",
                    empty_message="Nothing found.",
                    per_page=12,
                )
                await fts_pages.start(ctx)

    @law.command(name="read", description="Read the text of a law.")
    @app_commands.describe(law="Law ID or title")
    async def law_read(self, interaction: discord.Interaction, law: LawOption):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer(ephemeral=True)
        await self._show_bill_text(ctx, law)

    @bill.command(name="list", description="List all submitted bills.")
    async def bill_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._paginate_all_(ctx, model=models.Bill)

    @bill.command(name="show", description="Show details about one bill.")
    @app_commands.describe(bill="Bill ID or title")
    async def bill_show(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._show_detail(ctx, obj=bill)

    @bill.command(
        name="synchronize",
        description="Synchronize a bill with the latest Google Docs title and text.",
    )
    @slash_checks.is_democraciv_guild()
    @app_commands.describe(bill="Bill ID or title")
    async def bill_synchronize(
        self,
        interaction: discord.Interaction,
        bill: BillOption,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._synchronize_bill(ctx, bill)

    @bill.command(
        name="bulkedit",
        description="Bulk edit the Google Docs links of multiple bills.",
    )
    @slash_checks.is_democraciv_guild()
    async def bill_bulkedit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BillBulkEditModal(self))

    @bill.command(
        name="edit", description="Edit the Google Docs link or summary of a bill."
    )
    @slash_checks.is_democraciv_guild()
    @app_commands.describe(bill="Bill ID or title")
    async def bill_edit(self, interaction: discord.Interaction, bill: BillOption):
        await interaction.response.send_modal(BillEditModal(self, bill=bill))

    @bill.command(name="history", description="Show a bill's legal history.")
    @app_commands.describe(bill="Bill ID or title")
    async def bill_history(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()

        fmt_history = [
            f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}   "
            f"({entry.after.emojified_status(verbose=False)})"
            for entry in bill.history
        ]
        fmt_history.insert(
            0, f"[Link to the Google Docs document of this Bill]({bill.link}).\n"
        )

        pages = paginator.SimplePages(
            entries=fmt_history,
            author=f"{bill.name} (#{bill.id})",
            per_page=12,
            icon=self.bot.mk.NATION_ICON_URL,
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill/{bill.id}>) as well!"
        )
        await pages.start(ctx)

    @bill.command(name="read", description="Read the cached text of a bill.")
    @app_commands.describe(bill="Bill ID or title")
    async def bill_read(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer(ephemeral=True)
        await self._show_bill_text(ctx, bill)

    @bill.command(name="search", description="Search bills.")
    @app_commands.describe(query="At least 3 characters to search for")
    async def bill_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        results = await self._search_model(ctx, model=models.Bill, query=query)
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill>) as well!"
        )
        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Bills matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)
        fts_view = mixin.FullTextSearchView(ctx)
        index_map = {"law": "bill", "bill": "bill", "motion": "motion"}
        index = index_map.get(models.Bill.model.lower(), "bill")
        await ctx.send(
            "Do you want to perform a full-text search via Meilisearch?",
            view=fts_view,
        )
        result = await fts_view.prompt(silent=True)
        if result:
            api_result = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": index, "semantic_ratio": 0.0},
            )
            if api_result and "result" in api_result and api_result["result"]:
                fts_entries = api_result["result"]
                fts_pages = paginator.SimplePages(
                    entries=fts_entries,
                    icon=self.bot.mk.NATION_ICON_URL,
                    author=f"Full-text search results for '{query}'",
                    empty_message="Nothing found.",
                    per_page=12,
                )
                await fts_pages.start(ctx)

    @bill.command(name="from", description="List bills submitted by a member or party.")
    @app_commands.describe(
        member="Member or user to list bills from.",
        party="Political party to list bills from.",
    )
    async def bill_from(
        self,
        interaction: discord.Interaction,
        member: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        target = party or member or ctx.author
        await self._from_person_model(ctx, model=models.Bill, member_or_party=target)

    @bill.command(name="sponsor", description="Sponsor one submitted bill.")
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.describe(bill="Bill ID or title")
    async def bill_sponsor(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._sponsor_bill(ctx, bill)

    @bill.command(
        name="unsponsor", description="Remove your sponsorship from one bill."
    )
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.describe(bill="Bill ID or title")
    async def bill_unsponsor(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._unsponsor_bill(ctx, bill)

    @bill.command(name="withdraw", description="Withdraw one bill from its session.")
    @slash_checks.is_democraciv_guild()
    @app_commands.describe(bill="Bill ID or title")
    async def bill_withdraw(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._withdraw_bill(ctx, bill)

    @bill.command(
        name="resubmit",
        description="Resubmit one failed bill to the current submission-period session.",
    )
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.describe(
        bill="Bill ID or title",
        session_type="Target session type if multiple origin-house sessions are open.",
    )
    @app_commands.choices(session_type=SESSION_TYPE_CHOICES)
    async def bill_resubmit(
        self,
        interaction: discord.Interaction,
        bill: BillOption,
        session_type: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._resubmit_bill(
            ctx, bill, session_kind=_session_kind_from_choice(session_type)
        )

    @motion.command(name="list", description="List all submitted motions.")
    async def motion_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._paginate_all_(ctx, model=models.Motion)

    @motion.command(name="show", description="Show details about one motion.")
    @app_commands.describe(motion="Motion ID or title")
    async def motion_show(self, interaction: discord.Interaction, motion: MotionOption):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._show_detail(ctx, obj=motion)

    @motion.command(name="edit", description="Edit the title or content of a motion.")
    @slash_checks.is_democraciv_guild()
    @app_commands.describe(motion="Motion ID or title")
    async def motion_edit(
        self,
        interaction: discord.Interaction,
        motion: MotionOption,
    ):
        await interaction.response.send_modal(MotionEditModal(self, motion=motion))

    @motion.command(name="search", description="Search motions.")
    @app_commands.describe(query="At least 3 characters to search for")
    async def motion_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        results = await self._search_model(ctx, model=models.Motion, query=query)
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/motion>) as well!"
        )
        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Motions matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)
        fts_view = mixin.FullTextSearchView(ctx)
        index_map = {"law": "bill", "bill": "bill", "motion": "motion"}
        index = index_map.get(models.Motion.model.lower(), "bill")
        await ctx.send(
            "Do you want to perform a full-text search via Meilisearch?",
            view=fts_view,
        )
        result = await fts_view.prompt(silent=True)
        if result:
            api_result = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": index, "semantic_ratio": 0.0},
            )
            if api_result and "result" in api_result and api_result["result"]:
                fts_entries = api_result["result"]
                fts_pages = paginator.SimplePages(
                    entries=fts_entries,
                    icon=self.bot.mk.NATION_ICON_URL,
                    author=f"Full-text search results for '{query}'",
                    empty_message="Nothing found.",
                    per_page=12,
                )
                await fts_pages.start(ctx)

    @motion.command(
        name="from", description="List motions submitted by a member or party."
    )
    @app_commands.describe(
        member="Member or user to list motions from.",
        party="Political party to list motions from.",
    )
    async def motion_from(
        self,
        interaction: discord.Interaction,
        member: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        target = party or member or ctx.author
        await self._from_person_model(ctx, model=models.Motion, member_or_party=target)

    @motion.command(name="sponsor", description="Sponsor one submitted motion.")
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.describe(motion="Motion ID or title")
    async def motion_sponsor(
        self, interaction: discord.Interaction, motion: MotionOption
    ):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._sponsor_motion(ctx, motion)

    @motion.command(
        name="unsponsor",
        description="Remove your sponsorship from one motion.",
    )
    @slash_checks.is_democraciv_guild()
    @slash_checks.is_citizen_if_multiciv()
    @app_commands.describe(motion="Motion ID or title")
    async def motion_unsponsor(
        self, interaction: discord.Interaction, motion: MotionOption
    ):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._unsponsor_motion(ctx, motion)

    @motion.command(
        name="withdraw", description="Withdraw one motion from its session."
    )
    @slash_checks.is_democraciv_guild()
    @app_commands.describe(motion="Motion ID or title")
    async def motion_withdraw(
        self, interaction: discord.Interaction, motion: MotionOption
    ):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._withdraw_motion(ctx, motion)

    @law.command(name="repeal", description="Repeal one active law.")
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER,
        mk.DemocracivRole.VICE_SPEAKER,
    )
    @app_commands.describe(law="Law ID or title")
    async def law_repeal(self, interaction: discord.Interaction, law: LawOption):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        await self._repeal_law(ctx, law)

    @law.command(
        name="export",
        description="Generate a Legal Code as a Google Docs document from active laws.",
    )
    @slash_checks.has_any_democraciv_role(
        mk.DemocracivRole.SPEAKER,
        mk.DemocracivRole.VICE_SPEAKER,
        mk.DemocracivRole.MK13_SENATOR_PRESIDING,
        mk.DemocracivRole.PRIME_MINISTER,
    )
    @app_commands.checks.cooldown(rate=1, per=300.0)
    async def law_export(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()

        doc_url = self.bot.mk.LEGAL_CODE

        if not doc_url or not self.is_google_doc_link(doc_url):
            await ctx.send(
                f"{config.NO} This command cannot be used right now due to security concerns.",
                ephemeral=True,
            )
            return

        await ctx.send(
            f"{config.HINT} You can no longer choose the Google Document that will be used for this yourself. Instead, I will always use this document: {self.bot.mk.LEGAL_CODE}\n\n{config.HINT} You can DM @ Jonas for further information."
        )
        await asyncio.sleep(3)
        await ctx.send(
            f"{config.YES} I will generate an up-to-date Legal Code."
            f"\n:arrows_counterclockwise: This may take a few minutes..."
        )
        await asyncio.sleep(2)

        all_laws = await self.bot.db.fetch(
            "SELECT id, name, link FROM bill WHERE status = $1 ORDER BY id",
            models.BillIsLaw.flag.value,
        )
        ugly_laws = [dict(r) for r in all_laws]
        date = discord.utils.utcnow().strftime("%B %d, %Y at %H:%M")

        result = await self.bot.run_apps_script(
            script_id="MMV-pGVACMhaf_DjTn8jfEGqnXKElby-M",
            function="generate_legal_code",
            parameters=[
                doc_url,
                {"name": self.bot.mk.NATION_FULL_NAME, "date": date},
                ugly_laws,
            ],
        )

        view_url = result["response"]["result"]["view"]
        embed = text.SafeEmbed(
            title="Generated Legal Code",
            description=(
                "This Legal Code is not guaranteed to be correct. Its content "
                f"is based entirely on the list of Laws in `/law list`."
                "\n\nRemember to change the edit link you gave me earlier to not be public."
            ),
        )
        embed.add_field(name="Link to the Legal Code", value=view_url, inline=False)
        await ctx.send(embed=embed)

    async def _show_detail(
        self,
        ctx: slash_context.InteractionContext,
        *,
        obj: models.Bill | models.Motion | models.Law,
    ):
        embed = text.SafeEmbed(
            title=f"{obj.name} (#{obj.id})",
            description=obj.description or "*No summary provided.*",
            url=obj.link,
        )

        if obj.submitter is not None:
            embed.set_author(
                name=f"Submitted by {obj.submitter.name}",
                icon_url=obj.submitter.display_avatar.url,
            )
            submitted_by_value = f"{obj.submitter.mention} {obj.submitter}"
        else:
            submitted_by_value = "*Unknown Person*"

        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)

        if isinstance(obj, models.Bill) and not isinstance(obj, models.Law):
            if obj.session.house in models.HOUSE_NAMES:
                embed.add_field(
                    name="Orig. in Chamber", value=obj.origin_house_name, inline=True
                )
                embed.add_field(name="Type", value=obj.type_name, inline=True)
            else:
                is_vetoable = "Yes" if obj.is_vetoable else "No"
                embed.add_field(name="Vetoable", value=is_vetoable, inline=True)

            embed.add_field(
                name="Status",
                value=obj.status.emojified_status(verbose=True),
                inline=False,
            )

            if obj.executive_deadline_at is not None:
                embed.add_field(
                    name="Executive Deadline",
                    value=f"<t:{int(obj.executive_deadline_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R> ",
                    inline=True,
                )

            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

        if not isinstance(obj, models.Motion):
            history = [
                f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:10]
            ]

            if history:
                embed.add_field(name="History", value="\n".join(history), inline=False)

            if not isinstance(obj, models.Law) and obj.status.is_law:
                embed.set_footer(text="This is an active law.")

            context_hint = (
                f"-# {config.HINT} Check out [laws.democraciv.com]"
                f"(<https://laws.democraciv.com/{obj.model.lower()}/{obj.id}>) as well!"
            )
            await ctx.send(context_hint)
            view = mixin.ReadDocumentView(ctx=ctx)
            await ctx.send(embed=embed, view=view)
            do_continue = await view.prompt(silent=True)
            if do_continue:
                await self._show_bill_text(ctx, obj)
                return
        else:
            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

            context_hint = (
                f"-# {config.HINT} Check out [laws.democraciv.com]"
                f"(<https://laws.democraciv.com/{obj.model.lower()}/{obj.id}>) as well!"
            )
            await ctx.send(context_hint)
            await ctx.send(embed=embed)

    @app_commands.command(name="laws", description="List all active laws.")
    @app_commands.guild_only()
    async def laws_alias(self, interaction: discord.Interaction):
        await self.law_list.callback(self, interaction)

    @app_commands.command(name="bills", description="List all submitted bills.")
    @app_commands.guild_only()
    async def bills_alias(self, interaction: discord.Interaction):
        await self.bill_list.callback(self, interaction)

    @app_commands.command(name="motions", description="List all submitted motions.")
    @app_commands.guild_only()
    async def motions_alias(self, interaction: discord.Interaction):
        await self.motion_list.callback(self, interaction)


async def setup(bot):
    await bot.add_cog(LegalSlash(bot))
