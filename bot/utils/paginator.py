"""
The MIT License (MIT)

Copyright (c) 2015 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import discord
from discord.embeds import EmptyEmbed

from discord.ext import menus
from discord.ext.commands import Paginator as CommandPaginator
from bot.utils.text import SafeEmbed
from config import config


class Pages(menus.MenuPages):
    def __init__(
            self,
            source,
            *,
            title=EmptyEmbed,
            author="",
            icon=EmptyEmbed,
            title_url=EmptyEmbed,
            colour=config.BOT_EMBED_COLOUR,
            thumbnail=None,
    ):
        super().__init__(source=source, check_embeds=True)
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


class TextPageSource(menus.ListPageSource):
    def __init__(self, text, *, max_size=2000):
        pages = CommandPaginator(prefix="", suffix="", max_size=max_size - 200)
        for line in text.split("\n"):
            pages.add_line(line)

        super().__init__(entries=pages.pages, per_page=1)

    async def format_page(self, menu, entries):
        menu.embed.description = entries

        maximum = self.get_max_pages()
        if maximum > 1:
            footer = f"Page {menu.current_page + 1}/{maximum}"
            menu.embed.set_footer(text=footer)

        return menu.embed


class SimplePageSource(menus.ListPageSource):
    def __init__(self, entries, *, per_page=12):
        super().__init__(entries, per_page=per_page)
        self.initial_page = True

    async def format_page(self, menu, entries):
        maximum = self.get_max_pages()

        if maximum > 1:
            footer = f"Page {menu.current_page + 1}/{maximum}"
            menu.embed.set_footer(text=footer)

        menu.embed.description = "\n".join(entries)
        return menu.embed


class SimplePages(Pages, inherit_buttons=False):
    def __init__(self, entries, *, per_page=12, empty_message="*No entries.*", **kwargs):
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


class TextPages(Pages, inherit_buttons=False):
    def __init__(self, text, **kwargs):
        super().__init__(TextPageSource(text), **kwargs)

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
