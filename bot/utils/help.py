"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.

Based on RoboDanny by Rapptz: https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt
"""

import asyncio

from bot.config import config, mk
from bot.utils import text
from bot.utils.paginator import Pages
from discord.ext import commands, menus

BOT_INTRO = f"""Hey, thanks for using me!

I'm the Democraciv Bot, and was designed specifically for the [Discord server](https://discord.gg/AK7dYMG) of the [r/Democraciv](https://reddit.com/r/democraciv) community.

**__Democraciv__**
We're playing Sid Meier's Civilization with an elected, democratic government consisting of real players.
There's a lot of role-play around the game, there's the press, political parties, banks, intrigue and drama.


**__Bot__**
My purpose is to make sure the day-to-day on our Discord runs as smooth as possible. I am deeply integrated into some processes of the Government and I keep track of a lot of information. See 
[this](https://github.com/jonasbohmann/democraciv-discord-bot/blob/master/README.md) for a complete list of all my features.

This is my help command, which will list every command and a short explanation on what it does. 
Note that I will only list the commands that _you_ are allowed to use on _this_ server.
All my commands are organized into different categories, and these categories all have their own page here.

If you're still unsure how a specific command works, try `{config.BOT_PREFIX}help <command>`. Some commands have examples on their help page.

If you want to add me to your own Discord Server, invite me [here](https://discord.com/oauth2/authorize?client_id=486971089222631455&scope=bot&permissions=8).


:point_down:
Use these buttons below to navigate between the pages."""


class BotHelpPageSource(menus.ListPageSource):
    def __init__(self, help_command, commands):
        super().__init__(entries=sorted(commands.keys(), key=lambda c: c.qualified_name), per_page=6)
        self.commands = commands
        self.help_command = help_command
        self.prefix = config.BOT_PREFIX

    def format_commands(self, cog, commands):
        # A field can only have 1024 characters so we need to paginate a bit
        # just in case it doesn't fit perfectly
        # However, we have 6 per page so I'll try cutting it off at around 800 instead
        # Since there's a 6000 character limit overall in the embed
        if cog.description:
            short_doc = cog.description.split("\n", 1)[0] + "\n"
        else:
            short_doc = "No help found.\n"

        current_count = len(short_doc)
        ending_note = "+%d not shown"
        ending_length = len(ending_note)

        page = []
        for command in commands:
            value = f"`{self.prefix}{command.qualified_name}`"
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
            return short_doc + "  ".join(page)

        hidden = len(commands) - len(page)
        return short_doc + "  ".join(page) + "\n" + (ending_note % hidden)

    async def format_page(self, menu, cogs):
        prefix = config.BOT_PREFIX
        description = f"Use `{prefix}help thing` for more info on a category or command.\nOptionally, [this guide]" \
                      f"(https://drive.google.com/file/d/1fUWBeRPszLolRtX47OyhAMALudjqWaXc/view?usp=sharing) " \
                      f"explains some additional topics of the bot."

        embed = text.SafeEmbed(title="All Categories | Help", description=description)

        for cog in cogs:
            if cog.hidden:
                continue

            commands = self.commands.get(cog)
            if commands:
                # value = self.format_commands(cog, commands)

                if cog.description:
                    short_doc = cog.description.split("\n", 1)[0] + "\n"
                else:
                    short_doc = "No help found.\n"

                value = f"{short_doc}`{config.BOT_PREFIX}help {cog.qualified_name}`"
                embed.add_field(name=cog.qualified_name, value=value, inline=True)

        maximum = self.get_max_pages()
        embed.set_footer(text=f"Page {menu.current_page + 1}/{maximum}")
        return embed


class GroupHelpPageSource(menus.ListPageSource):
    def __init__(self, group, commands, *, prefix):
        super().__init__(entries=commands, per_page=6)
        self.group = group
        self.prefix = prefix
        self.title = f"{self.group.qualified_name} | Help"
        self.description = self.group.description

    async def format_page(self, menu, commands):
        embed = text.SafeEmbed(title=self.title, description=self.description)
        fmt_commands = []

        for command in commands:
            hlp = command.short_doc or "No help given."
            fmt_commands.append(f"__**{config.BOT_PREFIX}{command.qualified_name} {command.signature}**__\n{hlp}\n")

        if fmt_commands:
            embed.add_field(name="Subcommands",
                            value='\n'.join(fmt_commands),
                            inline=False)

        maximum = self.get_max_pages()

        if maximum > 1:
            embed.set_footer(text=f"Page {menu.current_page + 1}/{maximum} ({len(self.entries)} commands)")

        return embed


class CogHelpPageSource(menus.ListPageSource):
    def __init__(self, group, commands, *, prefix):
        super().__init__(entries=commands, per_page=6)
        self.group = group
        self.prefix = prefix
        self.title = f"{self.group.qualified_name} | Help"
        self.description = f"{self.group.description}\n\n*Commands in italic " \
                           f"cannot be used by you in the current context due to any " \
                           f"of these reasons: wrong server, missing role(s), or missing permission(s).*"

    async def format_page(self, menu, commands):
        embed = text.SafeEmbed(title=self.title, description=self.description)

        for command in commands:
            try:
                is_allowed = await command.can_run(menu.ctx)
            except Exception:
                is_allowed = False

            if is_allowed:
                signature = f"__{config.BOT_PREFIX}{command.qualified_name} {command.signature}__"
            else:
                default_sig = f"__*{config.BOT_PREFIX}{command.qualified_name} {command.signature}"

                if default_sig.endswith(" "):
                    default_sig = default_sig[:-1]

                signature = f"{default_sig}*__"

            embed.add_field(name=signature, value=command.short_doc or 'No help given.', inline=False)

        maximum = self.get_max_pages()
        if maximum > 1:
            embed.set_footer(text=f"Page {menu.current_page + 1}/{maximum} ({len(self.entries)} commands)")

        return embed


class HelpMenu(Pages, inherit_buttons=False):
    def __init__(self, source, *, send_intro=True):
        super().__init__(source)
        self.send_intro = send_intro

    async def send_initial_message(self, ctx, channel):
        if not self.send_intro:
            return await super().send_initial_message(ctx, channel)

        embed = text.SafeEmbed(title="Welcome to the Democraciv Bot")
        embed.description = BOT_INTRO
        embed.set_author(name=f"Made by {ctx.bot.owner}", icon_url=ctx.bot.owner.avatar_url_as(static_format="png"))
        self.current_page = -1
        return await channel.send(embed=embed)

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

    @menus.button(config.HELP_BOT_HELP, position=menus.Last(5))
    async def show_bot_help(self, payload):
        """shows how to use the bot"""

        embed = text.SafeEmbed(title="Using the Democraciv Bot",
                               description="Optionally, [this guide]"
                                           f"(https://drive.google.com/file/d/1fUWBeRPszLolRtX47OyhAMALudjqWaXc/view?usp=sharing) "
                                           f"explains some additional topics of the bot.")

        entries = (
            ("<argument>", "This means the argument is __**required**__."),
            ("[argument]", "This means the argument is __**optional**__."),
            ("[A|B]", "This means that it can be __**either A or B**__."),
            (
                "[argument...]",
                "This means you can have multiple arguments.\n\n__**You do not type in the brackets!**__",
            ),
        )

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        if self.current_page == -1:
            self.current_page = 0

        embed.set_footer(text=f"We were on page {self.current_page + 1} before this message.")
        await self.message.edit(embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_page(self.current_page)

        self.bot.loop.create_task(go_back_to_current_page())


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs={
                "cooldown": commands.Cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user),
                "help": "Shows help about the bot, a command, or a category",
                "aliases": ["man", 'manual', 'h'],
            },
            verify_checks=False
        )

    def command_not_found(self, string):
        return f"{config.NO} `{string}` is neither a command, nor a category."

    def subcommand_not_found(self, command, string):
        return f"{config.NO} `{string}` is not a subcommand of the `{config.BOT_PREFIX}{command.qualified_name}` command."

    def get_command_signature(self, command):
        parent = command.full_parent_name
        alias = command.name if not parent else f"{parent} {command.name}"
        return f"{config.BOT_PREFIX}{alias} {command.signature}"

    async def send_bot_help(self, mapping):
        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True, key=lambda c: c.qualified_name)

        all_commands = {}
        for command in entries:
            if command.cog is None:
                continue
            try:
                all_commands[command.cog].append(command)
            except KeyError:
                all_commands[command.cog] = [command]

        menu = HelpMenu(BotHelpPageSource(self, all_commands), send_intro=False)
        await menu.start(self.context)

    async def send_cog_help(self, cog):
        entries = await self.filter_commands(cog.walk_commands(), sort=True, key=lambda c: c.qualified_name)
        menu = HelpMenu(
            CogHelpPageSource(cog, entries, prefix=config.BOT_PREFIX),
            send_intro=False,
        )
        await menu.start(self.context)

    async def common_command_formatting(self, embed_like, command):
        embed_like.title = self.get_command_signature(command)
        if command.description:
            embed_like.description = f"{command.description}\n\n{command.help}"
        else:
            embed_like.description = command.help or "No help found."

        try:
            is_allowed = await command.can_run(self.context)
        except Exception:
            is_allowed = False

        if not is_allowed:
            embed_like.description = f"{embed_like.description}\n\n:warning: *You are not allowed to use " \
                                     f"this command in this context due to any of these reasons: wrong server, " \
                                     f"missing role(s), or missing permission(s).*"

    async def send_command_help(self, command):
        embed = text.SafeEmbed()
        await self.common_command_formatting(embed, command)

        parent_name = f"{command.full_parent_name} " if command.full_parent_name else ''
        aliases = [f"`{config.BOT_PREFIX}{parent_name}{a}`" for a in command.aliases]

        if aliases:
            embed.add_field(name="Aliases", value=', '.join(aliases))

        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        # The end user doesn't know the difference between a Group and a Command. To avoid confusion, just show them
        # the whole cog
        if group in (self.context.bot.get_command(f"{mk.MarkConfig.LEGISLATURE_COMMAND} withdraw"),
                     self.context.bot.get_command("random")):
            return await self._send_group_help(group)

        await self.send_cog_help(group.cog)

    async def _send_group_help(self, group):
        subcommands = list(group.walk_commands())
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        if len(entries) == 0:
            return await self.send_command_help(group)

        source = GroupHelpPageSource(group, entries, prefix=config.BOT_PREFIX)
        await self.common_command_formatting(source, group)
        menu = HelpMenu(source, send_intro=False)
        await menu.start(self.context)
