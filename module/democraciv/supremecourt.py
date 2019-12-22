import discord
from discord.ext import commands

from config import config
from util import mk, exceptions


class SupremeCourt(commands.Cog, name="Supreme Court"):

    def __init__(self, bot):
        self.bot = bot
        self.chief_justice = None

    def refresh_court_discord_objects(self):
        try:
            self.chief_justice = mk.get_chief_justice_role(self.bot).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Chief Justice")

    @commands.group(name='court', aliases=['sc'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def court(self, ctx, links=None):
        """Dashboard for Supreme Court Justices"""
        
        try:
            self.refresh_court_discord_objects()
        except exceptions.DemocracivBotException as e:
            await ctx.send(e.message)
            
        embed = self.bot.embeds.embed_builder(title=f"Supreme Court of {mk.NATION_NAME}", description="")

        chief_justice_value = f""

        if isinstance(self.chief_justice, discord.Member):
            chief_justice_value += f"Chief Justice: {self.chief_justice.mention}\n"

        else:
            chief_justice_value += f"Chief Justice: -\n"

        embed.add_field(name="Chief Justice", value=chief_justice_value)

        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Court Cases]({links.sccases})\n"
                                            f"[Court Worksheet]({links.scworksheet})", inline=True)


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
