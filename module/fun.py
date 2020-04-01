import discord
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

    @commands.command(name='excommunicate')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.COUNCIL_OF_SAGES, mk.DemocracivRole.SUPREME_LEADER,
                                   mk.DemocracivRole.WES_ROLE, mk.DemocracivRole.QI_ROLE)
    async def excommunicate(self, ctx, *, person: discord.Member):
        """Heretic!"""
        believer = ctx.guild.get_role(694958914030141441)
        role = ctx.guild.get_role(694972373824307341)
        channel = ctx.guild.get_channel(694974887424426115)
        await ctx.send(f"\U0001f329 {person.display_name} is a heretic, get him!")
        await person.add_roles(role)
        await person.remove_roles(believer)
        await channel.send(f"{person.display_name} has been banished to the dungeon.")


def setup(bot):
    bot.add_cog(ANewDawn(bot))
