import asyncio
import config
import discord

from discord.ext import commands


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
        available_roles = config.getRoles(ctx.guild.id)
        embed_message = ""

        for role in available_roles:
            embed_message += f"{role}\n"

        if embed_message == "":
            embed_message = "This server has no roles."

        embed = self.bot.embeds.embed_builder(title="Roles",
                                              description="In order to add or remove a role from you, use `-role Role`")
        embed.add_field(name="Available Roles", value=embed_message)
        await ctx.send(embed=embed)

    @commands.command(name='role')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def role(self, ctx, *role: str):
        """Add or remove yourself to/from a role"""

        if not role:
            await ctx.send(":x: You have to tell me which role you want to join or leave!")
            return

        role = ' '.join(role)
        member = ctx.message.author
        discord_role = discord.utils.get(ctx.guild.roles, name=role)

        if not discord_role:
            await ctx.send(f":x: The '{role}' role doesn't exist on this server!")
            return
        else:
            if discord_role not in member.roles:
                try:
                    await member.add_roles(discord_role)
                except discord.Forbidden:
                    await ctx.send(f":x: Either the '{discord_role.name}' role is higher than my role, or I "
                                   f"don't have the Administrator permission to give you the role!")
                    return
                await ctx.send(config.getRoles(ctx.guild.id)[role])


            elif discord_role in member.roles:
                try:
                    await member.remove_roles(discord_role)
                except discord.Forbidden:
                    await ctx.send(f":x: Either the '{discord_role.name}' role is higher than my role, or I "
                                   f"don't have the Administrator permission to give you the role!")
                    return
                await ctx.send(f":white_check_mark: The '{role}' role was removed from you.")

    @commands.command(name='addrole')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def addRole(self, ctx):
        """Create a new role on this guild and add it to the bot's -roles list. Doesn't take any arguments."""

        await ctx.send(":information_source: Answer with the name of the role you want to create:\n\n:warning: "
                       "The name should not contain *multiple* spaces between two words!\nExample:"
                       " 'Test Role' works, but 'Test    Role' will not work.")
        try:
            role_name = await self.bot.wait_for('message', check=self.bot.wait_for_message_check(ctx), timeout=240)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        # Check if role already exists
        discord_role = discord.utils.get(ctx.guild.roles, name=role_name.content)
        if discord_role:
            await ctx.send(f":x: This guild already has a role named {role_name.content}! Delete the old role before"
                           f" you use `-addrole` to create a role named {role_name.content} again.")
            return

        await ctx.send(":information_source: Answer with a short message the user should see when they get the role: ")
        try:
            role_join_message = await self.bot.wait_for('message', check=self.bot.wait_for_message_check(ctx),
                                                        timeout=300)
        except asyncio.TimeoutError:
            await ctx.send(":x: Aborted.")

        error = await config.addRole(ctx.guild, role_join_message.content, role_name.content)

        if error:
            await ctx.send(f':x: {error}')
        else:
            await ctx.send(f':white_check_mark: Added the role "{role_name.content}" with the join message '
                           f'"{role_join_message.content}"!')

    @commands.command(name='deleterole')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_permissions(administrator=True)
    async def deleteRole(self, ctx, *role: str):
        """Delete a role from the guild and from the bot's -roles list."""
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
