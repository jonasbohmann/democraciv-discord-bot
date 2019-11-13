import discord


class GenericException(Exception):

    def __init__(self, message, errors):
        super().__init__(message)
        self.message = message
        self.errors = errors


class GenericDiscordException(GenericException):

    def __init__(self, ctx):
        self.ctx = ctx


class RoleNotFoundError(GenericDiscordException):

    def __init__(self, role: str):
        super().ctx.send(f":x: Couldn't find a role named {role}!")


class MemberNotFoundError(GenericDiscordException):

    def __init__(self, member: str):
        super().ctx.send(f":x: Couldn't find a member of this guild named {member}!")
