import asyncio
import traceback
import util.utils as utils
import util.exceptions as exceptions

from util import mk
from discord.ext import commands


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_error(self, ctx, error, to_log_channel: bool = True, to_owner: bool = False,
                        to_context: bool = False):
        if ctx.guild is None:
            return

        log_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        embed = self.bot.embeds.embed_builder(title=':x:  Command Error', description="", time_stamp=True)

        embed.add_field(name='Error', value=f"{error.__class__.__name__}: {error}", inline=False)
        embed.add_field(name='Channel', value=ctx.channel.mention, inline=True)
        embed.add_field(name='Context', value=f"[Jump]({ctx.message.jump_url})", inline=True)
        embed.add_field(name='Caused by', value=ctx.message.clean_content, inline=False)

        if to_log_channel:
            if await self.bot.checks.is_logging_enabled(ctx.guild.id):
                if log_channel is not None:
                    await log_channel.send(embed=embed)

        if to_context:
            local_embed = self.bot.embeds.embed_builder(title=":warning:  Unexpected Error occurred",
                                                        description=f"An unexpected error occurred while"
                                                                    f" performing this command. The developer"
                                                                    f" has been notified."
                                                                    f"\n\n```{error.__class__.__name__}:"
                                                                    f" {error}```", has_footer=False)
            await ctx.send(embed=local_embed)

        if to_owner:
            embed.add_field(name='Guild', value=ctx.guild.name, inline=False)

            pretty_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__))

            if len(pretty_traceback) <= 1024:
                embed.add_field(name='Traceback', value=f'```py\n{pretty_traceback}```')
                await self.bot.owner.send(embed=embed)
            else:
                await self.bot.owner.send(embed=embed)
                if len(pretty_traceback) <= 2000:
                    await self.bot.owner.send(f'```py\n{pretty_traceback}```')

    @staticmethod
    def format_permissions(missing_perms: list) -> str:
        """
        The MIT License (MIT)

        Copyright (c) 2015-2019 Rapptz

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
        missing = [perm.replace('_', ' ').replace('guild', 'server').title() for perm in missing_perms]

        if len(missing) > 2:
            fmt = '{}, and {}'.format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = ' and '.join(missing)

        return fmt

    @staticmethod
    def format_roles(missing_roles: list) -> str:
        """
        The MIT License (MIT)

        Copyright (c) 2015-2019 Rapptz

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
        if isinstance(missing_roles[0], mk.DemocracivRole):
            missing = ["'{}'".format(role.printable_name) for role in missing_roles]
        else:
            missing = ["'{}'".format(role) for role in missing_roles]

        if len(missing) > 2:
            fmt = '{}, or {}'.format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = ' or '.join(missing)

        return fmt

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        ignored = commands.CommandNotFound

        error = getattr(error, 'original', error)

        # This prevents any commands with local handlers being handled here
        if hasattr(ctx.command, 'on_error'):
            return

        # Anything in ignored will return
        if isinstance(error, ignored):
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f":x: You forgot to give me the `{error.param.name}` argument!")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.TooManyArguments):
            await ctx.send(f":x: You gave me too many arguments!")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.BadArgument):
            await ctx.send(f":x: There was an error with one of the arguments you provided,"
                           f" take a look at the help page:")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.BadUnionArgument):
            await ctx.send(f":x: There was an error with the `{error.param.name}` argument you provided,"
                           f" take a look at the help page:")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f":x: You are on cooldown! Try again in {error.retry_after:.2f} seconds.")

        elif isinstance(error, commands.MissingPermissions):
            return await ctx.send(f":x: You need '{self.format_permissions(error.missing_perms)}' permission(s) to use"
                                  f" this command.")

        elif isinstance(error, commands.MissingRole):
            return await ctx.send(f":x: You need the '{error.missing_role}' role in order to use this command.")

        elif isinstance(error, commands.MissingAnyRole):
            return await ctx.send(f":x: You need at least one of these roles in order to use this command: "
                                  f"{self.format_roles(error.missing_roles)}")

        elif isinstance(error, commands.BotMissingPermissions):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(f":x: I don't have '{self.format_permissions(error.missing_perms)}' permission(s)"
                                  f" to perform this action for you.")

        elif isinstance(error, commands.BotMissingRole):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(f":x: I need the '{error.missing_role}' role in order to perform this"
                                  f" action for you.")

        elif isinstance(error, commands.BotMissingAnyRole):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(f":x: I need at least one of these roles in order to perform this action for you: "
                                  f"{self.format_roles(error.missing_roles)}")

        elif isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(":x: This command cannot be used in DMs!")

        elif isinstance(error, commands.PrivateMessageOnly):
            return await ctx.send(":x: This command can only be used in DMs!")

        elif isinstance(error, exceptions.PartyNotFoundError):
            await ctx.send(f":x: There is no political party named `{error.party}`.")

            parties = await self.bot.db.fetch("SELECT id FROM parties")
            parties = [record['id'] for record in parties]

            msg = ['**Try one of these:**']
            for party in parties:
                role = self.bot.democraciv_guild_object.get_role(party)
                if role is not None:
                    msg.append(role.name)

            if len(msg) > 1:
                await ctx.send('\n'.join(msg))
            return

        # This includes all exceptions declared in util.exceptions.py
        elif isinstance(error, exceptions.DemocracivBotException):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(error.message)

        elif isinstance(error, exceptions.TagCheckError):
            return await ctx.send(error.message)

        else:
            await self.log_error(ctx, error, to_log_channel=False, to_owner=True, to_context=True)

        print(f"[BOT] ERROR - Ignoring exception in command '{ctx.command}':")
        await asyncio.sleep(0.5)  # For some reason the traceback is printed before that ^ so we sleep for a bit
        traceback.print_exception(type(error), error, error.__traceback__)


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
