import collections
import copy
import datetime
import textwrap
import typing
import discord

from discord.ext import tasks, menus, commands
from bot.config import config, mk
from bot.utils import exceptions


def split_string_into_multiple(string: str, length: int):
    prefix = suffix = ""

    if string.startswith("```"):
        prefix = "```"
        string = string[3:]

    if string.endswith("```"):
        suffix = "```"
        string = string[:-3]

    paginator = commands.Paginator(prefix=prefix, suffix=suffix, max_size=length)

    for line in string.splitlines():
        paginator.add_line(line)

    return paginator.pages


class AnnouncementScheduler:
    def __init__(self, bot, channel):
        self.bot = bot
        self._channel: mk.DemocracivChannel = channel
        self._objects: typing.List = []
        self._last_addition = None
        self.wait_time = 5
        self._task = None

    def __del__(self):
        if self._task is not None:
            self._task.cancel()

    @property
    def channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.get_democraciv_channel(self._channel)

    def get_embed(self) -> typing.Optional[discord.Embed]:
        pass

    def get_message(self) -> typing.Optional[str]:
        pass

    def add(self, obj):
        if len(self._objects) == 0:
            self._task = copy.copy(self._wait)
            self._task.start()

        self._objects.append(obj)
        self._last_addition = discord.utils.utcnow()

    async def trigger_now(self):
        await self._trigger()

    async def _trigger(self):
        self._last_addition = None
        self._objects.sort(key=lambda obj: obj.id)
        await self.send_messages()
        self._objects.clear()

        if self._task:
            self._task.cancel()

    def _split_embeds(
        self, original_embed: discord.Embed
    ) -> typing.List[discord.Embed]:
        paginator = commands.Paginator(prefix="", suffix="", max_size=2035)

        for line in original_embed.description.splitlines():
            paginator.add_line(line)

        embeds = []

        for i, page in enumerate(paginator.pages):
            em = SafeEmbed(description=page)

            if i == 0:
                em.title = original_embed.title
                em.set_author(
                    icon_url=original_embed.author.icon_url,
                    name=original_embed.author.name,
                )

            embeds.append(em)

        return embeds

    async def send_messages(self):
        message = self.get_message()
        embed = self.get_embed()

        if len(embed) >= 5080 or len(embed.description) >= 2035:
            embeds = self._split_embeds(embed)
            first = embeds.pop(0)

            await self.channel.send(
                message,
                embed=first,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )

            for emb in embeds:
                await self.channel.send(embed=emb)

            return

        await self.channel.send(
            message, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True)
        )

    @tasks.loop(seconds=30)
    async def _wait(self):
        if (
            self._last_addition is not None
            and discord.utils.utcnow() - self._last_addition
            > datetime.timedelta(minutes=self.wait_time)
        ):
            await self._trigger()


class RedditAnnouncementScheduler(AnnouncementScheduler):
    def __init__(self, bot, channel, *, subreddit):
        self.subreddit = subreddit
        self.wait_time = 20
        super().__init__(bot, channel)

    def get_reddit_post_title(self) -> str:
        raise NotImplementedError()

    def get_reddit_post_content(self) -> str:
        raise NotImplementedError()

    async def send_messages(self):
        title = self.get_reddit_post_title()
        content = self.get_reddit_post_content()

        js = {"subreddit": self.subreddit, "title": title, "content": content}

        await super().send_messages()
        await self.bot.api_request("POST", "reddit/post", silent=True, json=js)


class CustomView(discord.ui.View):
    def __init__(self, ctx, *args, **kwargs):
        self.ctx = ctx
        self.bot = ctx.bot
        super().__init__(*args, **kwargs)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True

        return False


class PromptView(CustomView):
    def __init__(self, *args, **kwargs):
        self.result = None
        super().__init__(*args, **kwargs)

    async def prompt(self, silent=False):
        timed_out = await self.wait()

        if timed_out and not silent:
            raise exceptions.InvalidUserInputError(":zzz: You took too long to react.")

        return self.result


class SafeEmbed(discord.Embed):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.colour:
            self.colour = config.BOT_EMBED_COLOUR

    def clean(self):
        # called by monkey patched Messageable.send

        if len(self.description) > 2048:
            if self.description.endswith("```"):
                self.description = f"{self.description[:2035]}...```"
            else:
                self.description = f"{self.description[:2040]}..."

        if len(self.title) > 256:
            self.title = f"{self.title[:250]}..."

        if len(self.author.name) > 256:
            self.set_author(
                name=f"{self.author.name[:250]}...",
                url=self.author.url,
                icon_url=self.author.icon_url,
            )

    def add_field(
        self,
        *,
        name: typing.Any,
        value: typing.Any,
        inline: bool = True,
        too_long_value: str = "*Too long to display.*",
    ):
        field_index = len(self.fields)
        name = str(name)
        value = str(value)

        if len(value) > 1024:
            try:
                pages = split_string_into_multiple(value, 1004)
            except RuntimeError:
                pages = [too_long_value]

            for index, page in enumerate(pages):
                super().add_field(
                    name=name, value=page, inline=inline if index == 0 else False
                )

        else:
            super().add_field(name=name, value=value, inline=inline)

        if len(self) > 6000 or len(self.fields) > 25:
            for _ in self.fields:
                self.remove_field(field_index)

            super().add_field(name=name, value=too_long_value, inline=inline)


class DynamicSelect(discord.ui.Select):
    async def callback(self, interaction):
        index = int(self.values[0])
        self.view.result = self.view.choices[index]
        self.view.stop()


class FuzzyChoose(PromptView):
    def __init__(self, ctx, *args, **kwargs):
        self.question: str = kwargs.pop("question")
        self.choices: typing.Sequence = kwargs.pop("choices")
        self.description = kwargs.pop("description", None)
        super().__init__(ctx, *args, **kwargs, timeout=120.0)
        self._make_select()

    def _make_select(self):
        select = DynamicSelect(
            options=[
                discord.SelectOption(
                    label=textwrap.shorten(discord.utils.remove_markdown(str(x)), width=100, placeholder="..."),
                    value=str(self.choices.index(x)),
                )
                for x in self.choices
            ],
            row=0,
        )

        self.add_item(select)

    async def prompt(self, silent=True):
        if self.description:
            embed = SafeEmbed(
                title=f"{config.USER_INTERACTION_REQUIRED}   {self.question}",
                description=self.description,
            )
            msg = await self.ctx.send(embed=embed, view=self)
        else:
            msg = await self.ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} {self.question}", view=self
            )

        await self.wait()
        await msg.delete()
        return self.result


class FuzzyMultiModelChoose(FuzzyChoose):
    def __init__(self, ctx, *args, **kwargs):
        self.models: typing.Mapping[str, typing.Sequence] = kwargs.pop("models")
        super().__init__(ctx, *args, **kwargs)

    def _make_select(self):
        options = []

        for group, choices in self.models.items():
            for choice in choices:
                options.append(
                    discord.SelectOption(
                        label=textwrap.shorten(
                            discord.utils.remove_markdown(str(choice)), width=100, placeholder="..."
                        ),
                        description=textwrap.shorten(
                            discord.utils.remove_markdown(group), width=100, placeholder="..."
                        ),
                        value=str(self.choices.index(choice)),
                    )
                )

        select = DynamicSelect(options=options, row=0)

        self.add_item(select)


EditModelResult = collections.namedtuple("EditModelResult", ["confirmed", "choices"])


class MultiDynamicSelect(discord.ui.Select):
    async def callback(self, interaction):
        for value in self.values:
            self.view._result[value] = not self.view._result[value]

        self.view._confirmed = True
        self.view._make_result()
        self.view.stop()


class MultiDynamicSelectWithEdit(discord.ui.Select):
    async def callback(self, interaction):
        for value in self.values:
            self.view._result[value] = not self.view._result[value]

        await self.view.msg.edit(embed=self.view._make_embed())


class EditModelMenu(PromptView):
    def __init__(
        self,
        ctx,
        choices_with_formatted_explanation: typing.Dict[str, str],
        *,
        title=f"{config.USER_INTERACTION_REQUIRED}  What do you want to edit?",
    ):
        super().__init__(ctx)
        self.choices = choices_with_formatted_explanation
        self.title = title
        self._confirmed = False
        self._result = {choice: False for choice in self.choices.keys()}
        self._make_result()
        self._make_select()

    def _make_select(self):
        select = MultiDynamicSelect(
            max_values=len(self.choices),
            placeholder="Select as many things as you want",
            options=[
                discord.SelectOption(
                    label=textwrap.shorten(desc, width=100, placeholder="..."),
                    value=choice,
                )
                for choice, desc in self.choices.items()
            ],
            row=0,
        )

        self.add_item(select)

    def _make_result(self):
        self.result = EditModelResult(confirmed=self._confirmed, choices=self._result)
        return self.result

    async def prompt(self, silent=True):
        msg = await self.ctx.send(self.title, view=self)
        await self.wait()
        await msg.delete()
        return self.result


class EditSettingsWithEmojifiedLiveToggles(EditModelMenu):
    def __init__(self, ctx, settings, description, icon=discord.Embed.Empty, **kwargs):
        self.icon = icon
        self.description = description
        super().__init__(
            ctx,
            choices_with_formatted_explanation={k: v[0] for k, v in settings.items()},
            **kwargs,
        )
        self._result = {k: v[1] for k, v in settings.items()}

    def _make_select(self):
        select = MultiDynamicSelectWithEdit(
            max_values=len(self.choices),
            placeholder="Select as many things as you want",
            options=[
                discord.SelectOption(
                    label=textwrap.shorten(desc[1], width=100, placeholder="..."),
                    description=textwrap.shorten(desc[0], width=100, placeholder="...")
                    if desc[0]
                    else None,
                    value=choice,
                )
                for choice, desc in self.choices.items()
            ],
            row=0,
        )

        self.add_item(select)

    def _make_embed(self):
        embed = SafeEmbed()
        embed.set_author(name=self.title, icon_url=self.icon)
        fmt = [self.description]

        for choice in self.choices:
            fmt.append(
                f"{self.bot.emojify_boolean(self._result[choice])} {self.choices[choice][1]}"
            )

        fmt = "\n".join(fmt)
        embed.description = fmt
        return embed

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, row=1)
    async def confirm(self, btn, interaction):
        self._confirmed = True
        self._make_result()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=1)
    async def cancel(self, btn, interaction):
        self._make_result()
        self.stop()

    async def prompt(self, silent=True):
        self.msg = await self.ctx.send(embed=self._make_embed(), view=self)
        await self.wait()
        await self.msg.delete()
        return self.result
