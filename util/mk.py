from util import exceptions

"""
   Several functions to retrieve mk-specific names or objects such as roles & channels of government officials.

   This was separated into its own file so the maintainer only has to change this file (and links.py) in the actual
    code-base if a new Democraciv MK starts.
"""

# Moderation
MODERATION_TEAM_CHANNEL = 423938668710068224
CIV_GAME = "Sid Meier's Civilization 5"
MARK = "6"

# Government
NATION_NAME = "Arabia"
NATION_ADJECTIVE = "Arabian"
GOV_ANNOUNCEMENTS_CHANNEL = 423942916776525825

# Executive
EXECUTIVE_CHANNEL = 423938668710068224
MINISTER_ROLE = 549696492177195019
GOVERNOR_ROLE = 549696492177195019
EXECUTIVE_PROXY_ROLE = 549696492177195019
PRIME_MINISTER_ROLE = 643602222810398740
LT_PRIME_MINISTER_ROLE = 643602222810398740

# Legislature
SPEAKER_ROLE = 643602222810398740
VICE_SPEAKER_ROLE = 645760825931464705
LEGISLATOR_ROLE = 577244431892348960


def get_moderation_team_channel(bot):
    to_return = bot.democraciv_guild_object.get_channel(MODERATION_TEAM_CHANNEL)

    if to_return is None:
        raise exceptions.ChannelNotFoundError("moderation-team")

    return to_return


def get_executive_channel(bot):
    to_return = bot.democraciv_guild_object.get_channel(EXECUTIVE_CHANNEL)

    if to_return is None:
        raise exceptions.ChannelNotFoundError("executive")

    return to_return


def get_minister_role(bot):
    to_return = bot.democraciv_guild_object.get_role(MINISTER_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Minister")

    return to_return


def get_governor_role(bot):
    to_return = bot.democraciv_guild_object.get_role(GOVERNOR_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Governor")

    return to_return


def get_executive_proxy_role(bot):
    to_return = bot.democraciv_guild_object.get_role(EXECUTIVE_PROXY_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Executive Proxy")

    return to_return


def get_speaker_role(bot):
    to_return = bot.democraciv_guild_object.get_role(SPEAKER_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Speaker of the Legislature")

    return to_return


def get_vice_speaker_role(bot):
    to_return = bot.democraciv_guild_object.get_role(VICE_SPEAKER_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Vice-Speaker of the Legislature")

    return to_return


def get_legislator_role(bot):
    to_return = bot.democraciv_guild_object.get_role(LEGISLATOR_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Legislator")

    return to_return


def get_gov_announcements_channel(bot):
    to_return = bot.democraciv_guild_object.get_channel(GOV_ANNOUNCEMENTS_CHANNEL)

    if to_return is None:
        raise exceptions.ChannelNotFoundError("gov-announcements")

    return to_return


def get_prime_minister_role(bot):
    to_return = bot.democraciv_guild_object.get_role(PRIME_MINISTER_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Prime Minister")

    return to_return


def get_lt_prime_minister_role(bot):
    to_return = bot.democraciv_guild_object.get_role(LT_PRIME_MINISTER_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Lieutenant Prime Minister")

    return to_return
