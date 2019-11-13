from discord.ext import commands


class GenericException(Exception):

    def __init__(self, message, errors):
        super().__init__(message)
        self.message = message
        self.errors = errors


class GenericDiscordException(commands.CommandError):

    def __init__(self, message):
        self.message = message


class RoleNotFoundError(GenericDiscordException):

    def __init__(self, role: str):
        self.role = role
        self.message = f":x: Couldn't find a role named '{role}' on this guild!"


class MemberNotFoundError(GenericDiscordException):

    def __init__(self, member: str):
        self.member = member
        self.message = f":x: Couldn't find a member named {member} on this guild!"


class NoOneHasRoleError(GenericDiscordException):
    def __init__(self, role: str):
        self.role = role
        self.message = f":x: No one on this guild has the role named '{role}'!"
