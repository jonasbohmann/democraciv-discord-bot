import collections

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import config
from bot.utils import checks, context, converter, mixin, models, paginator, text
from bot.utils.converter import Fuzzy, FuzzySettings
from bot.utils.models import Motion, SessionStatus


class Motions(context.CustomCog, mixin.GovernmentMixin, name="Motion"):
    """List, search, edit, sponsor, and withdraw motions across the Senate and Commons."""

    @commands.group(
        name="motion",
        aliases=["motions", "mo"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def motion(
        self, ctx: context.CustomContext, *, motion_id: Fuzzy[Motion] = None
    ):
        """List all motions or get details about a single motion."""

        if motion_id is None:
            return await self._paginate_all_(ctx, model=models.Motion)

        return await self._detail_view(ctx, obj=motion_id)

    @motion.command(name="edit", aliases=["update", "e"])
    @checks.is_democraciv_guild()
    async def edit(self, ctx, *, motion_id: Fuzzy[Motion]):
        """Edit the title or content of a motion."""

        motion = motion_id
        house = self.get_house_for_object(motion)
        is_house_leadership = self.is_cabinet_for_house(ctx.author, house)

        if not is_house_leadership:
            if motion.submitter_id != ctx.author.id:
                return await ctx.send(
                    f"{config.NO} Only chamber leadership and the original submitter of a motion can edit it."
                )

            if motion.session.status is not SessionStatus.SUBMISSION_PERIOD:
                return await ctx.send(
                    f"{config.NO} You can only edit your motion if the session it was submitted in is still in "
                    f"Submission Period.\n{config.HINT} However, chamber leadership can edit your motion at any "
                    f"given time."
                )

        menu = text.EditModelMenu(
            ctx,
            choices_with_formatted_explanation={"title": "Title", "content": "Content"},
            title=f"{config.USER_INTERACTION_REQUIRED} What about {motion.name} (#{motion.id}) do you want to change?",
        )

        result = await menu.prompt()
        to_change = result.choices

        if not result.confirmed or True not in to_change.values():
            return

        if to_change["title"]:
            title = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new short **title** for the motion."
            )
        else:
            title = motion.title

        if to_change["content"]:
            content = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new **content** of the motion. If the motion is "
                f"inside a Google Docs document, just use a link to that for this."
            )
            paste = await self.bot.make_paste(content)

            if not paste:
                return await ctx.send(
                    f"{config.NO} The motion will not be updated, there was a problem with <https://mystb.in>. "
                    "Sorry, try again in a few minutes."
                )
        else:
            content = motion.description
            paste = motion._link

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit `{motion.name}` (#{motion.id})?"
        ):
            return await ctx.send("Cancelled.")

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

    @motion.command(name="sponsor", aliases=["cosponsor", "second"])
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def sponsor(self, ctx, motion_ids: Greedy[Motion]):
        """Show your support for one or multiple motions by sponsoring them."""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        failed = {}
        passed = []
        for motion in motion_ids:
            house = self.get_house_for_object(motion)

            if ctx.author.id == motion.submitter_id:
                failed[motion] = "The motion's author cannot sponsor their own motion."
                continue

            if ctx.author in motion.sponsors:
                failed[motion] = "You already sponsored this motion."
                continue

            if not self.can_member_sponsor_in_house(ctx.author, house):
                if house == "senate":
                    failed[motion] = "Only Senators can sponsor Senate motions."
                else:
                    failed[motion] = "Only Senators can sponsor this motion."
                continue

            if motion.session.closed_on:
                failed[motion] = (
                    "You can only sponsor motions if the session they were submitted in is still open."
                )
                continue

            passed.append(motion)

        if failed:
            await ctx.send(
                f":warning: The following motions cannot be sponsored.\n"
                + "\n".join(
                    f"-  **{motion.name}** (#{motion.id}): _{reason}_"
                    for motion, reason in failed.items()
                )
            )

        if not passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to sponsor the following motions?\n"
            + "\n".join(f"-  **{motion.name}** (#{motion.id})" for motion in passed)
        ):
            return await ctx.send("Cancelled.")

        for motion in passed:
            await self.bot.db.execute(
                "INSERT INTO motion_sponsor (motion_id, sponsor) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                motion.id,
                ctx.author.id,
            )

        await ctx.send(f"{config.YES} All motions were sponsored by you.")

    @motion.command(name="unsponsor", aliases=["usp"])
    @checks.is_democraciv_guild()
    @checks.is_citizen_if_multiciv()
    async def unsponsor(self, ctx: context.CustomContext, motion_ids: Greedy[Motion]):
        """Remove yourself from the list of sponsors of one or multiple motions."""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        failed = {}
        passed = []
        for motion in motion_ids:
            house = self.get_house_for_object(motion)

            if ctx.author not in motion.sponsors:
                failed[motion] = "You are not a sponsor of this motion."
                continue

            if motion.session.closed_on:
                failed[motion] = (
                    "You can only unsponsor motions if the session they were submitted in is still open."
                )
                continue

            passed.append(motion)

        if failed:
            await ctx.send(
                f":warning: The following motions cannot be unsponsored.\n"
                + "\n".join(
                    f"-  **{motion.name}** (#{motion.id}): _{reason}_"
                    for motion, reason in failed.items()
                )
            )

        if not passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to unsponsor the following motions?\n"
            + "\n".join(f"-  **{motion.name}** (#{motion.id})" for motion in passed)
        ):
            return await ctx.send("Cancelled.")

        for motion in passed:
            await self.bot.db.execute(
                "DELETE FROM motion_sponsor WHERE motion_id = $1 and sponsor = $2",
                motion.id,
                ctx.author.id,
            )

        await ctx.send(
            f"{config.YES} You were removed from the list of sponsors from all motions."
        )

    @motion.command(name="from", aliases=["f", "by"])
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
        """List all motions that a specific person or Political Party submitted."""

        return await self._from_person_model(
            ctx, model=models.Motion, member_or_party=person_or_party
        )

    @motion.command(name="search", aliases=["s"])
    async def search(self, ctx: context.CustomContext, *, query: str):
        """Search for a motion."""

        results = await self._search_model(ctx, model=models.Motion, query=query)
        pages = paginator.SimplePages(
            entries=results,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"Motions matching '{query}'",
            empty_message="Nothing found.",
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/motion>) as well!"
        )
        await pages.start(ctx)

        try:
            fts_pages = await self.prepare_full_text_search_paginator(
                ctx, query, index="motion"
            )
        except Exception:
            fts_pages = None

        if fts_pages:
            view = mixin.FullTextSearchView(ctx)
            delete_after = await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to perform a full-text search across all motions too? "
                f"This feature is a work-in-progress.\n{config.HINT} Known issue: This only shows 1 search result "
                f"per motion, even if there were more occurrences found.",
                view=view,
            )
            yes = await view.prompt(silent=True)

            if yes:
                await fts_pages.start(ctx)
                await delete_after.delete()

    @motion.command(name="withdraw", aliases=["w"])
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx: context.CustomContext, motion_ids: Greedy[Motion]):
        """Withdraw one or multiple motions from their current sessions."""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        failed = {}
        passed = []

        for motion in motion_ids:
            house = self.get_house_for_object(motion)

            if motion.session.closed_on:
                failed[motion] = (
                    "The session during which this motion was submitted is not open anymore."
                )
                continue

            if self.is_cabinet_for_house(ctx.author, house):
                passed.append(motion)
                continue

            if ctx.author.id != motion.submitter_id:
                failed[motion] = (
                    "Only chamber leadership and the original submitter of this motion can withdraw it."
                )
                continue

            if motion.session.status is not SessionStatus.SUBMISSION_PERIOD:
                failed[motion] = (
                    "The original submitter can only withdraw motions during the Submission Period."
                )
                continue

            passed.append(motion)

        if failed:
            await ctx.send(
                f":warning: The following motions cannot be withdrawn by you.\n"
                + "\n".join(
                    f"-  **{motion.name}** (#{motion.id}): _{reason}_"
                    for motion, reason in failed.items()
                )
            )

        if not passed:
            return

        if not await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to withdraw the following motions?\n"
            + "\n".join(f"-  **{motion.name}** (#{motion.id})" for motion in passed)
        ):
            return await ctx.send("Cancelled.")

        for motion in passed:
            await motion.withdraw()

        await ctx.send(f"{config.YES} All motions were withdrawn.")

        withdrawn_by_house = collections.defaultdict(list)
        for motion in passed:
            house = self.get_house_for_object(motion)
            if self.is_cabinet_for_house(ctx.author, house):
                continue

            withdrawn_by_house[house].append(f"-  **{motion.name}** (#{motion.id})")

        for house, formatted_motions in withdrawn_by_house.items():
            message = (
                f"The following motions were withdrawn by {ctx.author}.\n"
                f"{chr(10).join(formatted_motions)}"
            )

            for leader in self.get_cabinet_members_for_house(house):
                await self.bot.safe_send_dm(
                    target=leader,
                    reason="leg_session_withdraw",
                    message=message,
                )


async def setup(bot):
    await bot.add_cog(Motions(bot))
