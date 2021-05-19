import asyncpg
import discord

import bot.utils.exceptions as exceptions

from bot.config import config
from bot.utils import text, context, converter
from bot.utils.converter import Selfrole, Fuzzy
from discord.ext import commands


class Selfroles(context.CustomCog):
    """Self-assignable roles for this server."""

    async def _list_all_roles(self, ctx):
        role_list = await self.bot.db.fetch("SELECT role_id FROM selfrole WHERE guild_id = $1", ctx.guild.id)

        embed_message = []

        for role in role_list:
            role_object = ctx.guild.get_role(role["role_id"])
            if role_object is not None:
                embed_message.append(role_object.name)

        if not embed_message:
            embed_message = ["This server has no selfroles yet."]

        embed = text.SafeEmbed(description="\n".join(embed_message))
        embed.set_author(
            name=f"Selfroles in {ctx.guild.name}",
            icon_url=ctx.guild.icon_url_as(static_format="png"),
        )
        embed.set_footer(text=f"In order to add or remove a role from you, use: {config.BOT_PREFIX}role <role>")
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

        if selfrole.role not in ctx.message.author.roles:
            try:
                await ctx.message.author.add_roles(selfrole.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, selfrole.role.name)

            await ctx.send(f"{config.YES} {selfrole.join_message}")

        elif selfrole.role in ctx.message.author.roles:
            try:
                await ctx.message.author.remove_roles(selfrole.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.REMOVE_ROLE, selfrole.role.name)

            await ctx.send(f"{config.YES} The `{selfrole.role.name}` role was removed from you.")

    @roles.command(name="add", aliases=["create", "make"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def addrole(self, ctx: context.CustomContext):
        """Add a role to this server's `{PREFIX}roles` list"""

        await ctx.send(f"{config.USER_INTERACTION_REQUIRED} Reply with the name of the role you want to create.")

        role_name = await ctx.converted_input(converter=converter.CaseInsensitiveRole)

        if isinstance(role_name, str):
            await ctx.send(f"{config.YES} I will **create a new role** on this server named `{role_name}` for this.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            discord_role = role_name

            await ctx.send(f"{config.YES} I'll use the **pre-existing role** named `{discord_role.name}` for this.")

        role_join_message = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with a short message the user should see when they get the role."
        )

        try:
            await self.bot.db.execute(
                "INSERT INTO selfrole (guild_id, role_id, join_message) VALUES ($1, $2, $3) "
                "ON CONFLICT (guild_id, role_id) DO UPDATE SET join_message = $3",
                ctx.guild.id,
                discord_role.id,
                role_join_message,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(f"{config.NO} `{discord_role.name}` is already a selfrole on this server.")

        await ctx.send(f"{config.YES} `{discord_role.name}` was added as a selfrole.")

    @roles.command(name="edit", aliases=["change"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def editrole(self, ctx: context.CustomContext, *, role: Fuzzy[Selfrole]):
        """Edit the join message of a selfrole

        **Usage**
         `{PREFIX}{COMMAND} <role>`
        """

        new_join_message = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the new join message for `{role.role.name}`."
            f"\n{config.HINT} The current join message is: `{role.join_message}`"
        )

        await self.bot.db.execute(
            "UPDATE selfrole SET join_message = $1 WHERE role_id = $2", new_join_message, role.role.id
        )

        await ctx.send(f"{config.YES} The join message for `{role.role.name}` was updated.")

    @roles.command(name="delete", aliases=["remove"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def deleterole(self, ctx: context.CustomContext, *, role: str):
        """Remove a selfrole from this server's `{PREFIX}roles` list"""

        try:
            selfrole = await Fuzzy[Selfrole].convert(ctx, role)
        except exceptions.NotFoundError:
            return await ctx.send(f"{config.NO} This server has no selfrole that matches `{role}`.")

        if selfrole.role:
            hard_delete = await ctx.confirm(
                f"{config.USER_INTERACTION_REQUIRED} Should I also delete the "
                f"Discord role `{selfrole.role.name}`, instead of just removing the "
                f"selfrole from the list of selfroles in `{config.BOT_PREFIX}roles`?"
            )
        else:
            hard_delete = False

        await self.bot.db.execute(
            "DELETE FROM selfrole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            selfrole.role.id,
        )

        if hard_delete:
            try:
                await selfrole.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.DELETE_ROLE, detail=selfrole.role.name)

            return await ctx.send(f"{config.YES} The `{role}` selfrole and its Discord role were deleted.")

        await ctx.send(
            f"{config.YES} The `{role}` selfrole was removed from the `{config.BOT_PREFIX}roles` list but "
            f"I did not delete its Discord role."
        )


def setup(bot):
    bot.add_cog(Selfroles(bot))
