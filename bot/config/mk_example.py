# Adjust MarkConfig and rename this to mk.py

import enum
import inspect
import typing

from bot.utils import exceptions


class DemocracivRole(enum.Enum):
    # Moderation
    MODERATION = 319663296728924160

    # Executive
    EMPEROR = 0
    MINISTER = 745751525971722341
    GOVERNOR = 745731318079422594
    PRIME_MINISTER = 741485246465310740
    LT_PRIME_MINISTER = 745731318079422594

    # Legislature
    SPEAKER = 741467894759686236
    VICE_SPEAKER = 0
    LEGISLATOR = 741485036267634688

    # Courts
    CHIEF_JUSTICE = 0
    JUSTICE = 744356946580209815
    JUDGE = 0

    GOVERNMENT = 740454521934970901

    # multiciv
    NATION_ADMIN = 784596362338631690
    NATION_CITIZEN = 0


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

    IS_MULTICIV = False
    IS_NATION_BOT = False

    # -- Government Names --

    NATION_ROLE_PREFIX = "Ottoman - "
    NATION_CATEGORIES = [741477020659089538]
    PRESS_CHANNEL = []

    NATION_NAME = "Ottoman Mercantile Divan"
    NATION_FULL_NAME = "Ottoman Mercantile Divan"
    NATION_ADJECTIVE = "Ottoman"
    NATION_FLAG_URL = "https://cdn.discordapp.com/avatars/742114348083839008/565389e5e30b93e301111e3ebc64d2e3.png?size=1024"
    NATION_ICON_URL = "https://cdn.discordapp.com/avatars/742114348083839008/565389e5e30b93e301111e3ebc64d2e3.png?size=102496"
    NATION_EMOJI = "<:ottoman:784984719728836638>>"

    LEGISLATURE_NAME = "Grand Divan"
    LEGISLATURE_COMMAND = "divan"
    LEGISLATURE_ADJECTIVE = "Legislative"
    LEGISLATURE_CABINET_NAME = "Legislative Cabinet"
    LEGISLATURE_LEGISLATOR_NAME = "Legislator"
    LEGISLATURE_LEGISLATOR_NAME_PLURAL = ""
    LEGISLATURE_SPEAKER_NAME = "Grand Vizier"
    LEGISLATURE_VICE_SPEAKER_NAME = ""
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS = True
    LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS = True
    LEGISLATURE_MOTIONS_EXIST = True

    MINISTRY_NAME = "Ministry"
    MINISTRY_COMMAND = "ministry"
    MINISTRY_LEADERSHIP_NAME = "Head of State"
    MINISTRY_MINISTER_NAME = "Minister"
    MINISTRY_PRIME_MINISTER_NAME = "Sultan"
    MINISTRY_VICE_PRIME_MINISTER_NAME = "Premier"

    COURT_NAME = "Supreme Court"
    COURT_HAS_INFERIOR_COURT = False
    COURT_CHIEF_JUSTICE_NAME = "Chief Justice"
    COURT_INFERIOR_NAME = ""
    COURT_JUSTICE_NAME = "Justice"
    COURT_JUDGE_NAME = "Judge"

    # -- Links --
    CONSTITUTION = "https://docs.google.com/document/d/1N-kREZoRQcyt4E8_jemIF0RtYroiupE-f64p-niRC8Q/edit"
    LEGAL_CODE = "https://docs.google.com/document/d/1nmDfOy3DypadML817J_d2pCc8FpDlO7HUUhHOajWG2o/edit?usp=sharing"
    POLITICAL_PARTIES = "https://www.reddit.com/r/democraciv/wiki/parties"

    LEGISLATURE_DOCKET = "https://docs.google.com/spreadsheets/d/1k3NkAbh-32ciHMqboZRQVXXkdjT1T21qhtdom0JSm-Q/edit?usp=sharing"
    LEGISLATURE_PROCEDURES = "https://docs.google.com/document/d/1vUGVIv0F0ZK2cAJrhaDaOS02iKIz8KOXSwjoZZgnEmo/edit?usp=sharing"

    MINISTRY_WORKSHEET = "https://docs.google.com/spreadsheets/d/1hrBA2yftAilQFhPwCDtm74YBVFWRce5l41wRsKf9qdI/edit?usp=sharing"
    MINISTRY_PROCEDURES = "https://docs.google.com/document/d/1c6HtdY7urz4F3fH9Nra83Qc1bNVrp_O9zmaeFs6szgA/edit?usp=sharing"

    def __init__(self, bot):
        self.bot = bot

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        try:
            return self._attributes_as_dict
        except AttributeError:
            attributes = inspect.getmembers(self.__class__)
            as_dict = {
                a[0]: a[1]
                for a in attributes
                if not a[0].startswith("__") and not a[0].endswith("__")
            }

            for key, value in as_dict.items():
                if type(value) == property:
                    as_dict[key] = getattr(self, key)

            self._attributes_as_dict = as_dict
            return as_dict

    def _dynamic_role_term(self, role: DemocracivRole, alt: str):
        try:
            name = self.bot.get_democraciv_role(role).name

            if self.NATION_ROLE_PREFIX and name.lower().startswith(
                self.NATION_ROLE_PREFIX.lower()
            ):
                return name[len(self.NATION_ROLE_PREFIX) :]

            return name

        except exceptions.RoleNotFoundError:
            return alt

    legislator_term = _make_property(
        DemocracivRole.LEGISLATOR, LEGISLATURE_LEGISLATOR_NAME
    )
    speaker_term = _make_property(DemocracivRole.SPEAKER, LEGISLATURE_SPEAKER_NAME)
    vice_speaker_term = _make_property(
        DemocracivRole.VICE_SPEAKER, LEGISLATURE_VICE_SPEAKER_NAME
    )
    minister_term = _make_property(DemocracivRole.MINISTER, MINISTRY_MINISTER_NAME)
    pm_term = _make_property(
        DemocracivRole.PRIME_MINISTER, MINISTRY_PRIME_MINISTER_NAME
    )
    lt_pm_term = _make_property(
        DemocracivRole.LT_PRIME_MINISTER, MINISTRY_VICE_PRIME_MINISTER_NAME
    )
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
