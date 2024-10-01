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

        # if isinstance(self.lt_prime_minister, discord.Member):
        #    minister_value.append(f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}")
        # else:
        #    minister_value.append(f"{self.bot.mk.lt_pm_term}: -")

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=False,
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
            inline=True,
        )

        embed.add_field(
            name=f"{self.bot.mk.governor_term}s ({len(governors) if governors[0] != "-" else 0})",
            value="\n".join(governors),
            inline=True,
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
            inline=True,
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
            inline=True,
        )

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is None:
            current_session_value = "There currently is no open session."
        else:
            current_session_value = (
                f"Session #{active_leg_session.id} - {active_leg_session.status.value}"
            )

        embed.add_field(
            name=f"Current {self.bot.mk.LEGISLATURE_NAME} Session",
            value=current_session_value,
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

        embed.add_field(
            name=f"Total Members of Government ({len(members_of_gov) if members_of_gov[0] != "-" else 0})",
            value="\n".join(members_of_gov),
            inline=False,
        )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})",
            inline=False,
        )

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
            f"\n[Submit a Case](https://bot-placeholder.democraciv.com/)\n"
            f"[All Case Filings of the Supreme Court](https://bot-placeholder.democraciv.com/)\n[Judicial Procedure](https://bot-placeholder.democraciv.com/)",
            inline=False,
        )

        await ctx.send(embed=embed)

    MINISTRY_ALIASES = [
        "min",
        "exec",
        "minister",
        "ministry",
        "ministers",
        "governors",
        "governor",
    ]

    try:
        MINISTRY_ALIASES.remove(mk.MarkConfig.MINISTRY_COMMAND.lower())
    except ValueError:
        pass

    @commands.group(
        name=mk.MarkConfig.MINISTRY_COMMAND,
        aliases=MINISTRY_ALIASES,
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def ministry(self, ctx):
        """Dashboard for {minister_term}"""

        # """Dashboard for {minister_term} with important links and updates on new bills"""

        embed = text.SafeEmbed()
        embed.set_author(
            icon_url=self.bot.mk.NATION_ICON_URL,
            name=f"The {self.bot.mk.MINISTRY_NAME} of {self.bot.mk.NATION_FULL_NAME}",
        )

        # pretty_bills = await self.get_pretty_vetoes()

        # if not pretty_bills:
        #    pretty_bills = "There are no new bills to vote on."
        # else:
        #    pretty_bills = (
        #        f"You can vote on new bills, check `{config.BOT_PREFIX}{mk.MarkConfig.MINISTRY_COMMAND} bills`."
        #    )

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.pm_term}: {self.prime_minister.mention} {escape_markdown(str(self.prime_minister))}"
            )
        else:
            minister_value.append(f"{self.bot.mk.pm_term}: -")

        # if isinstance(self.lt_prime_minister, discord.Member):
        #    minister_value.append(f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}")
        # else:
        #    minister_value.append(f"{self.bot.mk.lt_pm_term}: -")

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=False,
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
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})\n"
            f"[Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})",
            inline=False,
        )

        # embed.add_field(name="Veto-able Bills", value=pretty_bills, inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Government(bot))
