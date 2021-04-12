import discord

from discord.ext import commands
from bot.utils import text, mixin, exceptions, context
from bot.config import mk


class SupremeCourt(context.CustomCog, mixin.GovernmentMixin, name=mk.MarkConfig.COURT_NAME):
    """Useful information about the {courts_term} of this nation."""

    def get_justices(self):
        try:
            _justices = self.justice_role
        except exceptions.RoleNotFoundError:
            return None

        if isinstance(self.chief_justice, discord.Member):
            justices = [justice.mention for justice in _justices.members if justice.id != self.chief_justice.id]
            justices.insert(
                0,
                f"{self.chief_justice.mention} ({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})",
            )
            return justices
        else:
            return [justice.mention for justice in _justices.members]

    def get_judges(self):
        try:
            _judges = self.judge_role
        except exceptions.RoleNotFoundError:
            return None

        return [judge.mention for judge in _judges.members]

    @commands.group(
        name="court", aliases=["sc", "courts", "j", "judicial"], case_insensitive=True, invoke_without_command=True
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
            name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s",
            value="\n".join(justices),
            inline=False,
        )

        if self.bot.mk.COURT_HAS_INFERIOR_COURT:
            embed.add_field(
                name=f"{self.bot.mk.COURT_INFERIOR_NAME} {self.bot.mk.COURT_JUDGE_NAME}s",
                value="\n".join(judges),
                inline=False,
            )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})"
                  f"\n[Submit a Case](https://forms.gle/ovDr3MsjTubuerZw9)\n"
                  f"[All Case Filings of the Supreme Court](https://docs.google.com/spreadsheets/d/1BuBk7n-_"
                  f"TSHPEQIT9fGyk7z9RRQxGGrEc-gC5Vc2DkI/edit?usp=sharing)",
            inline=False,
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
