import dataclasses
import typing

import discord

from bot.config import config
from bot.slash import forms
from bot.utils import converter


@dataclasses.dataclass
class TagFormResult:
    name: str = ""
    title: str = ""
    content: str = ""
    is_embedded: bool = False
    is_global: bool = False
    people_text: str = ""
    alias: str = ""


SubmitCallback = typing.Callable[
    [discord.Interaction, TagFormResult],
    typing.Awaitable[None],
]


def _modal_title(value: str) -> str:
    if len(value) <= 45:
        return value
    return f"{value[:42]}..."


class TagModal(forms.ErrorHandledModal):
    result: typing.Optional[TagFormResult] = None
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
        result: TagFormResult,
    ):
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()


class TagCreateModal(TagModal):
    def __init__(
        self,
        *,
        can_make_global: bool,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title="Create Tag",
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.name = forms.text_label(
            label="Name",
            description=f"Do not include the `{config.BOT_PREFIX}` prefix.",
            max_length=50,
        )
        self.title_field = forms.text_label(label="Title", max_length=256)
        self.content = forms.text_label(
            label="Content",
            max_length=2000,
            style=discord.TextStyle.long,
        )
        self.is_embedded = forms.checkbox_label(
            label="Send as Embed",
            description="Use an embed-like layout when the tag is shown.",
            default=False,
        )
        self.is_global = (
            forms.checkbox_label(
                label="Global Tag",
                description="Works in every server and in DMs.",
                default=False,
            )
            if can_make_global
            else None
        )

        self.add_item(self.name)
        self.add_item(self.title_field)
        self.add_item(self.content)
        self.add_item(self.is_embedded)
        if self.is_global is not None:
            self.add_item(self.is_global)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            TagFormResult(
                name=self.name.component.value,
                title=self.title_field.component.value,
                content=self.content.component.value,
                is_embedded=self.is_embedded.component.value,
                is_global=bool(self.is_global and self.is_global.component.value),
            ),
        )


class TagEditModal(TagModal):
    def __init__(
        self,
        *,
        tag: converter.Tag,
        can_make_global: bool,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=_modal_title(f"Edit {tag.name}"),
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.tag = tag
        self.title_field = forms.text_label(
            label="Title",
            default=tag.title,
            max_length=256,
        )
        self.content = forms.text_label(
            label="Content",
            default=tag.content,
            max_length=2000,
            style=discord.TextStyle.long,
        )
        self.is_embedded = forms.checkbox_label(
            label="Send as Embed",
            default=tag.is_embedded,
        )
        self.is_global = (
            forms.checkbox_label(
                label="Global Tag",
                description="Works in every server and in DMs.",
                default=tag.is_global,
            )
            if can_make_global
            else None
        )

        self.add_item(self.title_field)
        self.add_item(self.content)
        self.add_item(self.is_embedded)
        if self.is_global is not None:
            self.add_item(self.is_global)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            TagFormResult(
                title=self.title_field.component.value,
                content=self.content.component.value,
                is_embedded=self.is_embedded.component.value,
                is_global=(
                    self.is_global.component.value
                    if self.is_global
                    else self.tag.is_global
                ),
            ),
        )


class TagPeopleModal(TagModal):
    def __init__(
        self,
        *,
        add: bool,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=f"{'Add' if add else 'Remove'} Collaborators",
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
            TagFormResult(people_text=self.people.component.value),
        )


class TagAliasModal(TagModal):
    def __init__(
        self,
        *,
        tag: converter.Tag,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        super().__init__(
            title=_modal_title(f"Alias for {tag.name}"),
            timeout=timeout,
            on_submit_callback=on_submit_callback,
        )
        self.alias = forms.text_label(
            label="Alias",
            description=f"Do not include the `{config.BOT_PREFIX}` prefix.",
            max_length=50,
        )
        self.add_item(self.alias)

    async def on_submit(self, interaction: discord.Interaction):
        await self._complete(
            interaction,
            TagFormResult(alias=self.alias.component.value),
        )
