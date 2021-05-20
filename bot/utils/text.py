import collections
import copy
import datetime
import typing
import discord

from discord.ext import tasks, menus
from bot.config import config, mk


def split_string(string: str, length: int):
    return list((string[0 + i: length + i] for i in range(0, len(string), length)))


# todo fix this shit


def split_string_by_paragraphs(string: str, length: int):
    lines = string.splitlines(keepends=True)
    split_into_length = {}
    index = 0

    for paragraph in lines:
        if len(paragraph) > length:
            paragraph = split_string(paragraph, length)
        try:
            split_into_length[index]
        except KeyError:
            split_into_length[index] = ""

        split_into_length[index] = split_into_length[index] + "".join(paragraph)

        if (len("".join(split_into_length[index]))) > length:
            index += 1

    return split_into_length


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
        self._last_addition = datetime.datetime.utcnow()

    async def trigger_now(self):
        await self._trigger()

    async def _trigger(self):
        self._last_addition = None
        self._objects.sort(key=lambda obj: obj.id)
        await self.send_messages()
        self._task.cancel()
        self._objects.clear()

    async def send_messages(self):
        message = self.get_message()
        embed = self.get_embed()
        await self.channel.send(message, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))

    @tasks.loop(seconds=30)
    async def _wait(self):
        if self._last_addition is not None and datetime.datetime.utcnow() - self._last_addition > datetime.timedelta(
                minutes=self.wait_time
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

        js = {"subreddit": self.subreddit,
              "title": title,
              "content": content}

        await self.bot.api_request("POST", "reddit/post", silent=True, json=js)
        await super().send_messages()


class SafeEmbed(discord.Embed):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.colour:
            self.colour = config.BOT_EMBED_COLOUR

    def clean(self):
        # called by monkey patched Messageable.send

        if len(self.description) > 2048:
            if self.description.endswith("```"):
                self.description = f"{self.description[:2037]}...```"
            else:
                self.description = f"{self.description[:2040]}..."

        if len(self.title) > 256:
            self.title = f"{self.title[:250]}..."

        if len(self.author.name) > 256:
            self.set_author(name=f"{self.author.name[:250]}...", url=self.author.url, icon_url=self.author.icon_url)

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
            fields = split_string_by_paragraphs(value, 924)

            for index in fields:
                if index == 0:
                    super().add_field(name=name, value=fields[index], inline=inline)
                else:
                    super().add_field(name=name, value=fields[index], inline=False)
        else:
            super().add_field(name=name, value=value, inline=inline)

        if len(self) > 6000 or len(self.fields) > 25:
            for _ in self.fields:
                self.remove_field(field_index)

            super().add_field(name=name, value=too_long_value, inline=inline)


class FuzzyChoose(menus.Menu):
    def __init__(self, question: str, choices: typing.Sequence, *, description=None, **kwargs):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.question = question
        self.choices = choices
        self.result = None
        self._mapping = {}
        self._reverse_mapping = {}
        self.description = description

        for i, choice in enumerate(choices, start=1):
            emoji = f"{i}\N{variation selector-16}\N{combining enclosing keycap}"
            button = menus.Button(emoji=emoji, action=self.on_button)
            self.add_button(button=button)
            self._mapping[emoji] = choice
            self._reverse_mapping[choice] = emoji

        cancel = menus.Button(emoji=config.NO, action=self.cancel)
        self.add_button(button=cancel)

    def get_embed(self) -> discord.Embed:
        embed = SafeEmbed(title=f"{config.USER_INTERACTION_REQUIRED}  {self.question}")

        fmt = []

        if self.description:
            fmt.insert(0, self.description)

        for emoji, choice in self._mapping.items():
            fmt.append(f"{emoji}  {choice}")

        fmt = "\n".join(fmt)
        embed.description = fmt
        return embed

    async def send_initial_message(self, ctx, channel):
        return await ctx.send(embed=self.get_embed())

    async def on_button(self, payload):
        self.result = self._mapping[str(payload.emoji)]
        self.stop()

    async def cancel(self, payload):
        self.result = None
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class FuzzyMultiModelChoose(FuzzyChoose):

    def __init__(self, models: typing.Mapping[str, typing.Sequence], *args, **kwargs):
        self.models = models
        super().__init__(*args, **kwargs)

    def get_embed(self) -> discord.Embed:
        embed = SafeEmbed(title=f"{config.USER_INTERACTION_REQUIRED}  {self.question}")

        fmt = []
        if self.description:
            fmt.insert(0, self.description)

        for group, choices in self.models.items():
            fmt.append(f"__**{group}**__")

            for choice in choices:
                fmt.append(f"{self._reverse_mapping[choice]}  {choice}")

            fmt.append(" ")

        fmt = "\n".join(fmt)
        embed.description = fmt
        return embed


EditModelResult = collections.namedtuple("EditModelResult", ["confirmed", "choices"])


class EditModelMenu(menus.Menu):
    def __init__(self, choices_with_formatted_explanation: typing.Dict[str, str], *,
                 title=f"{config.USER_INTERACTION_REQUIRED}  What do you want to edit?"):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.choices = choices_with_formatted_explanation
        self.title = title
        self._confirmed = False
        self._result = {choice: False for choice in self.choices.keys()}
        self._mapping = {}
        self._make_result()

        for i, choice in enumerate(self.choices.keys(), start=1):
            emoji = f"{i}\N{variation selector-16}\N{combining enclosing keycap}"
            button = menus.Button(emoji=emoji, action=self.on_button)
            self.add_button(button=button)
            self._mapping[emoji] = choice

        confirm = menus.Button(emoji=config.YES, action=self.confirm)
        self.add_button(confirm)

        cancel = menus.Button(emoji=config.NO, action=self.cancel)
        self.add_button(cancel)

    def _make_result(self):
        self.result = EditModelResult(confirmed=self._confirmed, choices=self._result)
        return self.result

    async def send_initial_message(self, ctx, channel):
        embed = SafeEmbed(title=self.title)

        fmt = [f"Select as many things as you want, then click the {config.YES} button to continue, "
               f"or {config.NO} to cancel.\n"]

        for emoji, choice in self._mapping.items():
            fmt.append(f"{emoji}  {self.choices[choice]}")

        fmt = "\n".join(fmt)
        embed.description = fmt
        return await ctx.send(embed=embed)

    async def on_button(self, payload):
        choice = self._mapping[str(payload.emoji)]
        self._result[choice] = not self._result[choice]

    async def confirm(self, payload):
        self._confirmed = True
        self._make_result()
        self.stop()

    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class EditSettingsWithEmojifiedLiveToggles(EditModelMenu):
    def __init__(self, settings, description, icon=discord.Embed.Empty, **kwargs):
        self.icon = icon
        self.description = description
        super().__init__(choices_with_formatted_explanation={k: v[0] for k, v in settings.items()}, **kwargs)
        self._result = {k: v[1] for k, v in settings.items()}

    def _make_embed(self):
        embed = SafeEmbed()
        embed.set_author(name=self.title, icon_url=self.icon)
        fmt = [self.description]

        for emoji, choice in self._mapping.items():
            fmt.append(f"{emoji}  -  {self.bot.emojify_boolean(self._result[choice])} {self.choices[choice]}")

        fmt = "\n".join(fmt)
        embed.description = fmt
        return embed

    async def send_initial_message(self, ctx, channel):
        return await ctx.send(embed=self._make_embed())

    async def on_button(self, payload):
        choice = self._mapping[str(payload.emoji)]
        self._result[choice] = not self._result[choice]
        await self.message.edit(embed=self._make_embed())
