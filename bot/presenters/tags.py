import dataclasses
import typing

import discord

from bot.config import config
from bot.services import tags as tag_service
from bot.utils import converter, text


@dataclasses.dataclass
class TagDisplay:
    content: typing.Optional[str] = None
    embed: typing.Optional[text.SafeEmbed] = None
    fallback_content: typing.Optional[str] = None


def build_tag_display(
    tag: converter.Tag,
    content_type: tag_service.TagContentType,
) -> TagDisplay:
    if tag.is_embedded:
        if content_type is tag_service.TagContentType.IMAGE:
            embed = text.SafeEmbed(title=tag.title)
            embed.set_image(url=tag.content)
            return TagDisplay(embed=embed, fallback_content=tag.clean_content)

        if content_type is tag_service.TagContentType.VIDEO:
            return TagDisplay(content=tag.clean_content)

        return TagDisplay(
            embed=text.SafeEmbed(title=tag.title, description=tag.content)
        )

    return TagDisplay(content=tag.clean_content)


def build_info_embed(tag: converter.Tag) -> text.SafeEmbed:
    pretty_aliases = (
        ", ".join(f"`{config.BOT_PREFIX}{alias}`" for alias in tag.aliases)
    ) or "-"
    embed = text.SafeEmbed(title=tag.title)

    is_global = "Yes" if tag.is_global else "No"
    is_embedded = "Embed" if tag.is_embedded else "Plain Text"

    if isinstance(tag.author, discord.Member):
        embed.add_field(name="Author", value=tag.author.mention, inline=False)
        embed.set_author(
            name=tag.author.name,
            icon_url=tag.author.display_avatar.url,
        )
    elif isinstance(tag.author, discord.User):
        embed.add_field(
            name="Author",
            value=f"*The author of this tag left this server.*\n"
            f"*You can claim this tag to make it yours with*\n"
            f"`{config.BOT_PREFIX}tag claim {tag.name}`",
            inline=False,
        )
        embed.set_author(
            name=tag.author.name,
            icon_url=tag.author.display_avatar.url,
        )
    elif tag.author is None:
        embed.add_field(
            name="Author",
            value=f"*The author of this tag left this server.*\n"
            f"*You can claim this tag to make it yours with*\n"
            f"`{config.BOT_PREFIX}tag claim {tag.name}`",
            inline=False,
        )

    embed.add_field(name="Global Tag", value=is_global, inline=True)
    embed.add_field(name="Tag Format", value=is_embedded, inline=True)
    embed.add_field(name="Uses", value=tag.uses, inline=False)
    embed.add_field(
        name="Collaborators",
        value="\n".join(
            [
                f"{collaborator.mention} {collaborator}"
                for collaborator in tag.collaborators
            ]
            or [
                f"*The owner of this tag can add other people as collaborators "
                f"for this tag, so that they can edit and add & remove aliases, "
                f"with `{config.BOT_PREFIX}tag share {tag.name}`.*\n\n-"
            ]
        ),
    )
    embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
    return embed


def build_person_stats_embed(stats: tag_service.TagPersonStats) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    embed.set_author(
        name=stats.person.display_name,
        icon_url=stats.person.display_avatar.url,
    )

    embed.add_field(name="Amount of Tags from any Server", value=stats.total_tags)
    embed.add_field(
        name="Amount of Global Tags from any Server",
        value=stats.global_tags,
    )
    embed.add_field(
        name="Amount of Tags from this Server",
        value=stats.local_tags,
        inline=False,
    )
    embed.add_field(
        name="Top Tags from this Server (Global and Local)",
        value=format_tag_stats(stats.top_local_tags),
        inline=False,
    )
    embed.add_field(
        name="Top Global Tags from any Server",
        value=format_tag_stats(stats.top_global_tags),
        inline=False,
    )
    return embed


def build_overview_stats_embed(stats: tag_service.TagOverviewStats) -> text.SafeEmbed:
    embed = text.SafeEmbed(
        description=f"There are {stats.total_tags} tags in total, of which "
        f"{stats.global_tags} are global. {stats.local_tags} are from this server."
    )
    embed.set_author(name=f"Tags on {stats.guild_name}", icon_url=stats.guild_icon)
    embed.add_field(
        name="Top Global Tags",
        value=format_tag_stats(stats.top_global_tags),
        inline=False,
    )
    embed.add_field(
        name="Top Tags from this Server (Global and Local)",
        value=format_tag_stats(stats.top_server_tags),
        inline=False,
    )
    embed.add_field(
        name="Top Local Tags from this Server",
        value=format_tag_stats(stats.top_local_tags),
        inline=False,
    )
    embed.add_field(
        name="People with the most Global Tags from any Server",
        value=format_author_stats(stats.top_global_tag_creators, "global tags"),
        inline=False,
    )
    embed.add_field(
        name="People with the most Tags from this Server",
        value=format_author_stats(stats.top_server_tag_creators, "tags"),
        inline=False,
    )
    return embed


def format_tag_stats(records: typing.Sequence[tag_service.TagStatsRecord]) -> str:
    if not records:
        return "-"

    return "\n".join(
        f"{index}. `{config.BOT_PREFIX}{record.name}` ({record.uses} uses)"
        for index, record in enumerate(records, start=1)
    )


def format_author_stats(
    records: typing.Sequence[tag_service.TagAuthorStats],
    stats_name: str,
) -> str:
    lines = []

    for index, record in enumerate(records, start=1):
        name = stats_name[:-1] if record.amount == 1 else stats_name
        lines.append(f"{index}. {record.user.mention} with {record.amount} {name}")

    return "\n".join(lines) or "None"
