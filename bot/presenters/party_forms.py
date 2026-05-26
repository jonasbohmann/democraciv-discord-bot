import dataclasses
import typing

import discord

from bot.slash import forms
from bot.utils import converter

JOIN_MODE_OPTIONS = [
    discord.SelectOption(
        label="Public",
        value=converter.PoliticalPartyJoinMode.PUBLIC.value,
        description="Anyone can join this party.",
    ),
    discord.SelectOption(
        label="Request",
        value=converter.PoliticalPartyJoinMode.REQUEST.value,
        description="Leaders approve or deny join requests.",
    ),
    discord.SelectOption(
        label="Private",
        value=converter.PoliticalPartyJoinMode.PRIVATE.value,
        description="Only leaders can bypass the private setting.",
    ),
]


@dataclasses.dataclass
class PartyFormResult:
    role_name: str = ""
    leaders_text: str = ""
    invite: str = ""
    join_mode: str = ""
    parties_text: str = ""
    alias: str = ""


SubmitCallback = typing.Callable[
    [discord.Interaction, PartyFormResult],
    typing.Awaitable[None],
]


def _modal_title(value: str) -> str:
    if len(value) <= 45:
        return value
    return f"{value[:42]}..."


def _join_mode_options(default: str = None):
    options = []

    for option in JOIN_MODE_OPTIONS:
        options.append(
            discord.SelectOption(
                label=option.label,
                value=option.value,
                description=option.description,
                default=option.value == default,
            )
        )

    return options


class PartyModal(forms.ErrorHandledModal):
    result: typing.Optional[PartyFormResult] = None
    submit_interaction: typing.Optional[discord.Interaction] = None

    def __init__(
        self,
        *args,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        **kwargs,
    ):
        self._on_submit_callback = on_submit_callback
        super().__init__(*args, **kwargs)

    async def _complete(
        self,
        interaction: discord.Interaction,
        result: PartyFormResult,
    ):
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()


class PartyCreateModal(PartyModal):
    def __init__(
        self,
        *,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title="Create Political Party",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.name = forms.text_label(
            label="Party Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="Discord Invite",
            description="Optional invite link to the party server.",
            required=False,
            max_length=512,
        )
        self.join_mode = discord.ui.Label(
            text="Join Mode",
            description="How citizens can join this party.",
            component=discord.ui.Select(options=JOIN_MODE_OPTIONS),
        )
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            PartyFormResult(
                role_name=self.name.component.value,
                leaders_text=self.leaders.component.value,
                invite=self.invite.component.value,
                join_mode=self.join_mode.component.values[0],
            ),
        )


class PartyEditModal(PartyModal):
    def __init__(
        self,
        *,
        party: converter.PoliticalParty,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=_modal_title(f"Edit {party.role.name}"),
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.party = party
        self.name = forms.text_label(
            label="Party Name",
            default=party.role.name,
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            default="\n".join(str(leader.id) for leader in party.leaders),
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="Discord Invite",
            default=party.discord_invite or "",
            required=False,
            max_length=512,
        )
        self.join_mode = discord.ui.Label(
            text="Join Mode",
            description="How citizens can join this party.",
            component=discord.ui.Select(
                options=_join_mode_options(default=party.join_mode.value)
            ),
        )
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            PartyFormResult(
                role_name=self.name.component.value,
                leaders_text=self.leaders.component.value,
                invite=self.invite.component.value,
                join_mode=self.join_mode.component.values[0],
            ),
        )


class PartyMergeModal(PartyModal):
    def __init__(
        self,
        *,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title="Merge Political Parties",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.parties = forms.text_label(
            label="Parties to Merge",
            description="Party names, IDs, or aliases. One per line.",
            style=discord.TextStyle.long,
        )
        self.name = forms.text_label(
            label="New Party Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="New Party Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="New Party Discord Invite",
            description="Optional invite link to the party server.",
            required=False,
            max_length=512,
        )
        self.join_mode = discord.ui.Label(
            text="New Party Join Mode",
            description="How citizens can join the merged party.",
            component=discord.ui.Select(options=JOIN_MODE_OPTIONS),
        )
        self.add_item(self.parties)
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            PartyFormResult(
                parties_text=self.parties.component.value,
                role_name=self.name.component.value,
                leaders_text=self.leaders.component.value,
                invite=self.invite.component.value,
                join_mode=self.join_mode.component.values[0],
            ),
        )


class PartyAliasModal(PartyModal):
    def __init__(
        self,
        *,
        party: converter.PoliticalParty,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=_modal_title(f"Alias for {party.role.name}"),
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.alias = forms.text_label(
            label="Alias",
            max_length=100,
        )
        self.add_item(self.alias)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            PartyFormResult(alias=self.alias.component.value),
        )
