import collections
import io
import itertools
import pathlib
import textwrap
import traceback
import aiofiles
import aiohttp
import discord
import random
import typing
import logging

from PIL import Image
from discord.ext import commands
from fuzzywuzzy import process

from bot.utils import context, checks, text, exceptions, paginator, converter
from bot.config import config, mk

PokeInfo = collections.namedtuple(
    "PokeInfo", "is_legendary is_mythical types description"
)


class PokeballConverter(commands.Converter, converter.FuzzyableMixin):
    model = "Pokéball"

    async def get_fuzzy_source(self, ctx, argument: str):
        choices = ctx.bot.get_cog("Pokémon").pokeball_lookup.keys()
        match = process.extract(argument, choices, limit=5)

        if not match:
            return []

        return [m for m, _ in match]

    async def convert(self, ctx, argument: str):
        argument = argument.title()
        if argument not in ctx.bot.get_cog("Pokémon").pokeball_lookup.keys():
            raise commands.BadArgument(
                f"{config.NO} That's not a ball you can throw. Try `pokeball`, "
                f"`greatball`, `ultraball` or `masterball`."
            )

        return argument


class Pokemon(context.CustomCog, name="Pokémon"):
    """Catch em all!"""

    def __init__(self, bot):
        super().__init__(bot)
        self.path = pathlib.Path(__file__).parent / "data"
        self.dex = {
            "Tier 1": [],
            "Tier 2": [],
            "Tier 3": [],
            "Tier 4": [],
            "Legendary": [],
        }

        self.pokeball_lookup = {
            "Pokeball": ["Tier 1"],
            "Greatball": ["Tier 1", "Tier 2"],
            "Ultraball": ["Tier 2", "Tier 3"],
            "Masterball": ["Tier 3", "Tier 4", "Legendary"],
        }

        self.load_dex()
        self._cached_poke_info: typing.Dict[str, PokeInfo] = {}

    def load_dex(self) -> None:
        dex_file = open(self.path / "dex.csv")
        # TODO Pep - auto generate these
        pokemon_column = 1
        pool_column = 4

        dex_lines = []

        for line in dex_file:
            dex_lines.append(line)

        dex_file.close()

        try:
            dex_lines.pop(0)
        except IndexError:
            pass

        for line in dex_lines:
            try:
                if not line.startswith("\t") and not line.startswith(" "):
                    arr = line.split(",")
                    name = arr[pokemon_column]
                    pool = arr[pool_column]
                    self.dex[pool].append(name)
            except Exception as error:
                logging.error(
                    "".join(
                        traceback.format_exception(
                            type(error), error, error.__traceback__
                        )
                    )
                )
                logging.warning("skipping line in Pokemon.load_dex()")

    def throw_ball(self, tiers: typing.List[str]) -> typing.List[str]:
        pokeymans_list = []

        for tier in tiers:
            pokeymans_list.extend(self.dex[tier])

        result = []

        for i in range(3):
            new_pokeyman = random.choice(pokeymans_list)
            result.append(new_pokeyman)
            pokeymans_list.remove(new_pokeyman)

        return result

    async def pokemon_image(self, pokemon_name: str) -> Image.Image:
        pokemon_name = pokemon_name.lower()
        img = None

        # todo jonas - move all Image.open in executor

        # todo jonas - only use one image provider?

        try:
            return Image.open(self.path / "pokemon_imgs" / f"{pokemon_name}.png")

        except FileNotFoundError:
            logging.warning(f"no local image for {pokemon_name}")

            try:
                async with self.bot.session.get(
                    f"https://img.pokemondb.net/sprites/bank/normal/{pokemon_name}.png"
                ) as response:
                    bt = io.BytesIO(await response.read())
                    img = Image.open(bt)
            except Exception as error:
                logging.error(
                    "".join(
                        traceback.format_exception(
                            type(error), error, error.__traceback__
                        )
                    )
                )
                logging.warning("pokemondb error, falling back to pokeapi.co")
                async with self.bot.session.get(
                    f"https://pokeapi.co/api/v2/pokemon/{pokemon_name}"
                ) as response:
                    js = await response.json()
                    sprite_url = js["sprites"]["front_default"]

                    async with self.bot.session.get(sprite_url) as rsp:
                        byt = io.BytesIO(await rsp.read())
                        img = Image.open(byt)

            if img:
                img.save(self.path / "pokemon_imgs" / f"{pokemon_name}.png")

        return img

    async def combined_image(self, pokemon_list: typing.List[str]) -> discord.File:
        images = [await self.pokemon_image(pkmn) for pkmn in pokemon_list]
        return await self.bot.loop.run_in_executor(None, self._combined_image, images)

    def _combined_image(self, images: typing.List[Image.Image]) -> discord.File:
        result: Image.Image = Image.open(self.path / "background.png")

        indent = 0
        for pkmn in images:
            # todo jonas - pre convert all images to RGBA
            result.paste(
                pkmn, (indent, result.height - pkmn.size[1]), pkmn.convert("RGBA")
            )
            indent += pkmn.size[0]
            pkmn.close()

        buffer = io.BytesIO()
        result.save(buffer, "png")
        buffer.seek(0)
        result.close()
        return discord.File(buffer, filename="pokemon.png")

    @commands.group(
        name="pokémon",
        aliases=["pokemon", "pk"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def pokemon(self, ctx):
        """What is this?"""
        embed = text.SafeEmbed(
            description="Catch em all! This will be filled with useful information soon.\n\nThese Pokémon commands "
            "were made by Pep and integrated into the Democraciv Discord Bot by Jonas."
        )
        embed.set_author(icon_url=self.bot.mk.NATION_ICON_URL, name="The Hatima Region")
        await ctx.send(embed=embed)

    async def _get_poke_info(self, pokemon: str):
        pokemon = pokemon.lower()
        _types = []

        try:
            async with self.bot.session.get(
                f"https://pokeapi.co/api/v2/pokemon/{pokemon}"
            ) as response:
                js = await response.json()

                for _typ in js["types"]:
                    _types.append(_typ["type"]["name"].title())

                async with self.bot.session.get(js["species"]["url"]) as rsp:
                    jss = await rsp.json()

                    is_legendary = jss["is_legendary"]
                    is_mythical = jss["is_mythical"]

                    first_english_text = ""

                    for flavour in jss["flavor_text_entries"]:
                        if flavour["language"]["name"] == "en":
                            first_english_text = flavour["flavor_text"]
                            break

                _types = ", ".join(_types)

            return PokeInfo(is_legendary, is_mythical, _types, first_english_text)
        except (aiohttp.ClientError, KeyError):
            return None

    @pokemon.command()
    async def throw(self, ctx, ball: converter.Fuzzy[PokeballConverter]):
        """Throw a Pokéball and catch some randomly spawning Pokémon"""

        async with ctx.typing():
            result = self.throw_ball(self.pokeball_lookup[ball])  # type: ignore
            file = await self.combined_image(result)

        embed = text.SafeEmbed()
        embed.set_author(
            name="Tall Grass in the Hatima Region", icon_url=self.bot.mk.NATION_ICON_URL
        )
        embed.set_image(url="attachment://pokemon.png")
        embed.set_footer(text=ball)

        poke_info = {}

        for pkmn in result:
            cached_info = self._cached_poke_info.get(pkmn, None)

            if not cached_info:
                info = await self._get_poke_info(pkmn)
                self._cached_poke_info[pkmn] = info
                logging.info(
                    f"PokeInfo: Caching {pkmn}. Size Cache: {len(self._cached_poke_info)}"
                )
                poke_info[pkmn] = info
            else:
                logging.info(f"PokeInfo: Cache hit for {pkmn}")
                poke_info[pkmn] = cached_info

        len_text = min([len(pk.description) if pk else 50 for pk in poke_info.values()])

        for poke, info in poke_info.items():
            if info:
                desc = textwrap.shorten(
                    info.description, width=len_text, placeholder="..."
                )
                fmt = (
                    f"{desc}\n\n`Type`: {info.types}\n`Legendary`: "
                    f"{'Yes' if info.is_legendary else 'No'}\n`Mythical`: "
                    f"{'Yes' if info.is_mythical else 'No'}"
                )
            else:
                fmt = "*Couldn't get Pokémon Info*"

            embed.add_field(name=poke, value=fmt)

        await ctx.reply(embed=embed, file=file)

    async def _get_attachment(self, ctx, question: str) -> typing.Optional[bytes]:
        attachment_bytes = None

        if not ctx.message.attachments:
            attachment_url = await ctx.input(
                question,
                image_allowed=True,
            )

            if not attachment_url:
                return

            async with self.bot.session.get(attachment_url) as response:
                attachment_bytes = await response.read()

        else:
            attachment_bytes = await ctx.message.attachments[0].read()

        return attachment_bytes

    @pokemon.group(
        aliases=["pokédex", "dex"], case_insensitive=True, invoke_without_command=True
    )
    async def pokedex(self, ctx):
        """See what Pokémon and tiers there are in the Pokédex"""

        try:
            role = self.bot.get_democraciv_role(mk.DemocracivRole.POKECIV_BOT_MANAGER)
            role = role.name
        except exceptions.RoleNotFoundError:
            role = "Pokéciv Bot Manager"

        embed = text.SafeEmbed(
            description=f"In order to update the Pokédex, people with the {role} role "
            f"can use my `{config.BOT_PREFIX}pk dex update` command."
        )
        embed.set_author(
            name="The Pokédex of the Hatima Region",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        for tier, pokemom in self.dex.items():
            embed.add_field(name=tier, value=", ".join(pokemom) or "-", inline=False)

        await ctx.send(embed=embed)

    @pokedex.command()
    @checks.has_democraciv_role(mk.DemocracivRole.POKECIV_BOT_MANAGER)
    async def update(self, ctx: context.CustomContext):
        """Update the Pokédex by uploading a .csv file"""
        attachment_bytes = await self._get_attachment(
            ctx,
            f"{config.USER_INTERACTION_REQUIRED} Reply with the updated Pokédex by "
            f"uploading and sending the .csv file as here.",
        )

        async with aiofiles.open(self.path / "dex.csv", "wb") as f:
            await f.write(attachment_bytes)

        for _list in self.dex:
            self.dex[_list].clear()

        self.load_dex()
        await ctx.send(f"{config.YES} The pokédex was updated successfully.")

    @pokemon.command()
    @checks.has_democraciv_role(mk.DemocracivRole.POKECIV_BOT_MANAGER)
    async def updateimage(self, ctx, *, pokemon):
        """Update the image of a single Pokémon by uploading a .png file"""

        attachment_bytes = await self._get_attachment(
            ctx,
            f"{config.USER_INTERACTION_REQUIRED} Reply with the updated image by "
            f"uploading and sending the .png file as here.",
        )

        async with aiofiles.open(
            self.path / "pokemon_imgs" / f"{pokemon.lower()}.png", "wb"
        ) as f:
            await f.write(attachment_bytes)

        await ctx.send(
            f"{config.YES} The image for `{pokemon}` was updated successfully."
        )

    def _simulate_ball_throw(self, ball: str, times: int):
        throws = []

        for _ in range(times):
            throws.append(self.throw_ball(self.pokeball_lookup[ball]))  # type: ignore

        flat_throws = itertools.chain.from_iterable(throws)
        return collections.Counter(flat_throws).most_common()

    @pokemon.command()
    async def simulate(
        self, ctx, ball: typing.Optional[PokeballConverter] = None, times=1000
    ):
        """Repeatedly simulate the throwing of pokéballs"""

        if times < 1 or times >= 1000000:
            return await ctx.send(
                f"{config.NO} You can only simulate between 1 and 1000000 throws."
            )

        fmt = []

        if ball:
            author = f"Simulated Throw of {times} {ball.title()}s"  # type: ignore
            counted = self._simulate_ball_throw(ball, times)  # type: ignore

            for mon, tries in counted:
                fmt.append(f"{mon}: {tries}x")

        else:
            author = f"{times} Simulated Throws of each Ball"  # type: ignore

            for ball in self.pokeball_lookup.keys():
                counted = self._simulate_ball_throw(ball, times)

                fmt.append(f"__**{ball}**__")

                for mon, tries in counted:
                    fmt.append(f"{mon}: {tries}x")

                fmt.append("\n")

        pages = paginator.SimplePages(
            entries=fmt, author=author, icon=self.bot.mk.NATION_ICON_URL
        )
        await pages.start(ctx)


def setup(bot):
    bot.add_cog(Pokemon(bot))
