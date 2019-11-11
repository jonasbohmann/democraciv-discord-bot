import datetime
import operator

import config
import discord

from discord.ext import commands
from util.embed import embed_builder


# -- fun.py | module.fun --
#
# Fun commands.
#


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='say')
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, *, content: str):
        """Basically just Mod Abuse."""
        await ctx.message.delete()
        await ctx.send(content)

    @commands.command(name='whois')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def whois(self, ctx, member: str = None):
        """Get detailed information about a member of this guild

        Example:
        -------
        -whois
        -whois @DerJonas
        -whois DerJonas
        -whois DerJonas#8109
        """

        def _get_roles(roles):
            string = ''
            for role in roles[::-1]:
                if not role.is_default():
                    string += f'{role.mention}, '
            if string is '':
                return 'None'
            else:
                return string[:-2]

        def member_join_position(user, guild):
            try:
                joins = tuple(sorted(guild.members, key=operator.attrgetter("joined_at")))
                if None in joins:
                    return None
                for key, elem in enumerate(joins):
                    if elem == user:
                        return key + 1, len(joins)
                return None
            except Exception:
                return None

        # Thanks to:
        #   https:/github.com/Der-Eddy/discord_bot
        #   https:/github.com/Rapptz/RoboDanny/

        if member is None:
            member = ctx.author

        if member is not None:
            if type(member) is str:
                member = await commands.MemberConverter().convert(ctx, member)

            embed = embed_builder(title="User Information", description="")
            embed.add_field(name="User", value=f"{member} {member.mention}", inline=False)
            embed.add_field(name="ID", value=str(member.id), inline=False)
            embed.add_field(name='Status', value=member.status, inline=True)
            embed.add_field(name='Administrator', value=str(member.guild_permissions.administrator), inline=True)
            embed.add_field(name='Avatar', value=f"[Link]({member.avatar_url})", inline=True)
            embed.add_field(name='Discord Registration',
                            value=f'{member.created_at.strftime("%B %d, %Y")}', inline=True)
            embed.add_field(name='Joined this Guild on',
                            value=f'{member.joined_at.strftime("%B %d, %Y")}', inline=True)
            embed.add_field(name='Join Position', value=member_join_position(member, ctx.guild)[0], inline=True)
            embed.add_field(name='Roles', value=_get_roles(member.roles), inline=False)
            embed.set_thumbnail(url=member.avatar_url)
            await ctx.send(embed=embed)

        else:
            await ctx.send(':x: You have to give me a user as argument')


def setup(bot):
    bot.add_cog(Fun(bot))
