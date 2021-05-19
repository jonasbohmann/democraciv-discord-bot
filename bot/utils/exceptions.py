import enum

from discord.ext import commands
from bot.config import config


class DemocracivBotException(commands.CommandError):
    """Generic CommandError exception"""
    message = f"{config.NO} Something went wrong."

    def __init__(self, message=None):
        if message:
            self.message = message


class DemocracivBotAPIError(DemocracivBotException):
    pass


class InvalidUserInputError(DemocracivBotException):
    pass


class TagError(DemocracivBotException):
    pass


class NotFoundError(DemocracivBotException, commands.BadArgument):
    pass


class NotLawError(DemocracivBotException):
    pass


class GoogleAPIError(DemocracivBotException):
    message = (
        f"{config.NO} Something went wrong during the execution of a Google Apps Script. "
        f"Please try again later or contact the developer. If you have given me the URL "
        f"of a Google Docs or Google Forms, make sure that link is an edit link, so that I have edit permissions "
        f"for this document or form if needed."
    )


class RoleNotFoundError(NotFoundError):
    """Raised when the bot tries to find a non-existing role on a guild"""

    def __init__(self, role: str):
        self.role = role
        self.message = f"{config.NO} There is no role named `{role}` on this server."


class ChannelNotFoundError(NotFoundError):
    """Raised when the bot tries to find a non-existing channel on a guild"""

    def __init__(self, channel: str):
        self.channel = channel
        self.message = f"{config.NO} There is no channel named `{channel}` on this server."


class NotDemocracivGuildError(DemocracivBotException):
    """Raised when a Democraciv-specific command is called outside the Democraciv guild"""

    def __init__(self, message=f"{config.NO} You can only use this command on the Democraciv server."):
        self.message = message


class ForbiddenTask(enum.Enum):
    ADD_ROLE = (
        "{x} Either the `{detail}` role is higher than my top role, or "
        "I'm missing the required permissions to give you the role."
    )
    REMOVE_ROLE = (
        "{x} Either the `{detail}` role is higher than my top role, or "
        "I'm missing required permissions to remove the role from you."
    )
    CREATE_ROLE = "{x} I'm missing the required permissions to create the `{detail}` role."
    DELETE_ROLE = "{x} I'm missing the required permissions to delete the `{detail}` role."
    MESSAGE_SEND = "{x} I'm missing the required permissions to send messages in this channel."
    MESSAGE_DELETE = "{x} I'm missing the required permissions to delete that message."
    MEMBER_BAN = "{x} I'm not allowed to ban or unban that person."
    MEMBER_KICK = "{x} I'm not allowed to kick that person."


class ForbiddenError(DemocracivBotException):
    """Raised when a discord.Forbidden exception is raised"""

    def __init__(self, task: ForbiddenTask = None, detail: str = None):
        if task is None:
            self.message = f"{config.NO} I'm not allowed to perform this action."
        else:
            self.message = task.value.format(detail=detail, x=config.NO)
