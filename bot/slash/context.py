import types
import typing

import discord

from discord.utils import MISSING

from bot.utils import text


class InteractionContext:
    """Small compatibility wrapper for code that only needs basic Context fields."""

    def __init__(
        self,
        interaction: discord.Interaction,
        *,
        command_name: str = None,
        ephemeral: bool = False,
    ):
        self.interaction = interaction
        self.bot = interaction.client
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.author = interaction.user
        self.ephemeral = ephemeral
        self.message = types.SimpleNamespace(
            mentions=[],
            role_mentions=[],
            channel_mentions=[],
        )
        self.command = types.SimpleNamespace(
            name=command_name
            or getattr(getattr(interaction, "command", None), "name", None)
            or "slash"
        )

    @property
    def db(self):
        return self.bot.db

    @property
    def guild_icon(self):
        if self.guild and self.guild.icon:
            return self.guild.icon.url

    @property
    def author_icon(self):
        return self.author.display_avatar.url

    async def defer(self, *, ephemeral: bool = None, thinking: bool = True):
        if self.interaction.response.is_done():
            return

        if ephemeral is not None:
            self.ephemeral = ephemeral

        await self.interaction.response.defer(
            ephemeral=self.ephemeral if ephemeral is None else ephemeral,
            thinking=thinking,
        )

    async def send(
        self,
        content: str = MISSING,
        *,
        embed: discord.Embed = MISSING,
        view: typing.Optional[
            typing.Union[discord.ui.View, discord.ui.LayoutView]
        ] = MISSING,
        ephemeral: bool = None,
        **kwargs,
    ):
        if isinstance(embed, text.SafeEmbed):
            embed.clean()

        ephemeral = self.ephemeral if ephemeral is None else ephemeral

        if self.interaction.response.is_done():
            return await self.interaction.followup.send(
                content=content,
                embed=embed,
                view=view,
                ephemeral=ephemeral,
                **kwargs,
            )

        return await self.interaction.response.send_message(
            content=content,
            embed=embed,
            view=view,
            ephemeral=ephemeral,
            **kwargs,
        )


def from_interaction(
    interaction: discord.Interaction,
    *,
    command_name: str = None,
    ephemeral: bool = False,
) -> InteractionContext:
    return InteractionContext(
        interaction, command_name=command_name, ephemeral=ephemeral
    )
