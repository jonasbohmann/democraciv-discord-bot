import discord

from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import parties as party_presenter, party_forms
from bot.services.parties import PartyService
from bot.slash import (
    checks as slash_checks,
    context as slash_context,
    forms,
    transformers,
    ui,
)
from bot.utils import converter

PartyOption = app_commands.Transform[
    converter.PoliticalParty,
    transformers.PoliticalPartyTransformer,
]


class PartiesSlash(commands.Cog):
    party = app_commands.Group(
        name="party",
        description="Show, join, and manage political parties.",
        guild_only=True,
    )
    party_alias = app_commands.Group(
        name="alias",
        description="Manage political party aliases.",
        parent=party,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = PartyService(bot)

    async def find_or_create_role(
        self,
        ctx: slash_context.InteractionContext,
        name: str,
    ) -> discord.Role:
        resolution = await self.service.find_or_create_role(ctx, name)
        return resolution.role

    async def create_party(
        self,
        ctx: slash_context.InteractionContext,
        *,
        role_name: str,
        leaders_text: str,
        invite: str,
        join_mode: str,
        merge: bool = False,
    ) -> converter.PoliticalParty:
        role = await self.find_or_create_role(ctx, role_name)
        leaders = await forms.resolve_members(ctx, leaders_text)
        leader_ids = [leader.id for leader in leaders] or [0]

        return await self.service.create_party(
            ctx,
            role=role,
            leader_ids=leader_ids,
            invite=invite,
            join_mode=join_mode,
            merge=merge,
        )

    async def edit_party(
        self,
        ctx: slash_context.InteractionContext,
        *,
        party: converter.PoliticalParty,
        new_name: str,
        leaders_text: str,
        invite: str,
        join_mode: str,
    ):
        leaders = await forms.resolve_members(ctx, leaders_text)
        leader_ids = [leader.id for leader in leaders] or [0]
        result = await self.service.edit_party(
            ctx,
            party=party,
            new_name=new_name,
            leader_ids=leader_ids,
            invite=invite,
            join_mode=join_mode,
        )
        await ctx.send(result.message)

    async def finish_merge(self, ctx, *, new_party, old_parties):
        result = await self.service.finish_merge(
            new_party=new_party,
            old_parties=old_parties,
        )
        await ctx.send(result.message)

    async def _handle_create_modal(
        self,
        interaction: discord.Interaction,
        form: party_forms.PartyFormResult,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="party create")
        await ctx.defer()

        party = await self.create_party(
            ctx,
            role_name=form.role_name,
            leaders_text=form.leaders_text,
            invite=form.invite,
            join_mode=form.join_mode,
            merge=False,
        )
        await ctx.send(
            f"{config.YES} `{party.role.name}` was added as a new Political Party.\n"
            f"{config.HINT} Add abbreviations and alternative spellings with `/party alias add`."
            f"\n{config.HINT} Remember to update https://reddit.com/r/democraciv/wiki accordingly."
        )

    async def _handle_edit_modal(
        self,
        interaction: discord.Interaction,
        form: party_forms.PartyFormResult,
        *,
        party: converter.PoliticalParty,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="party edit")
        await ctx.defer()
        await self.edit_party(
            ctx,
            party=party,
            new_name=form.role_name,
            leaders_text=form.leaders_text,
            invite=form.invite,
            join_mode=form.join_mode,
        )

    async def _handle_merge_modal(
        self,
        interaction: discord.Interaction,
        form: party_forms.PartyFormResult,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="party merge")
        await ctx.defer(ephemeral=True)
        parties = await forms.resolve_parties(ctx, form.parties_text)

        if len(parties) < 2:
            return await ctx.send(
                f"{config.NO} You have to merge at least two parties.",
                ephemeral=True,
            )

        pretty = ", ".join(f"`{party.role.name}`" for party in parties)
        confirmed = await ui.confirm(
            ctx,
            title="Merge Parties",
            body=f"Merge {pretty} into one party?",
            confirm_label="Continue",
        )

        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        new_party = await self.create_party(
            ctx,
            role_name=form.role_name,
            leaders_text=form.leaders_text,
            invite=form.invite,
            join_mode=form.join_mode,
            merge=True,
        )
        await self.finish_merge(ctx, new_party=new_party, old_parties=parties)

    async def party_entries(self):
        return await self.service.collect_parties_and_members(clean_missing=False)

    @party.command(name="list", description="List political parties by member count.")
    async def list_parties(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="party list")
        await ctx.defer()

        sorted_parties_and_members = await self.party_entries()
        embed = party_presenter.build_party_list_embed(ctx, sorted_parties_and_members)
        await ctx.send(embed=embed)

    @party.command(name="show", description="Show details about one political party.")
    async def show_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party show")
        await ctx.defer()

        if not party.role:
            return await ctx.send(f"{config.NO} That party's role no longer exists.")

        embed = await party_presenter.build_party_embed(ctx, party)
        await ctx.send(embed=embed)

    @party.command(name="join", description="Join a political party.")
    @slash_checks.is_citizen_if_multiciv()
    async def join_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party join")
        await ctx.defer()

        result = await self.service.join_party(ctx, party=party)
        await ctx.send(result.message)

        if result.request:
            for leader in result.request.leaders:
                try:
                    embed = party_presenter.build_join_request_embed(
                        ctx, result.request, leader
                    )
                    message = await leader.send(embed=embed)
                    await message.add_reaction(config.YES)
                    await message.add_reaction(config.NO)
                except discord.Forbidden:
                    continue

                await self.service.record_join_request_message(
                    request_id=result.request.request_id,
                    message_id=message.id,
                )

    @party.command(name="leave", description="Leave a political party.")
    @slash_checks.is_citizen_if_multiciv()
    async def leave_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party leave")
        await ctx.defer()

        result = await self.service.leave_party(ctx, party=party)
        await ctx.send(result.message)

    @party.command(name="create", description="Create a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def create_party_command(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            party_forms.PartyCreateModal(on_submit_callback=self._handle_create_modal)
        )

    @party.command(name="edit", description="Edit a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def edit_party_command(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
    ):
        async def handle_edit(
            modal_interaction: discord.Interaction,
            form: party_forms.PartyFormResult,
        ):
            await self._handle_edit_modal(modal_interaction, form, party=party)

        await interaction.response.send_modal(
            party_forms.PartyEditModal(
                party=party,
                on_submit_callback=handle_edit,
            )
        )

    @party.command(name="delete", description="Delete a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def delete_party(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
        also_delete_discord_role: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="party delete")
        await ctx.defer(ephemeral=True)

        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {party.role.name}",
            body=(
                f"Remove `{party.role.name}` from the list of parties"
                + (
                    " and delete their Discord role too?"
                    if also_delete_discord_role
                    else "?"
                )
            ),
            confirm_label="Delete",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.delete_party(
            party=party,
            delete_role_too=also_delete_discord_role,
        )
        await ctx.send(result.message)

    @party.command(name="merge", description="Merge multiple parties into one.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def merge_parties(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            party_forms.PartyMergeModal(on_submit_callback=self._handle_merge_modal)
        )

    @party_alias.command(name="add", description="Add an alias to a political party.")
    @slash_checks.moderation_or_nation_leader()
    async def add_alias(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
        alias: str,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias add"
        )
        await ctx.defer(ephemeral=True)
        result = await self.service.add_alias(party=party, alias=alias)
        await ctx.send(result.message, ephemeral=True)

    @party_alias.command(name="remove", description="Remove one political party alias.")
    @slash_checks.moderation_or_nation_leader()
    async def remove_alias(self, interaction: discord.Interaction, alias: str):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias remove"
        )
        await ctx.defer(ephemeral=True)
        result = await self.service.remove_alias(ctx, alias=alias)
        await ctx.send(result.message, ephemeral=True)

    @party_alias.command(name="clear", description="Remove all aliases from a party.")
    @slash_checks.moderation_or_nation_leader()
    async def clear_aliases(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias clear"
        )
        await ctx.defer(ephemeral=True)

        confirmed = await ui.confirm(
            ctx,
            title=f"Clear aliases for {party.role.name}",
            body=f"Delete all aliases of `{party.role.name}` except the party's own name?",
            confirm_label="Clear",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.clear_aliases(party=party)
        await ctx.send(result.message, ephemeral=True)

    @app_commands.command(
        name="parties", description="List political parties by member count."
    )
    @app_commands.guild_only()
    async def parties_alias(self, interaction: discord.Interaction):
        await self.list_parties.callback(self, interaction)


async def setup(bot):
    await bot.add_cog(PartiesSlash(bot))
