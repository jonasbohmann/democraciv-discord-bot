import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import forms, transformers, ui
from bot.utils import converter, exceptions, text

SelfroleOption = app_commands.Transform[
    converter.Selfrole,
    transformers.SelfroleTransformer,
]


class RoleCreateModal(forms.ErrorHandledModal):
    def __init__(self, cog: "SelfrolesSlash"):
        super().__init__(title="Create Selfrole")
        self.cog = cog
        self.role_name = forms.text_label(
            label="Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.join_message = forms.text_label(
            label="Join Message",
            description="Shown when someone joins this selfrole.",
            max_length=1000,
            style=discord.TextStyle.long,
        )
        self.add_item(self.role_name)
        self.add_item(self.join_message)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="role create")
        await ctx.defer()
        await self.cog.create_selfrole(
            ctx,
            role_name=self.role_name.component.value,
            join_message=self.join_message.component.value,
        )


class RoleEditModal(forms.ErrorHandledModal):
    def __init__(self, cog: "SelfrolesSlash", *, selfrole: converter.Selfrole):
        super().__init__(title=f"Edit {ui.shorten(selfrole.role.name, width=35)}")
        self.cog = cog
        self.selfrole = selfrole
        self.join_message = forms.text_label(
            label="Join Message",
            description="Shown when someone joins this selfrole.",
            default=selfrole.join_message,
            max_length=1000,
            style=discord.TextStyle.long,
        )
        self.add_item(self.join_message)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="role edit")
        await ctx.defer()
        await self.cog.edit_selfrole(
            ctx,
            selfrole=self.selfrole,
            join_message=self.join_message.component.value,
        )


class SelfrolesSlash(commands.Cog):
    role = app_commands.Group(
        name="role",
        description="List and manage self-assignable roles.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    async def create_selfrole(
        self,
        ctx: slash_context.InteractionContext,
        *,
        role_name: str,
        join_message: str,
    ):
        role_name = (role_name or "").strip()
        discord_role = discord.utils.find(
            lambda role: role.name.lower() == role_name.lower(),
            ctx.guild.roles,
        )

        if discord_role is None:
            if not role_name:
                return await ctx.send(
                    f"{config.NO} Provide an existing or new role name.",
                    ephemeral=True,
                )

            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.CREATE_ROLE,
                    role_name,
                )

        try:
            await self.bot.db.execute(
                "INSERT INTO selfrole (guild_id, role_id, join_message) VALUES ($1, $2, $3) "
                "ON CONFLICT (guild_id, role_id) DO UPDATE SET join_message = $3",
                ctx.guild.id,
                discord_role.id,
                join_message,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(
                f"{config.NO} `{discord_role.name}` is already a selfrole on this server.",
                ephemeral=True,
            )

        await ctx.send(f"{config.YES} `{discord_role.name}` was added as a selfrole.")

    async def edit_selfrole(
        self,
        ctx: slash_context.InteractionContext,
        *,
        selfrole: converter.Selfrole,
        join_message: str,
    ):
        await self.bot.db.execute(
            "UPDATE selfrole SET join_message = $1 WHERE guild_id = $2 AND role_id = $3",
            join_message,
            ctx.guild.id,
            selfrole.role.id,
        )
        await ctx.send(
            f"{config.YES} The join message for `{selfrole.role.name}` was updated."
        )

    @role.command(name="list", description="List all selfroles on this server.")
    async def list_roles(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="role list")
        await ctx.defer()

        role_list = await self.bot.db.fetch(
            "SELECT role_id FROM selfrole WHERE guild_id = $1",
            ctx.guild.id,
        )

        embed_message = [
            f"-# Looking for political parties? Try `/party list` and `/party join`.\n-# In order to add or remove a role from you, use `/role toggle`.\n"
        ]

        for role in role_list:
            role_object = ctx.guild.get_role(role["role_id"])
            if role_object is not None:
                embed_message.append(f"* {role_object.name}")

        if not embed_message:
            embed_message = ["This server has no selfroles yet."]

        embed = text.SafeEmbed(description="\n".join(embed_message))
        embed.set_author(
            name=f"Selfroles in {ctx.guild.name}",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
        )

        await ctx.send(embed=embed)

    @role.command(name="toggle", description="Join or leave one selfrole.")
    async def toggle_role(
        self,
        interaction: discord.Interaction,
        role: SelfroleOption,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role toggle")
        await ctx.defer()

        if not isinstance(ctx.author, discord.Member):
            raise app_commands.NoPrivateMessage()

        if role.role not in ctx.author.roles:
            try:
                await ctx.author.add_roles(role.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.ADD_ROLE,
                    role.role.name,
                )

            return await ctx.send(f"{config.YES} {role.join_message}")

        try:
            await ctx.author.remove_roles(role.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.REMOVE_ROLE,
                role.role.name,
            )

        await ctx.send(
            f"{config.YES} The `{role.role.name}` role was removed from you.",
        )

    @role.command(name="create", description="Add a selfrole to this server.")
    @slash_checks.has_guild_permissions(manage_roles=True)
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def create_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RoleCreateModal(self))

    @role.command(name="edit", description="Edit a selfrole join message.")
    @slash_checks.has_guild_permissions(manage_roles=True)
    async def edit_role(
        self,
        interaction: discord.Interaction,
        role: SelfroleOption,
    ):
        await interaction.response.send_modal(RoleEditModal(self, selfrole=role))

    @role.command(name="delete", description="Remove a selfrole from this server.")
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

        await self.bot.db.execute(
            "DELETE FROM selfrole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.role.id,
        )

        if also_delete_discord_role:
            role_name = role.role.name
            try:
                await role.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.DELETE_ROLE,
                    detail=role_name,
                )

            return await ctx.send(
                f"{config.YES} The `{role_name}` selfrole and its Discord role were deleted.",
            )

        await ctx.send(
            f"{config.YES} The `{role.role.name}` selfrole was removed.",
        )

    @app_commands.command(
        name="roles", description="List all selfroles on this server."
    )
    @app_commands.guild_only()
    async def roles_alias(self, interaction: discord.Interaction):
        await self.list_roles.callback(self, interaction)


async def setup(bot):
    await bot.add_cog(SelfrolesSlash(bot))
