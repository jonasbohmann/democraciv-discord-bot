import typing

import bot.utils.exceptions as exceptions

from bot.config import config
from bot.presenters import selfroles as selfrole_presenter, selfrole_forms
from bot.services.selfroles import SelfroleService
from bot.utils import context, text
from bot.utils.converter import Selfrole, Fuzzy
from discord.ext import commands


class Selfroles(context.CustomCog):
    """Self-assignable roles for this server."""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = SelfroleService(bot)

    async def _list_all_roles(self, ctx):
        roles = await self.service.list_roles(ctx)
        embed = selfrole_presenter.build_selfrole_list_embed(ctx, roles)
        await ctx.send(embed=embed)

    @commands.group(
        name="role",
        aliases=["roles", "selfrole", "selfroles"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def roles(self, ctx, *, role: Fuzzy[Selfrole] = None):
        """List all selfroles on this server or toggle a selfrole by specifying the selfrole's name

        **Usage**
          `{PREFIX}{COMMAND}` List all available selfroles on this server
          `{PREFIX}{COMMAND} <role>` Toggle a selfrole
        """

        if role:
            await self._toggle_role(ctx, role)
        else:
            await self._list_all_roles(ctx)

    async def _toggle_role(self, ctx, selfrole: Selfrole):
        """Assigns or removes a role from someone"""

        result = await self.service.toggle_role(ctx, selfrole=selfrole)
        await ctx.send(result.message)

    async def _prompt_selfrole_form(
        self,
        ctx: context.CustomContext,
        *,
        modal_factory: typing.Callable[[], selfrole_forms.SelfroleModal],
        button_label: str,
        prompt: str,
    ) -> typing.Optional[selfrole_forms.SelfroleFormResult]:
        view = text.ModalPromptView(
            ctx,
            modal_factory=modal_factory,
            button_label=button_label,
            timeout=300,
        )
        return await view.prompt_message(prompt)

    @roles.command(name="add", aliases=["create", "make"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def addrole(self, ctx: context.CustomContext):
        """Add a role to this server's `{PREFIX}roles` list"""

        form = await self._prompt_selfrole_form(
            ctx,
            modal_factory=selfrole_forms.RoleCreateModal,
            button_label="Create Selfrole",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Fill out the selfrole details in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        resolution = await self.service.resolve_role(ctx, role=form.role_name)

        if resolution.created:
            await ctx.send(
                f"{config.YES} I will **create a new role** on this server named `{resolution.role.name}` for this."
            )
        else:
            await ctx.send(
                f"{config.YES} I'll use the **pre-existing role** named `{resolution.role.name}` for this."
            )

        result = await self.service.upsert_role(
            ctx, role=resolution.role, join_message=form.join_message
        )
        await ctx.send(result.message)

    @roles.command(name="edit", aliases=["change"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def editrole(self, ctx: context.CustomContext, *, role: Fuzzy[Selfrole]):
        """Edit the join message of a selfrole

        **Usage**
         `{PREFIX}{COMMAND} <role>`
        """

        form = await self._prompt_selfrole_form(
            ctx,
            modal_factory=lambda: selfrole_forms.RoleEditModal(selfrole=role),
            button_label="Edit Selfrole",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Update `{role.role.name}` in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        result = await self.service.edit_role(
            ctx, selfrole=role, join_message=form.join_message
        )
        await ctx.send(result.message)

    @roles.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def deleterole(self, ctx: context.CustomContext, *, role: str):
        """Remove a selfrole from this server's `{PREFIX}roles` list"""

        try:
            selfrole = await Fuzzy[Selfrole].convert(ctx, role)
        except exceptions.NotFoundError:
            return await ctx.send(
                f"{config.NO} This server has no selfrole that matches `{role}`."
            )

        if selfrole.role:
            hard_delete = await ctx.confirm(
                f"{config.USER_INTERACTION_REQUIRED} Should I also delete the "
                f"Discord role `{selfrole.role.name}`, instead of just removing the "
                f"selfrole from the list of selfroles in `{config.BOT_PREFIX}roles`?"
            )
        else:
            hard_delete = False

        result = await self.service.delete_role(
            ctx,
            selfrole=selfrole,
            hard_delete=hard_delete,
            display_name=role,
        )
        await ctx.send(result.message)


async def setup(bot):
    await bot.add_cog(Selfroles(bot))
