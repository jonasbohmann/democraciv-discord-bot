import enum

from discord.ext import commands

from config import config


class DemocracivBotException(commands.CommandError):
    """Generic CommandError exception that gets send to event.error_handler.on_command_error()"""

    def __init__(self, message=None):
        self.message = message


class InvalidUserInputError(DemocracivBotException):
    pass


class DemocracivBotAPIError(DemocracivBotException):
    pass


class GoogleAPIError(DemocracivBotException):
    message = f"{config.NO} Something went wrong during the execution of a Google Apps Script. " \
              f"Please try again later or contact the developer. Make sure that, if you have given me the URL " \
              f"of a Google Docs or Google Forms, that I have edit permissions on this document if needed."


class RoleNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing role on a guild"""

    def __init__(self, role: str):
        self.role = role
        self.message = f"{config.NO} There is no role named `{role}` on this server."


class ChannelNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing channel on a guild"""

    def __init__(self, channel: str):
        self.channel = channel
        self.message = f"{config.NO} There is no channel named `{channel}` on this server."


class MemberNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing member on a guild"""

    def __init__(self, member: str):
        self.member = member
        self.message = f"{config.NO} There is no member named `{member}` on this server."


class NoOneHasRoleError(DemocracivBotException):
    """Raised when the bot tries to get a member object from a role that no member has"""

    def __init__(self, role: str):
        self.role = role
        self.message = f"{config.NO} No one on this server has the role named `{role}`."


class NotDemocracivGuildError(DemocracivBotException):
    """Raised when a Democraciv-specific command is called outside the Democraciv guild"""

    def __init__(self, message=f"{config.NO} You can only use this command on the Democraciv server!"):
        self.message = message


class GuildNotFoundError(DemocracivBotException):
    """Raised when the bot tries to use a bot.get(guild) or similar query with a non-existing guild"""

    def __init__(self, name):
        self.message = f"{config.NO} Couldn't find a serer named/with the ID `{name}` that I am in."


class TagCheckError(commands.CheckFailure):
    def __init__(self, message):
        self.message = message


class TagError(DemocracivBotException):
    def __init__(self, message):
        self.message = message


class NotFoundError(DemocracivBotException):
    pass


class PartyNotFoundError(NotFoundError):
    def __init__(self, party):
        self.party = party


class ForbiddenTask(enum.Enum):
    ADD_ROLE = 1
    REMOVE_ROLE = 2
    CREATE_ROLE = 3
    DELETE_ROLE = 4
    MESSAGE_SEND = 5
    MESSAGE_DELETE = 6
    MEMBER_BAN = 7
    MEMBER_KICK = 8


class ForbiddenError(DemocracivBotException):
    """Raised when a discord.Forbidden exception is raised"""

    def __init__(self, task: ForbiddenTask = None, detail: str = None):

        if task == ForbiddenTask.ADD_ROLE:
            self.message = (
                f"{config.NO} Either the `{detail}` role is higher than my top role, or I'm missing the "
                f"required permissions to give you the role."
            )

        elif task == ForbiddenTask.REMOVE_ROLE:
            self.message = (
                f"{config.NO} Either the `{detail}` role is higher than my top role, or I'm missing "
                f"required permissions to remove the role from you."
            )

        elif task == ForbiddenTask.CREATE_ROLE:
            self.message = f"{config.NO} I'm missing the required permissions to create the `{detail}` role."

        elif task == ForbiddenTask.DELETE_ROLE:
            self.message = f"{config.NO} I'm missing the required permissions to delete the `{detail}` role."

        elif task == ForbiddenTask.MESSAGE_DELETE:
            self.message = "{config.NO} I'm missing the required permissions to delete that message."

        elif task == ForbiddenTask.MESSAGE_SEND:
            self.message = "{config.NO} I'm missing the required permissions to send messages in this channel."

        elif task == ForbiddenTask.MEMBER_BAN:
            self.message = "{config.NO} I'm not allowed to ban or unban that person."

        elif task == ForbiddenTask.MEMBER_KICK:
            self.message = "{config.NO} I'm not allowed to kick that person."

        else:
            self.message = "{config.NO} Discord didn't allow me to perform this action."
