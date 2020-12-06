import enum
import inspect
import typing

from bot.utils import exceptions


class DemocracivRole(enum.Enum):
    # Moderation
    MODERATION = 319663296728924160

    # Executive
    MINISTER = 742941704469872711
    GOVERNOR = 742941704469872711
    PRIME_MINISTER = 742941826608005190
    LT_PRIME_MINISTER = 0

    # Legislature
    SPEAKER = 742941979066761337
    VICE_SPEAKER = 742942042824638496
    LEGISLATOR = 740454667045044265

    # Courts
    CHIEF_JUSTICE = 0
    JUSTICE = 777697682696699944
    JUDGE = 0

    GOVERNMENT = 740454667045044265

    OTTOMAN_TAX_OFFICER = 744983252854636675

    # multiciv
    NATION_ADMIN = 784596362338631690
    NATION_CITIZEN = 740452398824161290


class DemocracivChannel(enum.Enum):
    # Moderation
    MOD_REQUESTS_CHANNEL = 208986206183227392
    MODERATION_TEAM_CHANNEL = 209410498804973569
    MODERATION_NOTIFICATIONS_CHANNEL = 661201604493443092

    # Government
    GOV_ANNOUNCEMENTS_CHANNEL = 0


def _make_property(role: DemocracivRole, alt: str):
    return property(lambda self: self._dynamic_role_term(role, alt))


class MarkConfig:
    MARK = "7"
    CIV_GAME = "Sid Meier's Civilization 6"
    IS_MULTICIV = True

    # -- Government Names --

    NATION_ROLE_PREFIX = "Maori - "
    NATION_CATEGORIES = [741479405968162897]

    NATION_NAME = "Maori"
    NATION_FULL_NAME = "United Iwi of the Maori Commonwealth"
    NATION_ADJECTIVE = "Maori"
    NATION_FLAG_URL = "https://cdn.discordapp.com/avatars/742114210615656470/0c2ef881582e4c77a7efaeb190452e77.png?size=1024"
    NATION_ICON_URL = "https://cdn.discordapp.com/avatars/742114210615656470/0c2ef881582e4c77a7efaeb190452e77.png?size=1024"
    NATION_EMOJI = "<:maori:747281783191633922>"

    LEGISLATURE_NAME = "Legislature"
    LEGISLATURE_COMMAND = "legislature"
    LEGISLATURE_ADJECTIVE = "Legislative"
    LEGISLATURE_CABINET_NAME = "Legislative Cabinet"
    LEGISLATURE_LEGISLATOR_NAME = "Citizen"
    LEGISLATURE_SPEAKER_NAME = "Speaker"
    LEGISLATURE_VICE_SPEAKER_NAME = "Vice-Speaker"
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS = True
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS = True
    LEGISLATURE_MOTIONS_EXIST = True

    MINISTRY_NAME = "Ariki"
    MINISTRY_COMMAND = "ariki"
    MINISTRY_LEADERSHIP_NAME = "Arikinui & Ariki"
    MINISTRY_MINISTER_NAME = "Ariki"
    MINISTRY_PRIME_MINISTER_NAME = "Arikinui"
    MINISTRY_VICE_PRIME_MINISTER_NAME = ""

    COURT_NAME = "Supreme Court"
    COURT_HAS_INFERIOR_COURT = False
    COURT_CHIEF_JUSTICE_NAME = "Chief Justice"
    COURT_INFERIOR_NAME = ""
    COURT_JUSTICE_NAME = "Justice"
    COURT_JUDGE_NAME = "Judge"

    # -- Links --
    CONSTITUTION = "https://docs.google.com/document/d/1Bz_yCic_uyrkhiJbE1On8kZIoHuxNY1hFWlYi4oaMs8/edit"
    LEGAL_CODE = ""
    POLITICAL_PARTIES = "https://www.reddit.com/r/democraciv/wiki/parties"

    LEGISLATURE_DOCKET = (
        ""
    )
    LEGISLATURE_PROCEDURES = (
        ""
    )

    MINISTRY_WORKSHEET = (
        ""
    )
    MINISTRY_PROCEDURES = (
        "g"
    )

    def __init__(self, bot):
        self.bot = bot

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        try:
            return self._attributes_as_dict
        except AttributeError:
            attributes = inspect.getmembers(self.__class__)
            as_dict = {a[0]: a[1] for a in attributes if not a[0].startswith("__") and not a[0].endswith("__")}

            for key, value in as_dict.items():
                if type(value) == property:
                    as_dict[key] = getattr(self, key)

            self._attributes_as_dict = as_dict
            return as_dict

    def _dynamic_role_term(self, role: DemocracivRole, alt: str):
        try:
            return self.bot.get_democraciv_role(role).name
        except exceptions.RoleNotFoundError:
            return alt

    legislator_term = _make_property(DemocracivRole.LEGISLATOR, LEGISLATURE_LEGISLATOR_NAME)
    speaker_term = _make_property(DemocracivRole.SPEAKER, LEGISLATURE_SPEAKER_NAME)
    vice_speaker_term = _make_property(DemocracivRole.VICE_SPEAKER, LEGISLATURE_VICE_SPEAKER_NAME)
    minister_term = _make_property(DemocracivRole.MINISTER, MINISTRY_MINISTER_NAME)
    pm_term = _make_property(DemocracivRole.PRIME_MINISTER, MINISTRY_PRIME_MINISTER_NAME)
    lt_pm_term = _make_property(DemocracivRole.LT_PRIME_MINISTER, MINISTRY_VICE_PRIME_MINISTER_NAME)
    justice_term = _make_property(DemocracivRole.JUSTICE, COURT_JUSTICE_NAME)
    judge_term = _make_property(DemocracivRole.JUDGE, COURT_JUDGE_NAME)

    @property
    def democraciv(self):
        return self.bot.dciv.name

    @property
    def safe_flag(self):
        return self.NATION_FLAG_URL or self.bot.dciv.icon_url_as(static_format="png")

    @property
    def courts_term(self):
        if self.COURT_HAS_INFERIOR_COURT:
            return "Courts"

        return self.COURT_NAME
