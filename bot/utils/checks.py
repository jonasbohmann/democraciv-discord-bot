import functools
import discord

from discord.ext import commands

from bot.config import config, mk
from bot.utils import exceptions


def is_democraciv_guild():
    """Commands check decorator to check if a command was invoked on the Democraciv guild"""

    def check(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        return True

    return commands.check(check)


def has_democraciv_role(role: mk.DemocracivRole):
    """Commands check decorator to check if a command was invoked on the Democraciv guild AND to check whether the
    person has the specified role from text.py"""

    def predicate(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        if ctx.author.id == ctx.bot.owner_id:
            return True

        found = discord.utils.get(ctx.author.roles, id=role.value)

        if found is None:
            raise commands.MissingRole(role)

        return True

    return commands.check(predicate)


def has_any_democraciv_role(*roles: mk.DemocracivRole):
    """Commands check decorator to check if a command was invoked on the Democraciv guild AND to check whether the
    person has any of the specified roles from text.py"""

    def predicate(ctx):
        if not isinstance(ctx.channel, discord.abc.GuildChannel):
            raise commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()

        if ctx.author.id == ctx.bot.owner_id:
            return True

        getter = functools.partial(discord.utils.get, ctx.author.roles)

        if any(getter(id=role.value) is not None for role in roles):
            return True

        raise commands.MissingAnyRole(roles)

    return commands.check(predicate)


def tag_check():
    """Check to see if tag creation is allowed by everyone or just Administrators."""

    async def check(ctx):
        if ctx.author.id == ctx.bot.owner_id:
            return True

        is_allowed = ctx.author.guild_permissions.administrator or await ctx.bot.get_guild_setting(
            ctx.guild.id, "tag_creation_allowed"
        )

        if is_allowed:
            return True
        else:
            raise exceptions.DemocracivBotException(
                message=f"{config.NO} Only Administrators can add or remove tags on this server."
                " Administrators can change this setting in "
                f"`{config.BOT_PREFIX}server tagcreation`."
            )

    return commands.check(check)


def moderation_or_nation_leader():
    if mk.MarkConfig.IS_MULTICIV:
        return has_any_democraciv_role(mk.DemocracivRole.MODERATION, mk.DemocracivRole.NATION_ADMIN)
    else:
        return has_democraciv_role(mk.DemocracivRole.MODERATION)
