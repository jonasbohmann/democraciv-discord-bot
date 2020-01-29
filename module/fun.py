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
from util.paginator import Pages


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

    @staticmethod
    def get_spotify_connection(member: discord.Member):
        if len(member.activities) > 0:
            for act in member.activities:
                if act.type == discord.ActivityType.listening:
                    return act
        return None

    @commands.command(name='spotify')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def spotify(self, ctx, *, member: discord.Member = None):
        """See what someone is listening to

            Usage:
             `-spotify`
             `-spotify @DerJonas`
             `-spotify DerJonas`
             `-spotify DerJonas#8109`
        """

        if member is None:
            member = ctx.author

        member_spotify = self.get_spotify_connection(member)

        if member_spotify is None:
            return await ctx.send(":x: That person is either not listening to something on Spotify right now, "
                                  "or I just can't detect it.")

        pretty_artists = ', '.join(member_spotify.artists)

        embed = self.bot.embeds.embed_builder(title=f"<:spotify:665703093425537046>  {member.name} on Spotify",
                                              description="", has_footer=False, colour=0x36393E)
        embed.add_field(name="Song", value=f"[{member_spotify.title}](https://open.spotify.com/"
                                           f"track/{member_spotify.track_id})", inline=False)
        embed.add_field(name="Artist(s)", value=pretty_artists, inline=True)
        embed.add_field(name="Album", value=member_spotify.album, inline=True)
        embed.set_thumbnail(url=member_spotify.album_cover_url)
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

    @commands.command()
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def lyrics(self, ctx, *, query: str = None):
        """Find lyrics for a song. Leave 'query' blank to get the lyrics for
        the song you're listening to on Spotify right now"""

        if query is None:
            now_playing = self.get_spotify_connection(ctx.author)

            if now_playing is None:
                return await ctx.send(":x: You either have to give me something to search for or listen to a song"
                                      " on Spotify!")

            query = f"{now_playing.title} {' '.join(now_playing.artists)}"

        if len(query) < 3:
            return await ctx.send(":x: The query has to be more than 3 characters!")

        async with ctx.typing():
            async with self.bot.session.get(f"https://some-random-api.ml/lyrics?title={query}") as response:
                lyrics = await response.json()

        try:

            lyrics['lyrics'] = lyrics['lyrics'].replace("[", "**[").replace("]", "]**")

            if len(lyrics['lyrics']) <= 2048:
                embed = self.bot.embeds.embed_builder(title=f"{lyrics['title']} by {lyrics['author']}",
                                                      description=lyrics['lyrics'], colour=0x36393E)
                embed.url = lyrics['links']['genius']
                embed.set_thumbnail(url=lyrics['thumbnail']['genius'])
                return await ctx.send(embed=embed)

            pages = Pages(ctx=ctx, entries=lyrics['lyrics'].splitlines(), show_entry_count=False,
                          title=f"{lyrics['title']} by {lyrics['author']}", show_index=False,
                          title_url=lyrics['links']['genius'], thumbnail=lyrics['thumbnail']['genius'], per_page=20,
                          colour=0x36393E, show_amount_of_pages=True)
        except KeyError:
            return await ctx.send(f":x: Couldn't find anything that matches `{query}`.")

        await pages.paginate()

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
            choices = list(arg)
            choices.pop(0)
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
