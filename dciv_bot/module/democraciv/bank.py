import aiohttp
from discord.ext import commands

from dciv_bot.config import config


class Bank(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='bank', aliases=['b'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def bank(self, ctx):
        await ctx.send(":tools: This is still under construction.")


def setup(bot):
    bot.add_cog(Bank(bot))
