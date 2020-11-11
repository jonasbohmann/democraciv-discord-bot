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


class Pages(menus.MenuPages):
    def __init__(self, source, *, title=EmptyEmbed, author="", icon=EmptyEmbed):
        super().__init__(source=source, check_embeds=True)
        self.embed = SafeEmbed(title=title)
        self.embed.set_author(name=author, icon_url=icon)

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
        for line in text.split('\n'):
            pages.add_line(line)

        super().__init__(entries=pages.pages, per_page=1)

    async def format_page(self, menu, entries):
        menu.embed.description = entries

        maximum = self.get_max_pages()
        if maximum > 1:
            footer = f'Page {menu.current_page + 1}/{maximum}'
            menu.embed.set_footer(text=footer)

        return menu.embed


class SimplePageSource(menus.ListPageSource):
    def __init__(self, entries, *, per_page=12):
        super().__init__(entries, per_page=per_page)
        self.initial_page = True

    async def format_page(self, menu, entries):
        maximum = self.get_max_pages()

        if maximum > 1:
            footer = f'Page {menu.current_page + 1}/{maximum}'
            menu.embed.set_footer(text=footer)

        menu.embed.description = '\n'.join(entries)
        return menu.embed


class SimplePages(Pages):
    def __init__(self, entries, *, per_page=12, **kwargs):
        super().__init__(SimplePageSource(entries, per_page=per_page), **kwargs)


class TextPages(Pages):
    def __init__(self, text, **kwargs):
        super().__init__(TextPageSource(text), **kwargs)
