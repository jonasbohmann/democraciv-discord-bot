import dataclasses
import typing

import discord

from bot.slash import forms
from bot.utils import converter


@dataclasses.dataclass
class SelfroleFormResult:
    role_name: str = ""
    join_message: str = ""


SubmitCallback = typing.Callable[
    [discord.Interaction, SelfroleFormResult],
    typing.Awaitable[None],
]


def _modal_title(value: str) -> str:
    if len(value) <= 45:
        return value
    return f"{value[:42]}..."


class SelfroleModal(forms.ErrorHandledModal):
    result: typing.Optional[SelfroleFormResult] = None
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
        result: SelfroleFormResult,
    ):
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()


class RoleCreateModal(SelfroleModal):
    def __init__(
        self,
        *,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title="Create Selfrole",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.role_name = forms.text_label(
            label="Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.join_message = forms.text_label(
            label="Join Message",
            description="Shown when someone joins this selfrole.",
            max_length=1000,
            style=discord.TextStyle.long,
        )
        self.add_item(self.role_name)
        self.add_item(self.join_message)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            SelfroleFormResult(
                role_name=self.role_name.component.value,
                join_message=self.join_message.component.value,
            ),
        )


class RoleEditModal(SelfroleModal):
    def __init__(
        self,
        *,
        selfrole: converter.Selfrole,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=_modal_title(f"Edit {selfrole.role.name}"),
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.join_message = forms.text_label(
            label="Join Message",
            description="Shown when someone joins this selfrole.",
            default=selfrole.join_message,
            max_length=1000,
            style=discord.TextStyle.long,
        )
        self.add_item(self.join_message)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            SelfroleFormResult(join_message=self.join_message.component.value),
        )
