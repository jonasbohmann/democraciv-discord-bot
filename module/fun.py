import random
import discord
import operator

import util.exceptions as exceptions

from config import config
from discord.ext import commands


# -- fun.py | module.fun --
#
# Fun commands.
#


class Fun(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.cached_sorted_veterans_on_democraciv = []

    @staticmethod
    def get_member_join_position(user, members: list):
        try:
            joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))
            if None in joins:
                return None
            for key, elem in enumerate(joins):
                if elem == user:
                    return key + 1
            return None
        except Exception:
            return None

    @commands.command(name='say')
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, *, content: str):
        """Make the bot say something"""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MESSAGE_DELETE, content)

        await ctx.send(content)

    @commands.command(name='whois')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def whois(self, ctx, *, member: discord.Member = None):
        """Get detailed information about a member of this guild

            Usage:
             `-whois`
             `-whois @DerJonas`
             `-whois DerJonas`
             `-whois DerJonas#8109`
        """

        def _get_roles(roles):
            string = ''
            for role in roles[::-1]:
                if not role.is_default():
                    string += f'{role.mention}, '
            if string == '':
                return 'None'
            else:
                return string[:-2]

        # Thanks to:
        #   https:/github.com/Der-Eddy/discord_bot
        #   https:/github.com/Rapptz/RoboDanny/

        if member is None:
            member = ctx.author

        embed = self.bot.embeds.embed_builder(title="User Information", description="")
        embed.add_field(name="User", value=f"{member} {member.mention}", inline=False)
        embed.add_field(name="ID", value=str(member.id), inline=False)
        embed.add_field(name='Status', value=member.status, inline=True)
        embed.add_field(name='Administrator', value=str(member.guild_permissions.administrator), inline=True)
        embed.add_field(name='Avatar', value=f"[Link]({member.avatar_url})", inline=True)
        embed.add_field(name='Discord Registration',
                        value=f'{member.created_at.strftime("%B %d, %Y")}', inline=True)
        embed.add_field(name='Joined this Guild on',
                        value=f'{member.joined_at.strftime("%B %d, %Y")}', inline=True)
        embed.add_field(name='Join Position', value=self.get_member_join_position(member, ctx.guild.members)
                        , inline=True)
        embed.add_field(name='Roles', value=_get_roles(member.roles), inline=False)
        embed.set_thumbnail(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(name='veterans')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def veterans(self, ctx):
        """List the first 15 members who joined this guild"""

        # As veterans rarely change, use a cached version of sorted list if exists
        if len(self.cached_sorted_veterans_on_democraciv) >= 2 and ctx.guild.id == self.bot.democraciv_guild_object.id:
            sorted_first_15_members = self.cached_sorted_veterans_on_democraciv

        # If cache is empty OR ctx not on democraciv guild, calculate & sort again
        else:
            async with ctx.typing():
                guild_members_without_bots = []

                for member in ctx.guild.members:
                    if not member.bot:
                        guild_members_without_bots.append(member)

                first_15_members = []

                # Veterans can only be human, exclude bot accounts
                for member in guild_members_without_bots:

                    join_position = self.get_member_join_position(member, guild_members_without_bots)

                    if join_position <= 15:
                        first_15_members.append((member, join_position))

                # Sort by join position
                sorted_first_15_members = sorted(first_15_members, key=lambda x: x[1])

                # Save to cache if democraciv guild. This should only be done once in the bot's life cycle.
                if ctx.guild.id == self.bot.democraciv_guild_object.id:
                    self.cached_sorted_veterans_on_democraciv = sorted_first_15_members

        # Send veterans
        message = "These are the first 15 people who joined this guild.\nBot accounts are not counted.\n\n"

        for veteran in sorted_first_15_members:
            message += f"{veteran[1]}. {veteran[0].name}\n"

        embed = self.bot.embeds.embed_builder(title=f"Veterans of {ctx.guild.name}", description=message)
        await ctx.send(embed=embed)

    @commands.command(name='random')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def random(self, ctx, *arg):
        """Returns a random number or choice

            Usage:
              `-random` will choose a random number between 1-100
              `-random coin` will choose Heads or Tails
              `-random 6` will choose a random number between 1-6
              `-random choice England Rome` will choose between "England" and "Rome"
            """

        """
        MIT License

        Copyright (c) 2016 - 2018 Eduard Nikoleisen
        
        Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:
        
        The above copyright notice and this permission notice shall be included in all
        copies or substantial portions of the Software.
        
        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
        IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
        OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
        SOFTWARE.
        """

        if not arg:
            start = 1
            end = 100

        elif arg[0] == 'flip' or arg[0] == 'coin':
            coin = ['Heads', 'Tails']
            return await ctx.send(f':arrows_counterclockwise: {random.choice(coin)}')

        elif arg[0] == 'choice':
            choices = list(arg).pop(0)
            return await ctx.send(f':tada: The winner is: `{random.choice(choices)}`')

        elif len(arg) == 1:
            start = 1
            end = int(arg[0])
        else:
            start = 1
            end = 100

        await ctx.send(
            f'**:arrows_counterclockwise:** Random number ({start} - {end}): {random.randint(start, end)}')


def setup(bot):
    bot.add_cog(Fun(bot))
