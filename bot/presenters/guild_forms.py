import dataclasses
import typing

import discord

from bot.slash import forms


@dataclasses.dataclass
class WelcomeMessageFormResult:
    message: str


@dataclasses.dataclass
class RedditFeedFormResult:
    subreddit: str


SubmitCallback = typing.Callable[
    [discord.Interaction, typing.Union[WelcomeMessageFormResult, RedditFeedFormResult]],
    typing.Awaitable[None],
]


class WelcomeMessageModal(forms.ErrorHandledModal):
    result: typing.Optional[WelcomeMessageFormResult] = None
    submit_interaction: typing.Optional[discord.Interaction] = None

    def __init__(
        self,
        *,
        current_message: str = "",
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        self._on_submit_callback = on_submit_callback
        super().__init__(
            title="Welcome Message",
            timeout=timeout,
        )
        self.message = forms.text_label(
            label="Welcome Message",
            description="Variables: {mention}, {user}, {username}, {server}, {channel}",
            default=current_message or "",
            style=discord.TextStyle.long,
            max_length=2000,
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        result = WelcomeMessageFormResult(message=self.message.component.value)
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()


class RedditFeedModal(forms.ErrorHandledModal):
    result: typing.Optional[RedditFeedFormResult] = None
    submit_interaction: typing.Optional[discord.Interaction] = None

    def __init__(
        self,
        *,
        on_submit_callback: typing.Optional[SubmitCallback] = None,
        timeout: float = 300,
    ):
        self._on_submit_callback = on_submit_callback
        super().__init__(
            title="Add Subreddit Feed",
            timeout=timeout,
        )
        self.subreddit = forms.text_label(
            label="Subreddit",
            description="Do not include the leading /r/.",
            max_length=100,
        )
        self.add_item(self.subreddit)

    async def on_submit(self, interaction: discord.Interaction):
        result = RedditFeedFormResult(subreddit=self.subreddit.component.value)
        self.result = result
        self.submit_interaction = interaction

        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, result)
        else:
            await interaction.response.send_message("Submitted.", ephemeral=True)

        self.stop()
