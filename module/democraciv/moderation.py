import discord

from util import utils
from config import config, token

from discord.ext import commands


class Moderation(commands.Cog):
    """Commands for the Mod Team"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='hub', aliases=['modhub', 'moderationhub', 'mhub'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def hub(self, ctx):
        """Link to the Moderation Hub"""
        link = token.MOD_HUB or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Moderation Hub", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='registry')
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def registry(self, ctx):
        """Link to the Democraciv Registry"""
        link = token.REGISTRY or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Democraciv Registry", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='drive', aliases=['googledrive', 'gdrive'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def gdrive(self, ctx):
        """Link to the Google Drive for MK6"""
        link = token.MK6_DRIVE or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Google Drive for MK6", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='elections', aliases=['election', 'pins', 'electiontool', 'pintool'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def electiontool(self, ctx):
        """Link to DerJona's Election Tool"""
        link = token.PIN_TOOL or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="DerJonas' Election Tool", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)


def setup(bot):
    bot.add_cog(Moderation(bot))
