import textwrap
import typing

import discord

from bot.config import config
from bot.services.guild import LOG_EVENT_COLUMNS
from bot.services.results import PageResult
from bot.utils import text


def build_server_overview_embed(ctx, settings) -> text.SafeEmbed:
    excluded_channels = len(settings["private_channels"])

    embed = text.SafeEmbed(
        description=f"Check **`{config.BOT_PREFIX}help server`** to see how you can configure me for this server.",
    )
    embed.set_author(name=ctx.guild.name, icon_url=ctx.guild_icon)
    embed.add_field(
        name="Settings",
        value=f"{ctx.bot.emojify_boolean(settings['welcome_enabled'])} Welcome Messages\n"
        f"{ctx.bot.emojify_boolean(settings['logging_enabled'])} Logging ({excluded_channels} hidden channels)\n"
        f"{ctx.bot.emojify_boolean(settings['default_role_enabled'])} Role on Join\n"
        f"{ctx.bot.emojify_boolean(settings['tag_creation_allowed'])} Tag Creation by Everyone\n"
        f"{ctx.bot.emojify_boolean(settings['npc_usage_allowed'])} NPC Usage Allowed",
    )
    embed.add_field(
        name="Statistics",
        value=f"{ctx.guild.member_count} members\n"
        f"{len(ctx.guild.text_channels)} text channels\n"
        f"{len(ctx.guild.voice_channels)} voice channels\n"
        f"{len(ctx.guild.roles)} roles\n"
        f"{len(ctx.guild.emojis)} custom emojis",
    )
    embed.set_footer(
        text=f"Server was created on {ctx.guild.created_at.strftime('%A, %B %d %Y')}"
    )
    embed.set_thumbnail(url=ctx.guild_icon)
    return embed


def build_welcome_embed(
    ctx,
    settings,
    current_channel: typing.Optional[discord.TextChannel],
) -> text.SafeEmbed:
    current_message = settings["welcome_message"]
    if not current_message:
        current_message = "-"
    elif len(current_message) > 1024:
        current_message = textwrap.shorten(current_message, 1024)

    embed = text.SafeEmbed()
    embed.set_author(
        name=f"Welcome Messages on {ctx.guild.name}", icon_url=ctx.guild_icon
    )
    embed.add_field(
        name="Enabled", value=ctx.bot.emojify_boolean(settings["welcome_enabled"])
    )
    embed.add_field(
        name="Welcome Channel",
        value=current_channel.mention if current_channel else "-",
    )
    embed.add_field(name="Welcome Message", value=current_message, inline=False)
    return embed


def build_logging_embed(
    ctx,
    settings,
    current_channel: typing.Optional[discord.TextChannel],
) -> text.SafeEmbed:
    embed = text.SafeEmbed(
        description=f"If you want to change what specific events I should log, use my `{config.BOT_PREFIX}server logs events` command."
    )
    embed.set_author(name=f"Event Logging on {ctx.guild.name}", icon_url=ctx.guild_icon)
    embed.add_field(
        name="Enabled", value=ctx.bot.emojify_boolean(settings["logging_enabled"])
    )
    embed.add_field(
        name="Log Channel",
        value=current_channel.mention if current_channel else "-",
    )
    return embed


def build_logging_events_embed(ctx, settings) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    embed.set_author(name=f"Events to Log on {ctx.guild.name}", icon_url=ctx.guild_icon)
    for event_name, column in LOG_EVENT_COLUMNS.items():
        embed.add_field(
            name=event_name.replace("_", " ").title(),
            value=ctx.bot.emojify_boolean(settings[column]),
        )
    return embed


def build_default_role_embed(ctx, settings) -> text.SafeEmbed:
    current_role = ctx.guild.get_role(settings["default_role_role"])
    embed = text.SafeEmbed()
    embed.set_author(name=f"Role on Join on {ctx.guild.name}", icon_url=ctx.guild_icon)
    embed.add_field(
        name="Enabled", value=ctx.bot.emojify_boolean(settings["default_role_enabled"])
    )
    embed.add_field(name="Role", value=current_role.mention if current_role else "-")
    return embed


def build_tag_creation_embed(ctx, settings) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    embed.set_author(name=f"Tag Creation on {ctx.guild.name}", icon_url=ctx.guild_icon)
    embed.add_field(
        name="Allowed Tag Creators",
        value="Everyone" if settings["tag_creation_allowed"] else "Only Administrators",
    )
    return embed


def build_npc_usage_embed(ctx, settings) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    embed.set_author(name=f"NPC Usage on {ctx.guild.name}", icon_url=ctx.guild_icon)
    embed.add_field(
        name="Allowed",
        value=ctx.bot.emojify_boolean(settings["npc_usage_allowed"]),
    )
    return embed


def hidden_channel_help_description(ctx, logging_channel: discord.TextChannel) -> str:
    command = (
        "/server hide-channel <channel_name>"
        if ctx.is_slash
        else f"{config.BOT_PREFIX}server hidechannel <channel_name>"
    )
    return (
        f"When you hide a channel, it (and all its threads) will no longer show up in "
        f"{logging_channel.mention}.\n\nAdditionally, :star: reactions for the "
        f"starboard will no longer count in that channel (and in all its threads).\n\n"
        f"You can hide a channel, or even an entire category at once, with "
        f"`{command}`\n\n__**Hidden Channels**__"
    )


def hidden_channels_empty_message(ctx, logging_channel: discord.TextChannel) -> str:
    if ctx.is_slash:
        return f"{config.NO} There are no hidden channels on this server yet."

    return (
        f"{config.NO} There are no hidden channels on this server yet. "
        f"You can hide a channel so that it no longer shows up in "
        f"{logging_channel.mention} with "
        f"`{config.BOT_PREFIX}server hidechannel <channel_name>`."
        f"\n{config.HINT} You can also hide entire categories! Just hide the category "
        f"and every channel in that category will be hidden automatically. "
        f"Note that if channel is hidden, :star: reactions for the starboard will no "
        f"longer count in it."
    )


def build_hidden_channels_page(
    ctx,
    settings,
    logging_channel: discord.TextChannel,
) -> PageResult:
    entries = [hidden_channel_help_description(ctx, logging_channel)]

    for channel_id in settings["private_channels"]:
        channel = ctx.bot.get_channel(channel_id)
        if channel:
            entries.append(
                channel.mention if hasattr(channel, "mention") else channel.name
            )

    return PageResult(
        entries=entries,
        author=f"Hidden Channels on {ctx.guild.name}",
        icon=ctx.guild_icon,
        empty_message="There are no hidden channels on this server.",
    )
