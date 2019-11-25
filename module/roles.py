import asyncio
import config
import discord

import util.exceptions as exceptions

from discord.ext import commands


# -- roles.py | module.role --
#
# User role management.
#


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_roles(self, ctx):
        role_list = await self.bot.db.fetch("SELECT * FROM roles WHERE guild_id = $1", ctx.guild.id)
        role_dict = {}

        for record in role_list:
            role_dict[record['role']] = record['join_message']

        return role_dict

    @commands.command(name='roles')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def roles(self, ctx):
        """Get a list of self-assignable roles"""
        available_roles = await self.get_roles(ctx)
        embed_message = ""

        for role in available_roles:
            role_object = ctx.guild.get_role(role)
            if role_object is not None:
                embed_message += f"{role_object.name}\n"

        if embed_message == "":
            embed_message = "This server has no roles."

        embed = self.bot.embeds.embed_builder(title="Roles",
                                              description="In order to add or remove a role from you, use `-role Role`")
        embed.add_field(name="Available Roles", value=embed_message)
        await ctx.send(embed=embed)

    @commands.command(name='role')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def role(self, ctx, *, role: str):
        """Add or remove yourself to/from a role"""

        if not role:
            await ctx.send(":x: You have to tell me which role you want to join or leave!")
            return

        available_roles = await self.get_roles(ctx)

        member = ctx.message.author
        discord_role = discord.utils.get(ctx.guild.roles, name=role)

        if not discord_role:
            raise exceptions.RoleNotFoundError(role)

        else:
            if discord_role not in member.roles:
                if discord_role.id in available_roles:
                    try:
                        await member.add_roles(discord_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError("add_roles", discord_role.name)

                    await ctx.send(available_roles[discord_role.id])
                else:
                    await ctx.send(f":x: You are not allowed to give yourself this role! "
                                   f"If you're trying to join a political party, use `-join {discord_role.name}`")
            elif discord_role in member.roles:
                if discord_role.id in available_roles:
                    try:
                        await member.remove_roles(discord_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError("remove_roles", discord_role.name)

                    await ctx.send(f":white_check_mark: The '{discord_role.name}' role was removed from you.")
                else:
                    await ctx.send(f":x: You are not allowed remove this role from you! "
                                   f"If you're trying to leave a political party, use `-leave {discord_role.name}`")

    @commands.command(name='addrole')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addrole(self, ctx):
        """Create a new role on this guild and add it to the bot's -roles list. Doesn't take any arguments."""

        await ctx.send(":information_source: Answer with the name of the role you want to create:\n\n:warning: "
                       "The name should not contain *multiple* spaces between two words!\nExample:"
                       " 'Test Role' works, but 'Test    Role' will not work.")
        try:
            role_name = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                timeout=240)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        # Check if role already exists
        discord_role = discord.utils.get(ctx.guild.roles, name=role_name.content)
        if discord_role:
            await ctx.send(f":white_check_mark: I will use the **already existing role** named '{discord_role.name}'"
                           f" for this.")
        else:
            await ctx.send(f":white_check_mark: I will **create a new role** on this guild named '{role_name.content}'"
                           f" for this.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name.content)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(task="create_role", detail=role_name.content)

        await ctx.send(":information_source: Answer with a short message the user should see when they get the role: ")
        try:
            role_join_message = await self.bot.wait_for('message', check=self.bot.checks.wait_for_message_check(ctx),
                                                        timeout=300)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        status = await self.bot.db.execute("INSERT INTO roles (guild_id, role, join_message) VALUES ($1, $2, $3)",
                                           ctx.guild.id, discord_role.id, role_join_message.content)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Added the role "{role_name.content}" with the join message '
                           f'"{role_join_message.content}"!')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name='deleterole')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def deleterole(self, ctx, hard: bool, *, role: str):
        """Remove a role from the bot's `-roles` list.

        Usage:
         `-deleterole true <role>` will remove the role **and** delete its Discord role
         `-deleterole false <role>` will remove the role but not delete its Discord role

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
                        raise exceptions.ForbiddenError(task="delete_role", detail=role)

                status = await self.bot.db.execute("DELETE FROM roles WHERE guild_id = $2 AND role = $1",
                                                   discord_role.id, ctx.guild.id)

                if status == "DELETE 1":
                    if hard:
                        await ctx.send(f":white_check_mark: Removed the role '{role}' and deleted its Discord "
                                       f"role.")
                    else:
                        await ctx.send(f":white_check_mark: Removed the role '{role}' but did not delete its "
                                       f"Discord role.")

                else:
                    await ctx.send(":x: Unexpected database error occurred.")

    @deleterole.error
    async def deleteroleerror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'hard':
                await ctx.send(':x: You have to specify if I should hard-delete or not!\n\n**Usage**:\n'
                               '`-deleterole true <role>` will remove the role **and** delete its Discord role\n'
                               '`-deleterole false <role>` will remove the role but not delete its Discord role')

            if error.param.name == 'role':
                await ctx.send(':x: You have to give me the name of a role to delete!\n\n**Usage**:\n'
                               '`-deleterole true <role>` will remove the role **and** delete its Discord role\n'
                               '`-deleterole false <role>` will remove the role but not delete its Discord role')

        elif isinstance(error, commands.BadArgument):
            await ctx.send(':x: Error!\n\n**Usage**:\n'
                           '`-deleterole true <role>` will remove the role **and** delete its Discord role\n'
                           '`-deleterole false <role>` will remove the role but not delete its Discord role')


def setup(bot):
    bot.add_cog(Roles(bot))
