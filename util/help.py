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
import itertools
import discord
from discord.embeds import EmptyEmbed

from config import config
from util.paginator import Pages
from util import mk
from discord.ext import commands


class HelpPaginator(Pages):
    def __init__(self, help_command, ctx, entries, *, per_page=4):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.reaction_emojis.append((config.HELP_BOT_HELP, self.show_bot_help))
        self.total = len(entries)
        self.help_command = help_command
        self.prefix = help_command.clean_prefix
        self.is_bot = False

    def show_introduction(self):
        p = config.BOT_PREFIX
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))

        introduction_message = f"Hey, thanks for using me!\n\nI'm the Democraciv Bot," \
                               f" and was designed specifically " \
                               f"for the [Discord server](https://discord.gg/AK7dYMG) of" \
                               f" the [r/Democraciv](https://reddit.com/r/democraciv)" \
                               f" community.\n\n**__Democraciv__**\nWe're playing {mk.CIV_GAME}" \
                               f" with an elected, democratic government consisting of real players." \
                               f" There's a lot of role-play around the game, there's the press, political " \
                               f"parties, banks, intrigue and drama.\n\n\n**__Bot__**\nMy purpose is to make sure the" \
                               f" day-to-day on our Discord runs as smooth as possible. I am deeply integrated into" \
                               f" some processes of the Government and I keep track of a lot of information. See " \
                               f"[this](https://github.com/jonasbohmann/democraciv-discord-bot/blob/master/README.md)" \
                               f" for a complete list of all my features. \n\nThis is my help command," \
                               f" which will list every command and a short explanation on what it does. Note" \
                               f" that I will only list the commands that _you_ are allowed to use on _this_ server." \
                               f" All my commands are organized into different categories, and these categories all" \
                               f" have their own page here.\n\nIf you're still unsure how a specific" \
                               f" command works, try `{p}help <command>`. Some commands have examples " \
                               f"on their help page.\n\nIf you want to add me to your own Discord Server," \
                               f" invite me [here]({invite_url}).\n\n\n:point_down:" \
                               f" Use these buttons below to navigate between the pages."
        self.title = "Welcome to the Democraciv Bot"
        self.description = introduction_message
        return []

    def get_bot_page(self, page):
        if self.is_bot and page == 0:
            return self.show_introduction()

        cog, description, commands = self.entries[page - 1]
        self.title = f"{cog} | Help"
        self.description = description
        return commands

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = self.description
        self.embed.title = self.title

        if page == 0 and self.is_bot:
            self.embed.set_author(icon_url=self.bot.owner.avatar_url_as(static_format="png"), name=self.bot.owner)
        elif page != 0:
            self.embed.set_author(name="", icon_url=EmptyEmbed)

        for entry in entries:
            if entry.signature:
                signature = f'**__{config.BOT_PREFIX}{entry.qualified_name} {entry.signature}__**'
            else:
                signature = f'**__{config.BOT_PREFIX}{entry.qualified_name}__**'

            self.embed.add_field(name=signature, value=entry.short_doc or "No help given", inline=False)

        if self.maximum_pages and page != 0:
            self.embed.set_footer(text=f'Page {page}/{self.maximum_pages} ({self.total} commands)')

    async def show_help(self):
        """shows this message"""

        self.embed.title = 'Paginator help'
        self.embed.description = 'Hello! Welcome to the help page.'

        messages = [f'{emoji} {func.__doc__}' for emoji, func in self.reaction_emojis]
        self.embed.clear_fields()
        self.embed.add_field(name='What are these reactions for?', value='\n'.join(messages), inline=False)
        self.embed.set_footer(text=f'We were on page {self.current_page} before this message.',
                              icon_url=config.BOT_ICON_URL)
        await self.message.edit(embed=self.embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())

    async def show_bot_help(self):
        """shows how to use the bot"""

        self.embed.title = 'Using the Democraciv Bot'
        self.embed.description = 'Hello! Welcome to the help page.'
        self.embed.clear_fields()

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            # ('[A|B]', 'This means that it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n\n'
                              '__**You do not type in the brackets!**__')
        )

        self.embed.add_field(name='How do I use this bot?', value='Reading the bot signature is pretty simple.')

        for name, value in entries:
            self.embed.add_field(name=name, value=value, inline=False)

        if self.is_bot and self.current_page == 0:
            self.current_page = 1

        self.embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(embed=self.embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())

    async def paginate(self):
        """Actually paginate the entries and run the interactive loop if necessary."""
        page = 0 if self.is_bot else 1
        first_page = self.show_page(page, first=True)

        if not self.paginating:
            await first_page
        else:
            # allow us to react to reactions right away if we're paginating
            self.bot.loop.create_task(first_page)

        while self.paginating:
            try:
                payload = await self.bot.wait_for('raw_reaction_add', check=self.react_check, timeout=120.0)
            except asyncio.TimeoutError:
                self.paginating = False
                try:
                    await self.message.clear_reactions()
                except:
                    pass
                finally:
                    break

            try:
                await self.message.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
            except:
                pass  # can't remove it so don't bother doing so

            await self.match()


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'cooldown': commands.Cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.member),
            'help': 'Shows help about the bot, a command, or a category',
            'hidden': False
        })

    @staticmethod
    def get_subcommands_too(commands_list: list):
        # ugly workaround since discord.py returns aliases in walk_commands()
        cmds = dict().fromkeys(commands_list)

        for cmd in commands_list:
            if isinstance(cmd, discord.ext.commands.Group):
                for c in cmd.commands:
                    if isinstance(c, discord.ext.commands.Group):
                        for co in c.commands:
                            cmds[co] = None
                    if c.qualified_name != "legislature withdraw":  # hacky :(
                        cmds[c] = None

        return list(cmds)

    def get_command_signature(self, command):
        parent = command.full_parent_name

        # if len(command.aliases) > 0:
        #    # aliases = '|'.join(command.aliases)
        #    # fmt = f'[{command.name}|{aliases}]'
        #    if parent:
        #        fmt = f'{parent} {fmt}'
        #    alias = fmt

        alias = command.name if not parent else f'{parent} {command.name}'

        return f'{config.BOT_PREFIX}{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bNo Category'

        bot = self.context.bot

        all_commands = self.get_subcommands_too(list(bot.commands))

        entries = await self.filter_commands(all_commands, sort=True, key=key)

        nested_pages = []
        per_page = 9
        total = 0

        for cog, commands in itertools.groupby(entries, key=key):
            commands = sorted(commands, key=lambda c: c.qualified_name)
            if len(commands) == 0:
                continue

            total += len(commands)
            actual_cog = bot.get_cog(cog)
            # get the description if it exists (and the cog is valid) or return Empty embed.
            description = (actual_cog and actual_cog.description) or discord.Embed.Empty
            nested_pages.extend((cog, description, commands[i:i + per_page]) for i in range(0, len(commands), per_page))

        # a value of 1 forces the pagination session
        pages = HelpPaginator(self, self.context, nested_pages, per_page=1)

        # swap the get_page implementation to work with our nested pages.
        pages.get_page = pages.get_bot_page
        pages.is_bot = True
        pages.total = total
        await pages.paginate()

    async def send_cog_help(self, cog):
        def key(c):
            return c.qualified_name

        all_commands = self.get_subcommands_too(cog.get_commands())

        entries = await self.filter_commands(all_commands, sort=True, key=key)
        pages = HelpPaginator(self, self.context, entries)
        pages.title = f"{cog.qualified_name} | Help"
        pages.description = cog.description

        await pages.paginate()

    def common_command_formatting(self, page_or_embed, command):
        page_or_embed.title = self.get_command_signature(command)

        if command.description:
            page_or_embed.description = f'{command.description}\n\n{command.help}'
        else:
            page_or_embed.description = command.help or 'No help found...'

    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=config.BOT_EMBED_COLOUR)
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        # The end user doesn't know the difference between a Group and a Command. To avoid confusion, just show them
        # the whole cog
        if group == self.context.bot.get_command("legislature withdraw"):
            return await self._send_group_help(group)

        await self.send_cog_help(group.cog)

    async def _send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        pages = HelpPaginator(self, self.context, entries)
        self.common_command_formatting(pages, group)
        await pages.paginate()
