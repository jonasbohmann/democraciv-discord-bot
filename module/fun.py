import config
import discord

from discord.ext import commands


# -- fun.py | module.fun --
#
# Fun commands.
#


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='say')
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, *, content: str):
        """Basically just Mod Abuse."""
        await ctx.message.delete()
        await ctx.send(content)


def setup(bot):
    bot.add_cog(Fun(bot))
