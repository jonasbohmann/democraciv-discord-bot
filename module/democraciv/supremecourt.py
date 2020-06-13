import typing
import discord

from bot import DemocracivBot
from util import mk, exceptions
from config import config
from discord.ext import commands


class SupremeCourt(commands.Cog, name="Supreme Court"):
    """Useful information about the Supreme Court of this nation."""

    def __init__(self, bot):
        self.bot: DemocracivBot = bot

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

    def get_justices(self):
        try:
            _justices = self.justice_role
        except exceptions.RoleNotFoundError:
            return None

        if isinstance(self.chief, discord.Member):
            justices = [justice.mention for justice in _justices.members if justice.id != self.chief.id]
            justices.insert(0, f"{self.chief.mention} ({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})")
            return justices
        else:
            return [justice.mention for justice in _justices.members]

    def get_judges(self):
        try:
            _judges = self.judge_role
        except exceptions.RoleNotFoundError:
            return None

        return [judge.mention for judge in _judges.members]

    @commands.group(name='court', aliases=['sc', 'courts', 'j', 'judicial'], case_insensitive=True,
                    invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def court(self, ctx):
        """Dashboard for Supreme Court Justices"""

        embed = self.bot.embeds.embed_builder(title=f"{self.bot.mk.NATION_EMOJI}  "
                                                    f"{self.bot.mk.courts_term} of the {self.bot.mk.NATION_FULL_NAME}")

        justices = self.get_justices() or ['-']
        judges = self.get_judges() or ['-']

        embed.add_field(name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s",
                        value='\n'.join(justices), inline=False)

        if self.bot.mk.COURT_HAS_INFERIOR_COURT:
            embed.add_field(name=f"{self.bot.mk.COURT_INFERIOR_NAME} {self.bot.mk.COURT_JUDGE_NAME}s",
                            value='\n'.join(judges), inline=False)

        embed.add_field(name="Links", value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
                                            f"[Legal Code]({self.bot.mk.LEGAL_CODE})",
                        inline=False)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
