import discord

from discord.ext import commands
from discord.utils import escape_markdown

from bot.utils import text, mixin, exceptions, context
from bot.config import mk


class Government(context.CustomCog, mixin.GovernmentMixin, name="Government"):
    """The current Government of {NATION_FULL_NAME}"""

    def get_justices(self):
        try:
            _justices = self.justice_role
        except exceptions.RoleNotFoundError:
            return None

        if isinstance(self.chief_justice, discord.Member):
            justices = [
                f"{justice.mention} {escape_markdown(str(justice))}"
                for justice in _justices.members
                if justice.id != self.chief_justice.id
            ]
            justices.insert(
                0,
                f"{self.chief_justice.mention} {escape_markdown(str(self.chief_justice))} **({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})**",
            )
            return justices
        else:
            return [
                f"{justice.mention} {escape_markdown(str(justice))}"
                for justice in _justices.members
            ]

    def get_judges(self):
        try:
            _judges = self.judge_role
        except exceptions.RoleNotFoundError:
            return None

        return [
            f"{judge.mention} {escape_markdown(str(judge))}"
            for judge in _judges.members
        ]

    @commands.command(
        name="legislature",
        aliases=["leg", "l"],
    )
    async def legislature(self, ctx: commands.Context):
        """MK13-specific information about the Commons and the Senate. See `-help commons` and `-help senate` for actual commands."""
        embeds = await self._build_legislature_info_embeds()
        for embed in embeds:
            await ctx.send(embed=embed)

    # todo oct-24: lots of duplicate code
    @commands.group(
        name="government",
        aliases=["gov", "g"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def government(self, ctx):
        """See all current members of Government"""
        embed = self._build_government_overview_embed()
        await ctx.send(embed=embed)

    def get_justices(self):
        try:
            _justices = self.justice_role
        except exceptions.RoleNotFoundError:
            return None

        if isinstance(self.chief_justice, discord.Member):
            justices = [
                f"{justice.mention} {escape_markdown(str(justice))}"
                for justice in _justices.members
                if justice.id != self.chief_justice.id
            ]
            justices.insert(
                0,
                f"{self.chief_justice.mention} {escape_markdown(str(self.chief_justice))} **({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})**",
            )
            return justices
        else:
            return [
                f"{justice.mention} {escape_markdown(str(justice))}"
                for justice in _justices.members
            ]

    def get_judges(self):
        try:
            _judges = self.judge_role
        except exceptions.RoleNotFoundError:
            return None

        return [
            f"{judge.mention} {escape_markdown(str(judge))}"
            for judge in _judges.members
        ]

    @commands.group(
        name="court",
        aliases=["sc", "courts", "j", "judicial"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def court(self, ctx):
        """Dashboard for {justice_term}s"""
        embed = self._build_court_overview_embed()
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Government(bot))
