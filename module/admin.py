import config
import discord
import importlib
import traceback

from discord.ext import commands
from util.checks import isDemocracivGuild


# -- admin.py | module.admin --
#
# Commands that manage the bot. Requires administrator permissions.
#


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='load', hidden=True)
    @commands.has_permissions(administrator=True)
    async def load(self, ctx, *, module):
        """Loads a module."""
        if not isDemocracivGuild(self.bot, ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Loaded ' + module)

    @commands.command(name='unload', hidden=True)
    @commands.has_permissions(administrator=True)
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        if not self.isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Unloaded ' + module)

    @commands.command(name='reload', hidden=True)
    @commands.has_permissions(administrator=True)
    async def reload(self, ctx, *, module):
        """Reloads a module."""
        if not self.isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Reloaded ' + module)

    @commands.command(name='stop', hidden=True)
    @commands.has_permissions(administrator=True)
    async def stop(self, ctx):
        if not self.isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        await ctx.send(':wave: Goodbye! Shutting down...')
        await self.bot.close()
        await self.bot.logout()

    @commands.command(name='reloadconfig', aliases=['rlc', 'rc', 'rlcfg'], hidden=True)
    @commands.has_permissions(administrator=True)
    async def reloadConfig(self, ctx):
        if not self.isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        await ctx.send(':white_check_mark: Reloaded config')
        await importlib.reload(config)

    @commands.has_permissions(manage_messages=True)
    @commands.command(name="clear", hidden=True)
    async def clear(self, ctx, num: int, target: discord.Member = None):
        if num > 500 or num < 0:
            return await ctx.send(":x: Invalid amount. Maximum is 500.")

        def msgcheck(amsg):
            if target:
                return amsg.author.id == target.id
            return True

        deleted = await ctx.channel.purge(limit=num, check=msgcheck)
        await ctx.send(f':white_check_mark: Deleted **{len(deleted)}/{num}** messages.', delete_after=10)


def setup(bot):
    bot.add_cog(Admin(bot))
