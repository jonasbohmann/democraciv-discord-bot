from discord.ext import commands

from config import config
from util import utils, mk


class ANewDawn(commands.Cog, name="A New Dawn"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='smite')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.COUNCIL_OF_SAGES, mk.DemocracivRole.SUPREME_LEADER,
                                   mk.DemocracivRole.WES_ROLE, mk.DemocracivRole.QI_ROLE)
    async def smite(self, ctx):
        """Unleash the power of the One on High"""
        messages = await ctx.channel.history(limit=5).flatten()
        messages.pop(0)

        for message in messages:
            await message.add_reaction("\U0001f329")


def setup(bot):
    bot.add_cog(ANewDawn(bot))
