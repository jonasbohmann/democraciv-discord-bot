import discord
from discord import app_commands
from discord.ext import commands

from bot.slash import context as slash_context
from bot.utils import mixin


class GovernmentSlash(commands.Cog, mixin.GovernmentMixin):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="government", description="Show the current government.")
    @app_commands.guild_only()  # todo
    async def government_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="government")
        embed = await self._build_government_overview_embed()
        await ctx.send(embed=embed)

    @app_commands.command(
        name="court", description="Show current court members and links."
    )
    @app_commands.guild_only()  # todo
    async def court(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="court")
        embed = await self._build_court_overview_embed()
        await ctx.send(embed=embed)

    @app_commands.command(
        name="legislature",
        description="Show the current Commons and Senate session status.",
    )
    @app_commands.guild_only()
    async def legislature_overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="legislature")
        embeds = await self._build_legislature_info_embeds(slash=True)
        await ctx.send(embed=embeds[0])


async def setup(bot):
    await bot.add_cog(GovernmentSlash(bot))
