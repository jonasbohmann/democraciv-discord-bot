import datetime

import discord
from discord.utils import escape_markdown

from bot.config import config
from bot.services.ministry import AwaitingBillsResult, MinistryDashboardResult
from bot.services.results import PageResult
from bot.utils import text


def _member_line(member: discord.Member) -> str:
    return f"{member.mention} {escape_markdown(str(member))}"


def _member_or_dash(member: discord.Member, term: str) -> str:
    if isinstance(member, discord.Member):
        return f"{term}: {_member_line(member)}"

    return f"{term}: -"


def _member_mention_or_dash(member: discord.Member, term: str) -> str:
    if isinstance(member, discord.Member):
        return f"{term}: {member.mention}"

    return f"{term}: -"


def _awaiting_hint(ctx, has_awaiting_bills: bool) -> str:
    if not has_awaiting_bills:
        return "There are no bills awaiting Executive action."

    command = (
        f"/{ctx.bot.mk.MINISTRY_COMMAND.lower()} bills"
        if ctx.is_slash
        else f"{config.BOT_PREFIX}{ctx.bot.mk.MINISTRY_COMMAND} bills"
    )
    return f":warning:    There are bills awaiting action. Review with `{command}`."


def build_dashboard_embed(ctx, result: MinistryDashboardResult) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    embed.set_author(
        icon_url=ctx.bot.mk.NATION_ICON_URL,
        name=f"The {ctx.bot.mk.MINISTRY_NAME} of {ctx.bot.mk.NATION_FULL_NAME}",
    )

    embed.add_field(
        name=ctx.bot.mk.MINISTRY_LEADERSHIP_NAME,
        value="\n".join(
            [
                _member_or_dash(result.prime_minister, ctx.bot.mk.pm_term),
                _member_mention_or_dash(
                    result.lt_prime_minister, ctx.bot.mk.lt_pm_term
                ),
            ]
        ),
        inline=False,
    )

    advisor_lines = [
        _member_or_dash(advisor.member, advisor.role_name)
        for advisor in result.advisors
    ] or ["-"]
    embed.add_field(
        name="Cabinet of Advisors",
        value="\n".join(advisor_lines),
        inline=False,
    )

    embed.add_field(
        name="Links",
        value=(
            f"[Constitution]({ctx.bot.mk.CONSTITUTION})\n"
            f"[Legal Code]({ctx.bot.mk.LEGAL_CODE}) "
            "*(try [laws.democraciv.com](https://laws.democraciv.com) too!)*\n"
            f"[Ministry Worksheet]({ctx.bot.mk.MINISTRY_WORKSHEET})\n"
            f"[Ministry Procedures]({ctx.bot.mk.MINISTRY_PROCEDURES})"
        ),
        inline=False,
    )

    embed.add_field(
        name="Bills Awaiting Executive Action",
        value=_awaiting_hint(ctx, result.has_awaiting_bills),
        inline=False,
    )
    return embed


def _format_deadline(deadline) -> str:
    if deadline is None:
        return "No deadline set"

    deadline = deadline.replace(tzinfo=datetime.timezone.utc)
    return f"<t:{int(deadline.timestamp())}:R>"


def build_awaiting_bills_page(ctx, result: AwaitingBillsResult) -> PageResult:
    entries = []

    if result.paste_link:
        entries.append(
            "-# View this list in Google Spreadsheets formatting for easy copy & pasting: "
            f"[Link]({result.paste_link})\n"
        )

    for record in result.records:
        entries.append(
            f"* Bill #{record['id']} - [{record['name']}]({record['link']})\n"
            f"-# Deadline: {_format_deadline(record['executive_deadline_at'])}\n"
        )

    return PageResult(
        entries=entries,
        icon=ctx.bot.mk.NATION_ICON_URL,
        author="Bills Awaiting Executive Action",
        empty_message="There are no bills awaiting Executive action.",
    )
