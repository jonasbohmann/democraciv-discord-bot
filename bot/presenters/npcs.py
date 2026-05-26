import collections
import dataclasses
import typing

import discord
from discord.utils import escape_markdown

from bot.config import config
from bot.services.results import PageResult
from bot.utils import text

DEFAULT_NPC_AVATAR = (
    "https://cdn.discordapp.com/avatars/487345900239323147/"
    "79c38314283392c7e21bab76f77e09e9.png"
)
NPC_EXAMPLE_IMAGE = (
    "https://cdn.discordapp.com/attachments/818226072805179392/"
    "818230819835215882/npc.gif"
)


@dataclasses.dataclass
class AutomaticOverview:
    page: typing.Optional[PageResult] = None
    embed: typing.Optional[discord.Embed] = None


def build_about_embed(ctx) -> text.SafeEmbed:
    prefix = config.BOT_PREFIX
    create_hint = "/npc create" if ctx.is_slash else f"{prefix}npc create"
    server_hint = "/server npc-usage" if ctx.is_slash else f"{prefix}server npc"
    help_hint = (
        f"`{prefix}help` or `{prefix}commands`"
        if ctx.is_slash
        else f"`{prefix}help npcs` or `{prefix}commands`"
    )

    embed = text.SafeEmbed(
        description=(
            "NPCs allow you to make it look like you speak as a different character, "
            "or on behalf of someone else, like an organization or group.\n\n"
            "This can elevate the role-playing experience by making it clear "
            "when someone talks in character, or out-of-character (OOC). "
            "Political parties, newspapers, government departments or other groups can "
            "use this to release official looking announcements.\n\n"
            f"To get started, you can create a new NPC with `{create_hint}`. NPCs are "
            "not bound to any server, every NPC that you make on this server can "
            "also be used in every other server I am in.\n\nServer administrators "
            "can disable NPC usage on their server for any reason with "
            f"`{server_hint}`.\n\n\nSee {help_hint} to see every NPC-related command "
            "and learn more about them."
        )
    )
    embed.set_author(name="What are NPCs?", icon_url=ctx.bot.dciv.icon.url)
    embed.set_image(url=NPC_EXAMPLE_IMAGE)
    return embed


def build_npc_list_pages(
    ctx, member, records: typing.Sequence[typing.Mapping]
) -> PageResult:
    entries = []

    for record in records:
        avatar = f"[Avatar]({record['avatar_url']})\n" if record["avatar_url"] else ""
        owner = ctx.bot.get_user(record["owner_id"])
        owner_value = (
            "\n"
            if not owner
            else f"Owner: {owner.mention} {escape_markdown(str(owner))}\n"
        )

        entries.append(
            f"**__NPC #{record['id']} - {escape_markdown(record['name'])}__**"
        )
        entries.append(
            f"{avatar}Trigger Phrase: `{escape_markdown(record['trigger_phrase'])}`"
        )
        entries.append(owner_value)

    if entries:
        if ctx.is_slash:
            entries.insert(
                0,
                "You can create a new NPC with `/npc create`, or edit the name, "
                "avatar and/or trigger phrase of an existing one with `/npc edit <npc>`.\n",
            )
        else:
            entries.insert(
                0,
                f"You can create a new NPC with `{config.BOT_PREFIX}npc create`, "
                "or edit the name, avatar and/or trigger phrase of an existing one "
                f"with `{config.BOT_PREFIX}npc edit <npc>`.\n",
            )

    return PageResult(
        entries=entries,
        author=f"{member.display_name}'s NPCs",
        icon=member.display_avatar.url,
        per_page=20,
        empty_message="This person hasn't made any NPCs yet.",
    )


def build_info_embed(
    ctx,
    *,
    npc,
    allowed_people,
    automatic_channels,
    has_access: bool,
    is_owner: bool,
) -> text.SafeEmbed:
    embed = text.SafeEmbed()

    if is_owner:
        edit_hint = (
            f"/npc edit {npc.id}"
            if ctx.is_slash
            else f"{config.BOT_PREFIX}npc edit {npc.id}"
        )
        embed.description = (
            "You, the owner of this NPC, can edit the name, avatar and/or the trigger "
            f"phrase of this NPC with `{edit_hint}`."
        )

    embed.set_author(
        name=f"NPC #{npc.id} - {npc.name}",
        icon_url=npc.avatar_url or DEFAULT_NPC_AVATAR,
    )

    if npc.avatar_url:
        embed.set_thumbnail(url=npc.avatar_url)

    embed.add_field(name="Owner", value=f"{npc.owner.mention} {npc.owner}")
    embed.add_field(
        name="Trigger Phrase",
        value=(
            f"`{npc.trigger_phrase}`\n\nPeople with access to this NPC can send "
            f"messages like this: `{npc.trigger_phrase.replace('text', 'Hello!')}`"
        ),
        inline=False,
    )

    pretty_people = []
    if is_owner:
        share_hint = (
            f"/npc share {npc.id}"
            if ctx.is_slash
            else f"{config.BOT_PREFIX}npc share {npc.id}"
        )
        unshare_hint = (
            f"/npc unshare {npc.id}"
            if ctx.is_slash
            else f"{config.BOT_PREFIX}npc unshare {npc.id}"
        )
        pretty_people.append(
            "You, the owner of this NPC, can allow other people to speak as this NPC "
            f"with `{share_hint}`, or deny someone that you previously allowed with "
            f"`{unshare_hint}`.\n"
        )

    pretty_people.append(f"{npc.owner.mention} ({escape_markdown(str(npc.owner))})")
    pretty_people.extend(
        f"{user.mention} ({escape_markdown(str(user))})" for user in allowed_people
    )
    embed.add_field(
        name="People with access to this NPC",
        value="\n".join(pretty_people),
        inline=False,
    )

    if ctx.guild and has_access:
        pretty_channels = [_format_channel(channel) for channel in automatic_channels]
        embed.add_field(
            name="Automatic Mode",
            value="\n".join(pretty_channels)
            or "__You__ don't have automatic mode enabled for this NPC in any channel "
            "or channel category on __this__ server.",
        )

    return embed


def build_automatic_overview(ctx, records, npc_cache) -> AutomaticOverview:
    grouped_by_npc = collections.defaultdict(list)
    entries = [_automatic_intro(ctx)]

    for record in records:
        channel = ctx.guild.get_channel(record["channel_id"])
        if channel is not None:
            grouped_by_npc[record["npc_id"]].append(channel)

    for npc_id, channels in grouped_by_npc.items():
        npc = npc_cache[npc_id]
        pretty_channels = [f"- {_format_channel(channel)}" for channel in channels]
        entries.append(
            f"**__{escape_markdown(npc['name'])}__**\n" + "\n".join(pretty_channels)
        )

    if len(entries) > 1:
        return AutomaticOverview(
            page=PageResult(
                entries=entries,
                icon=ctx.guild_icon,
                per_page=15,
                author=f"{ctx.author.display_name}'s Automatic NPCs",
            )
        )

    embed = text.SafeEmbed(description=entries[0])
    embed.set_author(
        name=f"{ctx.author.display_name}'s Automatic NPCs",
        icon_url=ctx.guild_icon,
    )
    return AutomaticOverview(embed=embed)


def _automatic_intro(ctx) -> str:
    if ctx.is_slash:
        enable_hint = "/npc automatic enable <npc>"
        disable_hint = "/npc automatic disable <npc>"
    else:
        enable_hint = f"{config.BOT_PREFIX}npc automatic on <npc>"
        disable_hint = f"{config.BOT_PREFIX}npc automatic off <npc>"

    return (
        "If you want to automatically speak as an NPC in a certain channel or channel "
        f"category without having to use the trigger phrase, use `{enable_hint}`, or "
        f"disable it with `{disable_hint}`.\n\nYou can only have one automatic NPC "
        "per channel.\n\nIf you have one NPC as automatic in an entire category, but "
        "a different NPC in a single channel that is in that same category, and you "
        "write something in that channel, you will only speak as the NPC for that "
        "specific channel, and not as both NPCs.\n\n"
    )


def _format_channel(channel) -> str:
    if isinstance(channel, discord.TextChannel):
        return channel.mention
    return f"{channel.name} Category"
