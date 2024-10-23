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

    # todo oct-24: lots of duplicate code
    @commands.group(
        name="government",
        aliases=["gov", "g"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def government(self, ctx):
        """See all current members of Government"""

        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Government of {self.bot.mk.NATION_FULL_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        justices = self.get_justices() or ["-"]

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.pm_term}: {self.prime_minister.mention} {escape_markdown(str(self.prime_minister))}"
            )
        else:
            minister_value.append(f"{self.bot.mk.pm_term}: -")

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}"
            )
        else:
            minister_value.append(f"{self.bot.mk.lt_pm_term}: -")

        attorney_general = self._safe_get_member(mk.DemocracivRole.ATTORNEY_GENERAL)

        if isinstance(attorney_general, discord.Member):
            minister_value.append(
                f"Attorney General: {attorney_general.mention} {escape_markdown(str(attorney_general))}"
            )
        else:
            minister_value.append(f"Attorney General: -")

        supreme_commander = self._safe_get_member(mk.DemocracivRole.SUPREME_COMMANDER)

        if isinstance(supreme_commander, discord.Member):
            minister_value.append(
                f"Supreme Commander: {supreme_commander.mention} {escape_markdown(str(supreme_commander))}"
            )
        else:
            minister_value.append(f"Supreme Commander: -")

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=True,
        )

        try:
            ministers = self.bot.get_democraciv_role(mk.DemocracivRole.MINISTER)
            ministers = [
                f"{m.mention} {escape_markdown(str(m))}" for m in ministers.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            ministers = ["-"]

        try:
            governors = self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNOR)
            governors = [
                f"{g.mention} {escape_markdown(str(g))}" for g in governors.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            governors = ["-"]

        embed.add_field(
            name=f"{self.bot.mk.minister_term}s ({len(ministers) if ministers[0] != "-" else 0})",
            value="\n".join(ministers),
            inline=False,
        )

        embed.add_field(
            name=f"{self.bot.mk.governor_term}s ({len(governors) if governors[0] != "-" else 0})",
            value="\n".join(governors),
            inline=False,
        )

        embed.add_field(
            name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s ({len(justices) if justices[0] != "-" else 0})",
            value="\n".join(justices),
            inline=False,
        )

        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(
                f"{self.bot.mk.speaker_term}: {self.speaker.mention} {escape_markdown(str(self.speaker))}"
            )
        else:
            speaker_value.append(f"{self.bot.mk.speaker_term}: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(
                f"{self.bot.mk.vice_speaker_term}: {self.vice_speaker.mention} {escape_markdown(str(self.vice_speaker))}"
            )
        else:
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: -")

        embed.add_field(
            name=f"{self.bot.mk.LEGISLATURE_NAME} {self.bot.mk.LEGISLATURE_CABINET_NAME}",
            value="\n".join(speaker_value),
            inline=False,
        )

        try:
            legislators = self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)
            legislators = [
                f"{l.mention} {escape_markdown(str(l))}" for l in legislators.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            legislators = ["-"]

        embed.add_field(
            name=f"{self.bot.mk.legislator_term}s ({len(legislators) if legislators[0] != "-" else 0})",
            value="\n".join(legislators),
            inline=False,
        )

        try:
            members_of_gov = self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNMENT)
            members_of_gov = [
                f"{mg.mention} {escape_markdown(str(mg))}"
                for mg in members_of_gov.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            members_of_gov = ["-"]

        # embed.add_field(
        #    name=f"Total Members of Government",
        #    value=f"{len(members_of_gov)}" if members_of_gov[0] != "-" else "0",
        #    inline=False,
        # )

        embed.description = (
            f"There are {len(members_of_gov)} members of government in total."
        )

        # embed.add_field(
        #    name="Links",
        #    value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})",
        #    inline=False,
        # )

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
            f"\n[Submit a Case](https://forms.gle/uhb9MP785J15f9vYA)\n"
            f"[All Case Filings of the Supreme Court](https://bot-placeholder.democraciv.com/)\n[Judicial Procedure](https://docs.google.com/document/d/14kqyDHeY5aAqw38Mr-d-b-Lu2RRVEHSBoLeFg9xy-1g/edit?usp=sharing)",
            inline=False,
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Government(bot))
