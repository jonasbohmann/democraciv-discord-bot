import datetime
import collections

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config, mk
from bot.slash import forms
from bot.slash import context as slash_context
from bot.slash import checks as slash_checks
from bot.slash import transformers, ui
from bot.utils import converter, exceptions, mixin, models

LawOption = app_commands.Transform[models.Law, transformers.LawTransformer]
BillOption = app_commands.Transform[models.Bill, transformers.BillTransformer]
MotionOption = app_commands.Transform[models.Motion, transformers.MotionTransformer]
PartyOption = app_commands.Transform[
    converter.PoliticalParty, transformers.PoliticalPartyTransformer
]


class ReadDocumentButton(discord.ui.Button):
    def __init__(self, cog: "LegalSlash", bill: models.Bill):
        super().__init__(
            label="Read Document",
            style=discord.ButtonStyle.primary,
            emoji="\U0001f4c3",
        )
        self.cog = cog
        self.bill = bill

    async def callback(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=self.bill.model.lower(),
            ephemeral=True,
        )
        await ctx.defer(ephemeral=True)
        await self.cog._read_document(
            ctx,
            bill=self.bill,
            title=f"{self.bill.name} (#{self.bill.id})",
        )


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

    async def _list_model(
        self,
        ctx: slash_context.InteractionContext,
        *,
        model,
        title: str,
        empty_message: str,
        per_page: int = None,
    ):
        if model is models.Bill:
            records = await self.bot.db.fetch("SELECT id FROM bill ORDER BY id;")
        elif model is models.Law:
            records = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE status = $1 ORDER BY id;",
                models.BillIsLaw.flag.value,
            )
        else:
            records = await self.bot.db.fetch("SELECT id FROM motion ORDER BY id;")

        entries = []
        for record in records:
            obj = await model.convert(ctx, record["id"])
            entries.append(f"* {obj.formatted}")

        await ui.send_pages(
            ctx,
            entries=entries,
            title=title,
            subtitle=f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com>) as well.",
            links=self._general_links(),
            empty_message=empty_message,
            per_page=per_page,
        )

    async def _search(
        self,
        ctx: slash_context.InteractionContext,
        *,
        model,
        query: str,
        title: str,
        site_path: str,
    ):
        results = await self._search_model(ctx, model=model, query=query)
        await ui.send_pages(
            ctx,
            entries=results,
            title=title,
            subtitle=f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{site_path}>) as well.",
            links=self._general_links(site_path),
            empty_message="Nothing found.",
        )

    def _general_links(self, site_path: str = None):
        laws_url = "https://laws.democraciv.com"
        if site_path:
            laws_url = f"{laws_url}/{site_path}"

        return [
            ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
            ui.LayoutLink("Laws Site", laws_url, "\U0001f517"),
        ]

    def _object_links(self, obj: models.Bill | models.Motion | models.Law):
        return [
            ui.LayoutLink("Document", obj.link, "\U0001f4c3"),
            ui.LayoutLink(
                "laws.democraciv.com",
                f"https://laws.democraciv.com/{obj.model.lower()}/{obj.id}",
                "\U0001f517",
            ),
            ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
        ]

    async def _from_model(
        self,
        ctx: slash_context.InteractionContext,
        *,
        model,
        member: discord.User = None,
        party: converter.PoliticalParty = None,
    ):
        if member is not None and party is not None:
            return await ctx.send(
                f"{config.NO} Choose either a member or a party, not both.",
                ephemeral=True,
            )

        target = party or member or ctx.author
        submit_term = "written" if model is models.Law else "submitted"
        per_page = 12 if model is models.Motion else None

        if isinstance(target, converter.PoliticalParty):
            ids = [person.id for person in target.role.members]
            target_name = target.role.name
            title = f"{model.__name__}s from members of {target_name}"
            empty_message = (
                f"No member of {target_name} has {submit_term} a "
                f"{model.__name__.lower()} yet."
            )
        else:
            ids = [target.id]
            target_name = getattr(target, "display_name", str(target))
            title = f"{model.__name__}s from {target_name}"
            empty_message = (
                f"{target_name} hasn't {submit_term} any "
                f"{model.__name__.lower()}s yet."
            )

        if model is models.Bill:
            records = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) ORDER BY id",
                ids,
            )
            site_path = "bill"
        elif model is models.Law:
            records = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) AND status = $2 ORDER BY id",
                ids,
                models.BillIsLaw.flag.value,
            )
            site_path = "law"
        else:
            records = await self.bot.db.fetch(
                "SELECT id FROM motion WHERE submitter = ANY($1::bigint[]) ORDER BY id",
                ids,
            )
            site_path = "motion"

        entries = []
        for record in records:
            obj = await model.convert(ctx, record["id"])
            entries.append(f"* {obj.formatted}")

        await ui.send_pages(
            ctx,
            entries=entries,
            title=title,
            subtitle=f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{site_path}>) as well.",
            links=self._general_links(site_path),
            empty_message=empty_message,
            per_page=per_page,
        )

    def _detail_sections(
        self, obj: models.Bill | models.Motion | models.Law
    ) -> list[ui.LayoutSection]:
        sections = [
            ui.LayoutSection("Summary", obj.description or "*No summary provided.*")
        ]

        submitter = obj.submitter
        submitted_by = (
            f"{submitter.mention} {submitter}"
            if submitter is not None
            else "*Unknown Person*"
        )
        sections.append(ui.LayoutSection("Submitter", submitted_by))

        if isinstance(obj, models.Bill) and not isinstance(obj, models.Law):
            bill_lines = []

            if obj.session.house in models.HOUSE_NAMES:
                bill_lines.append(f"Orig. in Chamber: {obj.origin_house_name}")
                bill_lines.append(f"Type: {obj.type_name}")
            else:
                bill_lines.append(f"Vetoable: {'Yes' if obj.is_vetoable else 'No'}")

            bill_lines.append(f"Status: {obj.status.emojified_status(verbose=True)}")

            if obj.executive_deadline_at is not None:
                timestamp = int(
                    obj.executive_deadline_at.replace(
                        tzinfo=datetime.timezone.utc
                    ).timestamp()
                )
                bill_lines.append(f"Executive Deadline: <t:{timestamp}:R>")

            sections.append(ui.LayoutSection("Bill Details", "\n".join(bill_lines)))

        if getattr(obj, "sponsors", None):
            sponsors = "\n".join(
                f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors
            )
            sections.append(ui.LayoutSection("Sponsors", sponsors))

        if not isinstance(obj, models.Motion):
            history = [
                f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:10]
            ]

            if history:
                sections.append(ui.LayoutSection("History", "\n".join(history)))

        sections.append(
            ui.LayoutSection(
                "Links",
                f"[{obj.name}]({obj.link})\n"
                f"[laws.democraciv.com](https://laws.democraciv.com/{obj.model.lower()}/{obj.id})",
            )
        )
        return sections

    async def _show_detail(
        self,
        ctx: slash_context.InteractionContext,
        *,
        obj: models.Bill | models.Motion | models.Law,
    ):
        actions = []
        if not isinstance(obj, models.Motion):
            actions.append(ReadDocumentButton(self, obj))

        await ui.send_static(
            ctx,
            title=f"{obj.name} (#{obj.id})",
            sections=self._detail_sections(obj),
            links=self._object_links(obj),
            action_items=actions,
        )

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

    async def _resubmit_bill(self, ctx, bill: models.Bill):
        consumer = models.LegalConsumer(
            ctx=ctx, objects=[bill], action=models.BillStatus.resubmit
        )
        await consumer.filter(resubmitter=ctx.author)

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

        await consumer.consume(resubmitter=ctx.author)
        await ctx.send(
            f"{config.YES} Bill #{bill.id} was resubmitted to its origin-house submission session."
        )

    async def _sponsor_motion(self, ctx, motion: models.Motion):
        house = self.get_house_for_object(motion)
        active_session = await self.get_active_leg_session(house=house)
        failed = None

        if ctx.author.id == motion.submitter_id:
            failed = "The motion's author cannot sponsor their own motion."
        elif ctx.author in motion.sponsors:
            failed = "You already sponsored this motion."
        elif not self.can_member_sponsor_in_house(ctx.author, house):
            failed = "Only Senators can sponsor Senate motions."
        elif not active_session or motion.session.id != active_session.id:
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
        house = self.get_house_for_object(motion)
        active_session = await self.get_active_leg_session(house=house)
        failed = None

        if ctx.author not in motion.sponsors:
            failed = "You are not a sponsor of this motion."
        elif not active_session or motion.session.id != active_session.id:
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

    async def _read_document(
        self,
        ctx: slash_context.InteractionContext,
        *,
        bill: models.Bill,
        title: str,
    ):
        leader_term = self.get_primary_leader_term_for_house(
            getattr(getattr(bill, "session", None), "house", None)
        )
        entries = (
            bill.content or "*No cached document content available.*"
        ).splitlines()
        entries.insert(
            0,
            f"[Link to the Google Docs document]({bill.link})\n"
            f"*Am I showing you outdated or wrong text? Tell the {leader_term} to synchronize this text "
            f"with `/bill synchronize`.*\n",
        )
        await ui.send_pages(
            ctx,
            entries=entries,
            title=title,
            subtitle=f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill/{bill.id}>) as well.",
            links=self._object_links(bill),
            empty_message="*No cached document content available.*",
        )

    @law.command(name="list", description="List all active laws.")
    async def law_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        await self._list_model(
            ctx,
            model=models.Law,
            title=f"All Laws in {self.bot.mk.NATION_NAME}",
            empty_message="There are no laws yet.",
        )

    @law.command(name="from", description="List laws submitted by a member or party.")
    @app_commands.describe(
        member="Member or user to list laws from.",
        party="Political party to list laws from.",
    )
    async def law_from(
        self,
        interaction: discord.Interaction,
        member: discord.User = None,
        party: PartyOption = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer()
        await self._from_model(ctx, model=models.Law, member=member, party=party)

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
        await self._search(
            ctx,
            model=models.Law,
            query=query,
            title=f"Laws matching '{query}'",
            site_path="law",
        )

    @law.command(name="read", description="Read the cached text of a law.")
    @app_commands.describe(law="Law ID or title")
    async def law_read(self, interaction: discord.Interaction, law: LawOption):
        ctx = slash_context.from_interaction(interaction, command_name="law")
        await ctx.defer(ephemeral=True)
        await self._read_document(ctx, bill=law, title=f"{law.name} (#{law.id})")

    @bill.command(name="list", description="List all submitted bills.")
    async def bill_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._list_model(
            ctx,
            model=models.Bill,
            title="All Submitted Bills - Senate & Commons",
            empty_message="No one has submitted any bills yet.",
        )

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

        entries = [
            f"* <t:{int(entry.date.timestamp())}:D> - "
            f"{entry.note if entry.note else entry.after} "
            f"({entry.after.emojified_status(verbose=False)})"
            for entry in bill.history
        ]
        entries.insert(0, f"[Link to the Google Docs document]({bill.link}).\n")
        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"{bill.name} (#{bill.id})",
            subtitle=f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill/{bill.id}>) as well.",
            links=self._object_links(bill),
            empty_message="No history entries found.",
            per_page=12,
        )

    @bill.command(name="read", description="Read the cached text of a bill.")
    @app_commands.describe(bill="Bill ID or title")
    async def bill_read(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer(ephemeral=True)
        await self._read_document(ctx, bill=bill, title=f"{bill.name} (#{bill.id})")

    @bill.command(name="search", description="Search bills.")
    @app_commands.describe(query="At least 3 characters to search for")
    async def bill_search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._search(
            ctx,
            model=models.Bill,
            query=query,
            title=f"Bills matching '{query}'",
            site_path="bill",
        )

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
        await self._from_model(ctx, model=models.Bill, member=member, party=party)

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
    @app_commands.describe(bill="Bill ID or title")
    async def bill_resubmit(self, interaction: discord.Interaction, bill: BillOption):
        ctx = slash_context.from_interaction(interaction, command_name="bill")
        await ctx.defer()
        await self._resubmit_bill(ctx, bill)

    @motion.command(name="list", description="List all submitted motions.")
    async def motion_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="motion")
        await ctx.defer()
        await self._list_model(
            ctx,
            model=models.Motion,
            title="All Submitted Motions - Senate & Commons",
            empty_message="No one has submitted any motions yet.",
            per_page=12,
        )

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
        await self._search(
            ctx,
            model=models.Motion,
            query=query,
            title=f"Motions matching '{query}'",
            site_path="motion",
        )

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
        await self._from_model(ctx, model=models.Motion, member=member, party=party)

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


async def setup(bot):
    await bot.add_cog(LegalSlash(bot))
