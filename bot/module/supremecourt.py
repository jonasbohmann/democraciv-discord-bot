import discord

from discord.ext import commands
from discord.utils import escape_markdown

from bot.utils import text, mixin, exceptions, context
from bot.config import mk


class SupremeCourt(
    context.CustomCog, mixin.GovernmentMixin, name=mk.MarkConfig.COURT_NAME
):
    """Useful information about the {courts_term} of this nation."""

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
        """Dashboard for {justice_term}"""

        embed = text.SafeEmbed()
        embed.set_author(
            name=f"{self.bot.mk.courts_term} of {self.bot.mk.NATION_FULL_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        justices = self.get_justices() or ["-"]
        judges = self.get_judges() or ["-"]

        embed.add_field(
            name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s ({len(justices) if justices[0] != "-" else 0})",
            value="\n".join(justices),
            inline=False,
        )

        if self.bot.mk.COURT_HAS_INFERIOR_COURT:
            embed.add_field(
                name=f"{self.bot.mk.COURT_INFERIOR_NAME} {self.bot.mk.COURT_JUDGE_NAME}s ({len(judges) if judges[0] != "-" else 0})",
                value="\n".join(judges),
                inline=False,
            )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})"
            f"\n[Submit a Case](https://bot-placeholder.democraciv.com/)\n"
            f"[All Case Filings of the Supreme Court](https://bot-placeholder.democraciv.com/)\n[Judicial Procedure](https://bot-placeholder.democraciv.com/)",
            inline=False,
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SupremeCourt(bot))
