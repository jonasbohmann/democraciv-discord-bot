import io
import typing
import random
from urllib import parse
import discord
import operator
import datetime
import re

from bot.config import config, token
from discord.ext import commands

from bot.utils import context
from bot.utils.converter import CaseInsensitiveRole, PoliticalParty, CaseInsensitiveMember


class Misc(context.CustomCog, name="Miscellaneous"):
    """Miscellaneous commands. Some useful, some not."""

    def __init__(self, bot):
        super().__init__(bot)
        self.cached_sorted_veterans_on_democraciv = []

    @staticmethod
    def percentage_encode_url(link: str) -> str:
        if link.startswith('https://'):
            link = link[8:]
            url = parse.quote(link)
            return 'https://' + url
        else:
            return parse.quote(link)

    async def get_wikipedia_result_with_rest_api(self, query):

        # This uses the newer REST API that MediaWiki offers to query their site.
        #   advantages: newer, cleaner, faster, gets thumbnail + URL
        #   disadvantages: doesn't work with typos in attr: query
        #
        #   see: https://www.mediawiki.org/wiki/REST_API

        async with self.bot.session.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}") as response:
            if response.status == 200:
                return await response.json()
            else:
                return None

    async def get_wikipedia_suggested_articles(self, query):

        # This uses the older MediaWiki Action API to query their site.
        #
        #    Used as a fallback when self.get_wikipedia_result_with_rest_api() returns None, i.e. there's a typo in the
        #    query string. Returns suggested articles from a 'disambiguation' article
        #
        #   see: https://en.wikipedia.org/w/api.php

        async with self.bot.session.get(f"https://en.wikipedia.org/w/api.php?format=json&action=query&list=search"
                                        f"&srinfo=suggestion&srprop&srsearch={query}") as response:
            if response.status == 200:
                return await response.json()
            else:
                return None

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for an article on Wikipedia"""
        async with ctx.typing():  # Show typing status so that user knows that stuff is happening
            result = await self.get_wikipedia_result_with_rest_api(topic)

            if result is None or result['type'] == 'disambiguation':

                # Fall back to MediaWiki Action API and ask for article suggestions as there's probably a typo in
                # 'topic'
                suggested_pages = await self.get_wikipedia_suggested_articles(topic)

                try:
                    suggested_query_name = suggested_pages['query']['search'][0]['title']
                except (IndexError, KeyError):
                    return await ctx.send(":x: Wikipedia could not suggest me anything. "
                                          "Did you search for something in a language other than English?")

                # Retry with new suggested article title
                result = await self.get_wikipedia_result_with_rest_api(suggested_query_name)

                if result is None or not result:
                    return await ctx.send(f":x: Didn't find any article that's related to `{topic}`")

            _title = result['title']
            _summary = result['extract']
            _summary_in_2_sentences = ' '.join(re.split(r'(?<=[.?!])\s+', _summary, 2)[:-1])
            _url = result['content_urls']['desktop']['page']
            _thumbnail_url = ''

            try:
                _thumbnail_url = result['thumbnail']['source']
            except KeyError:
                pass

            embed = self.bot.embeds.embed_builder(title=f"{config.WIKIPEDIA_LOGO}  {_title}",
                                                  description=_summary_in_2_sentences, has_footer=False)

            embed.add_field(name='Link', value=self.percentage_encode_url(_url))

            if _thumbnail_url.startswith('https://'):
                embed.set_thumbnail(url=_thumbnail_url)
        await ctx.send(embed=embed)

    @commands.command(name='time', aliases=['clock', 'tz'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def time(self, ctx, *, zone: str):
        """Displays the current time of a specified timezone"""

        # If input is an abbreviation (UTC, EST etc.), make it uppercase for the TimeZoneDB request to work
        if len(zone) <= 5:
            zone = zone.upper()

        if not token.TIMEZONEDB_API_KEY:
            return await ctx.send(":x: Invalid TimeZoneDB API key.")

        query_base = f"https://api.timezonedb.com/v2.1/get-time-zone?key={token.TIMEZONEDB_API_KEY}&format=json&" \
                     f"by=zone&zone={zone}"

        async with ctx.typing():
            async with self.bot.session.get(query_base) as response:
                if response.status == 200:
                    time_response = await response.json()

            if time_response['status'] != "OK":
                return await ctx.send(f":x: `{zone}` is not a valid time zone or area code. "
                                      f"See the list of available time zones here: "
                                      f"<https://timezonedb.com/time-zones>")

            date = datetime.datetime.utcfromtimestamp(time_response['timestamp']).strftime("%A, %B %d %Y")
            us_time = datetime.datetime.utcfromtimestamp(time_response['timestamp']).strftime("%I:%M:%S %p")
            eu_time = datetime.datetime.utcfromtimestamp(time_response['timestamp']).strftime("%H:%M:%S")

            if zone.lower() == "utc":
                title = f":clock1:  Current Time in UTC"
            else:
                title = f":clock1:  Current Time in {time_response['abbreviation']}"

            embed = self.bot.embeds.embed_builder(title=title, description="")
            embed.add_field(name="Date", value=date, inline=False)
            embed.add_field(name="Time (12-Hour Clock)", value=us_time, inline=False)
            embed.add_field(name="Time (24-Hour Clock)", value=eu_time, inline=False)
            embed.set_footer(text="See 'timezonedb.com/time-zones' for a list of available time zones.")
            await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def original_join_position_listener(self, member):
        if member.guild.id != self.bot.dciv.id:
            return

        joined_on = member.joined_at or datetime.datetime.utcnow()

        await self.bot.db.execute("INSERT INTO original_join_dates (member, join_date) "
                                  "VALUES ($1, $2) ON CONFLICT DO NOTHING", member.id, joined_on)

    async def get_member_join_date(self, member: discord.Member) -> datetime.datetime:
        if member.guild.id == self.bot.dciv.id:
            original_date = await self.bot.db.fetchval("SELECT join_date FROM original_join_dates WHERE member = $1",
                                                       member.id)
            if original_date is not None:
                return original_date

        return member.joined_at

    async def get_member_join_position(self, user, members: list):
        if user.guild.id == self.bot.dciv.id:
            original_position = await self.bot.db.fetchval("SELECT join_position FROM original_join_dates "
                                                           "WHERE member = $1", user.id)
            all_members = await self.bot.db.fetchval("SELECT max(join_position) FROM original_join_dates")

            if original_position:
                return original_position, all_members

        joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))
        if None in joins:
            return None, None
        for key, elem in enumerate(joins):
            if elem == user:
                return key + 1, len(members)
        return None, None

    @commands.command(name='whois')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def whois(self, ctx, *,
                    member: typing.Union[discord.Member, CaseInsensitiveMember,
                                         discord.Role, CaseInsensitiveRole, PoliticalParty] = None):
        """Get detailed information about a member of this server

            **Example:**
             `-whois`
             `-whois Jonas - u/Jovanos`
             `-whois @DerJonas`
             `-whois DerJonas`
             `-whois deRjoNAS`
             `-whois DerJonas#8109`
        """

        def _get_roles(roles):
            string = ''
            for role in roles[::-1]:
                if not role.is_default():
                    string += f'{role.mention}, '
            if string == '':
                return '-'
            else:
                return string[:-2]

        # Thanks to:
        #   https://github.com/Der-Eddy/discord_bot
        #   https://github.com/Rapptz/RoboDanny/

        if isinstance(member, discord.Role):
            return await self.role_info(ctx, member)

        elif isinstance(member, PoliticalParty):
            return await self.role_info(ctx, member.role)

        member = member or ctx.author
        join_pos, max_members = await self.get_member_join_position(member, ctx.guild.members)

        embed = self.bot.embeds.embed_builder(title="Member Information")
        embed.add_field(name="Member", value=f"{member} {member.mention}", inline=False)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(name='Discord Registration',
                        value=f'{member.created_at.strftime("%B %d, %Y")}', inline=True)
        embed.add_field(name='Joined',
                        value=f'{(await self.get_member_join_date(member)).strftime("%B %d, %Y")}', inline=True)
        embed.add_field(name='Join Position', value=f"{join_pos}/{max_members}", inline=True)
        embed.add_field(name=f'Roles ({len(member.roles) - 1})', value=_get_roles(member.roles), inline=False)
        embed.set_thumbnail(url=member.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @whois.error
    async def whois_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            await ctx.send(":x: I could not find that person. Are they on this server?")

    @commands.command(name='avatar')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def avatar(self, ctx, *, member: typing.Union[discord.Member, CaseInsensitiveMember] = None):
        """Get a members's avatar in detail

        **Example:**
             `-avatar`
             `-avatar @DerJonas`
             `-avatar DerJonas`
             `-avatar DerJonas#8109`
        """

        member = member or ctx.author
        avatar_png: discord.Asset = member.avatar_url_as(static_format="png", size=4096)

        embed = self.bot.embeds.embed_builder(title=f"{member.display_name}'s Avatar",
                                              description=f"[Link]({avatar_png})", has_footer=False)
        embed.set_image(url=str(avatar_png))
        await ctx.send(embed=embed)

    @avatar.error
    async def avatar_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

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
    async def spotify(self, ctx, *, member: typing.Union[discord.Member, CaseInsensitiveMember] = None):
        """See what someone is listening to on Spotify

            **Example:**
             `-spotify`
             `-spotify @DerJonas`
             `-spotify DerJonas`
             `-spotify DerJonas#8109`
        """

        member = member or ctx.author
        member_spotify = self.get_spotify_connection(member)

        if member_spotify is None:
            return await ctx.send(":x: That person is either not listening to something on Spotify right now, "
                                  "or I just can't detect it.")

        pretty_artists = ', '.join(member_spotify.artists)

        embed = self.bot.embeds.embed_builder(title=f"{config.SPOTIFY_LOGO}  {member.name} on Spotify",
                                              description="", colour=0x2F3136,
                                              footer=f"Use {config.BOT_PREFIX}lyrics to get the lyrics for this song.")

        embed.add_field(name="Song", value=f"[{member_spotify.title}](https://open.spotify.com/"
                                           f"track/{member_spotify.track_id})", inline=False)
        embed.add_field(name="Artist(s)", value=pretty_artists, inline=True)
        embed.add_field(name="Album", value=member_spotify.album, inline=True)
        embed.set_thumbnail(url=member_spotify.album_cover_url)
        await ctx.send(embed=embed)

    @spotify.error
    async def spotify_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

    @commands.command(name='veterans')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def veterans(self, ctx):
        """List the first 15 members who joined this server"""

        sorted_first_15_members = []

        # As veterans rarely change, use a cached version of sorted list if exists
        if ctx.guild.id == self.bot.dciv.id:
            if len(self.cached_sorted_veterans_on_democraciv) >= 2:
                sorted_first_15_members = self.cached_sorted_veterans_on_democraciv
            else:
                vets = await self.bot.db.fetch("SELECT member, join_position FROM original_join_dates WHERE "
                                               "join_position <= 15 ORDER BY join_position")
                for record in vets:
                    member = self.bot.get_user(record['member'])
                    sorted_first_15_members.append((member, record['join_position']))

                self.cached_sorted_veterans_on_democraciv = sorted_first_15_members

        # If cache is empty OR ctx not on democraciv guild, calculate & sort again
        else:
            async with ctx.typing():
                guild_members_without_bots = [member for member in ctx.guild.members if not member.bot]

                first_15_members = []

                # Veterans can only be human, exclude bot accounts
                for member in guild_members_without_bots:
                    join_position, max_members = await self.get_member_join_position(member, guild_members_without_bots)

                    if join_position <= 15:
                        first_15_members.append((member, join_position))

                # Sort by join position
                sorted_first_15_members = sorted(first_15_members, key=lambda x: x[1])

                # Save to cache if democraciv guild. This should only be done once in the bot's life cycle.
                if ctx.guild.id == self.bot.dciv.id:
                    self.cached_sorted_veterans_on_democraciv = sorted_first_15_members

        # Send veterans
        message = "These are the first 15 people who joined this server.\nBot accounts are not counted.\n\n"

        for veteran in sorted_first_15_members:
            message += f"{veteran[1]}. {str(veteran[0])}\n"

        embed = self.bot.embeds.embed_builder(title=f"Veterans of {ctx.guild.name}", description=message)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def lyrics(self, ctx, *, query: str = None):
        """Find lyrics for a song

        **Usage:**
            `-lyrics` to get the lyrics to the song you're currently listening to on Spotify
            `-lyrics <query>` to search for lyrics that match your query
        """

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
                if response.status == 200:
                    lyrics = await response.json()
                else:
                    return await ctx.send(f":x: Couldn't find anything that matches `{query}`.")

        try:

            lyrics['lyrics'] = lyrics['lyrics'].replace("[", "**[").replace("]", "]**")

            if len(lyrics['lyrics']) <= 2048:
                embed = self.bot.embeds.embed_builder(title=f"{lyrics['title']} by {lyrics['author']}",
                                                      description=lyrics['lyrics'], colour=0x2F3136)
                embed.url = lyrics['links']['genius']
                embed.set_thumbnail(url=lyrics['thumbnail']['genius'])
                return await ctx.send(embed=embed)

            pages = AlternativePages(ctx=ctx, entries=lyrics['lyrics'].splitlines(), show_entry_count=False,
                                     title=f"{lyrics['title']} by {lyrics['author']}", show_index=False,
                                     title_url=lyrics['links']['genius'], thumbnail=lyrics['thumbnail']['genius'],
                                     per_page=20, colour=0x2F3136, show_amount_of_pages=True)
        except KeyError:
            return await ctx.send(f":x: Couldn't find anything that matches `{query}`.")

        await pages.paginate()

    @commands.command(name="tinyurl", aliases=["tiny"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def tinyurl(self, ctx, url: str):
        """Shorten a link with tinyurl"""
        if len(url) <= 3:
            await ctx.send(":x: That doesn't look like a valid URL.")
            return

        tiny_url = await self.bot.laws.post_to_tinyurl(url)

        if tiny_url is None:
            return await ctx.send(":x: tinyurl.com returned an error, try again in a few minutes.")

        await ctx.send(f"<{tiny_url}>")

    @commands.command(name='whohas', aliases=['roleinfo'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def whohas(self, ctx, *, role: typing.Union[discord.Role, CaseInsensitiveRole, PoliticalParty]):
        """Detailed information about a role"""

        if isinstance(role, PoliticalParty):
            role = role.role

        await self.role_info(ctx, role)

    @whohas.error
    async def whohas_error(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            return

    async def role_info(self, ctx, role: discord.Role):
        if role is None:
            return await ctx.send(":x: `role` is neither a role on this server, nor on the Democraciv server.")

        if role.guild.id != ctx.guild.id:
            description = ":warning:  This role is from the Democraciv server, not from this server!"
            role_name = role.name
        else:
            description = ""
            role_name = f"{role.name} {role.mention}"

        if role != role.guild.default_role:
            role_members = '\n'.join([f"{member.mention} {member}" for member in role.members]) or '-'
        else:
            role_members = "*Too long to display.*"

        embed = self.bot.embeds.embed_builder(title="Role Information", description=description,
                                              colour=role.colour, has_footer=False)
        embed.add_field(name="Role", value=role_name, inline=False)
        embed.add_field(name="ID", value=role.id, inline=False)
        embed.add_field(name="Created on", value=role.created_at.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Colour", value=str(role.colour), inline=True)

        if len(role_members) <= 1024:
            embed.add_field(name=f"Members ({len(role.members)})", value=role_members, inline=False)
        else:
            fields = self.bot.get_cog("Legislature").split_embed_fields(role_members)

            for index in fields:
                if index == 0:
                    embed.add_field(name=f"Members ({len(role.members)})", value=fields[index], inline=False)
                else:
                    embed.add_field(name="Members (Cont.)", value=fields[index], inline=False)

        if len(embed) > 6000:
            for _ in embed.fields:
                embed.remove_field(4)

            embed.add_field(name=f"Members ({len(role.members)})", value="*Too long to display.*", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='random')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def random(self, ctx, *arg):
        """Get a random number or make the bot choose between something

            **Example:**
              `-random` will choose a random number between 1 and 100
              `-random 6` will choose a random number between 1 and 6
              `-random 50 200` will choose a random number between 50 and 200
              `-random coin` will choose Heads or Tails
              `-random choice "England" "Rome"` will choose between England and Rome
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

        elif arg[0].lower() in ('flip', 'coin', 'coinflip'):
            coin = ['Heads', 'Tails']
            msg = discord.utils.escape_mentions(f':arrows_counterclockwise: **{random.choice(coin)}**')
            return await ctx.send(msg)

        elif arg[0].lower() == 'choice':
            choices = list(arg)
            choices.pop(0)
            msg = discord.utils.escape_mentions(f':tada: The winner is: **{random.choice(choices)}**')
            return await ctx.send(msg)

        elif len(arg) == 1:
            start = 1
            try:
                end = int(arg[0])
            except ValueError:
                raise commands.BadArgument()

        elif len(arg) == 2:
            try:
                start = int(arg[0])
                end = int(arg[1])
            except ValueError:
                raise commands.BadArgument()

        else:
            start = 1
            end = 100

        try:
            result = random.randint(start, end)
        except Exception:
            raise commands.BadArgument()

        msg = discord.utils.escape_mentions(f':arrows_counterclockwise: Random number ({start} - {end}): **{result}**')
        await ctx.send(msg)

    @commands.command(name='vibecheck', hidden=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def vibecheck(self, ctx, *, member: typing.Union[discord.Member, CaseInsensitiveMember] = None):
        """vibecheck"""

        member = member or ctx.author

        not_vibing = [
            'https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg',
            'https://t6.rbxcdn.com/e92c5706e16411bdb1aeaa23e268c4aa',
            'https://s3.amazonaws.com/media.thecrimson.com/photos/2019/11/18/194724_1341037.png',
            'https://i.kym-cdn.com/photos/images/newsfeed/001/574/493/3ab.jpg',
            'https://i.imgflip.com/3ebtvt.jpg',
            'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT814jrNuqJsaVVHGqWw_0snlcysLN5fLpocEYrx6hzkgXYx7RV5w&s',
            'https://i.redd.it/qajwen1dpcn31.png',
            'https://pl.scdn.co/images/pl/default/8b3875b1f9c2a05ebc96df0fb4404265246bc4bb',
            'https://img.buzzfeed.com/buzzfeed-static/static/2019-10/7/15/asset/c5dd65974640/sub-buzz-521-1570462442-1.png?downsize=700:*&output-format=auto&output-quality=auto',
            'https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/12132fe4-1709-4287-9dcc-4ee9fc252a01/ddk55pz-bf72cab3-2b9e-474e-94a8-00e5f53d2baf.jpg?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZTBkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiJcL2ZcLzEyMTMyZmU0LTE3MDktNDI4Ny05ZGNjLTRlZTlmYzI1MmEwMVwvZGRrNTVwei1iZjcyY2FiMy0yYjllLTQ3NGUtOTRhOC0wMGU1ZjUzZDJiYWYuanBnIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.Sb6Axu0O6iZ3YmZJHg5wRe-r41iLnWVqa_ddWrtbQlo',
            'https://pbs.twimg.com/media/EHgYHjOX4AAuv6s.jpg',
            'https://pbs.twimg.com/media/EGTsxzaUwAAuBLG?format=jpg&name=900x900',
            'https://66.media.tumblr.com/c2fc65d9f8614dbd9bb7378983e0598e/tumblr_pxw332rEmZ1yom1s3o1_1280.png'
        ]

        vibing = ['https://i.redd.it/ax6jb6lhdah31.jpg',
                  'https://i.redd.it/3a6nr5b3u4x31.png',
                  'https://i.kym-cdn.com/photos/images/original/001/599/028/bf3.jpg',
                  'https://i.redd.it/p4e6a65i3bw31.jpg',
                  'https://media.makeameme.org/created/congratulations-you-have-61e05e0d4b.jpg']

        passed = True if random.randrange(1, stop=100) >= 65 else False

        if passed:
            image = random.choice(vibing)
            pretty = "passed"
        else:
            image = random.choice(not_vibing)
            pretty = "not passed"

        embed = self.bot.embeds.embed_builder(title=":flushed:  Vibe Check", description=f"{member.mention} "
                                                                                         f"has **{pretty}** "
                                                                                         f"the vibe check!")
        embed.set_image(url=image)
        await ctx.send(embed=embed)

    @vibecheck.error
    async def vibecheck_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            return

    @commands.command(name="dog", aliases=['doggo', 'doggos', 'dogs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def dog(self, ctx):
        """Just for Tay: A random image or video of a dog"""

        """The MIT License (MIT)

        Copyright (c) 2015 Rapptz
        
        Permission is hereby granted, free of charge, to any person obtaining a
        copy of this software and associated documentation files (the "Software"),
        to deal in the Software without restriction, including without limitation
        the rights to use, copy, modify, merge, publish, distribute, sublicense,
        and/or sell copies of the Software, and to permit persons to whom the
        Software is furnished to do so, subject to the following conditions:
        
        The above copyright notice and this permission notice shall be included in
        all copies or substantial portions of the Software.
        
        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
        OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
        FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
        DEALINGS IN THE SOFTWARE."""

        async with self.bot.session.get('https://random.dog/woof') as resp:
            if resp.status != 200:
                return await ctx.send(':x: No dog found :(')

            filename = await resp.text()
            url = f'https://random.dog/{filename}'
            filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
            if filename.endswith(('.mp4', '.webm')):
                async with ctx.typing():
                    async with self.bot.session.get(url) as other:
                        if other.status != 200:
                            return await ctx.send(':x: Could not download dog video :(')

                        if int(other.headers['Content-Length']) >= filesize:
                            return await ctx.send(f':x: Video was too big to upload, watch it here instead: {url}')

                        fp = io.BytesIO(await other.read())
                        await ctx.send(file=discord.File(fp, filename=filename))
            else:
                embed = self.bot.embeds.embed_builder(title="Random Dog", description="", has_footer=False)
                embed.set_image(url=url)
                embed.set_footer(text="Just for Taylor.")
                await ctx.send(embed=embed)

    @commands.command(name="cat", aliases=['cats'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def cat(self, ctx):
        """A random cat"""

        """The MIT License (MIT)

        Copyright (c) 2015 Rapptz

        Permission is hereby granted, free of charge, to any person obtaining a
        copy of this software and associated documentation files (the "Software"),
        to deal in the Software without restriction, including without limitation
        the rights to use, copy, modify, merge, publish, distribute, sublicense,
        and/or sell copies of the Software, and to permit persons to whom the
        Software is furnished to do so, subject to the following conditions:

        The above copyright notice and this permission notice shall be included in
        all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
        OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
        FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
        DEALINGS IN THE SOFTWARE."""

        async with self.bot.session.get('https://api.thecatapi.com/v1/images/search') as response:
            if response.status != 200:
                return await ctx.send(':x: No cat found :(')

            js = await response.json()

            embed = self.bot.embeds.embed_builder(title="Random Cat", description="", has_footer=False)
            embed.set_image(url=js[0]['url'])
            await ctx.send(embed=embed)

    @commands.command(name='serverinvite')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this server"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)

    @commands.command(name='roll')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def roll(self, ctx, *, dices):
        """Roll some dice

            **Supported Notation**
            - Dice rolls take the form NdX, where N is the number of dice to roll, and X are the faces of the dice. For example, 1d6 is one six-sided die.
            - A dice roll can be followed by an Ln or Hn, where it will discard the lowest n rolls or highest n rolls, respectively. So 2d20L1 means to roll two d20s and discard the lower. I.E advantage.
            - A dice roll can be part of a mathematical expression, such as 1d4 +5.

            **Example:**
              `-roll 1d6` will roll a d6
              `-roll (2d20L1) + 1d4 + 5` will roll 2d20s, discard the lower one, and add 1d4 and 5 to the result

            *Full notation can be found here: https://xdice.readthedocs.io/en/latest/dice_notation.html*
            """

        js = await self.bot.api_request("POST", "roll", json={'dices': dices})

        if 'error' in js:
            raise commands.BadArgument(js['error'])

        if 'result' in js:
            await ctx.send(js['result'])


def setup(bot):
    bot.add_cog(Misc(bot))