import collections

import discord

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import config
from bot.utils import (
    checks,
    context,
    converter,
    exceptions,
    mixin,
    models,
    paginator,
    text,
)
from bot.utils.converter import Fuzzy, FuzzySettings
from bot.utils.models import Bill, SessionStatus


class Bills(context.CustomCog, mixin.GovernmentMixin, name="Bill"):
    """List, search, edit, sponsor, and withdraw bills across the Senate and Commons."""

    @commands.group(
        name="bill",
        aliases=["b", "bills"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def bill(self, ctx: context.CustomContext, *, bill_id: Fuzzy[Bill] = None):
        """List all bills or get details about a single bill."""

        if bill_id is None:
            return await self._paginate_all_(ctx, model=models.Bill)

        return await self._detail_view(ctx, obj=bill_id)

    @bill.command(name="synchronize", aliases=["sync", "refresh", "synchronise"])
    @checks.is_democraciv_guild()
    async def synchronize(self, ctx, bill_ids: Greedy[models.Bill]):
        """Synchronize one or multiple bills with the latest Google Docs title and content."""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        failed = {}
        passed = []

        for bill in bill_ids:
            house = self.get_house_for_object(bill)

            if not self.is_cabinet_for_house(ctx.author, house):
                failed[bill] = "Only chamber leadership can synchronize this bill."
                continue

            passed.append(bill)

        if failed:
            await ctx.send(
                f":warning: The following bills cannot be synchronized.\n"
                + "\n".join(
                    f"-  **{bill.name}** (#{bill.id}): _{reason}_"
                    for bill, reason in failed.items()
                )
            )

        if not passed:
            return

        sync_errors = []

        async with ctx.typing():
            for bill in passed:
                success = await self._synchronize_bill(bill)
                if not success:
                    sync_errors.append(
                        f"Error synchronizing Bill #{bill.id} - {bill.name}. Skipping update."
                    )

        message = f"{config.YES} Synchronized {len(passed) - len(sync_errors)}/{len(passed)} bills with Google Docs."

        if sync_errors:
            message = f"{chr(10).join(sync_errors)}\n\n{message}"

        await ctx.send(message)

    @bill.command(name="bulkedit", aliases=["bulkupdate", "bulkchange", "be"])
    @checks.is_democraciv_guild()
    async def bulkedit(self, ctx: context.CustomContext):
        """Bulk edit the Google Docs links of multiple bills at once."""

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with a list of bills and their respective new links. "
            f"First, type the bill's id (like `12`), then type a space, and then the new link for that bill.\n"
            f"{config.HINT} For each bill/link pair, use a new line like in the image below.\n\n"
            "https://cdn.discordapp.com/attachments/759894147628269588/843804262777225226/bulkbill.PNG",
        )

        bulks = await ctx.input()
        skipped = []
        split = bulks.splitlines()

        async with ctx.typing():
            for i, bill_link in enumerate(split, start=1):
                bill_link = bill_link.strip()

                try:
                    bill_id, link = bill_link.split(" ")
                except ValueError:
                    skipped.append(
                        f"  - Incorrect input formatting on line {i}. See the image I sent for the correct formatting."
                    )
                    continue

                try:
                    bill = await Bill.convert(ctx, bill_id)
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
                        f"  - The new link for Bill #{bill_id} you gave me is not a valid Google Docs link."
                    )
                    continue

                try:
                    await bill.update_link(link)
                except exceptions.DemocracivBotException as error:
                    skipped.append(f"  - {error.message}")

        message = f"{config.YES} Changed the link of {len(split) - len(skipped)}/{len(split)} bills."

        if skipped:
            message = (
                f":warning: I skipped changing the link of some bills, see the errors below:\n\n"
                f"{chr(10).join(skipped)}\n\n{message}"
            )

        await ctx.send(message)

    @bill.command(name="edit", aliases=["update", "e", "change"])
    @checks.is_democraciv_guild()
    async def edit(self, ctx: context.CustomContext, *, bill_id: Fuzzy[Bill]):
        """Edit the Google Docs link or summary of a bill."""

        bill = bill_id
        house = self.get_house_for_object(bill)
        is_house_leadership = self.is_cabinet_for_house(ctx.author, house)

        if not is_house_leadership and bill.submitter_id != ctx.author.id:
            return await ctx.send(
                f"{config.NO} Only chamber leadership and the original submitter of a bill can edit it."
            )

        menu = text.EditModelMenu(
            ctx,
            choices_with_formatted_explanation={
                "link": "Google Docs Link",
                "description": "Short Summary",
            },
            title=f"{config.USER_INTERACTION_REQUIRED} What about {bill.name} (#{bill.id}) do you want to change?",
        )

        result = await menu.prompt()
        to_change = result.choices

        if not result.confirmed or True not in to_change.values():
            return

        link = None
        description = None

        if to_change["link"]:
            if (
                not is_house_leadership
                and bill.session.status is not SessionStatus.SUBMISSION_PERIOD
            ):
                return await ctx.send(
                    f"{config.NO} You can only change the link to your bill if the session it was submitted in is "
                    f"still in Submission Period.\n{config.HINT} However, chamber leadership can change the link of "
                    f"any bill at any given time."
                )

            link = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new Google Docs link to the bill.\n"
                f"{config.HINT} You can change the link of multiple bills at once with "
                f"`{config.BOT_PREFIX}bill bulkedit`."
            )

            if not self.is_google_doc_link(link):
                link = None
                await ctx.send(
                    f"{config.NO} That doesn't look like a Google Docs URL. The link to the bill will not be changed."
                )

        if to_change["description"]:
            description = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with a new **short** summary of what the bill does.",
                timeout=400,
                return_cleaned=True,
            )

            if not description:
                description = "*No summary provided by submitter.*"

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit `{bill.name}` (#{bill.id})?"
        ):
            return await ctx.send("Cancelled.")

        if link:
            changed_bill = models.Bill(
                id=bill.id,
                bot=self.bot,
                link=link,
                submitter_description=description or bill.description,
            )
            await changed_bill.update_link(link)

        if description:
            await self.bot.db.execute(
                "UPDATE bill SET submitter_description = $1 WHERE id = $2",
                description,
                bill.id,
            )

        await ctx.send(f"{config.YES} Bill #{bill.id} `{bill.name}` was updated.")

    @bill.command(name="history", aliases=["h"])
    async def history(self, ctx: context.CustomContext, *, bill_id: Fuzzy[Bill]):
        """See when a bill was introduced, passed, vetoed, or repealed."""

        fmt_history = [
            f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}   "
            f"({entry.after.emojified_status(verbose=False)})"
            for entry in bill_id.history
        ]
        fmt_history.insert(
            0, f"[Link to the Google Docs document of this Bill]({bill_id.link}).\n"
        )

        pages = paginator.SimplePages(
            entries=fmt_history,
            author=f"{bill_id.name} (#{bill_id.id})",
            per_page=12,
            icon=self.bot.mk.NATION_ICON_URL,
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill/{bill_id.id}>) as well!"
        )
        await pages.start(ctx)

    @bill.command(name="read", aliases=["text", "txt", "content"])
    async def read(self, ctx: context.CustomContext, *, bill_id: Fuzzy[Bill]):
        """Read the content of a bill."""

        await self._show_bill_text(ctx, bill_id)

    @bill.command(name="search", aliases=["s"])
    async def search(self, ctx: context.CustomContext, *, query: str):
        """Search for a bill."""

        results = await self._search_model(ctx, model=models.Bill, query=query)
        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Bills matching '{query}'",
            empty_message="Nothing found.",
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill>) as well!"
        )
        await pages.start(ctx)

        try:
            fts_pages = await self.prepare_full_text_search_paginator(ctx, query)
        except Exception:
            fts_pages = None

        if fts_pages:
            view = mixin.FullTextSearchView(ctx)
            delete_after = await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to perform a full-text search across all bills too? "
                f"This feature is a work-in-progress.\n{config.HINT} Known issue: This only shows 1 search result "
                f"per bill, even if there were more occurrences found.",
                view=view,
            )
            yes = await view.prompt(silent=True)

            if yes:
                await fts_pages.start(ctx)
                await delete_after.delete()

    @bill.command(name="advanced-search", aliases=["semantic-search", "asearch", "as"])
    async def aisearch(self, ctx, *, query):
        """Experimental bill searching."""

        if self.bot.mk.IS_MULTICIV:
            return await ctx.send(
                f"{config.NO} This command is disabled during Multiciv MKs."
            )

        await ctx.send(
            f":warning: This is a work in progress. The search on [laws.democraciv.com](<https://laws.democraciv.com/bill>) will probably work a lot better."
        )

        async with ctx.typing():
            response = await self.bot.api_request(
                "POST",
                "document/search",
                json={
                    "question": query,
                    "index": "bill",
                    "is_law": False,
                    "semantic_ratio": 1.0,
                },
            )

        if not response or not response["result"]["hits"]:
            return await ctx.send(
                f"{config.NO} I couldn't find anything that matches `{query}`. Sorry!"
            )

        formatted = [
            "This feature is a work-in-progress.\nKnown issue: This only shows 1 search result per bill, even if there were more occurrences found.\n"
        ]

        for hit in response["result"]["hits"]:
            try:
                bill = await models.Bill.convert(ctx, hit["id"])
            except Exception:
                continue

            trimmed = hit["_formatted"]["content"].strip()
            txt = discord.utils.escape_markdown(trimmed)
            txt = txt.replace("<DBS>", "[**")
            txt = txt.replace(
                "<DBE>", "**](https://this-is-not-a-real-url.democraciv.com)"
            )
            formatted.append(f"**__{bill.formatted}__**")
            formatted.append(f"{txt}\n")

        pages = paginator.SimplePages(
            entries=formatted,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"[BETA] Advanced search results for '{query}'",
        )

        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill>) as well!"
        )
        await ctx.send(
            ":warning: This only shows 1 search result per bill, even if there were more occurrences found in that bill."
        )
        await pages.start(ctx)

    @bill.command(name="from", aliases=["f", "by"])
    async def from_person(
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
        """List all bills that a specific person or Political Party submitted."""

        return await self._from_person_model(
            ctx, member_or_party=person_or_party, model=models.Bill
        )

    @bill.command(name="sponsor", aliases=["cosponsor", "second"])
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def sponsor(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Show your support for one or multiple bills by sponsoring them."""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.sponsor
        )

        def filter_sponsor(_ctx, bill, **kwargs):
            if _ctx.author.id == bill.submitter_id:
                return "The bill's author cannot sponsor their own bill."

            if _ctx.author in bill.sponsors:
                return "You already sponsored this bill."

            house = self.get_house_for_object(bill)
            if not self.can_member_sponsor_in_house(_ctx.author, house):
                if house == "senate":
                    return "Only Senators can sponsor Senate bills."

                return "Only Senators can sponsor this bill."

        await consumer.filter(filter_func=filter_sponsor, sponsor=ctx.author)

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills cannot be sponsored.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to sponsor the following bills?\n"
            f"{consumer.passed_formatted}"
        ):
            return await ctx.send("Cancelled.")

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(f"{config.YES} All bills were sponsored by you.")

    @bill.command(name="unsponsor", aliases=["usp"])
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def unsponsor(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Remove yourself from the list of sponsors of one or multiple bills."""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.unsponsor
        )

        def filter_unsponsor(_ctx, bill, **kwargs):
            if _ctx.author not in bill.sponsors:
                return "You are not a sponsor of this bill."

        await consumer.filter(filter_func=filter_unsponsor, sponsor=ctx.author)

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills cannot be unsponsored.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to remove yourself from the list of "
            f"sponsors of the following bills?\n{consumer.passed_formatted}"
        ):
            return await ctx.send("Cancelled.")

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(
            f"{config.YES} You were removed from the list of sponsors from all bills."
        )

    @bill.command(name="withdraw", aliases=["w"])
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Withdraw one or multiple bills from their current sessions."""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.withdraw
        )

        def verify_object(_ctx, bill, **kwargs):
            house = self.get_house_for_object(bill)

            if bill.session.closed_on:
                return "The session during which this bill was submitted is not open anymore."

            if self.is_cabinet_for_house(_ctx.author, house):
                return

            if _ctx.author.id != bill.submitter_id:
                return "Only chamber leadership and the original submitter of this bill can withdraw it."

            if bill.session.status is not SessionStatus.SUBMISSION_PERIOD:
                return "The original submitter can only withdraw bills during the Submission Period."

        await consumer.filter(filter_func=verify_object)

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills cannot be withdrawn by you.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to withdraw the following bills?\n"
            f"{consumer.passed_formatted}"
        ):
            return await ctx.send("Cancelled.")

        await consumer.consume()
        await ctx.send(f"{config.YES} All bills were withdrawn.")

        withdrawn_by_house = collections.defaultdict(list)
        for bill in consumer.passed:
            house = self.get_house_for_object(bill)
            if self.is_cabinet_for_house(ctx.author, house):
                continue

            withdrawn_by_house[house].append(f"-  **{bill.name}** (#{bill.id})")

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

    @bill.command(name="resubmit", aliases=["rs"])
    @checks.is_citizen_if_multiciv()
    async def resubmit(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Resubmit failed bills to the current submission-period session in their origin house."""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(
            ctx=ctx, objects=bill_ids, action=models.BillStatus.resubmit
        )
        await consumer.filter(resubmitter=ctx.author)

        if consumer.failed:
            await ctx.send(
                f":warning: The following bills cannot be resubmitted.\n{consumer.failed_formatted}"
            )

        passed = set(consumer.passed)
        target_sessions = {}
        failed = {}

        for house in {bill.origin_house for bill in passed}:
            sessions = await self.get_open_leg_sessions(
                house=house, status=models.SessionStatus.SUBMISSION_PERIOD
            )

            if len(sessions) == 0:
                for bill in list(passed):
                    if bill.origin_house == house:
                        failed[bill] = (
                            f"There is no {bill.origin_house_name} session in "
                            "Submission Period right now."
                        )
                        passed.remove(bill)
                continue

            if len(sessions) == 1:
                target_sessions[house] = sessions[0]
                continue

            target_session = await self.prompt_for_leg_session(
                ctx,
                sessions=sessions,
                action=f"resubmit {models.display_house_name(house)} bills to",
            )
            if target_session is None:
                return
            target_sessions[house] = target_session

        if failed:
            await ctx.send(
                f":warning: The following bills cannot be resubmitted.\n"
                + "\n".join(
                    f"-  **{bill.name}** (#{bill.id}): _{reason}_"
                    for bill, reason in failed.items()
                )
            )

        if not passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to resubmit the following bills to the "
            f"current submission-period session in their origin house?\n"
            + "\n".join(f"-  **{bill.name}** (#{bill.id})" for bill in passed)
        ):
            return await ctx.send("Cancelled.")

        for bill in passed:
            await bill.status.resubmit(
                resubmitter=ctx.author,
                target_session=target_sessions[bill.origin_house],
            )

        await ctx.send(
            f"{config.YES} All bills were resubmitted to their origin-house submission session."
        )


async def setup(bot):
    await bot.add_cog(Bills(bot))
