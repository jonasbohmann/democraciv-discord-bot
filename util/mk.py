import enum
import discord

from util import exceptions

"""
   Several functions to retrieve mk-specific names or objects such as roles & channels of government officials.

   This was separated into its own file so the maintainer only has to change this file (and links.py) in the actual
    code-base if a new Democraciv MK starts.
"""


class DemocracivRole(enum.Enum):
    # Moderation
    MODERATION_ROLE = 319663296728924160

    # Executive
    MINISTER_ROLE = 639438027852087297
    GOVERNOR_ROLE = 639438794239639573
    EXECUTIVE_PROXY_ROLE = 643190277494013962
    PRIME_MINISTER_ROLE = 639438159498838016
    LT_PRIME_MINISTER_ROLE = 646677815755931659

    # Legislature
    SPEAKER_ROLE = 643602222810398740
    VICE_SPEAKER_ROLE = 645760825931464705
    LEGISLATOR_ROLE = 639438268601204737

    # Courts
    CHIEF_JUSTICE_ROLE = 639442447721562122
    JUSTICE_ROLE = 639438578304417792


class DemocracivChannel(enum.Enum):
    # Moderation
    MOD_REQUESTS_CHANNEL = 208986206183227392
    MODERATION_TEAM_CHANNEL = 209410498804973569
    MODERATION_NOTIFICATIONS_CHANNEL = 661201604493443092

    # Government
    GOV_ANNOUNCEMENTS_CHANNEL = 647469752767479809

    # Executive
    EXECUTIVE_CHANNEL = 637051136955777049


MARK = "6"
NATION_NAME = "Arabia"
NATION_ADJECTIVE = "Arabian"
CIV_GAME = "Sid Meier's Civilization 5"


def get_democraciv_role(bot, role: DemocracivRole) -> discord.Role:
    to_return = bot.democraciv_guild_object.get_role(role.value)

    if to_return is None:
        raise exceptions.RoleNotFoundError(role.name)

    return to_return


def get_democraciv_channel(bot, channel: DemocracivChannel) -> discord.TextChannel:
    to_return = bot.democraciv_guild_object.get_channel(channel.value)

    if to_return is None:
        raise exceptions.ChannelNotFoundError(channel.name)

    return to_return
