import enum

from discord.ext import commands


class DemocracivBotException(commands.CommandError):
    """Generic CommandError exception that gets send to event.error_handler.on_command_error()"""

    def __init__(self, message):
        self.message = message


class RoleNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing role on a guild"""

    def __init__(self, role: str):
        self.role = role
        self.message = f":x: There is no role named `{role}` on this guild."


class ChannelNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing channel on a guild"""

    def __init__(self, channel: str):
        self.channel = channel
        self.message = f":x: There is no channel named `{channel}` on this guild."


class MemberNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing member on a guild"""

    def __init__(self, member: str):
        self.member = member
        self.message = f":x: There is no member named `{member}` on this guild."


class NoOneHasRoleError(DemocracivBotException):
    """Raised when the bot tries to get a member object from a role that no member has"""

    def __init__(self, role: str):
        self.role = role
        self.message = f":x: No one on this guild has the role named `{role}`!"


class NotDemocracivGuildError(DemocracivBotException):
    """Raised when a Democraciv-specific command is called outside the Democraciv guild"""

    def __init__(self, message=":x: You can only use this command on the Democraciv guild!"):
        self.message = message


class GuildNotFoundError(DemocracivBotException):
    """Raised when the bot tries to use a bot.get(guild) or similar query with a non-existing guild"""

    def __init__(self, name):
        self.message = f":x: Couldn't find a guild named/with the ID `{name}` that I am in!"


class TagCheckError(commands.CheckFailure):
    def __init__(self, message):
        self.message = message


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
            self.message = f":x: Either the `{detail}` role is higher than my role, or I'm missing Administrator " \
                           f"permissions to give you the role!"

        elif task == ForbiddenTask.REMOVE_ROLE:
            self.message = f":x: Either the `{detail}` role is higher than my role, or I'm missing Administrator " \
                           f"permissions to remove the role from you!"

        elif task == ForbiddenTask.CREATE_ROLE:
            self.message = f":x: I'm missing the required permissions to create the `{detail}` role."

        elif task == ForbiddenTask.DELETE_ROLE:
            self.message = f":x: I'm missing the required permissions to delete the `{detail}` role."

        elif task == ForbiddenTask.MESSAGE_DELETE:
            self.message = ":x: I'm missing the required permissions to delete that message."

        elif task == ForbiddenTask.MESSAGE_SEND:
            self.message = ":x: I'm missing the required permissions to send messages in this channel."

        elif task == ForbiddenTask.MEMBER_BAN:
            self.message = ":x: I'm not allowed to ban or unban that person."

        elif task == ForbiddenTask.MEMBER_KICK:
            self.message = ":x: I'm not allowed to kick that person."

        else:
            self.message = ":x: Discord didn't allow me to perform this action."
