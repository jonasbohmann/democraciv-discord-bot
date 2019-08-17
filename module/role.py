import config
import discord

from discord.ext import commands


# -- role.py | module.role --
#
# User role management.
#


class Role(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='archives')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def archives(self, ctx):
        """Gain access to the archived channels from past MKs"""
        member = ctx.message.author
        role = discord.utils.get(ctx.guild.roles, name="Archive")

        if role is None:
            await ctx.send(":x: Couldn't find the 'Archive' role!")
            return
        else:
            if role not in member.roles:
                await ctx.send(':white_check_mark: You joined the Archives!')
                await member.add_roles(role)

            elif role in member.roles:
                await ctx.send(':white_check_mark: You left the Archives!')
                await member.remove_roles(role)


def setup(bot):
    bot.add_cog(Role(bot))
