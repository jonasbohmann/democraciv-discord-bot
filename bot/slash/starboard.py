import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import starboard as starboard_presenter
from bot.services.starboard import StarboardService
from bot.slash import context as slash_context


class StarboardSlash(commands.Cog):
    starboard = app_commands.Group(
        name="starboard",
        description="Show Starboard statistics.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = StarboardService(bot)

    @starboard.command(
        name="overview", description="Show general Starboard statistics."
    )
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="starboard overview",
        )
        await ctx.defer()

        stats = await self.service.get_overview()
        embed = starboard_presenter.build_overview_embed(stats)
        await ctx.send(embed=embed)

    @starboard.command(
        name="person", description="Show Starboard stats for one person."
    )
    async def member(self, interaction: discord.Interaction, person: discord.Member):
        ctx = slash_context.from_interaction(
            interaction, command_name="starboard person"
        )
        await ctx.defer()
        stats = await self.service.get_member_stats(person)
        embed = starboard_presenter.build_member_embed(stats)
        await ctx.send(embed=embed)


async def setup(bot):
    if config.STARBOARD_ENABLED:
        await bot.add_cog(StarboardSlash(bot))
