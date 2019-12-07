from discord.ext import commands


class DemocracivBotException(commands.CommandError):
    """Generic CommandError exception that gets send to event.error_handler.on_command_error()"""

    def __init__(self, message):
        self.message = message


class RoleNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing role on a guild"""

    def __init__(self, role: str):
        self.role = role
        self.message = f":x: Couldn't find a role named '{role}' on this guild!"


class ChannelNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing channel on a guild"""

    def __init__(self, channel: str):
        self.channel = channel
        self.message = f":x: Couldn't find a channel named '{channel}' on this guild!"


class MemberNotFoundError(DemocracivBotException):
    """Raised when the bot tries to find a non-existing member on a guild"""

    def __init__(self, member: str):
        self.member = member
        self.message = f":x: Couldn't find a member named {member} on this guild!"


class NoOneHasRoleError(DemocracivBotException):
    """Raised when the bot tries to get a member object from a role that no member has"""

    def __init__(self, role: str):
        self.role = role
        self.message = f":x: No one on this guild has the role named '{role}'!"


class NotDemocracivGuildError(DemocracivBotException):
    """Raised when a Democraciv-specific command is called outside the Democraciv guild"""

    def __init__(self, message=None):
        if not message:
            self.message = ":x: You can only use this command on the Democraciv guild!"
        else:
            self.message = message


class GuildNotFoundError(DemocracivBotException):
    """Raised when the bot tries to use a bot.get(guild) or similar query with a non-existing guild"""

    def __init__(self, name):
        self.message = f":x: Couldn't find a guild named/with the ID '{name}' that I am in!"


class ForbiddenError(DemocracivBotException):
    """Raised when a discord.Forbidden exception is raised"""

    def __init__(self, task: str = None, detail: str = None):

        if task == "add_roles":
            self.message = f":x: Either the '{detail}' role is higher than my role, or I'm missing Administrator " \
                           f"permissions to give you the role!"

        elif task == "remove_roles":
            self.message = f":x: Either the '{detail}' role is higher than my role, or I'm missing Administrator " \
                           f"permissions to remove the role from you!"

        elif task == "create_role":
            self.message = f":x: I'm missing the required permissions to create the '{detail}' role."

        elif task == "delete_role":
            self.message = f":x: I'm missing the required permissions to delete the '{detail}' role."

        elif task == "message_delete":
            self.message = f":x: I'm missing the required permissions to delete that message."

        else:
            self.message = f":x: I'm missing the required permissions to perform this action."
