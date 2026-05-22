import re
import traceback
import typing

import discord
from discord.ext import commands

from bot.config import config
from bot.slash import context as slash_context
from bot.utils import converter, exceptions

SNOWFLAKE_RE = re.compile(r"(?P<id>[0-9]{15,21})")


class ErrorHandledModal(discord.ui.Modal):
    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        if isinstance(error, exceptions.DemocracivBotException):
            message = error.message
        elif isinstance(error, commands.BadArgument):
            message = str(error)
        else:
            message = f"{config.NO} Something went wrong."
            traceback.print_exception(type(error), error, error.__traceback__)

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


def text_label(
    *,
    label: str,
    description: str = None,
    default: str = None,
    placeholder: str = None,
    required: bool = True,
    max_length: int = None,
    style: discord.TextStyle = discord.TextStyle.short,
):
    return discord.ui.Label(
        text=label,
        description=description,
        component=discord.ui.TextInput(
            style=style,
            default=default,
            placeholder=placeholder,
            required=required,
            max_length=max_length,
        ),
    )


def checkbox_label(
    *,
    label: str,
    description: str = None,
    default: bool = False,
):
    return discord.ui.Label(
        text=label,
        description=description,
        component=discord.ui.Checkbox(default=default),
    )


def split_lines(value: str) -> typing.List[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def strip_prefix(value: str) -> str:
    value = (value or "").strip()
    if value.startswith(config.BOT_PREFIX):
        return value[len(config.BOT_PREFIX) :].strip()
    return value


def _snowflake(value: str) -> typing.Optional[int]:
    match = SNOWFLAKE_RE.search(value or "")
    if not match:
        return None

    return int(match.group("id"))


async def resolve_members(
    ctx: slash_context.InteractionContext,
    value: str,
    *,
    exclude_ids: typing.Iterable[int] = (),
    allow_bots: bool = False,
) -> typing.List[discord.Member]:
    excluded = set(exclude_ids)
    members = []
    seen = set()

    for line in split_lines(value):
        member = None
        maybe_id = _snowflake(line)

        if maybe_id is not None and ctx.guild is not None:
            member = ctx.guild.get_member(maybe_id)

        if member is None:
            try:
                member = await converter.CaseInsensitiveMember().convert(ctx, line)
            except commands.BadArgument:
                member = None

        if (
            member is None
            or member.id in seen
            or member.id in excluded
            or (member.bot and not allow_bots)
        ):
            continue

        seen.add(member.id)
        members.append(member)

    return members


async def resolve_channels(
    ctx: slash_context.InteractionContext,
    value: str,
) -> typing.List[typing.Union[discord.TextChannel, discord.CategoryChannel]]:
    channels = []
    seen = set()

    for line in split_lines(value):
        channel = None
        maybe_id = _snowflake(line)

        if maybe_id is not None and ctx.guild is not None:
            channel = ctx.guild.get_channel(maybe_id)

        if channel is None:
            for conv in (
                converter.CaseInsensitiveTextChannel,
                converter.CaseInsensitiveCategoryChannel,
            ):
                try:
                    channel = await conv().convert(ctx, line)
                    break
                except commands.BadArgument:
                    channel = None

        if (
            not isinstance(channel, (discord.TextChannel, discord.CategoryChannel))
            or channel.id in seen
        ):
            continue

        seen.add(channel.id)
        channels.append(channel)

    return channels


async def resolve_parties(ctx: slash_context.InteractionContext, value: str):
    parties = []
    seen = set()

    for line in split_lines(value):
        try:
            party = await converter.PoliticalParty.convert(ctx, line)
        except exceptions.DemocracivBotException:
            continue

        if party._id in seen:
            continue

        seen.add(party._id)
        parties.append(party)

    return parties
