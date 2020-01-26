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

        justices = [justice.mention for justice in mk.get_democraciv_role(self.bot, mk.DemocracivRole.JUSTICE_ROLE).members
                    if justice.id != self.chief_justice.id]

        if isinstance(self.chief_justice, discord.Member):
            justices.insert(0, f"{self.chief_justice.mention} (Chief Justice)")

        embed.add_field(name="Supreme Court Justices", value='\n'.join(justices), inline=False)

        embed.add_field(name="Appeals Court Judges", value='\n'.join([justice.mention for justice in
                                                                      mk.get_democraciv_role(self.bot,
                                                                                               mk.DemocracivRole.JUDGE_ROLE).members]),
                        inline=False)

        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Submit a new Case]({links.sue})\n"
                                            f"[Court Cases]({links.sccases})\n"
                                            f"[Court Worksheet]({links.scworksheet})\n"
                                            f"[Court Log on Trello]({links.sctrello})\n"
                                            f"[Court Policies]({links.scpolicy})", inline=False)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
