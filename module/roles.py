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

        embed = embed_builder(title="Roles", description="To get a role, use `-role Role`")
        embed.add_field(name="Available Roles", value=embed_message)
        await ctx.send(embed=embed)

    @commands.command(name='role')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def role(self, ctx, *role: str):
        """Add or remove yourself to/from a role"""

        if not role:
            await ctx.send(":x: You have to tell me which role you want to join or leave!")
            return

        role = string.capwords(' '.join(role))
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


def setup(bot):
    bot.add_cog(Roles(bot))
