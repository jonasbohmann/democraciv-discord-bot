import enum
import inspect
import typing

from bot.utils import exceptions


class DemocracivRole(enum.Enum):
    # Moderation
    MODERATION = 319663296728924160

    # Executive
    MINISTER = 768678167875026966
    GOVERNOR = 0
    PRIME_MINISTER = 768678167875026966
    LT_PRIME_MINISTER = 0

    # Legislature
    SPEAKER = 785004152111628298
    VICE_SPEAKER = 0
    LEGISLATOR = 746195001796722728

    # Courts
    CHIEF_JUSTICE = 0
    JUSTICE = 768678188624248864
    JUDGE = 0

    GOVERNMENT = 740454620307914772

    OTTOMAN_TAX_OFFICER = 744983252854636675

    # multiciv
    NATION_ADMIN = 784596362338631690
    NATION_CITIZEN = 740452229638651917


class DemocracivChannel(enum.Enum):
    # Moderation
    MOD_REQUESTS_CHANNEL = 208986206183227392
    MODERATION_TEAM_CHANNEL = 209410498804973569
    MODERATION_NOTIFICATIONS_CHANNEL = 661201604493443092

    # Government
    GOV_ANNOUNCEMENTS_CHANNEL = 647469752767479809

    # Executive
    EXECUTIVE_CHANNEL = 637051136955777049


def _make_property(role: DemocracivRole, alt: str):
    return property(lambda self: self._dynamic_role_term(role, alt))


class MarkConfig:
    MARK = "7"
    CIV_GAME = "Sid Meier's Civilization 6"
    IS_MULTICIV = False

    # -- Government Names --

    NATION_ROLE_PREFIX = ""
    NATION_CATEGORIES = []

    NATION_NAME = "Rome"
    NATION_FULL_NAME = "Rome"
    NATION_ADJECTIVE = "Rome"
    NATION_FLAG_URL = "https://cdn.discordapp.com/avatars/742114483798933605/abf918799b657f618aeb0a061088fd5a.png?size=1024"
    NATION_ICON_URL = "https://cdn.discordapp.com/avatars/742114483798933605/abf918799b657f618aeb0a061088fd5a.png?size=1024"
    NATION_EMOJI = "<:rome:784999996159819786>"

    LEGISLATURE_NAME = "Senate"
    LEGISLATURE_COMMAND = "senate"
    LEGISLATURE_ADJECTIVE = "Legislative"
    LEGISLATURE_CABINET_NAME = "Legislative Cabinet"
    LEGISLATURE_LEGISLATOR_NAME = "Senator"
    LEGISLATURE_SPEAKER_NAME = "Consul"
    LEGISLATURE_VICE_SPEAKER_NAME = "Vice-Speaker"
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS = True
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS = True
    LEGISLATURE_MOTIONS_EXIST = True

    MINISTRY_NAME = "Rex"
    MINISTRY_COMMAND = "rex"
    MINISTRY_LEADERSHIP_NAME = "Head of State"
    MINISTRY_MINISTER_NAME = ""
    MINISTRY_PRIME_MINISTER_NAME = "Rex"
    MINISTRY_VICE_PRIME_MINISTER_NAME = ""

    COURT_NAME = "Court"
    COURT_HAS_INFERIOR_COURT = False
    COURT_CHIEF_JUSTICE_NAME = "Decemvir"
    COURT_INFERIOR_NAME = "Appeals Court"
    COURT_JUSTICE_NAME = "Justice"
    COURT_JUDGE_NAME = "Judge"

    # -- Links --
    CONSTITUTION = "https://docs.google.com/document/d/1deWktyhCDWlmC88C2eP7vjpH6sP6NuJ7KfrXX8kcO-s/edit"
    LEGAL_CODE = "g"
    POLITICAL_PARTIES = "https://www.reddit.com/r/democraciv/wiki/parties"

    LEGISLATURE_DOCKET = (
        ""
    )
    LEGISLATURE_PROCEDURES = (
        "g"
    )

    MINISTRY_WORKSHEET = (
        ""
    )
    MINISTRY_PROCEDURES = (
        ""
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
