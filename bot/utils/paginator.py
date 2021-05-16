"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.

Based on RoboDanny by Rapptz: https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt
"""
import typing
import discord

from discord.embeds import EmptyEmbed
from discord.ext import menus
from discord.ext.commands import Paginator as CommandPaginator

from bot.utils.text import SafeEmbed
from bot.config import config


class Pages(menus.MenuPages):
    def __init__(
            self,
            source: menus.PageSource,
            *,
            title=EmptyEmbed,
            author="",
            icon=EmptyEmbed,
            title_url=EmptyEmbed,
            colour=config.BOT_EMBED_COLOUR,
            thumbnail=None,
            message=None
    ):
        super().__init__(source=source, check_embeds=True, message=message)
        self.embed = SafeEmbed(title=title, url=title_url, colour=colour)
        self.embed.set_author(name=author, icon_url=icon)

        if thumbnail:
            self.embed.set_thumbnail(url=thumbnail)

    async def finalize(self, timed_out):
        try:
            if timed_out:
                await self.message.clear_reactions()
            else:
                await self.message.delete()
        except discord.HTTPException:
            pass


class SimplePageSource(menus.ListPageSource):
    def __init__(self, entries: typing.List[str], *, per_page=None):
        self.initial_page = True

        if per_page is None:
            pages = CommandPaginator(prefix="", suffix="", max_size=1800)
            for line in entries:
                pages.add_line(line)

            super().__init__(pages.pages, per_page=1)

        else:
            super().__init__(entries, per_page=per_page)

    async def format_page(self, menu: Pages, entries: typing.Union[typing.List[str], str]):
        if isinstance(entries, list):
            menu.embed.description = "\n".join(entries)
        elif isinstance(entries, str):
            menu.embed.description = entries

        maximum = self.get_max_pages()

        if maximum > 1:
            footer = f"Page {menu.current_page + 1}/{maximum}"
            menu.embed.set_footer(text=footer)

        return menu.embed


class SimplePages(Pages, inherit_buttons=False):
    def __init__(self, entries: typing.List[str], *, per_page=None, empty_message: str = "*No entries.*", **kwargs):
        if len(entries) == 0:
            entries.append(empty_message)
        super().__init__(SimplePageSource(entries, per_page=per_page), **kwargs)

    @menus.button(config.HELP_FIRST, position=menus.First(0), skip_if=menus.MenuPages._skip_double_triangle_buttons)
    async def go_to_first_page(self, payload):
        await self.show_page(0)

    @menus.button(config.HELP_PREVIOUS, position=menus.First(1))
    async def go_to_previous_page(self, payload):
        await self.show_checked_page(self.current_page - 1)

    @menus.button(config.HELP_NEXT, position=menus.Last(0))
    async def go_to_next_page(self, payload):
        await self.show_checked_page(self.current_page + 1)

    @menus.button(config.HELP_LAST, position=menus.Last(1), skip_if=menus.MenuPages._skip_double_triangle_buttons)
    async def go_to_last_page(self, payload):
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)
