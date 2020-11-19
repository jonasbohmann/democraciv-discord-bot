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

import asyncio

import discord

from bot.config import config
from bot.utils import text
from bot.utils.paginator import Pages
from discord.ext import commands, menus

BOT_INTRO = f"""Hey, thanks for using me!

I'm the Democraciv Bot, and was designed specifically for the 
[Discord server](https://discord.gg/AK7dYMG) of the [r/Democraciv](https://reddit.com/r/democraciv) community.

**__Democraciv__**
We're playing Sid Meier's Civilization with an elected, democratic government consisting of real players.
There's a lot of role-play around the game, there's the press, political  
parties, banks, intrigue and drama.


**__Bot__**
My purpose is to make sure the
day-to-day on our Discord runs as smooth as possible. I am deeply integrated into
some processes of the Government and I keep track of a lot of information. See 
[this](https://github.com/jonasbohmann/democraciv-discord-bot/blob/master/README.md)
for a complete list of all my features.

This is my help command,
which will list every command and a short explanation on what it does. Note
that I will only list the commands that _you_ are allowed to use on _this_ server.
All my commands are organized into different categories, and these categories all
have their own page here.

If you're still unsure how a specific 
command works, try `{config.BOT_PREFIX}help <command>`. Some commands have examples
on their help page.

If you want to add me to your own Discord Server, invite me [here](https://discord.com/oauth2/authorize?client_id=486971089222631455&scope=bot&permissions=8).



:point_down:
Use these buttons below to navigate between the pages."""


class BotHelpPageSource(menus.ListPageSource):
    def __init__(self, help_command, commands):
        super().__init__(entries=sorted(commands.keys(), key=lambda c: c.qualified_name), per_page=6)
        self.commands = commands
        self.help_command = help_command
        self.prefix = help_command.clean_prefix

    def format_commands(self, cog, commands):
        # A field can only have 1024 characters so we need to paginate a bit
        # just in case it doesn't fit perfectly
        # However, we have 6 per page so I'll try cutting it off at around 800 instead
        # Since there's a 6000 character limit overall in the embed
        if cog.description:
            short_doc = cog.description.split('\n', 1)[0] + '\n'
        else:
            short_doc = 'No help found...\n'

        current_count = len(short_doc)
        ending_note = '+%d not shown'
        ending_length = len(ending_note)

        page = []
        for command in commands:
            value = f'`{self.prefix}{command.qualified_name}`'
            count = len(value) + 2  # The space
            if count + current_count < 800:
                current_count += count
                page.append(value)
            else:
                # If we're maxed out then see if we can add the ending note
                if current_count + ending_length + 1 > 800:
                    # If we are, pop out the last element to make room
                    page.pop()

                # Done paginating so just exit
                break

        if len(page) == len(commands):
            # We're not hiding anything so just return it as-is
            return short_doc + '  '.join(page)

        hidden = len(commands) - len(page)
        return short_doc + '  '.join(page) + '\n' + (ending_note % hidden)

    async def format_page(self, menu, cogs):
        prefix = menu.ctx.prefix
        description = f'Use `{prefix}help thing` for more info on a category or command.\n'

        embed = text.SafeEmbed(title='All Categories | Help', description=description)

        for cog in cogs:
            commands = self.commands.get(cog)
            if commands:
                value = self.format_commands(cog, commands)
                embed.add_field(name=cog.qualified_name, value=value, inline=True)

        maximum = self.get_max_pages()
        embed.set_footer(text=f'Page {menu.current_page + 1}/{maximum}')
        return embed


class GroupHelpPageSource(menus.ListPageSource):
    def __init__(self, group, commands, *, prefix):
        super().__init__(entries=commands, per_page=6)
        self.group = group
        self.prefix = prefix
        self.title = f'{self.group.qualified_name} | Help'
        self.description = self.group.description

    async def format_page(self, menu, commands):
        embed = text.SafeEmbed(title=self.title, description=self.description)

        for command in commands:
            signature = f'{command.qualified_name} {command.signature}'
            embed.add_field(name=signature, value=command.short_doc or 'No help given...', inline=False)

        maximum = self.get_max_pages()
        if maximum > 1:
            embed.set_footer(text=f'Page {menu.current_page + 1}/{maximum} ({len(self.entries)} commands)')

        return embed


class HelpMenu(Pages):
    def __init__(self, source, *, send_intro=True):
        super().__init__(source)
        self.send_intro = send_intro

    async def send_initial_message(self, ctx, channel):
        if not self.send_intro:
            return await super().send_initial_message(ctx, channel)

        embed = text.SafeEmbed(title="Welcome to the Democraciv Bot")
        embed.description = BOT_INTRO
        self.current_page = -1
        return await channel.send(embed=embed)

    @menus.button('\N{WHITE QUESTION MARK ORNAMENT}', position=menus.Last(5))
    async def show_bot_help(self, payload):
        """shows how to use the bot"""

        embed = text.SafeEmbed(title='Using the Democraciv Bot')

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            ('[A|B]', 'This means that it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n\n__**You do not type in the brackets!**__')
        )

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        if self.current_page == -1:
            self.current_page = 0

        embed.set_footer(text=f'We were on page {self.current_page + 1} before this message.')
        await self.message.edit(embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_page(self.current_page)

        self.bot.loop.create_task(go_back_to_current_page())


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'cooldown': commands.Cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user),
            'help': 'Shows help about the bot, a command, or a category',
            'aliases': ['man']
        })

    def get_command_signature(self, command):
        parent = command.full_parent_name
        alias = command.name if not parent else f'{parent} {command.name}'
        return f'{self.clean_prefix}{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True)

        all_commands = {}
        for command in entries:
            if command.cog is None:
                continue
            try:
                all_commands[command.cog].append(command)
            except KeyError:
                all_commands[command.cog] = [command]

        menu = HelpMenu(BotHelpPageSource(self, all_commands))
        await menu.start(self.context)

    async def send_cog_help(self, cog):
        entries = await self.filter_commands(cog.walk_commands(), sort=True)
        menu = HelpMenu(GroupHelpPageSource(cog, entries, prefix=self.clean_prefix), send_intro=False)
        await menu.start(self.context)

    def common_command_formatting(self, embed_like, command):
        embed_like.title = self.get_command_signature(command)
        if command.description:
            embed_like.description = f'{command.description}\n\n{command.help}'
        else:
            embed_like.description = command.help or 'No help found...'

    async def send_command_help(self, command):
        embed = text.SafeEmbed()
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        """subcommands = list(group.walk_commands())
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        if len(entries) == 0:
            return await self.send_command_help(group)

        source = GroupHelpPageSource(group, entries, prefix=self.clean_prefix)
        self.common_command_formatting(source, group)
        menu = HelpMenu(source)
        await menu.start(self.context)"""

        return await self.send_cog_help(group.cog)