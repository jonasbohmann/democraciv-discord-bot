import discord

from util import mk, exceptions, utils
from discord.ext import commands
from config import config, links
from util.flow import Flow
from util.paginator import Pages


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
            " WHERE has_passed_leg = true AND voted_on_by_ministry = false AND has_passed_ministry = false")

        if open_bills is not None:
            return open_bills

    async def get_pretty_vetos(self):
        open_bills = await self.get_open_vetos()

        pretty_bills = []

        if len(open_bills) > 0:
            for record in open_bills:
                pretty_bills.append(f"Bill #{record[0][0]} - [{record[0][2]}]({record[0][1]}) by "
                                    f"{self.bot.get_user(record[0][3]).mention}"
                                    f" from Leg. Session #{record[0][4]}")

        if len(pretty_bills) == 0:
            pretty_bills = ["There are no new bills to vote on."]

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
            await ctx.send(e.message)

        embed = self.bot.embeds.embed_builder(title=f"The Ministry of {mk.NATION_NAME}",
                                              description=f"")
        minister_value = f""

        pretty_bills = await self.get_pretty_vetos()

        if len(pretty_bills) == 1 and pretty_bills[0] == "There are no new bills to vote on.":
            pretty_bills = pretty_bills[0]

        elif len(pretty_bills) >= 1 and pretty_bills[0] != "There are no new bills to vote on.":
            pretty_bills = f"You can vote on new bills, check `{self.bot.commands_prefix}ministry bills`."

        if isinstance(self.prime_minister, discord.Member):
            minister_value += f"Prime Minister: {self.prime_minister.mention}\n"

        else:
            minister_value += f"Prime Minister: -\n"

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value += f"Lt. Prime Minister: {self.lt_prime_minister.mention}"
        else:
            minister_value += f"Lt. Prime Minister: -"

        embed.add_field(name="Head of State", value=minister_value)

        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Ministry Worksheet]({links.executiveworksheet})\n"
                                            f"[Ministry Procedures]({links.execprocedures})", inline=True)

        embed.add_field(name="Open Bills", value=f"{pretty_bills}", inline=False)

        await ctx.send(embed=embed)

    @ministry.group(name='bills', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def bills(self, ctx):
        """See all open bills to veto"""

        pretty_bills = await self.get_pretty_vetos()

        help_description = f"Use {self.bot.commands_prefix}ministry veto <law_id> to veto a bill, or " \
                           f"{self.bot.commands_prefix}ministry pass <law_id> to pass a bill into law."

        pages = Pages(ctx=ctx, entries=pretty_bills, show_entry_count=False, title="Open Bills to Veto"
                      , show_index=False, footer_text=help_description)

        await pages.paginate()

    @ministry.group(name='veto', aliases=['v'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Prime Minister", "Lieutenant Prime Minister")
    @utils.is_democraciv_guild()
    async def veto(self, ctx, bill_id: int):
        """Veto a bill"""

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

        if bill_details is None:
            return await ctx.send(f":x: Could not find any bill with ID #{bill_id}")

        if not bill_details['is_vetoable']:
            return await ctx.send(f":x: The Ministry cannot veto this!")

        if not bill_details['has_passed_leg']:
            return await ctx.send(f":x: This bill hasn't passed the Legislature yet!")

        if bill_details['voted_on_by_ministry'] or bill_details['has_passed_ministry']:
            return await ctx.send(f":x: You already voted on this bill!")

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to veto "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{bill_details['id']})?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if not reaction or reaction is None:
            return

        if str(reaction.emoji) == "\U00002705":
            # yes

            async with ctx.typing():
                await self.bot.db.execute(
                    "UPDATE legislature_bills SET voted_on_by_ministry = true, has_passed_ministry = "
                    "false WHERE id = $1", bill_id)

                await ctx.send(f":white_check_mark: Successfully vetoed {bill_details['bill_name']} "
                               f"(#{bill_details['id']})!")

                await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_speaker_role(self.bot).mention},"
                                                                      f" {bill_details['bill_name']} was vetoed "
                                                                      f"by the Ministry.")

        else:
            await ctx.send(f"Aborted.")

    @veto.error
    async def vetoerr(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the Prime Minister and Lt. Prime Minister are allowed to use this command!")

        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'bill_id':
                await ctx.send(':x: You have to give me the ID of the bill you want to veto!\n\n**Usage**:\n'
                               '`-ministry veto <bill_id>`')

    @ministry.group(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_any_role("Prime Minister", "Lieutenant Prime Minister")
    @utils.is_democraciv_guild()
    async def passbill(self, ctx, bill_id: int):
        """Pass a bill into law"""

        bill_details = await self.bot.db.fetchrow("SELECT * FROM legislature_bills WHERE id = $1", bill_id)

        if bill_details is None:
            return await ctx.send(f":x: Could not find any bill with ID #{bill_id}")

        if not bill_details['is_vetoable']:
            return await ctx.send(f":x: The Ministry cannot vote on this!")

        if not bill_details['has_passed_leg']:
            return await ctx.send(f":x: This bill hasn't passed the Legislature yet!")

        if bill_details['voted_on_by_ministry'] or bill_details['has_passed_ministry']:
            return await ctx.send(f":x: You already voted on this bill!")

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to pass "
                                      f"'{bill_details['bill_name']}"
                                      f"' (#{bill_details['id']}) into law?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if not reaction or reaction is None:
            return

        if str(reaction.emoji) == "\U00002705":
            # yes

            async with ctx.typing():
                if await self.bot.laws.pass_into_law(ctx, bill_id, bill_details):
                    await ctx.send(":white_check_mark: Successfully passed this bill into law!")
                    await mk.get_gov_announcements_channel(self.bot).send(f"{mk.get_speaker_role(self.bot).mention}, "
                                                                          f"'{bill_details['bill_name']}' was passed "
                                                                          f"into law by"
                                                                          f" the Ministry.")
                else:
                    await ctx.send(":x: Unexpected error occured.")
        else:
            await ctx.send(f"Aborted.")

    @passbill.error
    async def passbillerr(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only the Prime Minister and Lt. Prime Minister are allowed to use this command!")

        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'bill_id':
                await ctx.send(':x: You have to give me the ID of the bill you want to pass!\n\n**Usage**:\n'
                               '`-ministry pass <bill_id>`')


def setup(bot):
    bot.add_cog(Ministry(bot))
