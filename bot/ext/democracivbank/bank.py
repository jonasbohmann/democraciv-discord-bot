import asyncio
import sys
import textwrap
import uuid
import decimal
import aiohttp
import discord
import typing

from discord.ext import commands
from bot.utils import converter, exceptions, text, checks, context, paginator
from bot.config import config, token, mk
from discord.ext import menus
from aiohttp import web


CURRENCIES = {
    "LRA": ("Ottoman Lira", "£"),
    "MAO": ("Maori Pound", "P"),
    "CAN": ("Canadian Loonie", "Ⱡ"),
    "CIV": ("Civilization Coin", "C"),
}


def _(y) -> tuple:
    try:
        return CURRENCIES[y]
    except KeyError:
        return "Unknown Currency", "?"


class BankListener:
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.add_routes([web.post("/dm", self.send_dm)])
        self.runner = web.AppRunner(self.app)
        self.bot.loop.create_task(self.setup())

    async def shutdown(self):
        await self.runner.cleanup()

    async def setup(self):
        await self.runner.setup()
        site = web.TCPSite(self.runner, "localhost", 8080)
        await site.start()

    async def send_dm(self, request):
        json = await request.json()

        for target in json["targets"]:
            user = self.bot.get_user(target)

            if user is None:
                continue

            msg = json["message"] if json["message"] else None
            embed = discord.Embed.from_dict(json["embed"]) if json["embed"] else None

            try:
                await user.send(content=msg, embed=embed)
            except discord.Forbidden:
                continue

        return web.json_response({"ok": "ok"})


class CurrencySelector(menus.Menu):
    def __init__(self):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.result = None

    async def send_initial_message(self, ctx, channel):
        embed = text.SafeEmbed(title=f"{config.USER_INTERACTION_REQUIRED}  Currency Selection")
        embed.description = (
            "Since you did not specify an IBAN to send the money to, "
            "I cannot automatically determine the currency for this "
            "transaction. Once you've chosen a currency, I will send the money "
            "from your default account for the chosen currency, to the recipient's default "
            "account for the chosen currency.\n\n"
            "This only works provided that both you and the "
            "recipient have previously selected a default account for the chosen currency on "
            "[democracivbank.com](https://democracivbank.com)\n\n"
            "__**In which currency would you like to send the money?**__\n"
            f":one:  {_('LRA')[0]}\n"
            f":two:  {_('MAO')[0]}\n"
            f":three:  {_('CAN')[0]}\n"
            f":four:  {_('CIV')[0]}"
        )

        return await channel.send(embed=embed)

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_first_choice(self, payload):
        self.result = "LRA"
        self.stop()

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_second_choice(self, payload):
        self.result = "MAO"
        self.stop()

    @menus.button("3\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_third_choice(self, payload):
        self.result = "CAN"
        self.stop()

    @menus.button("4\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_fourth_choice(self, payload):
        self.result = "CIV"
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class BankConnectionError(exceptions.DemocracivBotException):
    pass


class BankDiscordUserNotConnected(exceptions.DemocracivBotException):
    pass


class BankNoDefaultAccountForCurrency(exceptions.DemocracivBotException):
    pass


class BankNoAccountFound(exceptions.DemocracivBotException):
    pass


class BankInvalidIBANFormat(exceptions.DemocracivBotException):
    pass


class BankTransactionError(exceptions.DemocracivBotException):
    pass


class BankRoute:
    DEMOCRACIV_BANK_API_BASE = "https://democracivbank.com/api/v1/"

    def __init__(self, method, path):
        self.method = method
        self.path = path
        self.url = self.DEMOCRACIV_BANK_API_BASE + self.path
        self.user_agent = (
            f"Democraciv Discord Bot {config.BOT_VERSION} - Python/{sys.version_info[0]}."
            f"{sys.version_info[1]}.{sys.version_info[2]} aiohttp/{aiohttp.__version__}"
        )
        self.headers = {
            "Authorization": f"Token {token.DEMOCRACIV_BANK_API_ADMIN_TOKEN}",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }


class BankCorporation(commands.Converter):
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.abbreviation = kwargs.get("abbreviation")
        self.description = kwargs.get("description")
        self.discord_server = kwargs.get("discord_server")
        self.nation = kwargs.get("nation")
        self.organization_type = kwargs.get("organization_type")
        self.industry = kwargs.get("industry")

    @classmethod
    async def convert(cls, ctx, argument):
        response = await ctx.bot.get_cog("Bank").request(BankRoute("GET", f"corporation/{argument}/"))

        if response.status == 404:
            raise commands.BadArgument(
                f"{config.NO} {argument} is either not the abbreviation of an existing "
                f"organization, or they decided not to publish their organization."
            )

        elif response.status == 200:
            json = await response.json()

            if json["is_public_viewable"]:
                return cls(**json)

        raise commands.BadArgument()


class Bank(context.CustomCog):
    """Open as many bank accounts as you want and send money in multiple currencies with [democracivbank.com](https://democracivbank.com)."""

    def __init__(self, bot):
        super().__init__(bot)
        self.BANK_NAME = "Bank of Arabia"
        self.BANK_ICON_URL = (
            "https://cdn.discordapp.com/attachments/663076007426785300/717434510861533344/ezgif-5-8a4edb1f0306.png"
        )
        self.bank_listener = BankListener(bot)

    def cog_unload(self):
        self.bot.loop.create_task(self.bank_listener.shutdown())

    async def is_connected_with_bank_user(self, ctx):
        response = await self.request(BankRoute("HEAD", f"discord_user/{ctx.author.id}/"))

        if response.status != 200:
            raise BankDiscordUserNotConnected(
                f"{config.NO} {ctx.author}, your Discord account is not connected to any "
                f"user on <https://democracivbank.com>.\n\nYou can connect here: "
                f"<https://democracivbank.com/me>"
            )

    async def request(self, route: BankRoute, **kwargs):
        response = await self.bot.session.request(
            route.method,
            route.url,
            headers=route.headers,
            data=kwargs.get("data", None),
            params=kwargs.get("params", None),
        )
        if response.status >= 500:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!\n`Status >= 500`")

        return response

    async def get_currency_from_iban(self, iban: str) -> str:
        response = await self.request(BankRoute("GET", f"account/{iban}/"))

        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        json = await response.json()
        return json["balance_currency"]

    async def resolve_iban(self, member_id_or_corp, currency, is_sender=False) -> str:
        get_params = {"currency": currency}

        if isinstance(member_id_or_corp, int):
            get_params["discord_id"] = member_id_or_corp
        else:
            get_params["corporation"] = member_id_or_corp

        response = await self.request(BankRoute("GET", "default_account/"), params=get_params)

        if response.status == 200:
            json = await response.json()
            return json["iban"]

        elif response.status == 404:
            if "discord_id" in get_params:
                name = self.bot.get_user(get_params["discord_id"])
                raise BankDiscordUserNotConnected(
                    f"{config.NO} {name} is not connected with any user account on "
                    f"<https://democracivbank.com>. Tell them to connect their "
                    f"Discord account here: <https://democracivbank.com/me>"
                )

            else:
                raise BankNoAccountFound(
                    f"{config.NO} {member_id_or_corp} is either not the abbreviation of an existing "
                    f"organization, or they decided not to publish their organization."
                )

        elif response.status == 400:
            if "discord_id" in get_params:
                if not is_sender:
                    name = self.bot.get_user(get_params["discord_id"])
                    raise BankNoDefaultAccountForCurrency(
                        f"{config.NO} **{name}** does not have a default bank account "
                        f"for this currency. Tell them to set a default bank "
                        f"account for this currency on "
                        f"<https://democracivbank.com>."
                    )
                if is_sender:
                    raise BankNoDefaultAccountForCurrency(
                        f"{config.NO} You do not have a default bank account for "
                        "this currency. You can make one of your personal "
                        "bank accounts that holds this currency to be the "
                        "default bank account for this currency on "
                        "<https://democracivbank.com>."
                    )
            else:
                raise BankNoDefaultAccountForCurrency(
                    f"{config.NO} This organization does not have a default democracivbank account " f"for this currency."
                )

    async def send_money(self, from_discord, from_iban, to_iban, amount, purpose):
        payload = {
            "from_account": from_iban,
            "to_account": to_iban,
            "amount": amount,
            "purpose": purpose,
            "discord_id": from_discord,
        }

        response = await self.request(BankRoute("POST", "send/"), data=payload)
        json = await response.json()

        if response.status == 201:
            return json

        elif response.status == 400:
            if "non_field_errors" in json:
                message = [f"{config.NO} The transaction could not be completed, take a look at the error(s):"]

                for error in json["non_field_errors"]:
                    message.append(f"- {error}")

                raise BankTransactionError("\n".join(message))

            else:
                raise BankTransactionError(
                    f"{config.NO} The transaction could not be completed, please notify " f"{self.bot.owner}."
                )

    @commands.group(
        name="bank",
        aliases=["b", "economy", "cash", "currency"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def bank(self, ctx):
        """The Bank of Arabia"""

        response = await self.request(BankRoute("GET", "statistics/"))

        embed = text.SafeEmbed()
        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        embed.description = (
            f"The {self.BANK_NAME} provides the international community with free financial "
            f"services: Personal & Shared Bank Accounts with complete transaction records, a "
            f"corporate registry, personalized notifications, support for multiple currencies and a "
            f"deep integration into the Democraciv Discord Bot.\n\nSign up for an account over at "
            f"[democracivbank.com](https://democracivbank.com) and connect your Discord Account on "
            f"[democracivbank.com/me](https://democracivbank.com/me) for the full experience."
        )

        if response.status == 200:
            json = await response.json()
            pl = []

            for k, v in json.items():
                pl.append(f"{k}: {v}")

            pl = "\n".join(pl)
            embed.add_field(name="Statistics", value=pl, inline=False)

        await ctx.send(embed=embed)

    @bank.command(
        name="organization",
        aliases=["org", "corp", "company", "corporation", "marketplace", "m"],
    )
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def organization(self, ctx, organization: BankCorporation = None):
        """Details about a specific organization or corporation on the Marketplace"""
        if organization is None:
            response = await self.request(BankRoute("GET", "featured_corporation/"))

            embed = text.SafeEmbed(
                description="Check out all corporations and organizations from around"
                " the world and what they have to offer on "
                "[**democracivbank.com/marketplace**]"
                "(https://democracivbank.com/marketplace)"
            )
            embed.url = "https://democracivbank.com/marketplace"
            embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)

            if response.status != 200:
                return await ctx.send(embed=embed)

            json = await response.json()
            for result in json["results"]:
                # this will break/look like shit if too many ads
                value = (
                    f"[{result['corporation']['organization_type']} from the "
                    f"{result['corporation']['nation']}]"
                    f"(https://democracivbank.com/organization/{result['corporation']['abbreviation']})"
                    f"\n\n{textwrap.shorten(result['ad_message'], width=800, placeholder='...')}"
                )

                embed.add_field(
                    name=f"{result['corporation']['name']} ({result['corporation']['abbreviation']})",
                    value=value,
                    inline=False,
                )

            embed.description = (
                f"{embed.description}\n\nThe following organizations are paid ads on the " f"Marketplace."
            )
            return await ctx.send(embed=embed)

        embed = text.SafeEmbed(
            title=f"{organization.name} ({organization.abbreviation})",
            description=f"{organization.organization_type} from the " f"{organization.nation}",
        )

        embed.add_field(name="Description", value=organization.description, inline=False)
        embed.url = f"https://democracivbank.com/organization/{organization.abbreviation}"
        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        embed.set_footer(text=f"Send money to this organization with: -bank send {organization.abbreviation} <amount>")

        if organization.discord_server:
            embed.add_field(name="Discord Server", value=organization.discord_server)

        if organization.industry:
            embed.add_field(name="Industry", value=organization.industry)

        await ctx.send(embed=embed)

    @bank.command(
        name="accounts",
        aliases=["bal", "money", "cash", "b", "account", "balance", "a", "acc"],
    )
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def accounts(self, ctx):
        """See the balance of every bank account you have access to"""
        await self.is_connected_with_bank_user(ctx)

        if ctx.guild:
            embed = text.SafeEmbed(title=f"{config.USER_INTERACTION_REQUIRED}  Privacy Prompt")
            embed.description = (
                "Are you sure that you want to proceed?\n\n"
                "Everyone in this channel would be able to see information about all bank accounts "
                "you have access to, including their IBAN and their balance.\n\n*Using this command "
                "in DMs with me does not trigger this question.*"
            )
            privacy_q = await ctx.send(embed=embed)
            reaction = await ctx.confirm(message=privacy_q, timeout=100)

            if not reaction:
                return

            await privacy_q.delete()

        response = await self.request(BankRoute("GET", f"accounts/{ctx.author.id}/"))
        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        json = await response.json()
        desc = ["\n"]
        total_per_currency = {}

        for account in json:
            if ctx.guild:
                name = "__*Bank Account Name Censored - Use command in DMs to reveal*__"
            else:
                if not account["corporate_holder"]:
                    name = f"__**{account['name']}**__"
                else:
                    name = f"__**{account['corporate_holder']['name']}: {account['name']}**__"

            desc.append(
                f"{name}\n*{account['iban']}*\n```diff\n+ {account['balance']}{_(account['balance_currency'])[1]}```"
            )

            try:
                total_per_currency[account["pretty_balance_currency"]] += decimal.Decimal(account["balance"])
            except KeyError:
                total_per_currency[account["pretty_balance_currency"]] = decimal.Decimal(account["balance"])

        prepend_desc = ["**Total Balance per Currency**"]
        for cur, amount in total_per_currency.items():
            prepend_desc.append(f"{cur}: {amount}")

        desc.append("\n".join(prepend_desc))

        pages = paginator.SimplePages(
            entries=desc,
            author=f"{ctx.author.display_name}'s Bank Accounts",
            icon=ctx.author_icon,
        )
        await pages.start(ctx)

    @bank.command(name="send", aliases=["s", "transfer", "t", "give"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def send(
        self,
        ctx,
        to_member_or_iban_or_organization: typing.Union[
            discord.Member,
            converter.CaseInsensitiveMember,
            discord.User,
            uuid.UUID,
            str,
        ],
        amount: decimal.Decimal,
        *,
        purpose: str = None,
    ):
        """Send money to a specific bank account, organization, or person on this server

        **Example**
            `{PREFIX}{COMMAND} @DerJonas 9.99`
            `{PREFIX}{COMMAND} DerJonas#8036 250`
            `{PREFIX}{COMMAND} c4a3ec17-cba4-462f-bdda-05620f574dce 32.10 Thanks ;)`
            `{PREFIX}{COMMAND} GOOGLE 1000.21` assuming 'GOOGLE' is the abbreviation of an existing, published organization
        """

        await self.is_connected_with_bank_user(ctx)
        currency = "XYZ"  # linter

        if not isinstance(to_member_or_iban_or_organization, uuid.UUID):
            # if IBAN, skip currency selection
            currency = await CurrencySelector().prompt(ctx)

            if not currency:
                return await ctx.send(f"{config.NO} You did not select a currency, the transaction was cancelled.")

            from_iban = await self.resolve_iban(ctx.author.id, currency, is_sender=True)

        if isinstance(to_member_or_iban_or_organization, discord.Member):
            to_iban = await self.resolve_iban(to_member_or_iban_or_organization.id, currency)
        elif isinstance(to_member_or_iban_or_organization, str):
            to_iban = await self.resolve_iban(to_member_or_iban_or_organization, currency)
        else:
            # is UUID
            if to_member_or_iban_or_organization.version != 4:
                raise BankInvalidIBANFormat(
                    f"{config.NO} That is not a valid IBAN, it needs to be in this "
                    "format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`"
                )

            to_iban = str(to_member_or_iban_or_organization)
            currency = await self.get_currency_from_iban(to_iban)
            from_iban = await self.resolve_iban(ctx.author.id, currency, is_sender=True)

        purpose = "Sent via the Democraciv Discord Bot" if not purpose else purpose

        transaction = await self.send_money(ctx.author.id, from_iban, to_iban, amount, purpose)

        embed = text.SafeEmbed(
            title=f"You sent {amount}{_(transaction['amount_currency'])[1]} to {transaction['safe_to_account']}",
            description=f"[See the transaction details here.](https://democracivbank.com/transaction/{transaction['id']})",
        )
        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        await ctx.send(embed=embed)

    @bank.command(name="applyottomantax", aliases=["applyottomanformula"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.OTTOMAN_TAX_OFFICER)
    async def apply_ottoman_formula(self, ctx):
        """See the outcome of a dry-run of the tax on all bank accounts with the Ottoman currency and then apply that tax """

        # Do the dry run first
        response = await self.request(BankRoute("GET", "ottoman/apply/"))

        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        dry_run_results = await response.json()
        desc = [
            "This is just a dry run, the changes have not been applied yet. Double check the results and once "
            "you're ready, confirm that you actually want to apply the changes.\n"
        ]

        for result in dry_run_results["results"]:
            for k, v in result.items():
                desc.append(
                    f"__**Bank Account with IBAN {k}**__\nPre-Tax Balance: {v['old']}{_('LRA')[1]}"
                    f"\nPost-Tax Balance: {v['new']}{_('LRA')[1]}\nEquilibrium variable: {v['ibal']}\n"
                )

        pages = paginator.SimplePages(entries=desc, title="Results of Ottoman Tax Dry Run")
        self.bot.loop.create_task(pages.start(ctx))
        await asyncio.sleep(15)

        reaction = await ctx.confirm(f"{config.USER_INTERACTION_REQUIRED} Do you want to apply the changes now?")

        if not reaction:
            return

        response = await self.request(BankRoute("POST", "ottoman/apply/"))

        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        await ctx.send(f"{config.YES} Tax was applied to all accounts with the Ottoman currency.")

    @bank.command(name="liracirculation")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.OTTOMAN_TAX_OFFICER)
    async def ottoman_circulation(self, ctx):
        """See how much Lira is currently in circulation"""

        response = await self.request(BankRoute("GET", "circulation/LRA/"))
        lira = await response.json()

        embed = text.SafeEmbed(
            title=f"{lira['result']}{_('LRA')[1]}",
            description="This does not include the Ottoman Government's Lira Reserve.",
        )
        await ctx.send(embed=embed)

    @bank.command(name="listottomanvariable", aliases=["listottomanvariables"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.OTTOMAN_TAX_OFFICER)
    async def list_ottoman_ibal(self, ctx):
        """List all bank accounts with the Ottoman currency and check their Equilibrium variable"""

        response = await self.request(BankRoute("GET", "ottoman/threshold/"))

        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        json = await response.json()
        desc = []

        for account in json:
            p_or_c = "Personal" if account["individual_holder"] else "Corporate"
            desc.append(
                f"__**{p_or_c} Bank Account with IBAN {account['iban']}**__\n"
                f"Owner: {account['pretty_holder']}\n"
                f"Equilibrium variable: {account['ottoman_threshold_variable']}\n"
            )

        pages = paginator.SimplePages(entries=desc, title=f"All Bank Accounts with Ottoman Currency ({len(json)})")
        await pages.start(ctx)

    @bank.command(
        name="changeottomanvariable",
        aliases=[
            "changeottomanvariables",
            "editottomanvariables",
            "editottomanvariable",
        ],
    )
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @checks.has_democraciv_role(mk.DemocracivRole.OTTOMAN_TAX_OFFICER)
    async def edit_ottoman_ibal(self, ctx, iban: uuid.UUID, new_ibal: decimal.Decimal):
        """Change the Equilibrium variable of a bank account with the Ottoman currency

        **Example:**
            `{PREFIX}{COMMAND} c4a3ec17-cba4-462f-bdda-05620f574dce 200` their new variable will be 200
        """

        if iban.version != 4:
            raise BankInvalidIBANFormat(
                "{config.NO} That is not a valid IBAN, it needs to be in this " "format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`"
            )

        payload = {"iban": str(iban), "new": new_ibal}
        response = await self.request(BankRoute("POST", "ottoman/threshold/"), data=payload)

        if response.status != 200:
            raise BankConnectionError(f"{config.NO} {self.bot.owner.mention}, something went wrong!")

        json = await response.json()
        p_or_c = "Personal" if json["individual_holder"] else "Corporate"
        embed = text.SafeEmbed(
            title="Updated Ottoman Bank Account",
            description=f"**IBAN**\n{json['iban']}\n"
            f"**Bank Account Type**\n{p_or_c}\n"
            f"**Owner**\n{json['pretty_holder']}\n"
            f"**Equilibrium variable**\n"
            f"{json['ottoman_threshold_variable']}",
        )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Bank(bot))
