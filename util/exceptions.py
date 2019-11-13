from discord.ext import commands


class GenericException(Exception):
    """Generic Exception. Unused for now."""
    def __init__(self, message, errors):
        super().__init__(message)
        self.message = message
        self.errors = errors


class GenericDiscordException(commands.CommandError):
    """Generic CommandError exception that gets send to event.error_handler.on_command_error()"""
    def __init__(self, message):
        self.message = message


class RoleNotFoundError(GenericDiscordException):
    """Raised when the bot tries to find a non-existing role on a guild"""
    def __init__(self, role: str):
        self.role = role
        self.message = f":x: Couldn't find a role named '{role}' on this guild!"


class MemberNotFoundError(GenericDiscordException):
    """Raised when the bot tries to find a non-existing member on a guild"""
    def __init__(self, member: str):
        self.member = member
        self.message = f":x: Couldn't find a member named {member} on this guild!"


class NoOneHasRoleError(GenericDiscordException):
    """Raised when the bot tries to get a member object from a role that no member has"""
    def __init__(self, role: str):
        self.role = role
        self.message = f":x: No one on this guild has the role named '{role}'!"
