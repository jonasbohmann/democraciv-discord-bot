import discord

from discord.ext import commands

from util import mk, exceptions
from config import config, links


class SupremeCourt(commands.Cog, name="Supreme Court"):
    """Useful information for Supreme Court Justices"""

    def __init__(self, bot):
        self.bot = bot
        self.chief_justice = None

    def refresh_court_discord_objects(self):
        try:
            self.chief_justice = mk.get_democraciv_role(self.bot, mk.DemocracivRole.CHIEF_JUSTICE_ROLE).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Chief Justice")

    @commands.group(name='court', aliases=['sc', 'courts'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def court(self, ctx):
        """Dashboard for Supreme Court Justices"""
        
        try:
            self.refresh_court_discord_objects()
        except exceptions.DemocracivBotException as e:
            if isinstance(e, exceptions.RoleNotFoundError):
                await ctx.send(e.message)
            
        embed = self.bot.embeds.embed_builder(title=f"Courts of {mk.NATION_NAME}", description="")

        chief_justice_value = f""

        if isinstance(self.chief_justice, discord.Member):
            chief_justice_value += f"{self.chief_justice.mention}"

        else:
            chief_justice_value += f"-"

        embed.add_field(name="Chief Justice", value=chief_justice_value)

        embed.add_field(name="Supreme Court Justices", value='\n'.join([justice.mention for justice in
                                                                        mk.get_democraciv_role(self.bot,
                                                                                               mk.DemocracivRole.JUSTICE_ROLE).members]),
                        inline=True)

        embed.add_field(name="Appeals Court Judges", value='\n'.join([justice.mention for justice in
                                                                        mk.get_democraciv_role(self.bot,
                                                                                               mk.DemocracivRole.JUDGE_ROLE).members]),
                        inline=False)

        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Submit a new Case]({links.sue})\n"
                                            f"[Court Cases]({links.sccases})\n"
                                            f"[Court Worksheet]({links.scworksheet})\n"
                                            f"[Court Policies]({links.scpolicy})", inline=True)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
