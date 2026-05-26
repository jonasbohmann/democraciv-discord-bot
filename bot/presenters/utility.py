from bot.services.utility import RoleInfoResult, VeteransResult, WhoisResult
from bot.utils import text


def build_whois_embed(result: WhoisResult) -> text.SafeEmbed:
    person = result.person
    embed = text.SafeEmbed()

    if result.outside_server:
        embed.description = ":warning: This person is not here in this server."

    embed.add_field(name="Person", value=f"{person} {person.mention}", inline=False)
    embed.add_field(name="ID", value=person.id, inline=False)
    embed.add_field(
        name="Discord Registration",
        value=person.created_at.strftime("%B %d, %Y"),
        inline=True,
    )

    if result.role_count is not None:
        join_pos = result.join_position or "Unknown"
        join_date = (
            result.join_date.strftime("%B %d, %Y") if result.join_date else "Unknown"
        )
        embed.add_field(name="Joined", value=join_date, inline=True)
        embed.add_field(
            name="Join Position",
            value=f"{join_pos}/{result.max_members}",
            inline=True,
        )
        embed.add_field(
            name=f"Roles ({result.role_count})",
            value=result.role_mentions,
            inline=False,
        )

    embed.set_thumbnail(url=person.display_avatar.url)
    return embed


def build_role_info_embed(result: RoleInfoResult) -> text.SafeEmbed:
    role = result.role
    embed = text.SafeEmbed(
        title="Role Information",
        description=result.description,
        colour=role.colour,
    )

    embed.add_field(name="Role", value=result.role_name, inline=False)
    embed.add_field(name="ID", value=role.id, inline=False)
    embed.add_field(
        name="Created on", value=role.created_at.strftime("%B %d, %Y"), inline=True
    )
    embed.add_field(name="Colour", value=role.colour, inline=True)
    embed.add_field(
        name=f"Members ({len(role.members)})",
        value=result.role_members,
        inline=False,
    )
    return embed


def build_veterans_embed(result: VeteransResult) -> text.SafeEmbed:
    message = [
        "These are the first 15 people who joined this server.\n"
        "Bot accounts are not counted.\n"
    ]

    for position, veteran in enumerate(result.veterans, start=1):
        fmt = f"{veteran.mention} {veteran}" if veteran else "*Unknown User*"
        message.append(f"{position}. {fmt}")

    embed = text.SafeEmbed(description="\n".join(message))
    embed.set_author(
        name=f"Veterans of {result.guild_name}", icon_url=result.guild_icon
    )
    return embed
