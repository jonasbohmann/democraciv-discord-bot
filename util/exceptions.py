from discord.ext import commands


class GenericException(Exception):

    def __init__(self, message, errors):
        super().__init__(message)
        self.message = message
        self.errors = errors


class GenericDiscordException(commands.CommandError):

    def __init__(self):
        pass


class RoleNotFoundError(GenericDiscordException):

    def __init__(self, role: str):
        self.role = role


class NoOneHasRoleError(GenericDiscordException):
    def __init__(self, role: str):
        self.role = role


class MemberNotFoundError(GenericDiscordException):

    def __init__(self, member: str):
        self.member = member


