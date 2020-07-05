import enum
import discord
import typing

from dciv_bot.config import config
from dciv_bot.util import exceptions

"""Several functions to retrieve mk-specific names or objects such as roles & channels of government officials."""


class MarkConfig:
    MARK = "6"
    CIV_GAME = "Sid Meier's Civilization 5"
    IS_MULTICIV = False

    # -- Government Names --

    NATION_NAME = "Arabia"
    NATION_FULL_NAME = "Arabian People’s Democratic Union"
    NATION_ADJECTIVE = "Arabian"
    NATION_FLAG_URL = "https://i.imgur.com/M97zPrP.jpg"
    NATION_ICON_URL = ""
    NATION_EMOJI = config.NATION_FLAG

    LEGISLATURE_NAME = "Legislature"
    LEGISLATURE_CABINET_NAME = "Legislative Cabinet"
    LEGISLATURE_LEGISLATOR_NAME = "Legislator"
    LEGISLATURE_SPEAKER_NAME = "Speaker"
    LEGISLATURE_VICE_SPEAKER_NAME = "Vice-Speaker"
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS = True
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS = True

    MINISTRY_NAME = "Ministry"
    MINISTRY_LEADERSHIP_NAME = "Head of State"
    MINISTRY_MINISTER_NAME = "Minister"
    MINISTRY_PRIME_MINISTER_NAME = "Prime Minister"
    MINISTRY_VICE_PRIME_MINISTER_NAME = "Lt. Prime Minister"

    COURT_NAME = "Supreme Court"
    COURT_HAS_INFERIOR_COURT = True
    COURT_CHIEF_JUSTICE_NAME = "Chief Justice"
    COURT_INFERIOR_NAME = "Appeals Court"
    COURT_JUSTICE_NAME = "Justice"
    COURT_JUDGE_NAME = "Judge"

    # -- Links --
    CONSTITUTION = "https://docs.google.com/document/d/1deWktyhCDWlmC88C2eP7vjpH6sP6NuJ7KfrXX8kcO-s/edit"
    LEGAL_CODE = "https://docs.google.com/document/d/1nmDfOy3DypadML817J_d2pCc8FpDlO7HUUhHOajWG2o/edit?usp=sharing"
    POLITICAL_PARTIES = "https://www.reddit.com/r/democraciv/wiki/parties"

    LEGISLATURE_DOCKET = "https://docs.google.com/spreadsheets/d/1k3NkAbh-32ciHMqboZRQVXXkdjT1T21qhtdom0JSm-Q/edit?usp=sharing"
    LEGISLATURE_PROCEDURES = "https://docs.google.com/document/d/1vUGVIv0F0ZK2cAJrhaDaOS02iKIz8KOXSwjoZZgnEmo/edit?usp=sharing"

    MINISTRY_WORKSHEET = "https://docs.google.com/spreadsheets/d/1hrBA2yftAilQFhPwCDtm74YBVFWRce5l41wRsKf9qdI/edit?usp=sharing"
    MINISTRY_PROCEDURES = "https://docs.google.com/document/d/1c6HtdY7urz4F3fH9Nra83Qc1bNVrp_O9zmaeFs6szgA/edit?usp=sharing"

    def __init__(self, bot):
        self.bot = bot

    @property
    def safe_flag(self):
        return self.NATION_FLAG_URL or self.bot.democraciv_guild_object.icon_url_as(static_format='png')

    @property
    def legislator_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.LEGISLATOR_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.LEGISLATURE_LEGISLATOR_NAME

    @property
    def speaker_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.SPEAKER_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.LEGISLATURE_SPEAKER_NAME

    @property
    def vice_speaker_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.VICE_SPEAKER_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.LEGISLATURE_VICE_SPEAKER_NAME

    @property
    def minister_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.MINISTER_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.MINISTRY_MINISTER_NAME

    @property
    def pm_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.PRIME_MINISTER_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.MINISTRY_PRIME_MINISTER_NAME

    @property
    def vice_pm_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.LT_PRIME_MINISTER_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.MINISTRY_VICE_PRIME_MINISTER_NAME

    @property
    def courts_term(self):
        if self.COURT_HAS_INFERIOR_COURT:
            return "Courts"
        return self.COURT_NAME

    @property
    def justice_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.JUSTICE_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.COURT_JUSTICE_NAME

    @property
    def judge_term(self):
        try:
            return get_democraciv_role(self.bot, DemocracivRole.JUDGE_ROLE).name
        except exceptions.RoleNotFoundError:
            return self.COURT_JUDGE_NAME


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
