import config
import discord

from discord.ext import commands


# -- role.py | module.role --
#
# User role management.
#


class Role:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='endgame')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def endgame(self, ctx):
        """Gain access to the Avengers: Endgame Spoilers channel."""
        member = ctx.message.author

        try:
            endgame_role = discord.utils.get(ctx.guild.roles,
                                         name="Avengers: Endgame Spoilers")
            endgame_channel = discord.utils.get(ctx.guild.text_channels, name='endgame-spoilers')
        except AttributeError:
            await ctx.send(":x: Couldn't find an 'Avengers: Endgame Spoilers' role and the #endgame-spoilers channel on "
                     "this server.")

        if endgame_role not in member.roles:
            await ctx.send(
                f':white_check_mark: You joined {endgame_channel.mention}!\n\nKeep in mind that talking about '
                f'Avengers: Endgame spoilers anywhere outside of {endgame_channel.mention} is against the rules and '
                f'a punishable offense.')
            await member.add_roles(endgame_role)

        elif endgame_role in member.roles:
            await ctx.send(f':white_check_mark: You left {endgame_channel.mention}!')
            await member.remove_roles(endgame_role)


def setup(bot):
    bot.add_cog(Role(bot))
