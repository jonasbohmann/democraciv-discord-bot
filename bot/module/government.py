from discord.ext import commands

from bot.utils import mixin, context


class Government(context.CustomCog, mixin.GovernmentMixin, name="Government"):
    """The current Government of {NATION_FULL_NAME}"""

    @commands.command(
        name="legislature",
        aliases=["leg", "l"],
    )
    async def legislature(self, ctx: commands.Context):
        """MK13-specific information about the Commons and the Senate. See `-help commons` and `-help senate` for actual commands."""
        embeds = await self._build_legislature_info_embeds()
        for embed in embeds:
            await ctx.send(embed=embed)

    @commands.group(
        name="government",
        aliases=["gov", "g"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def government(self, ctx):
        """See all current members of Government"""
        embed = self._build_government_overview_embed()
        await ctx.send(embed=embed)

    @commands.group(
        name="court",
        aliases=["sc", "courts", "j", "judicial"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def court(self, ctx):
        """Dashboard for {justice_term}s"""
        embed = self._build_court_overview_embed()
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Government(bot))
