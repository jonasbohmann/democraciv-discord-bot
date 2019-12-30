from util import exceptions

"""
   Several functions to retrieve mk-specific names or objects such as roles & channels of government officials.

   This was separated into its own file so the maintainer only has to change this file (and links.py) in the actual
    code-base if a new Democraciv MK starts.
"""

# Moderation
MOD_REQUESTS_CHANNEL = 423942916776525825
MODERATION_TEAM_CHANNEL = 209410498804973569
MODERATION_NOTIFICATIONS_CHANNEL = 232108753477042187
MODERATION_ROLE = 547530938712719373
CIV_GAME = "Sid Meier's Civilization 5"
MARK = "6"

# Government
NATION_NAME = "Arabia"
NATION_ADJECTIVE = "Arabian"
GOV_ANNOUNCEMENTS_CHANNEL = 647469752767479809

# Executive
EXECUTIVE_CHANNEL = 637051136955777049
MINISTER_ROLE = 639438027852087297
GOVERNOR_ROLE = 639438794239639573
EXECUTIVE_PROXY_ROLE = 643190277494013962
PRIME_MINISTER_ROLE = 639438159498838016
LT_PRIME_MINISTER_ROLE = 646677815755931659

# Legislature
SPEAKER_ROLE = 639438304705642506
VICE_SPEAKER_ROLE = 639439805729734656
LEGISLATOR_ROLE = 639438268601204737

# Courts
CHIEF_JUSTICE_ROLE = 639442447721562122
JUSTICE_ROLE = 639438578304417792


def get_moderation_role(bot):
    to_return = bot.democraciv_guild_object.get_role(MODERATION_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Moderation")

    return to_return


def get_mod_requests_channel(bot):
    to_return = bot.democraciv_guild_object.get_channel(MOD_REQUESTS_CHANNEL)

    if to_return is None:
        raise exceptions.ChannelNotFoundError("mod-requests")

    return to_return


def get_moderation_notifications_channel(bot):
    to_return = bot.democraciv_guild_object.get_channel(MODERATION_NOTIFICATIONS_CHANNEL)

    if to_return is None:
        raise exceptions.ChannelNotFoundError("moderation-notifications")

    return to_return


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


def get_chief_justice_role(bot):
    to_return = bot.democraciv_guild_object.get_role(CHIEF_JUSTICE_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Chief Justice")

    return to_return


def get_justice_role(bot):
    to_return = bot.democraciv_guild_object.get_role(JUSTICE_ROLE)

    if to_return is None:
        raise exceptions.RoleNotFoundError("Justice")

    return to_return
