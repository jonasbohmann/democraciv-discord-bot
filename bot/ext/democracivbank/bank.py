import sys
import textwrap
import uuid
import decimal
import aiohttp
import discord

from aiohttp import web
from dataclasses import dataclass
from discord.ext import commands, tasks
from bot.utils import converter, exceptions, text, paginator, context
from bot.config import config, token
from discord.ext import menus

from bot.utils.converter import Fuzzy, FuzzySettings


class CurrencySelector(menus.Menu):
    def __init__(self, currencies):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.result = None
        self.currencies: dict = currencies
        self._make_buttons()

    def get_curr_name(self, code):
        return self.currencies.get(code).name

    async def send_initial_message(self, ctx, channel):
        embed = text.SafeEmbed(
            title=f"{config.USER_INTERACTION_REQUIRED}  Currency Selection"
        )

        description = (
            "Since you did not specify an IBAN to send the money to, "
            "I cannot automatically determine the currency for this "
            "transaction. Once you've chosen a currency, I will send the money "
            "from your default account for the chosen currency, to the recipient's default "
            "account for the chosen currency.\n\n"
            "This only works provided that both you and the "
            "recipient have previously selected a default account for the chosen currency on "
            "[democracivbank.com](https://democracivbank.com)\n\n"
            "__**In which currency would you like to send the money?**__\n"
        )

        currs = []

        for emoji, code in self.mapping.items():
            currs.append(f"{emoji}  {self.get_curr_name(code)}")

        currs = "\n".join(currs)

        embed.description = f"{description}{currs}"

        return await channel.send(embed=embed)

    def _make_buttons(self):
        self.mapping = {}

        for i, kv in enumerate(self.currencies.items(), start=1):
            code, _ = kv
            emoji = f"{i}\N{variation selector-16}\N{combining enclosing keycap}"
            button = menus.Button(emoji=emoji, action=self.on_button)
            self.add_button(button=button)
            self.mapping[emoji] = code

    async def on_button(self, payload):
        code = self.mapping.get(str(payload.emoji))
        self.result = code
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
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
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


class BankRoute:
    DEMOCRACIV_BANK_API_BASE = "https://democracivbank.com/api/v1/"

    def __init__(self, method, path):
        self.method = method
        self.path = path
        self.url = self.DEMOCRACIV_BANK_API_BASE + self.path
        self.user_agent = (
            f"Democraciv Discord Bot - Python/{sys.version_info[0]}."
            f"{sys.version_info[1]}.{sys.version_info[2]} aiohttp/{aiohttp.__version__}"
        )
        self.headers = {
            "Authorization": f"Token {token.DEMOCRACIV_BANK_API_ADMIN_TOKEN}",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }


class BankUUIDConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return uuid.UUID(argument)
        except (ValueError, TypeError):
            raise BankInvalidIBANFormat()


class BankCorporationMarketplace(commands.Converter):
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.abbreviation = kwargs.get("abbreviation")
        self.description = kwargs.get("description")
        self.discord_server = kwargs.get("discord_server")
        self.nation = kwargs.get("nation")
        self.organization_type = kwargs.get("organization_type")
        self.industry = kwargs.get("industry")

    @classmethod
    async def convert(cls, ctx, argument, *, allow_private=False):
        response = await ctx.bot.get_cog("Bank").request(
            BankRoute("GET", f"corporation/{argument}/")
        )

        if response.status == 404:
            raise commands.BadArgument(
                f"{config.NO} {argument} is either not the abbreviation of an existing "
                f"organization, or they decided not to publish their organization."
            )

        elif response.status == 200:
            json = await response.json()

            if json["is_public_viewable"] or allow_private:
                return cls(**json)

        raise commands.BadArgument(
            f"{config.NO} {argument} is either not the abbreviation of an existing "
            "organization, or they decided not to publish their organization."
        )


class BankCorporationAbbreviation(commands.Converter):
    @classmethod
    async def convert(cls, ctx, argument):
        try:
            corp = await BankCorporationMarketplace.convert(
                ctx, argument, allow_private=True
            )
            return corp.abbreviation
        except commands.BadArgument:
            raise commands.BadArgument(
                f"{config.NO} {argument} is not the abbreviation of an existing organization."
            )


@dataclass
class Currency:
    code: str
    name: str
    prefix: str
    suffix: str

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Currency) and self.code == other.code

    def __ne__(self, other):
        return not self.__eq__(other)

    def with_amount(self, amount):
        return f"{self.prefix}{amount}{self.suffix}"

    _ = with_amount


class Bank(context.CustomCog):
    """Open as many bank accounts as you want and send money in multiple currencies with https://democracivbank.com"""

    def __init__(self, bot):
        super().__init__(bot)
        self.BANK_NAME = "Bank of Democraciv"
        self.BANK_ICON_URL = "https://cdn.discordapp.com/attachments/663076007426785300/717434510861533344/ezgif-5-8a4edb1f0306.png"
        self.bank_listener = BankListener(bot)

        if not bot.IS_DEBUG:
            self.bank_db_backup.start()

        self._currencies = {}
        self.bot.loop.create_task(self._fetch_currencies())

    def cog_unload(self):
        self.bot.loop.create_task(self.bank_listener.shutdown())

        if not self.bot.IS_DEBUG:
            self.bank_db_backup.cancel()

    @tasks.loop(hours=config.DATABASE_DAILY_BACKUP_INTERVAL)
    async def bank_db_backup(self):
        await self.bot.do_db_backup("live_bank")

    async def is_connected_with_bank_user(self, ctx):
        response = await self.request(
            BankRoute("HEAD", f"discord_user/{ctx.author.id}/")
        )

        if response.status != 200:
            raise BankDiscordUserNotConnected(
                f"{config.NO} {ctx.author.mention}, your Discord account is not connected to any "
                f"user on <https://democracivbank.com>.\n\nYou can connect here: "
                f"https://democracivbank.com/me/discord"
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
            raise BankConnectionError(
                f"{config.NO} {self.bot.owner.mention}, something went wrong!\n`Status >= 500`"
            )

        return response

    async def _fetch_currencies(self):
        response = await self.request(BankRoute("GET", f"currencies/"))
        js = await response.json()
        currencies = {}

        for curr in js["result"]:
            currencies[curr["code"]] = Currency(
                code=curr["code"],
                name=curr["name"],
                prefix=curr["sign"]["prefix"],
                suffix=curr["sign"]["suffix"],
            )

        self._currencies = currencies

    def get_currency(self, code) -> Currency:
        try:
            return self._currencies[code]
        except KeyError:
            self.bot.loop.create_task(self._fetch_currencies())
            return Currency(code="???", name="Unknown Currency", prefix="", suffix="?")

    async def get_currency_from_iban(self, iban: str) -> str:
        response = await self.request(BankRoute("GET", f"account/{iban}/"))

        if response.status != 200:
            raise BankConnectionError(
                f"{config.NO} {self.bot.owner.mention}, something went wrong!"
            )

        json = await response.json()
        return json["balance_currency"]

    async def resolve_iban(self, member_id_or_corp, currency, is_sender=False) -> str:
        get_params = {"currency": currency}

        if isinstance(member_id_or_corp, int):
            get_params["discord_id"] = member_id_or_corp
        else:
            get_params["corporation"] = member_id_or_corp

        response = await self.request(
            BankRoute("GET", "default_account/"), params=get_params
        )

        if response.status == 200:
            json = await response.json()
            return json["iban"]

        elif response.status == 404:
            if "discord_id" in get_params:
                name = self.bot.get_user(get_params["discord_id"])
                raise BankDiscordUserNotConnected(
                    f"{config.NO} {name} is not connected with any user account on "
                    f"<https://democracivbank.com>. Tell them to connect their "
                    f"Discord account here: https://democracivbank.com/me/discord"
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
                        f"for this currency. Tell them to open a bank account in this currency at "
                        "https://democracivbank.com/account/new/."
                    )
                if is_sender:
                    raise BankNoDefaultAccountForCurrency(
                        f"{config.NO} You do not have a default bank account for "
                        "this currency. Open a bank account in this currency at "
                        "https://democracivbank.com/account/new/ and set "
                        "it as your default bank account for that currency."
                    )
            else:
                raise BankNoDefaultAccountForCurrency(
                    f"{config.NO} This organization does not have a default bank account for this currency."
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
                message = [
                    f"{config.NO} The transaction could not be completed, take a look at the error(s):"
                ]

                for error in json["non_field_errors"]:
                    message.append(f"- {error}")

                raise BankTransactionError("\n".join(message))

            else:
                raise BankTransactionError(
                    f"{config.NO} The transaction could not be completed, please notify {self.bot.owner}."
                )

    @commands.group(
        name="bank",
        aliases=["ba", "economy", "cash", "currency"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def bank(self, ctx):
        """The Bank of Democraciv"""

        embed = text.SafeEmbed(
            description=f"The [{self.BANK_NAME}](https://democracivbank.com) provides the international community "
            f"with free financial "
            f"services: Personal & Shared Bank Accounts with complete transaction records, a "
            f"corporate registry, personalized notifications, support for multiple currencies and a "
            f"deep integration into the Democraciv Discord Bot.\n\nYou can register at "
            f"[democracivbank.com](https://democracivbank.com) and open as many bank accounts as you want. "
            f"We don't have, give out or loan any money ourselves, so to actually get some "
            f"money you need to consult with our third-party partners (usually governments) "
            f"that issue the currencies.\n\n"
            f"Connect your Discord Account on "
            f"[democracivbank.com/me/discord](https://democracivbank.com/me/discord) to get access to "
            f"the `{config.BOT_PREFIX}bank` commands, like "
            f"`{config.BOT_PREFIX}bank accounts` to view all of your balances right here in Discord, "
            f"and to enable personalized "
            f"notifications in real-time whenever someone sends you money.\n\nSee `{config.BOT_PREFIX}help "
            f"bank` for a list of all bank related commands here on Discord."
        )

        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/738903909535318086/837833943377903616/bank.PNG"
        )
        await ctx.send(embed=embed)

    @bank.command(
        name="organization",
        aliases=["org", "corp", "company", "corporation", "marketplace", "m"],
    )
    async def organization(self, ctx, organization: BankCorporationMarketplace = None):
        """Details about a specific organization or corporation on the Marketplace"""
        if organization is None:
            response = await self.request(BankRoute("GET", "featured_corporation/"))

            embed = text.SafeEmbed(
                description="Check out all corporations and organizations from around"
                " the world and what they have to offer on "
                "[**democracivbank.com/marketplace**]"
                "(https://democracivbank.com/marketplace)",
                url="https://democracivbank.com/marketplace",
            )

            embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)

            if response.status != 200:
                return await ctx.send(embed=embed)

            json = await response.json()
            for result in json["results"]:
                # this will break/look like shit if too many ads
                value = (
                    f"[{result['corporation']['organization_type']} from "
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
                f"{embed.description}\n\nThe following organizations are paid ads on the "
                f"Marketplace."
            )
            return await ctx.send(embed=embed)

        embed = text.SafeEmbed(
            title=f"{organization.name} ({organization.abbreviation})",
            description=f"{organization.organization_type} from {organization.nation}",
            url=f"https://democracivbank.com/organization/{organization.abbreviation}",
        )

        embed.add_field(
            name="Description", value=organization.description, inline=False
        )
        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        embed.set_footer(
            text=f"Send money to this organization with: {config.BOT_PREFIX}bank send "
            f"{organization.abbreviation} <amount>"
        )

        if organization.discord_server:
            embed.add_field(name="Discord Server", value=organization.discord_server)

        if organization.industry:
            embed.add_field(name="Industry", value=organization.industry)

        await ctx.send(embed=embed)

    @bank.command(
        name="accounts",
        aliases=["bal", "money", "cash", "b", "account", "balance", "a", "acc"],
    )
    async def accounts(self, ctx):
        """See the balance of every bank account you have access to"""
        await self.is_connected_with_bank_user(ctx)

        if ctx.guild:
            embed = text.SafeEmbed(
                title=f"{config.HINT}  Privacy Prompt",
                description="Are you sure that you want to proceed?\n\n"
                "Everyone in this channel would be able to see the balance of all bank accounts "
                "you have access to.\n\n*Using this command in DMs with me does not "
                "trigger this question.*",
            )
            privacy_q = await ctx.send(embed=embed)
            reaction = await ctx.confirm(message=privacy_q)

            if not reaction:
                return

            await privacy_q.delete()

        response = await self.request(BankRoute("GET", f"accounts/{ctx.author.id}/"))
        if response.status != 200:
            raise BankConnectionError(
                f"{config.NO} {self.bot.owner.mention}, something went wrong!"
            )

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

            amount = self.get_currency(account["balance_currency"]).with_amount(
                account["balance"]
            )

            desc.append(f"{name}\n*{account['iban']}*\n```diff\n+ {amount}```")

            try:
                total_per_currency[
                    account["pretty_balance_currency"]
                ] += decimal.Decimal(account["balance"])
            except KeyError:
                total_per_currency[
                    account["pretty_balance_currency"]
                ] = decimal.Decimal(account["balance"])

        prepend_desc = ["**Total Balance per Currency**"]
        for cur, amount in total_per_currency.items():
            prepend_desc.append(f"{cur}: {amount}")

        desc.append("\n".join(prepend_desc))

        pages = paginator.SimplePages(
            entries=desc,
            author=f"{ctx.author.display_name}'s Bank Accounts",
            icon=ctx.author_icon,
            per_page=12,
        )
        await pages.start(ctx)

    @bank.command(name="send", aliases=["s", "transfer", "t", "give"])
    async def send(
        self,
        ctx,
        to_person_or_iban_or_organization: Fuzzy[
            converter.CaseInsensitiveMember,
            converter.CaseInsensitiveUser,
            BankCorporationAbbreviation,
            BankUUIDConverter,
            FuzzySettings(weights=(5, 1)),
        ],
        amount: decimal.Decimal,
        *,
        purpose: str = None,
    ):
        """Send money to a specific bank account, organization, or person on this server

        **Examples**
            `-bank send @DerJonas 9.99`
            `-bank send DerJonas#8036 250`
            `-bank send c4a3ec17-cba4-462f-bdda-05620f574dce 32.10 Thanks ;)`
            `-bank send GOOGLE 1000.21` assuming 'GOOGLE' is the abbreviation of an existing, published organization
        """

        await self.is_connected_with_bank_user(ctx)
        currency = "XYZ"  # linter

        if not isinstance(to_person_or_iban_or_organization, uuid.UUID):
            # if IBAN, skip currency selection
            currency = await CurrencySelector(self._currencies).prompt(ctx)

            if not currency:
                return await ctx.send(
                    f"{config.NO} You did not select a currency, the transaction was cancelled."
                )

            from_iban = await self.resolve_iban(ctx.author.id, currency, is_sender=True)

        if isinstance(to_person_or_iban_or_organization, discord.Member):
            to_iban = await self.resolve_iban(
                to_person_or_iban_or_organization.id, currency
            )
        elif isinstance(to_person_or_iban_or_organization, str):
            to_iban = await self.resolve_iban(
                to_person_or_iban_or_organization, currency
            )
        else:
            # is UUID
            if to_person_or_iban_or_organization.version != 4:
                raise BankInvalidIBANFormat(
                    f"{config.NO} That is not a valid IBAN, it needs to be in this "
                    "format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`"
                )

            to_iban = str(to_person_or_iban_or_organization)
            currency = await self.get_currency_from_iban(to_iban)
            from_iban = await self.resolve_iban(ctx.author.id, currency, is_sender=True)

        purpose = "Sent via the Democraciv Discord Bot" if not purpose else purpose
        transaction = await self.send_money(
            ctx.author.id, from_iban, to_iban, amount, purpose
        )

        pretty_amount = self.get_currency(transaction["amount_currency"]).with_amount(
            amount
        )

        embed = text.SafeEmbed(
            title=f"You sent {pretty_amount} to {transaction['safe_to_account']}",
            description=f"[See the transaction details here.](https://democracivbank.com/transaction/{transaction['id']})",
        )
        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)
        await ctx.send(embed=embed)

    @bank.command(name="stats", aliases=["circulation", "statistics", "total"])
    async def statistics(self, ctx):
        """See how much of every currency is currently in circulation and other statistics"""

        response = await self.request(BankRoute("GET", f"currencies/"))
        currencies = await response.json()

        stat_response = await self.request(BankRoute("GET", f"statistics/"))
        stats = await stat_response.json()

        embed = text.SafeEmbed(
            description=f"\n\nThere are a total of {stats['total_bank_accounts']} open bank accounts across "
            f"all currencies with a total of {stats['total_transactions']} transactions between "
            f"all of them.\n\nThe shown circulation of a currency does not include any currency reserves that "
            f"were provided by the {self.BANK_NAME} when this currency "
            f"was originally created.\n\nThe velocity is calculated as the amount of currency transferred "
            f"in the last 7 days divided by its total circulation."
        )

        embed.set_author(name=self.BANK_NAME, icon_url=self.BANK_ICON_URL)

        for currency in currencies["result"]:
            as_object = self.get_currency(currency["code"])

            stat = stats["currencies"]["detail"][currency["code"].upper()]
            value = (
                f"Circulation: {as_object.with_amount(currency['circulation'])}\n"
                f"Transactions: {stat['transactions']}\n"
                f"Bank Accounts: {stat['bank_accounts']}\n"
                f"Velocity in the last 7 days: {stat['velocity']:.3f}"
            )

            embed.add_field(name=currency["name"], value=value)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Bank(bot))
