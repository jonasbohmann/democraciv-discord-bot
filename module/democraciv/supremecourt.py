import typing
import discord

from util import mk, exceptions
from config import config, links
from discord.ext import commands


class SupremeCourt(commands.Cog, name="Supreme Court"):
    """Useful information about the Supreme Court of this nation."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def chief(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.CHIEF_JUSTICE_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def justice_role(self) -> typing.Optional[discord.Role]:
        return mk.get_democraciv_role(self.bot, mk.DemocracivRole.JUSTICE_ROLE)

    @property
    def judge_role(self) -> typing.Optional[discord.Role]:
        return mk.get_democraciv_role(self.bot, mk.DemocracivRole.JUDGE_ROLE)

    @commands.group(name='court', aliases=['sc', 'courts', 'j', 'judicial'], case_insensitive=True,
                    invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def court(self, ctx):
        """Dashboard for Supreme Court Justices"""

        embed = self.bot.embeds.embed_builder(title=f"Courts of {mk.NATION_NAME}", description="")

        if isinstance(self.chief, discord.Member):
            justices = [justice.mention for justice in self.justice_role.members if justice.id != self.chief.id]
            justices.insert(0, f"{self.chief.mention} (Chief Justice)")

        else:
            justices = [justice.mention for justice in self.justice_role.members]

        justices = justices or ['-']

        judges = ([justice.mention for justice in self.judge_role.members])
        judges = judges or ['-']

        embed.add_field(name="Supreme Court Justices", value='\n'.join(justices), inline=False)
        embed.add_field(name="Appeals Court Judges", value='\n'.join(judges), inline=False)
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
