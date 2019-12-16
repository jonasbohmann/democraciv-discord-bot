import discord

from util import mk, exceptions, utils
from discord.ext import commands
from config import config, links


class Ministry(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.prime_minister = None
        self.lt_prime_minister = None

    def refresh_minister_discord_objects(self):
        try:
            self.prime_minister = mk.get_prime_minister_role(self.bot).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Prime Minister")

        try:
            self.lt_prime_minister = mk.get_lt_prime_minister_role(self.bot).members[0]
        except IndexError:
            raise exceptions.NoOneHasRoleError("Lieutenant Prime Minister")

    async def get_open_vetos(self):
        open_bills = await self.bot.db.fetch(
            "SELECT (id, link, bill_name, submitter, leg_session) FROM legislature_bills"
            " WHERE has_passed_leg = true AND has_passed_ministry = false AND is_law = false")

        if open_bills is not None:
            return open_bills

    async def get_pretty_vetos(self):
        open_bills = await self.get_open_vetos()

        pretty_bills = f""

        if len(open_bills) > 0:
            for record in open_bills:
                pretty_bills += f"Bill #{record[0][0]} - [{record[0][2]}]({record[0][1]}) by " \
                                f"{self.bot.get_user(record[0][3]).mention}" \
                                f" from Legislative Session #{record[0][4]}\n"

        if pretty_bills == "":
            pretty_bills = "There are no new bills to veto."

        return pretty_bills

    @commands.group(name='ministry', aliases=['m'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ministry(self, ctx):
        """Dashboard for Ministers"""

        try:
            self.refresh_minister_discord_objects()
        except exceptions.DemocracivBotException as e:
            # We're raising the same exception again because discord.ext.commands.Exceptions only "work" (i.e. get sent
            # to events/error_handler.py) if they get raised in an actual command
            raise e

        embed = self.bot.embeds.embed_builder(title=f"The Ministry of {mk.NATION_NAME}",
                                              description=f"")
        minister_value = f""

        pretty_bills = await self.get_pretty_vetos()

        if isinstance(self.prime_minister, discord.Member):
            minister_value += f"Prime Minister: {self.prime_minister.mention}\n"

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value += f"Lt. Prime Minister: {self.lt_prime_minister.mention}"

        embed.add_field(name="Head of State", value=minister_value)

        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Ministry Worksheet]({links.executiveworksheet})\n"
                                            f"[Ministry Procedures]({links.execprocedures})", inline=True)

        embed.add_field(name="Open Vetos", value=f"{pretty_bills}", inline=False)

        await ctx.send(embed=embed)

    @ministry.group(name='veto', aliases=['v'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Prime Minister", "Lieutenant Prime Minister")
    @utils.is_democraciv_guild()
    async def veto(self, ctx, law: int = None):
        """Veto a bill"""

        if not law or law is None:
            pretty_bills = await self.get_pretty_vetos()

            pretty_bills = f"Use `{config.BOT_PREFIX}ministry veto <law_id>` to veto a bill.\n\n{pretty_bills}"

            embed = self.bot.embeds.embed_builder(title=f"Open Bills to Veto",
                                                  description=pretty_bills)

            await ctx.send(embed=embed)

        elif law:
            pass


def setup(bot):
    bot.add_cog(Ministry(bot))
