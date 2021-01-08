import io
import typing
import random
import discord
import operator
import datetime
import re

from discord.ext import commands
from urllib import parse

from bot.config import config, token
from bot.utils import context, paginator, text
from bot.utils.converter import (
    PoliticalParty,
    CaseInsensitiveMember, CaseInsensitiveUser, DemocracivCaseInsensitiveRole,
)


class Utility(context.CustomCog):
    """Utility commands. Some more useful than others."""

    def __init__(self, bot):
        super().__init__(bot)
        self.cached_sorted_veterans_on_democraciv = []

    @staticmethod
    def percentage_encode_url(link: str) -> str:
        if link.startswith("https://"):
            link = link[8:]
            url = parse.quote(link)
            return "https://" + url
        else:
            return parse.quote(link)

    async def get_wikipedia_result_with_rest_api(self, query):
        """This uses the newer REST API that MediaWiki offers to query their site.
           advantages: newer, cleaner, faster, gets thumbnail + URL
           disadvantages: doesn't work with typos in attr: query

           see: https://www.mediawiki.org/wiki/REST_API"""

        async with self.bot.session.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}") as response:
            if response.status == 200:
                return await response.json()

    async def get_wikipedia_suggested_articles(self, query):
        """This uses the older MediaWiki Action API to query their site.

           Used as a fallback when self.get_wikipedia_result_with_rest_api() returns None, i.e. there's a typo in the
           query string. Returns suggested articles from a 'disambiguation' article

           see: https://en.wikipedia.org/w/api.php"""

        async with self.bot.session.get(
                f"https://en.wikipedia.org/w/api.php?format=json&action=query&list=search"
                f"&srinfo=suggestion&srprop&srsearch={query}"
        ) as response:
            if response.status == 200:
                return await response.json()

    @commands.command(name="wikipedia")
    async def wikipedia(self, ctx, *, topic: str):
        """Search for an article on Wikipedia"""
        async with ctx.typing():  # Show typing status so that user knows that stuff is happening
            result = await self.get_wikipedia_result_with_rest_api(topic)

            if result is None or result["type"] == "disambiguation":

                # Fall back to MediaWiki Action API and ask for article suggestions as there's probably a typo in
                # 'topic'
                suggested_pages = await self.get_wikipedia_suggested_articles(topic)

                try:
                    suggested_query_name = suggested_pages["query"]["search"][0]["title"]
                except (IndexError, KeyError):
                    return await ctx.send(
                        f"{config.NO} Wikipedia could not suggest me anything. "
                        "Did you search for something in a language other than English?"
                    )

                # Retry with new suggested article title
                result = await self.get_wikipedia_result_with_rest_api(suggested_query_name)

                if result is None or not result:
                    return await ctx.send(f"{config.NO} Wikipedia couldn't suggest me any articles that are "
                                          f"related to `{topic}`.")

            title = result["title"]
            summary = result["extract"]
            summary_in_2_sentences = " ".join(re.split(r"(?<=[.?!])\s+", summary, 2)[:-1])
            url = result["content_urls"]["desktop"]["page"]
            thumbnail_url = ""

            try:
                thumbnail_url = result["thumbnail"]["source"]
            except KeyError:
                pass

            embed = text.SafeEmbed(
                title=f"{config.WIKIPEDIA_LOGO}  {title}",
                description=summary_in_2_sentences
            )

            embed.add_field(name="Link", value=self.percentage_encode_url(url))

            if thumbnail_url.startswith("https://"):
                embed.set_thumbnail(url=thumbnail_url)

        await ctx.send(embed=embed)

    @commands.command(name="time", aliases=["clock", "tz"])
    async def time(self, ctx, *, zone: str):
        """Displays the current time of a specified timezone"""

        # If input is an abbreviation (UTC, EST etc.), make it uppercase for the TimeZoneDB request to work
        if len(zone) <= 5:
            zone = zone.upper()

        if not token.TIMEZONEDB_API_KEY:
            await self.bot.owner.send(f"Invalid TimeZoneDB API key in `bot/config/token.py`")
            return await ctx.send(f"{config.NO} This command cannot be used right now.")

        query_base = (
            f"https://api.timezonedb.com/v2.1/get-time-zone?key={token.TIMEZONEDB_API_KEY}&format=json&"
            f"by=zone&zone={zone}"
        )

        async with ctx.typing():
            async with self.bot.session.get(query_base) as response:
                if response.status == 200:
                    time_response = await response.json()

            if time_response["status"] != "OK":
                return await ctx.send(
                    f"{config.NO} `{zone}` is not a valid time zone or area code. "
                    f"See the list of available time zones here: "
                    f"<https://timezonedb.com/time-zones>"
                )

            date = datetime.datetime.utcfromtimestamp(time_response["timestamp"]).strftime("%A, %B %d %Y")
            us_time = datetime.datetime.utcfromtimestamp(time_response["timestamp"]).strftime("%I:%M:%S %p")
            eu_time = datetime.datetime.utcfromtimestamp(time_response["timestamp"]).strftime("%H:%M:%S")

            if zone.lower() == "utc":
                title = f":clock1:  Current Time in UTC"
            else:
                title = f":clock1:  Current Time in {time_response['abbreviation']}"

            embed = text.SafeEmbed(title=title, description="")
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

        await self.bot.db.execute(
            "INSERT INTO original_join_date (member, join_date) " "VALUES ($1, $2) ON CONFLICT DO NOTHING",
            member.id,
            joined_on,
        )

    async def get_member_join_date(self, member: discord.Member) -> datetime.datetime:
        if member.guild.id == self.bot.dciv.id:
            original_date = await self.bot.db.fetchval(
                "SELECT join_date FROM original_join_date WHERE member = $1", member.id
            )
            if original_date is not None:
                return original_date

        return member.joined_at

    async def get_member_join_position(self, user, members: list):
        if user.guild.id == self.bot.dciv.id:
            row = await self.bot.db.fetchrow(
                "SELECT join_position FROM original_join_date WHERE member = $1",
                user.id)

            all_members = await self.bot.db.fetchval("SELECT max(join_position) FROM original_join_date")

            if row:
                return row['join_position'], all_members

        joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))

        if None in joins:
            return None, None

        for key, elem in enumerate(joins):
            if elem == user:
                return key + 1, len(members)

        return None, None

    @commands.command(name="whois")
    @commands.guild_only()
    async def whois(
            self,
            ctx,
            *,
            member: typing.Union[
                CaseInsensitiveMember,
                DemocracivCaseInsensitiveRole,
                PoliticalParty,
            ] = None,
    ):
        """Get detailed information about a member of this server

        **Example**
         `{PREFIX}{COMMAND}`
         `{PREFIX}{COMMAND} Jonas - u/Jovanos`
         `{PREFIX}{COMMAND} @DerJonas`
         `{PREFIX}{COMMAND} DerJonas`
         `{PREFIX}{COMMAND} deRjoNAS`
         `{PREFIX}{COMMAND} DerJonas#8109`
        """

        def _get_roles(roles):
            fmt = []

            for role in roles[::-1]:
                if not role.is_default():
                    fmt.append(role.mention)

            if not fmt:
                return "-"
            else:
                return ', '.join(fmt)

        if isinstance(member, discord.Role):
            return await self.role_info(ctx, member)

        elif isinstance(member, PoliticalParty):
            return await self.role_info(ctx, member.role)

        member = member or ctx.author
        join_pos, max_members = await self.get_member_join_position(member, ctx.guild.members)

        embed = text.SafeEmbed(title="Member Information")
        embed.add_field(name="Member", value=f"{member} {member.mention}", inline=False)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(
            name="Discord Registration",
            value=f'{member.created_at.strftime("%B %d, %Y")}',
            inline=True,
        )
        embed.add_field(
            name="Joined",
            value=f'{(await self.get_member_join_date(member)).strftime("%B %d, %Y")}',
            inline=True,
        )
        embed.add_field(name="Join Position", value=f"{join_pos}/{max_members}", inline=True)
        embed.add_field(
            name=f"Roles ({len(member.roles) - 1})",
            value=_get_roles(member.roles),
            inline=False,
        )
        embed.set_thumbnail(url=member.avatar_url_as(static_format="png"))
        await ctx.send(embed=embed)

    @commands.command(name="avatar", aliases=['pfp'])
    @commands.guild_only()
    async def avatar(self, ctx, *, member: typing.Union[CaseInsensitiveMember, CaseInsensitiveUser] = None):
        """View someone's avatar in detail

        **Example**
             `{PREFIX}{COMMAND}`
             `{PREFIX}{COMMAND} @DerJonas`
             `{PREFIX}{COMMAND} DerJonas`
             `{PREFIX}{COMMAND} DerJonas#8109`
        """

        member = member or ctx.author
        avatar_png = str(member.avatar_url_as(static_format="png", size=4096))
        embed = text.SafeEmbed()
        embed.set_image(url=avatar_png)
        embed.set_author(name=member, icon_url=avatar_png, url=avatar_png)
        await ctx.send(embed=embed)

    @commands.command(name="veterans")
    @commands.guild_only()
    async def veterans(self, ctx):
        """List the first 15 members who joined this server"""

        sorted_first_15_members = []

        # As veterans rarely change, use a cached version of sorted list if exists
        if ctx.guild.id == self.bot.dciv.id:
            if len(self.cached_sorted_veterans_on_democraciv) >= 2:
                sorted_first_15_members = self.cached_sorted_veterans_on_democraciv
            else:
                vets = await self.bot.db.fetch(
                    "SELECT member, join_position FROM original_join_date WHERE "
                    "join_position <= 15 ORDER BY join_position"
                )
                for record in vets:
                    member = self.bot.get_user(record["member"])
                    sorted_first_15_members.append((member, record["join_position"]))

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
        message = ["These are the first 15 people who joined this server.\nBot accounts are not counted.\n"]

        for veteran in sorted_first_15_members:
            person = str(veteran[0]) if veteran[0] else f"*Person left {self.bot.dciv.name}*"
            message.append(f"{veteran[1]}. {person}")

        embed = text.SafeEmbed(description='\n'.join(message))
        embed.set_author(name=f"Veterans of {ctx.guild.name}", icon_url=ctx.guild_icon)
        await ctx.send(embed=embed)

    @commands.command()
    async def lyrics(self, ctx, *, query: str):
        """Find lyrics for a song

        **Usage**
            `{PREFIX}{COMMAND} <query>` to search for lyrics that match your query
        """

        if len(query) < 3:
            return await ctx.send(f"{config.NO} The query to search for has to be more than 3 characters!")

        async with ctx.typing():
            async with self.bot.session.get(f"https://some-random-api.ml/lyrics?title={query}") as response:
                if response.status == 200:
                    lyrics = await response.json()
                else:
                    return await ctx.send(f"{config.NO} Genius could not suggest me anything related to `{query}`.")

        try:
            lyrics["lyrics"] = lyrics["lyrics"].replace("[", "**[").replace("]", "]**")

            if len(lyrics["lyrics"]) <= 2048:
                embed = text.SafeEmbed(
                    title=lyrics['title'],
                    description=lyrics["lyrics"],
                    colour=0x2F3136,
                    url=lyrics["links"]["genius"]
                )
                embed.set_author(name=lyrics['author'])
                embed.set_thumbnail(url=lyrics["thumbnail"]["genius"])
                return await ctx.send(embed=embed)

            pages = paginator.SimplePages(
                entries=lyrics["lyrics"].splitlines(),
                title=lyrics['title'],
                title_url=lyrics["links"]["genius"],
                author=lyrics['author'],
                thumbnail=lyrics["thumbnail"]["genius"],
                colour=0x2F3136
            )

        except KeyError:
            return await ctx.send(f"{config.NO} Genius could not suggest me anything related to `{query}`.")

        await pages.start(ctx)

    @commands.command(name="tinyurl", aliases=["tiny"])
    async def tinyurl(self, ctx, *, url: str):
        """Shorten a link with tinyurl"""
        if len(url) <= 3:
            await ctx.send(f"{config.NO} That doesn't look like a valid URL.")
            return

        tiny_url = await self.bot.tinyurl(url)

        if tiny_url is None:
            return await ctx.send(f"{config.NO} tinyurl.com returned an error, try again in a few minutes.")

        await ctx.send(f"<{tiny_url}>")

    @commands.command(name="whohas", aliases=["roleinfo"])
    @commands.guild_only()
    async def whohas(
            self,
            ctx,
            *,
            role: typing.Union[DemocracivCaseInsensitiveRole, PoliticalParty],
    ):
        """Detailed information about a role"""

        if isinstance(role, PoliticalParty):
            role = role.role

        await self.role_info(ctx, role)

    async def role_info(self, ctx, role: discord.Role):
        if role is None:
            return await ctx.send(f"{config.NO} `role` is neither a role on this server, nor on the Democraciv server.")

        if role.guild.id != ctx.guild.id:
            description = f":warning:  This role is from the {self.bot.dciv.name} server, not from this server!"
            role_name = role.name
        else:
            description = ""
            role_name = f"{role.name} {role.mention}"

        if role != role.guild.default_role:
            role_members = "\n".join([f"{member.mention} {member}" for member in role.members]) or "-"
        else:
            role_members = "*Too long to display.*"

        embed = text.SafeEmbed(
            title="Role Information",
            description=description,
            colour=role.colour
        )

        embed.add_field(name="Role", value=role_name, inline=False)
        embed.add_field(name="ID", value=role.id, inline=False)
        embed.add_field(name="Created on", value=role.created_at.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Colour", value=role.colour, inline=True)
        embed.add_field(name=f"Members ({len(role.members)})", value=role_members, inline=False)
        await ctx.send(embed=embed)

    @commands.group(name="random", case_insensitive=True, invoke_without_command=True)
    async def random(self, ctx, start: int = 1, end: int = 100):
        """Generate a random number

        **Example**
          `{PREFIX}{COMMAND}` will choose a random number between 1 and 100
          `{PREFIX}{COMMAND} 50 200` will choose a random number between 50 and 200
        """

        try:
            result = random.randint(start, end)
        except Exception:
            raise commands.BadArgument()

        await ctx.send(f":arrows_counterclockwise: Random number ({start} - {end}): **{result}**")

    @random.command(name="choose", aliases=['choice'])
    async def random_choice(self, ctx, *choices):
        """Make me choose between things

        **Example**
          `{PREFIX}{COMMAND} "Civ 4" "Civ 5" "Civ 6" "Civ BE"`"""

        await ctx.send(f":tada: The winner is: **{random.choice(choices)}**")

    @random.command(name="coin", aliases=['flip', 'coinflip'])
    async def random_coin(self, ctx):
        """Flip a coin"""

        coins = ["Heads", "Tails"]
        return await ctx.send(f":arrows_counterclockwise: **{random.choice(coins)}**")

    @commands.command(name="vibecheck", hidden=True)
    @commands.guild_only()
    async def vibecheck(self, ctx, *, member: typing.Union[CaseInsensitiveMember, CaseInsensitiveUser] = None):
        """vibecheck"""

        member = member or ctx.author

        not_vibing = [
            "https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg",
            "https://t6.rbxcdn.com/e92c5706e16411bdb1aeaa23e268c4aa",
            "https://s3.amazonaws.com/media.thecrimson.com/photos/2019/11/18/194724_1341037.png",
            "https://i.kym-cdn.com/photos/images/newsfeed/001/574/493/3ab.jpg",
            "https://i.imgflip.com/3ebtvt.jpg",
            "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT814jrNuqJsaVVHGqWw_0snlcysLN5fLpocEYrx6hzkgXYx7RV5w&s",
            "https://i.redd.it/qajwen1dpcn31.png",
            "https://pl.scdn.co/images/pl/default/8b3875b1f9c2a05ebc96df0fb4404265246bc4bb",
            "https://img.buzzfeed.com/buzzfeed-static/static/2019-10/7/15/asset/c5dd65974640/sub-buzz-521-1570462442-1.png?downsize=700:*&output-format=auto&output-quality=auto",
            "https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/12132fe4-1709-4287-9dcc-4ee9fc252a01/ddk55pz-bf72cab3-2b9e-474e-94a8-00e5f53d2baf.jpg?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZTBkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiJcL2ZcLzEyMTMyZmU0LTE3MDktNDI4Ny05ZGNjLTRlZTlmYzI1MmEwMVwvZGRrNTVwei1iZjcyY2FiMy0yYjllLTQ3NGUtOTRhOC0wMGU1ZjUzZDJiYWYuanBnIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.Sb6Axu0O6iZ3YmZJHg5wRe-r41iLnWVqa_ddWrtbQlo",
            "https://pbs.twimg.com/media/EHgYHjOX4AAuv6s.jpg",
            "https://pbs.twimg.com/media/EGTsxzaUwAAuBLG?format=jpg&name=900x900",
            "https://66.media.tumblr.com/c2fc65d9f8614dbd9bb7378983e0598e/tumblr_pxw332rEmZ1yom1s3o1_1280.png",
        ]

        vibing = [
            "https://i.redd.it/ax6jb6lhdah31.jpg",
            "https://i.redd.it/3a6nr5b3u4x31.png",
            "https://i.kym-cdn.com/photos/images/original/001/599/028/bf3.jpg",
            "https://i.redd.it/p4e6a65i3bw31.jpg",
            "https://media.makeameme.org/created/congratulations-you-have-61e05e0d4b.jpg",
        ]

        passed = True if random.randrange(1, stop=100) >= 65 else False

        if passed:
            image = random.choice(vibing)
            pretty = "passed"
        else:
            image = random.choice(not_vibing)
            pretty = "not passed"

        embed = text.SafeEmbed(
            title=f"{member} has __{pretty}__ the vibe check",
        )

        embed.set_image(url=image)
        await ctx.send(embed=embed)

    @commands.command(name="dog", aliases=["doggo", "doggos", "dogs"])
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

        async with self.bot.session.get("https://random.dog/woof") as resp:
            if resp.status != 200:
                return await ctx.send(f"{config.NO} No dog found :(")

            filename = await resp.text()
            url = f"https://random.dog/{filename}"
            filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
            if filename.endswith((".mp4", ".webm")):
                async with ctx.typing():
                    async with self.bot.session.get(url) as other:
                        if other.status != 200:
                            return await ctx.send(f"{config.NO} Could not download dog video :(")

                        if int(other.headers["Content-Length"]) >= filesize:
                            return await ctx.send(
                                f"{config.NO} Video was too big to upload, watch it here instead: {url}")

                        fp = io.BytesIO(await other.read())
                        await ctx.send(file=discord.File(fp, filename=filename))
            else:
                embed = text.SafeEmbed(title="Random Dog")
                embed.set_image(url=url)
                embed.set_footer(text="Just for Taylor.")
                await ctx.send(embed=embed)

    @commands.command(name="cat", aliases=["cats"])
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

        async with self.bot.session.get("https://api.thecatapi.com/v1/images/search") as response:
            if response.status != 200:
                return await ctx.send(f"{config.NO} No cat found :(")

            js = await response.json()

            embed = text.SafeEmbed(title="Random Cat")
            embed.set_image(url=js[0]["url"])
            await ctx.send(embed=embed)

    @commands.command(name="serverinvite")
    async def invite(self, ctx):
        """Get an active invite link to this server"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)

    @commands.command(name="roll", aliases=['r', 'dice'])
    async def roll(self, ctx, *, dices):
        """Roll some dice

        **Supported Notation**
        - Dice rolls take the form NdX, where N is the number of dice to roll, and X are the faces of the dice. For example, 1d6 is one six-sided die.
        - A dice roll can be followed by an Ln or Hn, where it will discard the lowest n rolls or highest n rolls, respectively. So 2d20L1 means to roll two d20s and discard the lower. I.E advantage.
        - A dice roll can be part of a mathematical expression, such as 1d4 +5.

        **Example**
          `{PREFIX}{COMMAND} 1d6` will roll a d6
          `{PREFIX}{COMMAND} (2d20L1) + 1d4 + 5` will roll 2d20s, discard the lower one, and add 1d4 and 5 to the result

        *Full notation can be found here: https://xdice.readthedocs.io/en/latest/dice_notation.html*
        """

        js = await self.bot.api_request("POST", "roll", json={"dices": dices})

        if "error" in js:
            raise commands.BadArgument()

        if "result" in js:
            await ctx.reply(js["result"])


def setup(bot):
    bot.add_cog(Utility(bot))
