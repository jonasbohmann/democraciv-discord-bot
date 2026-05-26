import dataclasses
import typing

import discord

from bot.slash import forms


@dataclasses.dataclass
class NPCFormResult:
    name: str = ""
    avatar_url: str = ""
    trigger_phrase: str = ""
    people_text: str = ""
    channels_text: str = ""


SubmitCallback = typing.Callable[
    [discord.Interaction, NPCFormResult],
    typing.Awaitable[None],
]


class NPCModal(forms.ErrorHandledModal):
    result: typing.Optional[NPCFormResult] = None
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
        result: NPCFormResult,
    ):
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()


class NPCFormModal(NPCModal):
    def __init__(
        self,
        *,
        npc: typing.Optional[typing.Any] = None,
        name_default: str = None,
        avatar_default: str = None,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title="Edit NPC" if npc else "Create NPC",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.name = forms.text_label(
            label="Name",
            default=npc.name if npc else name_default,
            max_length=80,
        )
        self.avatar_url = forms.text_label(
            label="Avatar URL",
            description="Optional permanent image URL.",
            default=npc.avatar_url if npc and npc.avatar_url else avatar_default or "",
            required=False,
            max_length=512,
        )
        self.trigger_phrase = forms.text_label(
            label="Trigger Phrase",
            description="Use `text` where the message content should go, e.g. <<text",
            default=npc.trigger_phrase if npc else None,
            max_length=100,
        )
        self.add_item(self.name)
        self.add_item(self.avatar_url)
        self.add_item(self.trigger_phrase)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            NPCFormResult(
                name=self.name.component.value,
                avatar_url=self.avatar_url.component.value,
                trigger_phrase=self.trigger_phrase.component.value,
            ),
        )


class NPCPeopleModal(NPCModal):
    def __init__(
        self,
        *,
        add: bool,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=f"{'Share' if add else 'Unshare'} NPC",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.people = forms.text_label(
            label="People",
            description="Mentions, IDs, names, or nicknames. One per line.",
            style=discord.TextStyle.long,
        )
        self.add_item(self.people)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            NPCFormResult(people_text=self.people.component.value),
        )


class NPCAutomaticChannelsModal(NPCModal):
    def __init__(
        self,
        *,
        add: bool,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=f"{'Enable' if add else 'Disable'} Automatic NPC",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.channels = forms.text_label(
            label="Channels or Categories",
            description="Mentions, IDs, or names. One per line.",
            style=discord.TextStyle.long,
        )
        self.add_item(self.channels)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            NPCFormResult(channels_text=self.channels.component.value),
        )
