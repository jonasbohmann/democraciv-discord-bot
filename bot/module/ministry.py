import datetime
import typing
import discord

from bot import DemocracivBot
from discord.ext import commands

from bot.utils.context import CustomContext
from bot.utils.converter import Bill, BillStatus
from bot.config import config, mk
from bot.utils import exceptions, text, paginator, checks, context
from discord.ext.commands import Greedy
from bot.utils.text import AnnouncementScheduler
from bot.utils.mixin import GovernmentMixin


class LawPassScheduler(AnnouncementScheduler):
    def get_message(self) -> str:
        message = [f"{self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNMENT_ROLE).mention}, "
                   f"the following bills were **passed into law by the {self.bot.mk.MINISTRY_NAME}**.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        message.append(f"\nAll new laws were added to `{config.BOT_PREFIX}laws` and can now be found with "
                       f"`{config.BOT_PREFIX}laws search <query>`. The "
                       f"{self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER).mention} should add them to "
                       f"the Legal Code as soon as possible.")

        return '\n'.join(message)


class LawVetoScheduler(AnnouncementScheduler):
    def get_message(self) -> str:
        message = [f"{self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER).mention}, "
                   f"the following bills were **vetoed by the {self.bot.mk.MINISTRY_NAME}**.\n"]

        for obj in self._objects:
            message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")

        return '\n'.join(message)


class Ministry(context.CustomCog, GovernmentMixin):
    """Allows the {MINISTRY_NAME} to pass and veto bills from the {LEGISLATURE_NAME}."""

    def __init__(self, bot):
        super().__init__(bot)
        self.pass_scheduler = LawPassScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)
        self.veto_scheduler = LawVetoScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    async def get_pretty_vetos(self) -> typing.Optional[typing.List[str]]:
        """Gets all bills that passed the Legislature, are vetoable and were not yet voted on by the Ministry"""

        open_bills = await self.bot.db.fetch('SELECT id, bill_name, link, tiny_link FROM legislature_bills '
                                             'WHERE is_vetoable = true AND status = $1 ORDER BY id',
                                             BillStatus.LEG_PASSED.value)

        if not open_bills:
            return None

        pretty_bills = []
        b_ids = []
        b_hyperlinks = []

        for record in open_bills:
            b_ids.append(f"Bill #{record['id']}")
            b_hyperlinks.append(f"=HYPERLINK(\"{record['link']}\"; \"{record['bill_name']}\")")
            pretty_bills.append(f"Bill #{record['id']} - [{record['bill_name']}]({record['tiny_link']})")

        exported = [
            f"Export of Vetoable Bills -- {datetime.datetime.utcnow().strftime('%c')}\n\n\n",
            "----- Vetoable Bills -----\n"]

        exported.extend(b_ids)
        exported.append("\n")
        exported.extend(b_hyperlinks)

        link = await self.bot.make_paste('\n'.join(exported))

        if link:
            pretty_bills.insert(0, f"[View this list in Google Spreadsheets formatting for"
                                   f" easy copy & pasting]({link})\n")

        return pretty_bills

    @commands.group(name='ministry', aliases=['m', 'min'], case_insensitive=True, invoke_without_command=True)
    async def ministry(self, ctx):
        """Dashboard for Ministers with important links and updates on new bills"""

        embed = text.SafeEmbed(title=f"{self.bot.mk.NATION_EMOJI}  The {self.bot.mk.MINISTRY_NAME} of "
                                     f"{self.bot.mk.NATION_FULL_NAME}")

        pretty_bills = await self.get_pretty_vetos()

        if pretty_bills is None:
            pretty_bills = 'There are no new bills to vote on.'
        else:
            pretty_bills = f"You can vote on new bills, check `{config.BOT_PREFIX}ministry bills`."

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(f"{self.bot.mk.pm_term}: {self.prime_minister.mention}")
        else:
            minister_value.append(f"{self.bot.mk.pm_term}: -")

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value.append(f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}")
        else:
            minister_value.append(f"{self.bot.mk.lt_pm_term}: -")

        embed.add_field(name=self.bot.mk.MINISTRY_LEADERSHIP_NAME, value='\n'.join(minister_value))
        embed.add_field(name="Links", value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
                                            f"[Legal Code]({self.bot.mk.LEGAL_CODE})\n", inline=True)
        embed.add_field(name="Veto-able Bills", value=pretty_bills, inline=False)
        await ctx.send(embed=embed)

    @ministry.command(name='bills', aliases=['b'])
    async def bills(self, ctx):
        """See all open bills from the {LEGISLATURE_NAME} to vote on"""

        pretty_bills = await self.get_pretty_vetos()

        if pretty_bills is None:
            embed = text.SafeEmbed(title="There are no new bills to vote on.")
            return await ctx.send(embed=embed)

        pages = paginator.SimplePages(entries=pretty_bills, title=f"{self.bot.mk.NATION_EMOJI}  Open Bills to Vote On")
        await pages.start(ctx)

    async def verify_bill(self, bill: Bill) -> str:
        if not bill.is_vetoable:
            return f"The {self.bot.mk.MINISTRY_NAME} cannot vote on this."

        if bill.status is BillStatus.MIN_PASSED or bill.status is BillStatus.MIN_FAILED:
            return "You already voted on this bill."

        if bill.status is not BillStatus.LEG_PASSED:
            return "You aren't allowed to vote on this bill."

    @ministry.command(name='veto', aliases=['v'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.PRIME_MINISTER, mk.DemocracivRole.LT_PRIME_MINISTER)
    async def veto(self, ctx: CustomContext, bill_ids: Greedy[Bill]):
        """Veto one or multiple bills

        **Example:**
            `-ministry veto 12` will veto Bill #12
            `-ministry veto 45 46 49 51 52` will veto all those bills"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        bills = bill_ids

        error_messages = []

        for _bill in bills:
            error = await self.verify_bill(_bill)

            if error:
                error_messages.append((_bill, error))

        if error_messages:
            # Remove bills that did not pass verify_bill from bills list
            bills[:] = [b for b in bills if b not in list(map(list, zip(*error_messages)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_bill.name}** (#{_bill.id}): _{reason}_" for _bill, reason in error_messages])
            await ctx.send(f":warning: The following bills can not be vetoed.\n{error_messages}")

        # If all bills failed verify_bills, return
        if not bills:
            return

        pretty_bills = '\n'.join([f"-  **{_bill.name}** (#{_bill.id})" for _bill in bills])

        reaction = await ctx.confirm(f":information_source: Are you sure that you want to veto the following bills?"
                                     f"\n{pretty_bills}")

        if not reaction:
            return

        async with ctx.typing():
            for _bill in bills:
                await _bill.veto()
                self.veto_scheduler.add(_bill)

            await ctx.send(":white_check_mark: All bills were vetoed.")

    @ministry.command(name='pass', aliases=['p'])
    @checks.has_any_democraciv_role(mk.DemocracivRole.PRIME_MINISTER, mk.DemocracivRole.LT_PRIME_MINISTER)
    async def pass_bill(self, ctx, bill_ids: Greedy[Bill]):
        """Pass one or multiple bills into law

        **Example:**
            `-ministry pass 12` will pass Bill #12 into law
            `-ministry pass 45 46 49 51 52` will pass all those bills into law"""

        bills = bill_ids

        error_messages = []

        for bill in bills:
            error = await self.verify_bill(bill)
            if error:
                error_messages.append((bill, error))

        if error_messages:
            # Remove bills that did not pass verify_bill from bills list
            bills = [b for b in bills if b not in list(map(list, zip(*error_messages)))[0]]

            error_messages = '\n'.join(
                [f"-  **{_bill.name}** (#{_bill.id}): _{reason}_" for _bill, reason in error_messages])
            await ctx.send(f":warning: The following bills can not be passed into law.\n{error_messages}")

        # If all bills failed verify_bills, return
        if not bills:
            return

        pretty_bills = '\n'.join([f"-  **{_bill.name}** (#{_bill.id})" for _bill in bills])

        reaction = await ctx.confirm(f":information_source: Are you sure that you want "
                                     f"to pass the following bills into law?"
                                     f"\n{pretty_bills}")

        if not reaction:
            return

        async with ctx.typing():
            for bill in bills:
                await bill.pass_into_law()
                self.pass_scheduler.add(bill)

            await ctx.send(":white_check_mark: All bills were passed into law.")


def setup(bot):
    bot.add_cog(Ministry(bot))
