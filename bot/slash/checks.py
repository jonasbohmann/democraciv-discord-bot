import functools

import discord
from discord import app_commands

from bot.config import config, mk
from bot.utils import exceptions


def is_owner():
    async def predicate(interaction: discord.Interaction):
        return await interaction.client.is_owner(interaction.user)

    return app_commands.check(predicate)


def is_democraciv_guild():
    def predicate(interaction: discord.Interaction):
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != interaction.guild.id:
            raise exceptions.NotDemocracivGuildError()

        return True

    return app_commands.check(predicate)


def has_democraciv_role(role: mk.DemocracivRole):
    def predicate(interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            raise app_commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != interaction.guild.id:
            raise exceptions.NotDemocracivGuildError()

        if interaction.user.id == interaction.client.owner_id:
            return True

        found = discord.utils.get(interaction.user.roles, id=role.value)
        if found is None:
            raise app_commands.MissingRole(role.value)

        return True

    return app_commands.check(predicate)


def has_any_democraciv_role(*roles: mk.DemocracivRole):
    def predicate(interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            raise app_commands.NoPrivateMessage()

        if config.DEMOCRACIV_GUILD_ID != interaction.guild.id:
            raise exceptions.NotDemocracivGuildError()

        if interaction.user.id == interaction.client.owner_id:
            return True

        getter = functools.partial(discord.utils.get, interaction.user.roles)
        if any(getter(id=role.value) is not None for role in roles):
            return True

        raise app_commands.MissingAnyRole([role.value for role in roles])

    return app_commands.check(predicate)


def is_citizen_if_multiciv():
    if not mk.MarkConfig.IS_MULTICIV:
        return app_commands.check(lambda _: True)

    return has_democraciv_role(mk.DemocracivRole.NATION_CITIZEN)


def moderation_or_nation_leader():
    if mk.MarkConfig.IS_MULTICIV:
        return has_any_democraciv_role(
            mk.DemocracivRole.MODERATION, mk.DemocracivRole.NATION_ADMIN
        )

    return has_democraciv_role(mk.DemocracivRole.MODERATION)


def has_guild_permissions(**perms):
    return app_commands.checks.has_permissions(**perms)


def bot_has_guild_permissions(**perms):
    return app_commands.checks.bot_has_permissions(**perms)


def tag_check():
    async def predicate(interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            raise app_commands.NoPrivateMessage()

        if interaction.user.id == interaction.client.owner_id:
            return True

        is_allowed = (
            interaction.user.guild_permissions.administrator
            or await interaction.client.get_guild_setting(
                interaction.guild.id, "tag_creation_allowed"
            )
        )

        if is_allowed:
            return True

        raise exceptions.DemocracivBotException(
            message=f"{config.NO} Only Administrators can add or remove tags on this server."
            " Administrators can change this setting in "
            f"`{config.BOT_PREFIX}server tagcreation`."
        )

    return app_commands.check(predicate)
