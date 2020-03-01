import typing
import discord


from util.flow import Flow
from util.converter import Bill
from config import config, links
from util.paginator import Pages
from discord.ext import commands
from util.law_helper import MockContext
from util import mk, exceptions, utils


class Ministry(commands.Cog):
    """Vote on recently passed bills from the Legislature"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def prime_minister(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.PRIME_MINISTER_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def lt_prime_minister(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.LT_PRIME_MINISTER_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def speaker(self) -> typing.Optional[discord.Member]:
        try:
            return mk.get_democraciv_role(self.bot, mk.DemocracivRole.SPEAKER_ROLE).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    async def get_open_vetos(self) -> typing.List[Bill]:
        """Gets all bills that passed the Legislature, are vetoable and were not yet voted on by the Ministry"""
        open_bills = await self.bot.db.fetch('SELECT id FROM legislature_bills WHERE has_passed_leg = true'
                                             ' AND is_vetoable = true AND voted_on_by_ministry = false'
                                             ' AND has_passed_ministry = false ORDER BY id')

        return [await Bill.convert(MockContext(self.bot), record['id']) for record in open_bills]

    async def get_pretty_vetos(self) -> typing.Optional[typing.List[str]]:
        """Prettifies a list of Bill objects of open vetoes into list of strings"""
        open_bills = await self.get_open_vetos()

        pretty_bills = []

        if len(open_bills) > 0:
            for bill in open_bills:
                if bill.submitter is not None:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.name}]({bill.tiny_link}) by "
                                        f"{bill.submitter.mention} from session #{bill.session.id}")
                else:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.name}]({bill.tiny_link}) "
                                        f"from session #{bill.session.id}")

        if not pretty_bills:
            return None

        return pretty_bills

    @commands.group(name='ministry', aliases=['m'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ministry(self, ctx):
        """Dashboard for Ministers"""

        embed = self.bot.embeds.embed_builder(title=f"The Ministry of {mk.NATION_NAME}", description="")

        pretty_bills = await self.get_pretty_vetos()

        if pretty_bills is None:
            pretty_bills = 'There are no new bills to vote on.'
        else:
            pretty_bills = f"You can vote on new bills, check `{ctx.prefix}ministry bills`."

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(f"Prime Minister: {self.prime_minister.mention}")
        else:
            minister_value.append("Prime Minister: -")

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value.append(f"Lt. Prime Minister: {self.lt_prime_minister.mention}")
        else:
            minister_value.append("Lt. Prime Minister: -")

        embed.add_field(name="Head of State", value='\n'.join(minister_value))
        embed.add_field(name="Links", value=f"[Constitution]({links.constitution})\n"
                                            f"[Legal Code]({links.laws})\n"
                                            f"[Ministry Worksheet]({links.executiveworksheet})\n"
                                            f"[Ministry Procedures]({links.execprocedures})", inline=True)
        embed.add_field(name="Open Bills", value=pretty_bills, inline=False)
        await ctx.send(embed=embed)

    @ministry.group(name='bills', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def bills(self, ctx):
        """See all open bills from the Legislature to vote on"""

        pretty_bills = await self.get_pretty_vetos()

        if pretty_bills is None:
            pretty_bills = ['There are no new bills to vote on.']

        help_description = f"Use {self.bot.commands_prefix}ministry veto <bill_id> to veto a bill, or " \
                           f"{self.bot.commands_prefix}ministry pass <bill_id> to pass a bill into law."

        pages = Pages(ctx=ctx, entries=pretty_bills, show_entry_count=False, title="Open Bills to Vote On",
                      show_index=False, footer_text=help_description)
        await pages.paginate()

    @ministry.group(name='veto', aliases=['v'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.PRIME_MINISTER_ROLE, mk.DemocracivRole.LT_PRIME_MINISTER_ROLE)
    async def veto(self, ctx, bill_id: Bill):
        """Veto a bill"""

        bill = bill_id

        if not bill.is_vetoable:
            return await ctx.send(f":x: The Ministry cannot veto this!")

        if not bill.passed_leg:
            return await ctx.send(f":x: This bill hasn't passed the Legislature yet!")

        if bill.voted_on_by_ministry:
            return await ctx.send(f":x: You already voted on this bill!")

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to "
                                      f"veto `{bill.name}` (#{bill.id}?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if reaction:
            async with ctx.typing():
                await self.bot.db.execute(
                    "UPDATE legislature_bills SET voted_on_by_ministry = true, has_passed_ministry = "
                    "false WHERE id = $1", bill.id)

                await ctx.send(f":white_check_mark: `{bill.name}` was vetoed.")

                await self.gov_announcements_channel.send(
                    f"{self.speaker.mention}, `{bill.name}` ({bill.tiny_link}) was **vetoed** by the Ministry.")

        elif not reaction:
            await ctx.send(f"Aborted.")

    @ministry.group(name='pass', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.PRIME_MINISTER_ROLE, mk.DemocracivRole.LT_PRIME_MINISTER_ROLE)
    async def passbill(self, ctx, bill_id: Bill):
        """Pass a bill into law"""

        bill = bill_id

        if not bill.is_vetoable:
            return await ctx.send(f":x: The Ministry cannot veto this!")

        if not bill.passed_leg:
            return await ctx.send(f":x: This bill hasn't passed the Legislature yet!")

        if bill.voted_on_by_ministry:
            return await ctx.send(f":x: You already voted on this bill!")

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to pass `{bill.name}` "
                                      f"(#{bill.id}) into law?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if reaction:
            async with ctx.typing():
                if await self.bot.laws.pass_into_law(ctx, bill):
                    await ctx.send(":white_check_mark: Passed into law.")
                    await self.gov_announcements_channel.send(
                        f"{self.speaker.mention}, `{bill.name}` ({bill.tiny_link}) was "
                        f"**passed into law** by the Ministry.")
                else:
                    await ctx.send(":x: Unexpected error occurred.")

        elif not reaction:
            await ctx.send(f"Aborted.")


def setup(bot):
    bot.add_cog(Ministry(bot))
