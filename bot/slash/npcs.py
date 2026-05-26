import typing
import discord

from discord import app_commands
from discord.ext import commands

from bot.module.npcs import AccessToNPCConverter, AnyNPCConverter, NPCConverter
from bot.presenters import npc_forms, npcs as npc_presenter
from bot.services.npcs import NPCService
from bot.slash import context as slash_context, forms, transformers, ui
from bot.utils import paginator

OwnedNPCOption = app_commands.Transform[NPCConverter, transformers.NPCTransformer]
AnyNPCOption = app_commands.Transform[AnyNPCConverter, transformers.AnyNPCTransformer]
AccessNPCOption = app_commands.Transform[
    AccessToNPCConverter,
    transformers.AccessToNPCTransformer,
]

ChannelOption = typing.Union[discord.TextChannel, discord.CategoryChannel]


class NPCSlash(commands.Cog):
    npc = app_commands.Group(
        name="npc",
        description="Create and manage NPCs.",
    )

    npc_automatic = app_commands.Group(
        name="automatic",
        description="Manage automatic NPC mode.",
        parent=npc,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = NPCService(bot)

    @property
    def legacy_cog(self):
        return self.bot.get_cog("NPC")

    async def create_npc(
        self,
        ctx: slash_context.InteractionContext,
        *,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ):

        result = await self.service.create_npc(
            ctx,
            name=name,
            avatar_url=avatar_url,
            trigger_phrase=trigger_phrase,
        )
        await ctx.send(result.message)

    async def edit_npc(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: NPCConverter,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ):
        result = await self.service.edit_npc(
            npc=npc,
            name=name,
            avatar_url=avatar_url,
            trigger_phrase=trigger_phrase,
        )
        await ctx.send(result.message)

    async def update_access(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: NPCConverter,
        people,
        add: bool,
    ):
        result = await self.service.update_access(npc=npc, people=people, add=add)
        await ctx.send(result.message)

    async def update_automatic(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: AccessToNPCConverter,
        channels,
        add: bool,
    ):
        result = await self.service.update_automatic(
            ctx,
            npc=npc,
            channels=channels,
            add=add,
        )
        await ctx.send(result.message)

    async def _send_pages(self, ctx: slash_context.InteractionContext, result):
        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            empty_message=result.empty_message,
            per_page=result.per_page,
        )
        await pages.start(ctx)

    async def _handle_form_modal(
        self,
        interaction: discord.Interaction,
        form: npc_forms.NPCFormResult,
        *,
        npc: NPCConverter = None,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc edit" if npc else "npc create",
        )
        await ctx.defer()

        if npc:
            await self.edit_npc(
                ctx,
                npc=npc,
                name=form.name,
                avatar_url=form.avatar_url,
                trigger_phrase=form.trigger_phrase,
            )
        else:
            await self.create_npc(
                ctx,
                name=form.name,
                avatar_url=form.avatar_url,
                trigger_phrase=form.trigger_phrase,
            )

    async def _handle_people_modal(
        self,
        interaction: discord.Interaction,
        form: npc_forms.NPCFormResult,
        *,
        npc: NPCConverter,
        add: bool,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc share-bulk" if add else "npc unshare-bulk",
        )
        await ctx.defer()
        people = await forms.resolve_members(
            ctx,
            form.people_text,
            exclude_ids={npc.owner_id},
        )
        await self.update_access(ctx, npc=npc, people=people, add=add)

    async def _handle_automatic_modal(
        self,
        interaction: discord.Interaction,
        form: npc_forms.NPCFormResult,
        *,
        npc: AccessToNPCConverter,
        add: bool,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=(
                "npc automatic bulk-enable" if add else "npc automatic bulk-disable"
            ),
        )
        await ctx.defer()
        channels = await forms.resolve_channels(ctx, form.channels_text)
        await self.update_automatic(ctx, npc=npc, channels=channels, add=add)

    @npc.command(name="about", description="Explain NPCs.")
    async def about(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="npc about")
        await ctx.defer()
        embed = npc_presenter.build_about_embed(ctx)
        await ctx.send(embed=embed)

    @npc.command(name="list", description="List all NPCs someone has access to.")
    async def list_npcs(
        self,
        interaction: discord.Interaction,
        person: discord.Member = None,
    ):

        ctx = slash_context.from_interaction(interaction, command_name="npc list")
        await ctx.defer()
        member = person or ctx.author
        records = self.service.list_accessible_records(member)
        result = npc_presenter.build_npc_list_pages(ctx, member, records)
        await self._send_pages(ctx, result)

    @npc.command(name="show", description="Show details about one NPC.")
    async def show(self, interaction: discord.Interaction, npc: AnyNPCOption):
        ctx = slash_context.from_interaction(interaction, command_name="npc show")
        await ctx.defer()
        has_access = self.service.has_access(ctx.author, npc)
        is_owner = npc.owner_id == ctx.author.id
        allowed_people = await self.service.get_allowed_people(npc)
        automatic_channels = (
            await self.service.get_automatic_channels(ctx, npc) if has_access else []
        )
        embed = npc_presenter.build_info_embed(
            ctx,
            npc=npc,
            allowed_people=allowed_people,
            automatic_channels=automatic_channels,
            has_access=has_access,
            is_owner=is_owner,
        )
        await ctx.send(embed=embed)

    @npc.command(name="create", description="Create a new NPC.")
    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            npc_forms.NPCFormModal(on_submit_callback=self._handle_form_modal)
        )

    @npc.command(name="edit", description="Edit one of your NPCs.")
    async def edit(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        async def handle_form(
            modal_interaction: discord.Interaction,
            form: npc_forms.NPCFormResult,
        ):
            await self._handle_form_modal(modal_interaction, form, npc=npc)

        await interaction.response.send_modal(
            npc_forms.NPCFormModal(npc=npc, on_submit_callback=handle_form)
        )

    @npc.command(name="delete", description="Delete one of your NPCs.")
    async def delete(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        ctx = slash_context.from_interaction(interaction, command_name="npc delete")
        await ctx.defer()
        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {npc.name}",
            body=f"Delete NPC #{npc.id} `{npc.name}`?",
            confirm_label="Delete",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.delete_npc(ctx, npc=npc)
        await ctx.send(result.message)

    @npc.command(name="share", description="Allow one person to use your NPC.")
    @app_commands.guild_only()
    async def share(
        self,
        interaction: discord.Interaction,
        npc: OwnedNPCOption,
        person: discord.Member,
    ) -> None:
        ctx = slash_context.from_interaction(interaction, command_name="npc share")
        await ctx.defer()
        await self.update_access(ctx, npc=npc, people=[person], add=True)

    @npc.command(name="unshare", description="Remove one person's access to your NPC.")
    @app_commands.guild_only()
    async def unshare(
        self,
        interaction: discord.Interaction,
        npc: OwnedNPCOption,
        person: discord.Member,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="npc unshare")
        await ctx.defer()
        await self.update_access(ctx, npc=npc, people=[person], add=False)

    @npc.command(
        name="share-bulk", description="Allow multiple people to use your NPC."
    )
    @app_commands.guild_only()
    async def share_bulk(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        async def handle_people(
            modal_interaction: discord.Interaction,
            form: npc_forms.NPCFormResult,
        ):
            await self._handle_people_modal(modal_interaction, form, npc=npc, add=True)

        await interaction.response.send_modal(
            npc_forms.NPCPeopleModal(add=True, on_submit_callback=handle_people)
        )

    @npc.command(name="unshare-bulk", description="Remove access for multiple people.")
    @app_commands.guild_only()
    async def unshare_bulk(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        async def handle_people(
            modal_interaction: discord.Interaction,
            form: npc_forms.NPCFormResult,
        ):
            await self._handle_people_modal(modal_interaction, form, npc=npc, add=False)

        await interaction.response.send_modal(
            npc_forms.NPCPeopleModal(add=False, on_submit_callback=handle_people)
        )

    @npc_automatic.command(name="list", description="List your automatic NPC channels.")
    @app_commands.guild_only()
    async def automatic_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="npc automatic list"
        )
        await ctx.defer()
        records = await self.service.get_automatic_overview_records(ctx)
        display = npc_presenter.build_automatic_overview(
            ctx,
            records,
            self.legacy_cog._npc_cache,
        )

        if display.page is not None:
            return await self._send_pages(ctx, display.page)

        await ctx.send(embed=display.embed)

    @npc_automatic.command(
        name="enable", description="Enable automatic mode in one channel."
    )
    @app_commands.guild_only()
    async def automatic_enable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
        channel: ChannelOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic enable",
        )
        await ctx.defer()
        await self.update_automatic(ctx, npc=npc, channels=[channel], add=True)

    @npc_automatic.command(
        name="disable", description="Disable automatic mode in one channel."
    )
    @app_commands.guild_only()
    async def automatic_disable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
        channel: ChannelOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic disable",
        )
        await ctx.defer()
        await self.update_automatic(ctx, npc=npc, channels=[channel], add=False)

    @npc_automatic.command(
        name="clear", description="Disable automatic mode everywhere for one NPC."
    )
    @app_commands.guild_only()
    async def automatic_clear(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic clear",
        )
        await ctx.defer()
        result = await self.service.clear_automatic(ctx, npc=npc)
        await ctx.send(result.message)

    @npc_automatic.command(
        name="bulk-enable", description="Enable automatic mode in multiple channels."
    )
    @app_commands.guild_only()
    async def automatic_bulk_enable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        async def handle_automatic(
            modal_interaction: discord.Interaction,
            form: npc_forms.NPCFormResult,
        ):
            await self._handle_automatic_modal(
                modal_interaction, form, npc=npc, add=True
            )

        await interaction.response.send_modal(
            npc_forms.NPCAutomaticChannelsModal(
                add=True,
                on_submit_callback=handle_automatic,
            )
        )

    @npc_automatic.command(
        name="bulk-disable", description="Disable automatic mode in multiple channels."
    )
    @app_commands.guild_only()
    async def automatic_bulk_disable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        async def handle_automatic(
            modal_interaction: discord.Interaction,
            form: npc_forms.NPCFormResult,
        ):
            await self._handle_automatic_modal(
                modal_interaction, form, npc=npc, add=False
            )

        await interaction.response.send_modal(
            npc_forms.NPCAutomaticChannelsModal(
                add=False,
                on_submit_callback=handle_automatic,
            )
        )


async def setup(bot):
    await bot.add_cog(NPCSlash(bot))
