import textwrap
import typing

import discord
from discord import app_commands
from discord.ext import commands

from bot.slash import context as slash_context
from bot.utils import converter, exceptions, models


class TransformError(app_commands.AppCommandError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class _BaseConverterTransformer(app_commands.Transformer):
    converter_cls = None
    model_name = "value"
    command_name = "slash"

    async def transform(self, interaction: discord.Interaction, value: str):
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )

        try:
            return await self.converter_cls().convert(ctx, value)
        except exceptions.DemocracivBotException as error:
            raise TransformError(error.message) from error
        except commands.BadArgument as error:
            raise TransformError(str(error)) from error


class _BaseFuzzyTransformer(_BaseConverterTransformer):
    async def _recent(self, interaction: discord.Interaction):
        return []

    async def _matches(self, ctx, current: str):
        source = await self.converter_cls().get_fuzzy_source(ctx, current)
        return list(source)

    def _choice_value(self, match) -> str:
        return str(getattr(match, "id", getattr(match, "_id", str(match))))

    def _choice_name(self, match) -> str:
        name = getattr(match, "name", str(match))
        description = getattr(match, "_fuzzy_menu_description", None)

        if description:
            name = f"{description} - {name}"

        return textwrap.shorten(
            discord.utils.remove_markdown(name),
            width=100,
            placeholder="...",
        )

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> typing.List[app_commands.Choice[str]]:
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        current = (value or "").strip()

        try:
            matches = (
                await self._matches(ctx, current)
                if current
                else await self._recent(interaction)
            )
        except Exception:
            return []

        choices = []
        seen = set()

        for match in matches:
            value = self._choice_value(match)
            if value in seen:
                continue

            seen.add(value)

            choices.append(
                app_commands.Choice(
                    name=self._choice_name(match),
                    value=value,
                )
            )

            if len(choices) >= 25:
                break

        return choices


class BillTransformer(_BaseFuzzyTransformer):
    converter_cls = models.Bill
    model_name = "bill"
    command_name = "bill"

    async def _recent(self, interaction: discord.Interaction):
        records = await interaction.client.db.fetch(
            "SELECT id FROM bill ORDER BY id DESC LIMIT 10"
        )
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        return [await models.Bill.convert(ctx, record["id"]) for record in records]


class AwaitingExecutiveBillTransformer(BillTransformer):
    model_name = "bill awaiting Executive action"
    command_name = "executive"

    async def transform(self, interaction: discord.Interaction, value: str):
        bill = await super().transform(interaction, value)

        if bill.status.flag is not models.BillAwaitingExecutive.flag:
            raise TransformError(
                f"{bill.name} (#{bill.id}) is not awaiting Executive action."
            )

        return bill

    async def _recent(self, interaction: discord.Interaction):
        records = await interaction.client.db.fetch(
            "SELECT id FROM bill WHERE status = $1 ORDER BY id DESC LIMIT 25",
            models.BillAwaitingExecutive.flag.value,
        )
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        return [await models.Bill.convert(ctx, record["id"]) for record in records]

    async def _matches(self, ctx, current: str):
        records = []

        try:
            bill_id = int(current.removeprefix("#"))
        except ValueError:
            bill_id = None

        if bill_id is not None:
            records = await ctx.bot.db.fetch(
                "SELECT id FROM bill WHERE status = $1 AND id = $2",
                models.BillAwaitingExecutive.flag.value,
                bill_id,
            )

        if not records:
            records = await ctx.bot.db.fetch(
                "SELECT id FROM bill WHERE status = $2 AND "
                "(lower(name) % $1 OR lower(name) LIKE '%' || $1 || '%') "
                "ORDER BY similarity(lower(name), $1) DESC LIMIT 25",
                current.lower(),
                models.BillAwaitingExecutive.flag.value,
            )

        return [await models.Bill.convert(ctx, record["id"]) for record in records]


class LawTransformer(_BaseFuzzyTransformer):
    converter_cls = models.Law
    model_name = "law"
    command_name = "law"

    async def _recent(self, interaction: discord.Interaction):
        records = await interaction.client.db.fetch(
            "SELECT id FROM bill WHERE status = $1 ORDER BY id DESC LIMIT 10",
            models.BillIsLaw.flag.value,
        )
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        return [await models.Law.convert(ctx, record["id"]) for record in records]


class MotionTransformer(_BaseFuzzyTransformer):
    converter_cls = models.Motion
    model_name = "motion"
    command_name = "motion"

    async def _recent(self, interaction: discord.Interaction):
        records = await interaction.client.db.fetch(
            "SELECT id FROM motion ORDER BY id DESC LIMIT 10"
        )
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        return [await models.Motion.convert(ctx, record["id"]) for record in records]


class PoliticalPartyTransformer(_BaseFuzzyTransformer):
    converter_cls = converter.PoliticalParty
    model_name = "political party"
    command_name = "party"

    async def _recent(self, interaction: discord.Interaction):
        records = await interaction.client.db.fetch("SELECT id FROM party ORDER BY id")
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        parties = []

        for record in records:
            try:
                parties.append(
                    await converter.PoliticalParty.convert(ctx, record["id"])
                )
            except Exception:
                continue

        return parties[:25]


class SelfroleTransformer(_BaseFuzzyTransformer):
    converter_cls = converter.Selfrole
    model_name = "selfrole"
    command_name = "role"

    def _choice_value(self, match) -> str:
        return match.role.name

    async def _recent(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return []

        records = await interaction.client.db.fetch(
            "SELECT * FROM selfrole WHERE guild_id = $1", interaction.guild.id
        )
        return [
            converter.Selfrole(**dict(record), bot=interaction.client)
            for record in records
            if interaction.guild.get_role(record["role_id"]) is not None
        ][:25]


class TagTransformer(_BaseFuzzyTransformer):
    converter_cls = converter.Tag
    model_name = "tag"
    command_name = "tag"

    async def _matches(self, ctx, current: str):
        lowered = current.lower()
        guild_id = 0 if ctx.guild is None else ctx.guild.id
        records = await ctx.bot.db.fetch(
            """SELECT 
                 tag.id, tag.guild_id, tag.name, tag.title, tag.content, tag.global, 
                 tag.author, tag.uses, tag.is_embedded, look.alias
               FROM tag
               INNER JOIN tag_lookup look ON look.tag_id = tag.id
               WHERE
                 (look.alias % $1 OR lower(look.alias) LIKE '%' || $1 || '%')
               AND
                 (tag.global = true OR tag.guild_id = $2)
               ORDER BY similarity(lower(look.alias), $1) DESC LIMIT 25""",
            lowered,
            guild_id,
        )
        found = {}
        permission_filter = self.converter_cls()

        for record in records:
            aliases = await ctx.bot.db.fetch(
                "SELECT alias FROM tag_lookup WHERE tag_id = $1",
                record["id"],
            )
            collaborators = await ctx.bot.db.fetch(
                "SELECT user_id FROM tag_collaborator WHERE tag_id = $1",
                record["id"],
            )
            tag = converter.Tag(
                **record,
                bot=ctx.bot,
                aliases=[alias["alias"] for alias in aliases],
                invoked_with=record["alias"],
                collaborators=[
                    collaborator["user_id"] for collaborator in collaborators
                ],
            )

            if hasattr(
                permission_filter, "_is_allowed"
            ) and not permission_filter._is_allowed(ctx, tag):
                continue

            found[tag] = None

        return list(found.keys())

    def _choice_value(self, match) -> str:
        return match.invoked_with or match.name

    def _choice_name(self, match) -> str:
        scope = "Global" if match.is_global else "Local"
        return textwrap.shorten(
            discord.utils.remove_markdown(f"{scope} - {match.name}: {match.title}"),
            width=100,
            placeholder="...",
        )

    async def _recent(self, interaction: discord.Interaction):
        guild_id = 0 if interaction.guild is None else interaction.guild.id
        records = await interaction.client.db.fetch(
            "SELECT name FROM tag WHERE global = true OR guild_id = $1 "
            "ORDER BY uses DESC LIMIT 25",
            guild_id,
        )
        ctx = slash_context.from_interaction(
            interaction, command_name=self.command_name
        )
        tags = []

        for record in records:
            try:
                tags.append(await self.converter_cls().convert(ctx, record["name"]))
            except Exception:
                continue

        return tags


class CollaboratorTagTransformer(TagTransformer):
    converter_cls = converter.CollaboratorOfTag
    model_name = "tag you can edit"


class OwnedTagTransformer(TagTransformer):
    converter_cls = converter.OwnedTag
    model_name = "tag you own"


class BankUUIDTransformer(_BaseConverterTransformer):
    from bot.ext.democracivbank.bank import BankUUIDConverter as converter_cls

    model_name = "bank account"
    command_name = "bank"


try:
    from bot.module.npcs import AccessToNPCConverter, AnyNPCConverter, NPCConverter
except Exception:
    NPCConverter = None
    AnyNPCConverter = None
    AccessToNPCConverter = None


if NPCConverter is not None:

    class _BaseNPCTransformer(_BaseFuzzyTransformer):
        async def _recent_from_ids(self, interaction: discord.Interaction, npc_ids):
            npc_cog = interaction.client.get_cog("NPC")
            if npc_cog is None:
                return []

            ctx = slash_context.from_interaction(
                interaction,
                command_name=self.command_name,
            )
            npcs = []

            for npc_id in list(npc_ids)[:25]:
                try:
                    npcs.append(await self.converter_cls().convert(ctx, str(npc_id)))
                except Exception:
                    continue

            return npcs

    class NPCTransformer(_BaseFuzzyTransformer):
        converter_cls = NPCConverter
        model_name = "NPC"
        command_name = "npc"

        async def _recent(self, interaction: discord.Interaction):
            npc_cog = interaction.client.get_cog("NPC")
            if npc_cog is None:
                return []

            owned = [
                npc_id
                for npc_id in npc_cog._npc_access_cache[interaction.user.id]
                if npc_cog._npc_cache[npc_id]["owner_id"] == interaction.user.id
            ]
            return await _BaseNPCTransformer._recent_from_ids(
                self,
                interaction,
                sorted(owned),
            )

    class AnyNPCTransformer(_BaseFuzzyTransformer):
        converter_cls = AnyNPCConverter
        model_name = "NPC"
        command_name = "npc"

        async def _recent(self, interaction: discord.Interaction):
            npc_cog = interaction.client.get_cog("NPC")
            if npc_cog is None:
                return []

            return await _BaseNPCTransformer._recent_from_ids(
                self,
                interaction,
                sorted(npc_cog._npc_cache.keys()),
            )

    class AccessToNPCTransformer(_BaseFuzzyTransformer):
        converter_cls = AccessToNPCConverter
        model_name = "NPC you can use"
        command_name = "npc"

        async def _recent(self, interaction: discord.Interaction):
            npc_cog = interaction.client.get_cog("NPC")
            if npc_cog is None:
                return []

            return await _BaseNPCTransformer._recent_from_ids(
                self,
                interaction,
                sorted(npc_cog._npc_access_cache[interaction.user.id]),
            )
