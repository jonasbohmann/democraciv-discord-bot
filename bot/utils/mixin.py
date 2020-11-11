import discord
import typing

from bot import DemocracivBot
from bot.config import mk
from bot.utils import exceptions


def _make_property(role: mk.DemocracivRole):
    return property(lambda self: self._safe_get_member(role))


class GovernmentMixin:
    def __init__(self, bot):
        self.bot: DemocracivBot = bot

    def _safe_get_member(self, role) -> typing.Optional[discord.Member]:
        try:
            return self.bot.get_democraciv_role(role).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.get_democraciv_channel(mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    speaker = _make_property(mk.DemocracivRole.SPEAKER)
    vice_speaker = _make_property(mk.DemocracivRole.VICE_SPEAKER)
    chief_justice = _make_property(mk.DemocracivRole.CHIEF_JUSTICE)
    prime_minister = _make_property(mk.DemocracivRole.PRIME_MINISTER)
    lt_prime_minister = _make_property(mk.DemocracivRole.LT_PRIME_MINISTER)

    @property
    def speaker_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER)

    @property
    def vice_speaker_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.VICE_SPEAKER)

    @property
    def legislator_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)

    async def dm_legislators(self, *, message: str, reason: str):
        for legislator in self.legislator_role.members:
            await self.bot.safe_send_dm(target=legislator, reason=reason, message=message)

    def is_cabinet(self, member: discord.Member) -> bool:
        if self.speaker_role in member.roles or self.vice_speaker_role in member.roles:
            return True
        return False

    @property
    def justice_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUSTICE)

    @property
    def judge_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUDGE)
