import asyncio
import discord

from discord.ext import commands


class Flow:

    def __init__(self, bot, ctx):
        self.bot = bot
        self.ctx = ctx

    async def gear_reaction_confirm(self, message, timeout):
        await message.add_reaction("\U00002699")

        try:
            await self.ctx.bot.wait_for('reaction_add',
                                        check=self.bot.checks.
                                        wait_for_gear_reaction_check(self.ctx, message),
                                        timeout=timeout)

        except asyncio.TimeoutError:
            return False

        else:
            return True

    async def yes_no_reaction_confirm(self, message, timeout):
        await message.add_reaction("\U00002705")
        await message.add_reaction("\U0000274c")

        try:
            reaction, user = await self.ctx.bot.wait_for('reaction_add',
                                                         check=self.bot.checks.wait_for_reaction_check(self.ctx,
                                                                                                       message),
                                                         timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":x: Aborted.")
            return None

        else:
            return reaction, user

    async def get_new_channel(self, timeout):
        try:
            channel = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(self.ctx),
                                              timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":x: Aborted.")
            return

        if not channel.content:
            await self.ctx.send(":x: Aborted.")
            return

        try:
            channel_object = await commands.TextChannelConverter().convert(self.ctx, channel.content)
        except commands.BadArgument:
            return channel.content

        if not channel_object:
            return channel.content

        return channel_object

    async def get_text_input(self, timeout):
        try:
            text = await self.bot.wait_for('message',
                                           check=self.bot.checks.wait_for_message_check(self.ctx),
                                           timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":x: Aborted.")
            return

        if not text.content:
            await self.ctx.send(":x: Aborted.")
            return

        else:
            return text.content

    async def get_new_role(self, timeout):
        try:
            role = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(self.ctx),
                                           timeout=timeout)
        except asyncio.TimeoutError:
            await self.ctx.send(":x: Aborted.")
            return

        if not role.content:
            await self.ctx.send(":x: Aborted.")
            return

        try:
            role_object = await commands.RoleConverter().convert(self.ctx, role.content)
        except commands.BadArgument:
            role_object = role.content

        if not role_object:
            return role.content

        return role_object
