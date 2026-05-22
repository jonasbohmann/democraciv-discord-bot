import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from bot.config import mk
from bot.slash import context as slash_context
from bot.slash import ui
from bot.utils import exceptions, mixin


def _member_line(member: discord.Member) -> str:
    return f"{member.mention} {escape_markdown(str(member))}"


def _member_or_dash(member: discord.Member, term: str) -> str:
    if isinstance(member, discord.Member):
        return f"{term}: {_member_line(member)}"

    return f"{term}: -"


class GovernmentSlash(commands.Cog, mixin.GovernmentMixin):
    def __init__(self, bot):
        self.bot = bot

    def _safe_role_members(self, role) -> list[str]:
        try:
            members = self.bot.get_democraciv_role(role).members
        except exceptions.RoleNotFoundError:
            return ["-"]

        return [_member_line(member) for member in members] or ["-"]

    def _justices(self) -> list[str]:
        try:
            justices = list(self.justice_role.members)
        except exceptions.RoleNotFoundError:
            return ["-"]

        chief_justice = self.chief_justice
        lines = []

        if isinstance(chief_justice, discord.Member):
            lines.append(
                f"{_member_line(chief_justice)} **({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})**"
            )
            justices = [
                justice for justice in justices if justice.id != chief_justice.id
            ]

        lines.extend(_member_line(justice) for justice in justices)
        return lines or ["-"]

    def _judges(self) -> list[str]:
        try:
            judges = list(self.judge_role.members)
        except exceptions.RoleNotFoundError:
            return ["-"]

        return [_member_line(judge) for judge in judges] or ["-"]

    @app_commands.command(name="government", description="Show the current government.")
    @app_commands.guild_only()
    async def government_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="government")

        ministry = [
            _member_or_dash(self.prime_minister, self.bot.mk.pm_term),
            _member_or_dash(self.lt_prime_minister, self.bot.mk.lt_pm_term),
        ]

        advisors = []
        for role_name in (
            "MK13_FINANCE_MIN",
            "MK13_FOREIGN_MIN",
            "MK13_DEFENCE_MIN",
            "MK13_ATTORNEY_GENERAL",
        ):
            role = getattr(mk.DemocracivRole, role_name, None)
            if role is None:
                continue

            try:
                discord_role = self.bot.get_democraciv_role(role)
            except exceptions.RoleNotFoundError:
                continue

            advisors.append(
                _member_or_dash(self._safe_get_member(role), discord_role.name)
            )

        legislature_cabinet = [
            _member_or_dash(self.speaker, self.bot.mk.speaker_term),
            _member_or_dash(self.vice_speaker, self.bot.mk.vice_speaker_term),
        ]

        senator_presiding_role = getattr(
            mk.DemocracivRole, "MK13_SENATOR_PRESIDING", None
        )
        if senator_presiding_role is not None:
            legislature_cabinet.append(
                _member_or_dash(
                    self._safe_get_member(senator_presiding_role),
                    "Senator Presiding",
                )
            )

        legislators = self._safe_role_members(mk.DemocracivRole.LEGISLATOR)
        members_of_government = self._safe_role_members(mk.DemocracivRole.GOVERNMENT)
        total = 0 if members_of_government == ["-"] else len(members_of_government)

        await ui.send_static(
            ctx,
            title=f"Government of {self.bot.mk.NATION_FULL_NAME}",
            body=f"There are {total} members of government in total.",
            sections=[
                ui.LayoutSection(
                    self.bot.mk.MINISTRY_LEADERSHIP_NAME,
                    "\n".join(ministry),
                ),
                ui.LayoutSection("Cabinet of Advisors", "\n".join(advisors or ["-"])),
                ui.LayoutSection(
                    f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s",
                    "\n".join(self._justices()),
                ),
                ui.LayoutSection(
                    self.bot.mk.LEGISLATURE_CABINET_NAME,
                    "\n".join(legislature_cabinet),
                ),
                ui.LayoutSection(
                    f"Senators ({0 if legislators == ['-'] else len(legislators)})",
                    "\n".join(legislators),
                ),
            ],
            links=[
                ui.LayoutLink("Constitution", self.bot.mk.CONSTITUTION, "\U0001f4dc"),
                ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
                ui.LayoutLink("Laws Site", "https://laws.democraciv.com", "\U0001f517"),
            ],
        )

    @app_commands.command(
        name="court", description="Show current court members and links."
    )
    @app_commands.guild_only()
    async def court(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="court")

        sections = [
            ui.LayoutSection(
                f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s",
                "\n".join(self._justices()),
            )
        ]

        if self.bot.mk.COURT_HAS_INFERIOR_COURT:
            sections.append(
                ui.LayoutSection(
                    f"{self.bot.mk.COURT_INFERIOR_NAME} {self.bot.mk.COURT_JUDGE_NAME}s",
                    "\n".join(self._judges()),
                )
            )

        await ui.send_static(
            ctx,
            title=f"{self.bot.mk.courts_term} of {self.bot.mk.NATION_FULL_NAME}",
            sections=sections,
            links=[
                ui.LayoutLink("Constitution", self.bot.mk.CONSTITUTION, "\U0001f4dc"),
                ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
                ui.LayoutLink("Laws Site", "https://laws.democraciv.com", "\U0001f517"),
            ],
        )

    @app_commands.command(
        name="legislature",
        description="Show the current Commons and Senate session status.",
    )
    @app_commands.guild_only()
    async def legislature_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="legislature")
        commons = await self.get_active_leg_session(house="commons")
        senate = await self.get_active_leg_session(house="senate")

        def fmt_session(session):
            if session is None:
                return "No active session."

            return f"Session #{session.mk13_house_id} - {session.status.value}"

        await ui.send_static(
            ctx,
            title="The Commons and the Senate",
            body=(
                "In MK13, the Legislature consists of two chambers: the Commons as "
                "the Lower House and the Senate as the Upper House."
            ),
            sections=[
                ui.LayoutSection("Commons", fmt_session(commons)),
                ui.LayoutSection("Senate", fmt_session(senate)),
                ui.LayoutSection(
                    "Slash Commands",
                    "Use `/senate`, `/commons`, `/bill`, `/motion`, and `/law` for document and session commands.",
                ),
            ],
            links=[
                ui.LayoutLink("Constitution", self.bot.mk.CONSTITUTION, "\U0001f4dc"),
                ui.LayoutLink("Legal Code", self.bot.mk.LEGAL_CODE, "\U00002696"),
                ui.LayoutLink("Docket", self.bot.mk.LEGISLATURE_DOCKET, "\U0001f4ca"),
                ui.LayoutLink(
                    "Procedures", self.bot.mk.LEGISLATURE_PROCEDURES, "\U0001f4d6"
                ),
                ui.LayoutLink("Laws Site", "https://laws.democraciv.com", "\U0001f517"),
            ],
        )


async def setup(bot):
    await bot.add_cog(GovernmentSlash(bot))
