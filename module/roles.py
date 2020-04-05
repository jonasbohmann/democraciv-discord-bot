import typing
import discord
import util.exceptions as exceptions

from config import config
from util.flow import Flow
from discord.ext import commands


class Roles(commands.Cog):
    """Self-assignable roles for this guild."""

    def __init__(self, bot):
        self.bot = bot

    async def get_roles(self, ctx) -> typing.Dict[int, str]:
        role_list = await self.bot.db.fetch("SELECT role_id, join_message FROM roles WHERE guild_id = $1",
                                            ctx.guild.id)
        role_dict = {}

        for record in role_list:
            role_dict[record['role_id']] = record['join_message']

        return role_dict

    async def get_role_from_db(self, ctx, role: str) -> typing.Optional[discord.Role]:
        role_id = await self.bot.db.fetchrow("SELECT role_id FROM roles WHERE guild_id = $1 AND role_name = $2",
                                             ctx.guild.id, role.lower())

        if role_id is None:
            return discord.utils.get(ctx.guild.roles, name=role)
        else:
            return ctx.guild.get_role(role_id['role_id'])

    @commands.group(name='role', aliases=['roles'], case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def roles(self, ctx, *, role: str = None):
        """List all roles or get/lose a role by specifying the role's name

        ****Usage:****
          `-role` List all available roles
          `-role <role>` Get/Lose a role
        """

        if role:
            await self.toggle_role(ctx, role)

        else:
            available_roles = await self.get_roles(ctx)
            embed_message = []

            for role in available_roles:
                role_object = ctx.guild.get_role(role)
                if role_object is not None:
                    embed_message.append(f"{role_object.name}")

            if not embed_message:
                embed_message = ["This guild has no roles yet."]

            embed = self.bot.embeds.embed_builder(title="Roles", description="In order to add or remove a role "
                                                                             "from you, use `-role Role`")
            embed.add_field(name="Available Roles", value='\n'.join(embed_message))
            await ctx.send(embed=embed)

    async def toggle_role(self, ctx, role: str):
        """Assigns or removes a role from someone"""

        available_roles = await self.get_roles(ctx)
        discord_role = await self.get_role_from_db(ctx, role)

        if not discord_role:
            raise exceptions.RoleNotFoundError(role)

        else:
            if discord_role not in ctx.message.author.roles:
                if discord_role.id in available_roles:
                    try:
                        await ctx.message.author.add_roles(discord_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, discord_role.name)

                    await ctx.send(available_roles[discord_role.id])
                else:
                    await ctx.send(f":x: You are not allowed to give yourself this role! "
                                   f"If you're trying to join a political party, use `-join {discord_role.name}`.")
            elif discord_role in ctx.message.author.roles:
                if discord_role.id in available_roles:
                    try:
                        await ctx.message.author.remove_roles(discord_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.REMOVE_ROLE, discord_role.name)

                    await ctx.send(f":white_check_mark: The `{discord_role.name}` role was removed from you.")
                else:
                    await ctx.send(f":x: You are not allowed remove this role from you! "
                                   f"If you're trying to leave a political party, use `-leave {discord_role.name}`.")

    @roles.command(name='add', aliases=['create, make'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def addrole(self, ctx):
        """Add a role to this guild's `-role` list"""

        await ctx.send(":information_source: Reply with the name of the role you want to create.")

        flow = Flow(self.bot, ctx)
        role_name = await flow.get_new_role(240)

        if isinstance(role_name, str):
            await ctx.send(
                f":white_check_mark: I will **create a new role** on this guild named `{role_name}`"
                f" for this.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            discord_role = role_name

            await ctx.send(
                f":white_check_mark: I'll use the **pre-existing role** named "
                f"`{discord_role.name}` for this.")

        await ctx.send(":information_source: Reply with a short message the user should see when they get the role.")

        role_join_message = await flow.get_text_input(300)

        if not role_join_message:
            return

        status = await self.bot.db.execute("INSERT INTO roles (guild_id, role_id, role_name, join_message) "
                                           "VALUES ($1, $2, $3, $4)", ctx.guild.id, discord_role.id,
                                           discord_role.name.lower(), role_join_message)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: The role `{discord_role.name}` was added.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @roles.command(name='delete', aliases=['remove'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def deleterole(self, ctx, hard: bool, *, role: str):
        """Remove a role from this guild's `-role` list

        **Usage:**
         `-role delete true <role>` will remove the role **and** delete its Discord role
         `-role delete false <role>` will remove the role but not delete its Discord role

        """
        discord_role = discord.utils.get(ctx.guild.roles, name=role)

        if discord_role is None:
            raise exceptions.RoleNotFoundError(role)

        else:
            if discord_role.id in await self.get_roles(ctx):
                if hard:
                    try:
                        await discord_role.delete()
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.DELETE_ROLE, detail=role)

                status = await self.bot.db.execute("DELETE FROM roles WHERE guild_id = $2 AND role_id = $1",
                                                   discord_role.id, ctx.guild.id)

                if status == "DELETE 1":
                    if hard:
                        await ctx.send(f":white_check_mark: The role `{role}` and its Discord "
                                       f"role was deleted.")
                    else:
                        await ctx.send(f":white_check_mark: Removed the role `{role}` but did **not** delete its "
                                       f"Discord role.")

                else:
                    await ctx.send(":x: Unexpected database error occurred.")


def setup(bot):
    bot.add_cog(Roles(bot))
