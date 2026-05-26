import typing

import discord
from discord.utils import escape_markdown

from bot.config import config
from bot.services.parties import PartyMemberCount
from bot.utils import converter, text


async def build_party_embed(ctx, party: converter.PoliticalParty) -> text.SafeEmbed:
    embed = text.SafeEmbed()
    logo = await party.get_logo()
    embed.set_author(
        name=party.role.name,
        icon_url=logo or ctx.bot.mk.NATION_ICON_URL,
    )

    if not party.is_independent:
        if ctx.is_slash:
            shortest = (
                min(party.aliases, key=len)
                if party.aliases
                else party.role.name.lower()
            )
            join_hint = f"`/party join` (shortcut: `{shortest}`)."
        else:
            shortest = (
                min(party.aliases, key=len)
                if party.aliases
                else party.role.name.lower()
            )
            join_hint = f"`{config.BOT_PREFIX}join {shortest}`."

        embed.description = (
            f"-# [Platform and Description]({ctx.bot.mk.POLITICAL_PARTIES})\n"
            f"-# Join this party with {join_hint}"
        )
        members_name = "Members"

        if logo:
            embed.set_thumbnail(url=logo)

        embed.add_field(
            name="Server",
            value=party.discord_invite if party.discord_invite else "*N/A*",
        )
        embed.add_field(name="Join Setting", value=party.join_mode.value)

        aliases = [alias for alias in party.aliases if alias != party.role.name.lower()]
        embed.add_field(
            name="Aliases",
            value=", ".join([f"`{alias}`" for alias in aliases]) or "-",
            inline=False,
        )
    else:
        join_hint = (
            f"`/party join`"
            if ctx.is_slash
            else f"`{config.BOT_PREFIX}join {party.role.name}`"
        )
        embed.description = (
            "These people have decided to remain Independent and to not join any "
            f"political party. Become an Independent with {join_hint}."
            f"\n\n[Overview of existing Political Parties]({ctx.bot.mk.POLITICAL_PARTIES})"
        )
        members_name = "Independents"

    party_members = [
        f"{member.mention} {escape_markdown(str(member))}"
        for member in party.role.members
        if member.id not in party.leader_ids
    ]

    for index, leader in enumerate(party.leaders):
        if leader in party.role.members:
            party_members.insert(
                index,
                f"{leader.mention} **{escape_markdown(str(leader))} (Leader)**",
            )

    embed.add_field(
        name=f"{members_name} ({len(party.role.members)})",
        value="\n".join(party_members or ["-"]),
        inline=False,
    )
    return embed


def build_party_list_embed(
    ctx,
    parties_and_members: typing.Sequence[PartyMemberCount],
) -> text.SafeEmbed:
    party_list_embed_content = []

    for party in parties_and_members:
        if party.name == "Independent":
            continue
        suffix = "member" if party.count == 1 else "members"
        party_list_embed_content.append(f"**{party.name}**\n{party.count} {suffix}")

    independent_role = discord.utils.get(ctx.bot.dciv.roles, name="Independent")
    embed = text.SafeEmbed()

    if not party_list_embed_content:
        party_list_embed_content = ["There are no political parties yet."]

    if ctx.is_slash:
        detail_hint = "`/party show`"
        join_hint = "`/party join`"
    else:
        detail_hint = f"`{config.BOT_PREFIX}party <party>`"
        join_hint = f"`{config.BOT_PREFIX}join <party>`"

    base_description = (
        f"-# Check out the [party platforms & descriptions on our Wiki]"
        f"({ctx.bot.mk.POLITICAL_PARTIES}).\n-# For more information about a single "
        f"party, use {detail_hint}.\n-# Join a party with {join_hint}.\n"
    )

    if len(party_list_embed_content) > 5:
        first_half = party_list_embed_content[: len(party_list_embed_content) // 2]
        second_half = party_list_embed_content[len(party_list_embed_content) // 2 :]

        if len(second_half) > len(first_half):
            first_half.append(second_half.pop(0))

        if independent_role:
            independent_count = len(independent_role.members)
            embed.description = (
                f"{base_description}\nThere {'is' if independent_count == 1 else 'are'} "
                f"{independent_count} Independent"
                f"{'s' if independent_count != 1 else ''}."
            )
        else:
            embed.description = base_description

        embed.add_field(name="\u200b", value="\n\n".join(first_half))
        embed.add_field(name="\u200b", value="\n\n".join(second_half))
    else:
        if parties_and_members and independent_role:
            independent_count = len(independent_role.members)
            party_list_embed_content.append(
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n"
                f"{independent_count} citizen"
                f"{'s' if independent_count != 1 else ''}"
            )
        party_lines = "\n\n".join(party_list_embed_content)
        embed.description = f"{base_description}\n\n{party_lines}"

    embed.set_author(
        name=f"Ranking of Political Parties in {ctx.bot.mk.NATION_NAME}",
        icon_url=ctx.bot.mk.NATION_ICON_URL,
    )
    return embed


def build_join_request_embed(ctx, request, leader) -> text.SafeEmbed:
    other_leaders = [
        candidate for candidate in request.leaders if candidate.id != leader.id
    ]
    other_help = ""

    if other_leaders:
        other_help = (
            "\nThe other party leaders, "
            + ", ".join(f"`{other}`" for other in other_leaders)
            + ", also received this message. Once any of you either accept or deny, "
            "that is the final decision."
        )

    embed = text.SafeEmbed(
        title=f"Request to join {request.party.role.name}",
        description=(
            f"{ctx.author.display_name} wants to join your political party "
            f"**{request.party.role.name}**. Do you want to accept their request?\n\n"
            f"{config.HINT} This has no timeout, so you don't have to decide immediately."
            f"{other_help}"
        ),
    )
    embed.set_author(name=ctx.author, icon_url=ctx.author_icon)
    return embed
