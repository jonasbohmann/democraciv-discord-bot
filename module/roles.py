import string
import config
import discord

from discord.ext import commands
from util.embed import embed_builder


# -- roles.py | module.role --
#
# User role management.
#


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='roles')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def roles(self, ctx):
        """Get a list of self-assignable roles"""
        available_roles = config.getRoles()
        embed_message = ""

        for role in available_roles:
            embed_message += f"{role}\n"

        embed = embed_builder(title="Roles", description="In order to add or remove a role from you, use `-role Role`")
        embed.add_field(name="Available Roles", value=embed_message)
        await ctx.send(embed=embed)

    @commands.command(name='role')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def role(self, ctx, *role: str):
        """Add or remove yourself to/from a role"""

        if not role:
            await ctx.send(":x: You have to tell me which role you want to join or leave!")
            return

        role = ''.join(role)
        member = ctx.message.author
        discord_role = discord.utils.get(ctx.guild.roles, name=role)

        if not discord_role:
            await ctx.send(f":x: The '{role}' role doesn't exist on this server!")
            return
        else:
            if discord_role not in member.roles:
                await ctx.send(config.getRoles()[role])
                await member.add_roles(discord_role)

            elif discord_role in member.roles:
                await ctx.send(f":white_check_mark: The '{role}' role was removed from you.")
                await member.remove_roles(discord_role)

    @commands.command(name='addrole', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addRole(self, ctx):
        """Add a new role to the server"""
        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        await ctx.send(":information_source: Answer with the name of the role you want to add: \n\n:warning: The name "
                       "should not contain *multiple* spaces between any word!")
        role_name = await self.bot.wait_for('message', check=check, timeout=60.0)

        await ctx.send(":information_source: Answer with a short message the user should see when he gets the role: ")
        role_join_message = await self.bot.wait_for('message', check=check, timeout=60.0)

        error = await config.addRole(ctx.guild, role_join_message.content, role_name.content)

        if error:
            await ctx.send(f':x: {error}')
        else:
            await ctx.send(f':white_check_mark: Added the role "{role_name.content}" with the join message '
                           f'"{role_join_message.content}"!')

    @commands.command(name='deleterole', hidden=True)
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def deleteRole(self, ctx, *role: str):
        """Delete a role from the server"""
        if not role:
            await ctx.send(':x: You have to give me the name of a role to delete!')

        else:
            role = ' '.join(role)
            error = await config.deleteRole(ctx.guild, role)

            if error:
                await ctx.send(f':x: {error}')
            else:
                await ctx.send(f':white_check_mark: Deleted {role}!')


def setup(bot):
    bot.add_cog(Roles(bot))
