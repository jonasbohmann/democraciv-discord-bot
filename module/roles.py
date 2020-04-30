import typing

import asyncpg
import discord
import util.exceptions as exceptions

from config import config
from util.converter import Selfrole
from util.flow import Flow
from discord.ext import commands


class Roles(commands.Cog, name="Selfroles"):
    """Self-assignable roles for this server."""

    def __init__(self, bot):
        self.bot = bot

    async def list_all_roles(self, ctx):
        role_list = await self.bot.db.fetch("SELECT role_id FROM roles WHERE guild_id = $1", ctx.guild.id)

        embed_message = []

        for role in role_list:
            role_object = ctx.guild.get_role(role['role_id'])
            if role_object is not None:
                embed_message.append(role_object.name)

        if not embed_message:
            embed_message = ["This server has no selfroles yet."]

        embed = self.bot.embeds.embed_builder(title=f"Selfroles in {ctx.guild.name}",
                                              description='\n'.join(embed_message),
                                              has_footer=False)
        embed.set_footer(text=f"In order to add or remove a role from you, use '{config.BOT_PREFIX}role <role>'")
        await ctx.send(embed=embed)

    @commands.group(name='role', aliases=['roles', 'selfrole', 'selfroles'], case_insensitive=True,
                    invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def roles(self, ctx, *, role: Selfrole = None):
        """List all roles on this server or get/lose a role by specifying the role's name

        **Usage:**
          `-role` List all available roles on this server
          `-role <role>` Get/Lose a role
        """

        if role:
            if role.role is None:
                return await ctx.send(":x: This selfrole was deleted.")

            await self.toggle_role(ctx, role)

        else:
            await self.list_all_roles(ctx)

    async def toggle_role(self, ctx, selfrole: Selfrole):
        """Assigns or removes a role from someone"""

        if selfrole.role not in ctx.message.author.roles:
            try:
                await ctx.message.author.add_roles(selfrole.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, selfrole.role.name)

            await ctx.send(selfrole.join_message)

        elif selfrole.role in ctx.message.author.roles:
            try:
                await ctx.message.author.remove_roles(selfrole.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.REMOVE_ROLE, selfrole.role.name)

            await ctx.send(f":white_check_mark: The `{selfrole.role.name}` role was removed from you.")

    @roles.command(name='add', aliases=['create, make'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx):
        """Add a role to this server's `-roles` list"""

        await ctx.send(":information_source: Reply with the name of the role you want to create.")

        flow = Flow(self.bot, ctx)
        role_name = await flow.get_new_role(240)

        if isinstance(role_name, str):
            await ctx.send(
                f":white_check_mark: I will **create a new role** on this server named `{role_name}` for this.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            discord_role = role_name

            await ctx.send(
                f":white_check_mark: I'll use the **pre-existing role** named `{discord_role.name}` for this.")

        await ctx.send(":information_source: Reply with a short message the user should see when they get the role.")

        role_join_message = await flow.get_text_input(300)

        if not role_join_message:
            return

        await self.bot.db.execute("INSERT INTO roles (guild_id, role_id, join_message) VALUES ($1, $2, $3) "
                                  "ON CONFLICT (guild_id, role_id) DO UPDATE set join_message = $3",
                                  ctx.guild.id, discord_role.id, role_join_message)

        await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a selfrole or its join message was '
                       f'updated in case the selfrole already existed.')

    @roles.command(name='delete', aliases=['remove'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def deleterole(self, ctx, hard: typing.Optional[bool] = False, *, role: str):
        """Remove a selfrole from this server's `-roles` list

        **Usage:**
         `-role delete true <role>` will remove the selfrole **and** delete its Discord role
         `-role delete false <role>` will remove the selfrole but not delete its Discord role

        """

        try:
            selfrole = await Selfrole.convert(ctx, role)
        except exceptions.NotFoundError:
            return await ctx.send(f":x: This server has no selfrole that matches `{role}`.")

        await self.bot.db.execute("DELETE FROM roles WHERE guild_id = $1 AND role_id = $2",
                                  ctx.guild.id, selfrole.role.id)

        if hard:
            if selfrole.role:
                try:
                    await selfrole.role.delete()
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(exceptions.ForbiddenTask.DELETE_ROLE, detail=selfrole.role.name)

            await ctx.send(f":white_check_mark: The `{role}` selfrole and its Discord role were deleted.")

        else:
            await ctx.send(f":white_check_mark: The `{role}` selfrole was removed from the `-roles` list but "
                           f"I did not delete its Discord role.")


def setup(bot):
    bot.add_cog(Roles(bot))
