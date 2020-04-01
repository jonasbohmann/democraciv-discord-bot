import enum
import discord
import typing

from util import exceptions

"""
   Several functions to retrieve mk-specific names or objects such as roles & channels of government officials.

   This was separated into its own file so the maintainer only has to change this file (and links.py) in the actual
    code-base if a new Democraciv MK starts.
"""

MARK = "6"
NATION_NAME = "Arabia"
NATION_ADJECTIVE = "Arabian"
CIV_GAME = "Sid Meier's Civilization 5"


class PrettyEnumValue(object):
    def __init__(self, value, printable_name):
        self.value = value
        self.printable_name = printable_name


class PrettyEnum(enum.Enum):
    def __new__(cls, value):
        obj = object.__new__(cls)
        obj._value_ = value.value
        obj.printable_name = value.printable_name
        return obj


class DemocracivRole(PrettyEnum):
    # Moderation
    MODERATION_ROLE = PrettyEnumValue(319663296728924160, 'Moderation')

    # Executive
    MINISTER_ROLE = PrettyEnumValue(639438027852087297, 'Minister')
    GOVERNOR_ROLE = PrettyEnumValue(639438794239639573, 'Governor')
    EXECUTIVE_PROXY_ROLE = PrettyEnumValue(643190277494013962, 'Executive Proxy')
    PRIME_MINISTER_ROLE = PrettyEnumValue(639438159498838016, 'Prime Minister')
    LT_PRIME_MINISTER_ROLE = PrettyEnumValue(646677815755931659, 'Lieutenant Prime Minister')

    # Legislature
    SPEAKER_ROLE = PrettyEnumValue(639438304705642506, 'Speaker of the Legislature')
    VICE_SPEAKER_ROLE = PrettyEnumValue(639439805729734656, 'Vice-Speaker of the Legislature')
    LEGISLATOR_ROLE = PrettyEnumValue(639438268601204737, 'Legislator')

    # Courts
    CHIEF_JUSTICE_ROLE = PrettyEnumValue(639442447721562122, 'Chief Justice')
    JUSTICE_ROLE = PrettyEnumValue(639438578304417792, 'Justice')
    JUDGE_ROLE = PrettyEnumValue(668544161884143657, 'Judge')

    GOVERNMENT_ROLE = PrettyEnumValue(641077467204943916, 'Arabian Government')

    COUNCIL_OF_SAGES = PrettyEnumValue(694953789815521290, 'Council of Sages')
    SUPREME_LEADER = PrettyEnumValue(694954211741401310, 'Supreme Leader')
    WES_ROLE = PrettyEnumValue(694962133737275422, 'Holy Commander of the Arabian Holy Revolutionary Guard')
    QI_ROLE = PrettyEnumValue(694964085074296933, 'Holy Director of Faith and Heresy')


class DemocracivChannel(enum.Enum):
    # Moderation
    MOD_REQUESTS_CHANNEL = 208986206183227392
    MODERATION_TEAM_CHANNEL = 209410498804973569
    MODERATION_NOTIFICATIONS_CHANNEL = 661201604493443092

    # Government
    GOV_ANNOUNCEMENTS_CHANNEL = 647469752767479809

    # Executive
    EXECUTIVE_CHANNEL = 637051136955777049


def get_democraciv_role(bot, role: DemocracivRole) -> typing.Optional[discord.Role]:
    to_return = bot.democraciv_guild_object.get_role(role.value)

    if to_return is None:
        raise exceptions.RoleNotFoundError(role.printable_name)

    return to_return


def get_democraciv_channel(bot, channel: DemocracivChannel) -> typing.Optional[discord.TextChannel]:
    to_return = bot.democraciv_guild_object.get_channel(channel.value)

    if to_return is None:
        raise exceptions.ChannelNotFoundError(channel.name)

    return to_return
