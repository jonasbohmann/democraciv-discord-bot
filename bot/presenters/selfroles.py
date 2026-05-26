import typing

import discord

from bot.config import config
from bot.utils import text


def build_selfrole_list_embed(
    ctx,
    roles: typing.Sequence[discord.Role],
) -> text.SafeEmbed:
    if ctx.is_slash:
        hint = (
            "-# Looking for political parties? Try `/party list` and `/party join`.\n"
            "-# In order to add or remove a role from you, use `/role toggle`.\n"
        )
    else:
        hint = (
            f"-# Looking for political parties? Try `{config.BOT_PREFIX}party` and "
            f"`{config.BOT_PREFIX}join <party>`.\n"
            f"-# In order to add or remove a role from you, use "
            f"`{config.BOT_PREFIX}role <role>`.\n"
        )

    embed_message = [hint]
    embed_message.extend(f"* {role.name}" for role in roles)

    embed = text.SafeEmbed(description="\n".join(embed_message))
    embed.set_author(
        name=f"Selfroles in {ctx.guild.name}",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
    )
    return embed
