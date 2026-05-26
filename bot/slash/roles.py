import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import selfroles as selfrole_presenter, selfrole_forms
from bot.services.selfroles import SelfroleService
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import transformers, ui
from bot.utils import converter

SelfroleOption = app_commands.Transform[
    converter.Selfrole,
    transformers.SelfroleTransformer,
]


class SelfrolesSlash(commands.Cog):
    role = app_commands.Group(
        name="role",
        description="List and manage self-assignable roles.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = SelfroleService(bot)

    async def create_selfrole(
        self,
        ctx: slash_context.InteractionContext,
        *,
        role_name: str,
        join_message: str,
    ):
        result = await self.service.create_role(
            ctx, role_name=role_name, join_message=join_message
        )
        await ctx.send(result.message)

    async def edit_selfrole(
        self,
        ctx: slash_context.InteractionContext,
        *,
        selfrole: converter.Selfrole,
        join_message: str,
    ):
        result = await self.service.edit_role(
            ctx, selfrole=selfrole, join_message=join_message
        )
        await ctx.send(result.message)

    async def _handle_create_modal(
        self,
        interaction: discord.Interaction,
        form: selfrole_forms.SelfroleFormResult,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role create")
        await ctx.defer()
        await self.create_selfrole(
            ctx,
            role_name=form.role_name,
            join_message=form.join_message,
        )

    async def _handle_edit_modal(
        self,
        interaction: discord.Interaction,
        form: selfrole_forms.SelfroleFormResult,
        *,
        selfrole: converter.Selfrole,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role edit")
        await ctx.defer()
        await self.edit_selfrole(
            ctx,
            selfrole=selfrole,
            join_message=form.join_message,
        )

    @role.command(name="list", description="List all selfroles on this server.")
    @app_commands.guild_only()
    async def list_roles(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="role list")
        await ctx.defer()

        roles = await self.service.list_roles(ctx)
        embed = selfrole_presenter.build_selfrole_list_embed(ctx, roles)
        await ctx.send(embed=embed)

    @role.command(name="toggle", description="Join or leave one selfrole.")
    @app_commands.guild_only()
    async def toggle_role(
        self,
        interaction: discord.Interaction,
        role: SelfroleOption,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role toggle")
        await ctx.defer()

        if not isinstance(ctx.author, discord.Member):
            raise app_commands.NoPrivateMessage()

        result = await self.service.toggle_role(ctx, selfrole=role)
        await ctx.send(result.message)

    @role.command(name="create", description="Add a selfrole to this server.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(manage_roles=True)
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def create_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            selfrole_forms.RoleCreateModal(on_submit_callback=self._handle_create_modal)
        )

    @role.command(name="edit", description="Edit a selfrole join message.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(manage_roles=True)
    async def edit_role(
        self,
        interaction: discord.Interaction,
        role: SelfroleOption,
    ):
        async def handle_edit(
            modal_interaction: discord.Interaction,
            form: selfrole_forms.SelfroleFormResult,
        ):
            await self._handle_edit_modal(modal_interaction, form, selfrole=role)

        await interaction.response.send_modal(
            selfrole_forms.RoleEditModal(
                selfrole=role,
                on_submit_callback=handle_edit,
            )
        )

    @role.command(name="delete", description="Remove a selfrole from this server.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(manage_roles=True)
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def delete_role(
        self,
        interaction: discord.Interaction,
        role: SelfroleOption,
        also_delete_discord_role: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role delete")
        await ctx.defer()

        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {role.role.name}",
            body=(
                f"Remove `{role.role.name}` from the selfrole list"
                + (
                    " and delete the Discord role too?"
                    if also_delete_discord_role
                    else "?"
                )
            ),
            confirm_label="Delete",
        )

        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.delete_role(
            ctx,
            selfrole=role,
            hard_delete=also_delete_discord_role,
        )
        await ctx.send(result.message)

    @app_commands.command(
        name="roles", description="List all selfroles on this server."
    )
    @app_commands.guild_only()
    async def roles_alias(self, interaction: discord.Interaction):
        await self.list_roles.callback(self, interaction)


async def setup(bot):
    await bot.add_cog(SelfrolesSlash(bot))
