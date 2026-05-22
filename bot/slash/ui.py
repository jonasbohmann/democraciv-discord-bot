import textwrap
import typing

import discord

from bot.config import config


def _clean(value: str) -> str:
    return discord.utils.remove_markdown(str(value)).strip()


def shorten(value: str, *, width: int = 100) -> str:
    return textwrap.shorten(_clean(value), width=width, placeholder="...")


def split_entries(
    entries: typing.Iterable[str],
    *,
    max_size: int = 3600,
    per_page: int = None,
    empty_message: str = "*No entries.*",
) -> typing.List[str]:
    entries = [str(entry) for entry in entries]

    if not entries:
        return [empty_message]

    pages = []
    current = []
    current_size = 0

    for entry in entries:
        entry_size = len(entry) + 1

        if current and (
            current_size + entry_size > max_size
            or (per_page is not None and len(current) >= per_page)
        ):
            pages.append("\n".join(current))
            current = []
            current_size = 0

        if entry_size > max_size:
            for start in range(0, len(entry), max_size):
                pages.append(entry[start : start + max_size])
            continue

        current.append(entry)
        current_size += entry_size

    if current:
        pages.append("\n".join(current))

    return pages or [empty_message]


class LayoutLink(typing.NamedTuple):
    label: str
    url: str
    emoji: typing.Optional[str] = None


class LayoutSection(typing.NamedTuple):
    title: str
    body: str
    separator_before: bool = False


def default_title_emoji(bot) -> typing.Optional[str]:
    return getattr(getattr(bot, "mk", None), "NATION_EMOJI", None) or None


def _link_row(
    links: typing.Sequence[LayoutLink],
) -> typing.Optional[discord.ui.ActionRow]:
    buttons = [
        discord.ui.Button(
            label=shorten(link.label, width=80),
            url=link.url,
            emoji=link.emoji,
            style=discord.ButtonStyle.link,
        )
        for link in links
        if link.url
    ]

    if not buttons:
        return None

    return discord.ui.ActionRow(*buttons[:5])


def _add_header(
    container: discord.ui.Container,
    *,
    title: str,
    subtitle: str = None,
    title_emoji: str = None,
):
    if title_emoji:
        title = f"{title_emoji} {title}"

    content = f"## {title}"

    if subtitle:
        content = f"{content}\n{subtitle}"

    container.add_item(discord.ui.TextDisplay(content))


def _add_sections(
    container: discord.ui.Container,
    sections: typing.Sequence[LayoutSection],
):
    blocks = []

    def flush():
        nonlocal blocks

        if blocks:
            container.add_item(discord.ui.TextDisplay("\n\n".join(blocks)[:4000]))
            blocks = []

    for section in sections:
        if section.separator_before:
            flush()
            container.add_item(
                discord.ui.Separator(
                    visible=True,
                    spacing=discord.SeparatorSpacing.small,
                )
            )

        block = f"### {section.title}\n{section.body}"
        if len("\n\n".join(blocks + [block])) > 3800:
            flush()

        blocks.append(block[:4000])

    flush()


def _add_media(
    container: discord.ui.Container,
    media_urls: typing.Sequence[str] = (),
):
    items = [discord.MediaGalleryItem(url) for url in media_urls if url]

    if items:
        container.add_item(discord.ui.MediaGallery(*items[:10]))


class _PageButton(discord.ui.Button):
    def __init__(self, target: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.target = target

    async def callback(self, interaction: discord.Interaction):
        view = typing.cast("SlashPaginator", self.view)
        await view.change_page(interaction, self.target)


class SlashPaginator(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        pages: typing.Sequence[str],
        author_id: int,
        title: str,
        subtitle: str = None,
        title_emoji: str = None,
        links: typing.Sequence[LayoutLink] = (),
        accent_colour: typing.Optional[int] = None,
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.pages = list(pages) or ["*No entries.*"]
        self.author_id = author_id
        self.title = title
        self.subtitle = subtitle
        self.title_emoji = title_emoji
        self.links = links
        self.index = 0
        self.container = discord.ui.Container(
            accent_colour=accent_colour or config.BOT_EMBED_COLOUR
        )
        self.add_item(self.container)

        self.first_button = None
        self.previous_button = None
        self.next_button = None
        self.last_button = None

        if len(self.pages) > 1:
            self.first_button = _PageButton("first", "First")
            self.previous_button = _PageButton("previous", "Previous")
            self.next_button = _PageButton("next", "Next")
            self.last_button = _PageButton("last", "Last")

            row = discord.ui.ActionRow(
                self.first_button,
                self.previous_button,
                self.next_button,
                self.last_button,
            )
            self.add_item(row)

        link_row = _link_row(links)
        if link_row:
            self.add_item(link_row)

        self._render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            f"{config.NO} This menu is not for you.", ephemeral=True
        )
        return False

    async def change_page(self, interaction: discord.Interaction, target: str):
        if target == "first":
            self.index = 0
        elif target == "previous":
            self.index = max(0, self.index - 1)
        elif target == "next":
            self.index = min(len(self.pages) - 1, self.index + 1)
        elif target == "last":
            self.index = len(self.pages) - 1

        self._render()
        await interaction.response.edit_message(view=self)

    def _render(self):
        self.container.clear_items()

        body = self.pages[self.index]
        footer = f"-# Page {self.index + 1}/{len(self.pages)}"
        _add_header(
            self.container,
            title=self.title,
            subtitle=self.subtitle,
            title_emoji=self.title_emoji,
        )
        self.container.add_item(discord.ui.TextDisplay(body[:4000]))

        if len(self.pages) > 1:
            self.container.add_item(discord.ui.TextDisplay(footer))

        if self.first_button is not None:
            self.first_button.disabled = self.index == 0
            self.previous_button.disabled = self.index == 0
            self.next_button.disabled = self.index >= len(self.pages) - 1
            self.last_button.disabled = self.index >= len(self.pages) - 1


class RichLayout(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        title: str,
        body: str = None,
        sections: typing.Sequence[LayoutSection] = (),
        title_emoji: str = None,
        media_urls: typing.Sequence[str] = (),
        links: typing.Sequence[LayoutLink] = (),
        action_items: typing.Sequence[discord.ui.Item] = (),
        author_id: int = None,
        accent_colour: typing.Optional[int] = None,
    ):
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.container = discord.ui.Container(
            accent_colour=accent_colour or config.BOT_EMBED_COLOUR
        )
        self.add_item(self.container)
        _add_header(self.container, title=title, title_emoji=title_emoji)

        if body:
            self.container.add_item(discord.ui.TextDisplay(body[:4000]))

        if sections:
            _add_sections(self.container, sections)

        _add_media(self.container, media_urls)

        link_row = _link_row(links)
        if link_row:
            self.add_item(link_row)

        if action_items:
            self.add_item(discord.ui.ActionRow(*action_items[:5]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None or interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            f"{config.NO} This menu is not for you.", ephemeral=True
        )
        return False


async def send_pages(
    ctx,
    *,
    entries: typing.Iterable[str],
    title: str,
    subtitle: str = None,
    title_emoji: str = None,
    links: typing.Sequence[LayoutLink] = (),
    per_page: int = None,
    empty_message: str = "*No entries.*",
    ephemeral: bool = None,
):
    pages = split_entries(entries, per_page=per_page, empty_message=empty_message)
    view = SlashPaginator(
        pages=pages,
        author_id=ctx.author.id,
        title=title,
        subtitle=subtitle,
        title_emoji=(
            title_emoji if title_emoji is not None else default_title_emoji(ctx.bot)
        ),
        links=links,
    )
    return await ctx.send(view=view, ephemeral=ephemeral)


async def send_static(
    ctx,
    *,
    title: str,
    body: str = None,
    sections: typing.Sequence[LayoutSection] = (),
    title_emoji: str = None,
    media_urls: typing.Sequence[str] = (),
    links: typing.Sequence[LayoutLink] = (),
    action_items: typing.Sequence[discord.ui.Item] = (),
    ephemeral: bool = None,
):
    return await ctx.send(
        view=RichLayout(
            title=title,
            body=body,
            sections=sections,
            title_emoji=(
                title_emoji if title_emoji is not None else default_title_emoji(ctx.bot)
            ),
            media_urls=media_urls,
            links=links,
            action_items=action_items,
            author_id=ctx.author.id,
        ),
        ephemeral=ephemeral,
    )


class ConfirmView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        author_id: int,
        title: str,
        body: str,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        title_emoji: str = None,
    ):
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.result = None
        self.container = discord.ui.Container(accent_colour=config.BOT_EMBED_COLOUR)
        self.add_item(self.container)
        _add_header(self.container, title=title, title_emoji=title_emoji)
        self.container.add_item(discord.ui.TextDisplay(body[:4000]))
        self.add_item(
            discord.ui.ActionRow(
                ConfirmButton(confirm_label),
                CancelButton(cancel_label),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            f"{config.NO} This confirmation is not for you.", ephemeral=True
        )
        return False


class ConfirmButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        view = typing.cast(ConfirmView, self.view)
        view.result = True
        await interaction.response.defer()
        view.stop()


class CancelButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        view = typing.cast(ConfirmView, self.view)
        view.result = False
        await interaction.response.defer()
        view.stop()


async def confirm(
    ctx,
    *,
    title: str,
    body: str,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
):
    view = ConfirmView(
        author_id=ctx.author.id,
        title=title,
        body=body,
        confirm_label=confirm_label,
        cancel_label=cancel_label,
        title_emoji=default_title_emoji(ctx.bot),
    )
    message = await ctx.send(view=view, ephemeral=True)
    await view.wait()

    try:
        await message.delete()
    except discord.HTTPException:
        pass

    return bool(view.result)
