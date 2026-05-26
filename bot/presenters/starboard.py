from bot.services.starboard import StarboardMemberStats, StarboardOverview
from bot.utils import text


def records_to_value(records, fmt=None, default="-"):
    if not records:
        return default

    emoji = 0x1F947
    fmt = fmt or (lambda value: value)
    return "\n".join(
        f"{chr(emoji + index)} {fmt(record.id)} ({record.stars} stars)"
        for index, record in enumerate(records)
    )


def build_overview_embed(stats: StarboardOverview) -> text.SafeEmbed:
    embed = text.SafeEmbed(
        title="Starboard Stats",
        description=f"So far, there are {stats.total_starred_messages} messages starred"
        f" with a total of {stats.total_stars} stars.",
        colour=0xFFAC33,
    )

    embed.add_field(
        name="Top Starred Messages",
        value=records_to_value(stats.top_starred_messages),
        inline=False,
    )

    to_mention = lambda member_id: f"<@{member_id}>"
    embed.add_field(
        name="Top Star Receivers",
        value=records_to_value(stats.top_star_receivers, to_mention, default="No one!"),
        inline=False,
    )
    embed.add_field(
        name="Top Star Givers",
        value=records_to_value(stats.top_star_givers, to_mention, default="No one!"),
        inline=False,
    )

    if stats.starboard_channel is not None:
        embed.set_footer(
            text="Collecting stars since",
            icon_url="https://cdn.discordapp.com/attachments/"
            "639549494693724170/679824104190115911/star.png",
        )
        embed.timestamp = stats.starboard_channel.created_at

    return embed


def build_member_embed(stats: StarboardMemberStats) -> text.SafeEmbed:
    embed = text.SafeEmbed(colour=0xFFAC33)
    embed.set_author(
        name=stats.member.display_name,
        icon_url=stats.member.display_avatar.url,
    )

    embed.add_field(
        name="Messages on the Starboard",
        value=stats.messages_starred,
        inline=False,
    )
    embed.add_field(name="Stars Received", value=stats.stars_received, inline=True)
    embed.add_field(name="Stars Given", value=stats.stars_given, inline=True)
    embed.add_field(
        name="Top Starred Messages",
        value=records_to_value(stats.top_starred_messages),
        inline=False,
    )
    return embed
