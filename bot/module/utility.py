"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.

The -cat and -dog commands are based on RoboDanny by Rapptz: https://github.com/Rapptz/RoboDanny/blob/rewrite/LICENSE.txt
"""
import asyncio
import io
import logging
import traceback
import typing
import random
import aiohttp
import discord
import operator
import datetime
import textwrap
import pytz

from fuzzywuzzy import process
from discord.ext import commands
from urllib import parse

from bot.config import config
from bot.utils import context, paginator, text
from bot.utils.converter import (
    PoliticalParty,
    CaseInsensitiveUser,
    CaseInsensitiveRole,
    DemocracivCaseInsensitiveRole,
    CaseInsensitiveMember,
    Fuzzy,
    FuzzySettings,
)


class Utility(context.CustomCog):
    """Utility commands. Some more useful than others."""

    def __init__(self, bot):
        super().__init__(bot)
        self.cached_sorted_veterans_on_democraciv = []
        self.active_press_flows: typing.Set[int] = set()

    @commands.Cog.listener(name="on_message")
    async def on_press_message(self, message: discord.Message):
        if (
            message.author.bot
            or not message.guild
            or message.guild.id != self.bot.dciv.id
            or message.channel.id not in self.bot.mk.PRESS_CHANNEL
        ):
            return

        if message.author.id in self.active_press_flows:
            return

        ctx = await self.bot.get_context(message)

        if ctx.valid:
            return

        never_role_name = "Reddit Press"
        never_role = discord.utils.get(self.bot.dciv.roles, name=never_role_name)

        if never_role and never_role in message.author.roles:
            return

        self.active_press_flows.add(message.author.id)
        # wait for any other messages from same author
        start = discord.utils.utcnow()
        messages = [message]

        while True:
            try:
                _m = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.author == message.author
                    and m.channel == message.channel,
                    timeout=120,
                )

                _ctx = await self.bot.get_context(_m)

                if _ctx.valid:
                    continue

                messages.append(_m)
                start = discord.utils.utcnow()
            except asyncio.TimeoutError:
                if discord.utils.utcnow() - start >= datetime.timedelta(minutes=2):
                    break
                else:
                    continue

        # check if messages were not deleted before asking
        messages = [
            discord.utils.get(self.bot.cached_messages, id=mes.id) for mes in messages
        ]

        if not any(messages):
            self.active_press_flows.remove(message.author.id)
            return

        messages = list(filter(None, messages))

        confirm = await message.channel.send(
            f"{config.USER_INTERACTION_REQUIRED} {message.author.mention}, do you want "
            f"me to post these last {len(messages)} messages from you to our "
            f"subreddit **r/{config.DEMOCRACIV_SUBREDDIT}** in one, single press post?"
            f"\n{config.HINT} *You have 2 minutes to decide. After that with no reaction from you I "
            f"will cancel this process and delete this message.*"
            f"\n{config.HINT} *If you would like to opt-out from this feature entirely so that I "
            f"no longer ask you this, give yourself the `{never_role_name}` selfrole with "
            f"`{config.BOT_PREFIX}role {never_role_name}`.*",
            allowed_mentions=discord.AllowedMentions(users=True),
            delete_after=120,
        )

        yes_emoji = config.YES
        no_emoji = config.NO

        await confirm.add_reaction(yes_emoji)
        await confirm.add_reaction(no_emoji)

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add",
                check=lambda r, u: u.id == message.author.id
                and r.message.id == confirm.id,
                timeout=120,
            )
        except asyncio.TimeoutError:
            self.active_press_flows.remove(message.author.id)
            self.bot.loop.create_task(confirm.delete())
            return
        else:
            if not reaction or str(reaction.emoji) != yes_emoji:
                self.active_press_flows.remove(message.author.id)
                self.bot.loop.create_task(confirm.delete())
                return

        title_q = await message.channel.send(
            f"{config.USER_INTERACTION_REQUIRED} {message.author.mention}, what should be the "
            f"title of the Reddit post?\n{config.HINT} *You have 3 minutes to respond. "
            f"After that with no reply from you I will cancel this process and delete this message.*",
            allowed_mentions=discord.AllowedMentions(users=True),
            delete_after=180,
        )

        try:
            title_message = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == message.author
                and m.channel == message.channel,
                timeout=180,
            )

        except asyncio.TimeoutError:
            self.active_press_flows.remove(message.author.id)
            return

        else:
            if not title_message.content:
                self.active_press_flows.remove(message.author.id)
                return

        title = f"{title_message.clean_content} — by {message.author.name}"
        cleaned_up = [
            f"*The following was written by the journalist {message.author.display_name} ({message.author}) "
            f"in #{message.channel.name} on our [Discord server](https://discord.gg/AK7dYMG)*."
        ]

        for mes in messages:
            cntn = ""

            # get message again in case it was edited
            mes = discord.utils.get(self.bot.cached_messages, id=mes.id)

            # message was deleted
            if not mes:
                continue

            if mes.content:
                cntn = mes.clean_content.replace("\n", "\n\n")

            if mes.attachments:
                cntn = f"{cntn} [*Attachment*]({mes.attachments[0].url})"

            cleaned_up.append(cntn)

        if len(cleaned_up) == 1:
            self.active_press_flows.remove(message.author.id)
            return await ctx.send(
                f"{config.HINT} {message.author}, you deleted your messages, "
                f"so I cancelled this process."
            )

        outro = f"""\n\n &nbsp; \n\n --- \n\n*This is an automated press post from our Discord server. I am a 
        [bot](https://github.com/jonasbohmann/democraciv-discord-bot/) and this is an automated service. 
        Contact u/Jovanos (DerJonas#8036 on Discord) for further questions or bug reports. !A_ID: {message.author.id}*"""

        cleaned_up.append(outro)

        content = "\n\n  &nbsp; \n\n".join(cleaned_up)

        js = {
            "subreddit": config.DEMOCRACIV_SUBREDDIT,
            "title": title,
            "content": content,
        }
        self.active_press_flows.remove(message.author.id)

        try:
            result = await self.bot.api_request("POST", "reddit/post", json=js)

            if "error" in result:
                raise RuntimeError(result["error"])

        except Exception as e:
            await message.channel.send(
                f"{config.NO} {message.author}, something went wrong, your article was not "
                f"posted to Reddit.",
                delete_after=10,
            )
            logging.warning(f"Failed to post press article to Reddit: ")
            traceback.print_exception(type(e), e, e.__traceback__)

        else:
            await message.channel.send(
                f"{config.YES} {message.author}, your press article was posted to "
                f"r/{config.DEMOCRACIV_SUBREDDIT}.\n{config.HINT} Don't like how it turned out? "
                f"You can make me delete the reddit post with the `{config.BOT_PREFIX}deletepresspost` command.",
                delete_after=15,
            )

        self.bot.loop.create_task(confirm.delete())
        self.bot.loop.create_task(title_q.delete())
        self.bot.loop.create_task(title_message.delete())

    @commands.command(
        name="deletepresspost",
        aliases=["deletepress", "removepress", "removepresspost", "dpp", "rpp", "dp"],
    )
    async def delete_press_post(self, ctx, *, url):
        """Make me delete a reddit post that I made out of your #press messages and posted to our subreddit

        **Example**
        `{PREFIX}{COMMAND} https://www.reddit.com/r/democraciv/comments/ibr37f/introducing_the_bank_of_democraciv/`"""

        if (
            f"reddit.com/r/{config.DEMOCRACIV_SUBREDDIT.lower()}" not in url.lower()
            and "comments" not in url.lower()
        ):
            return await ctx.send(
                f"{config.NO} Make sure the link to your Reddit press post is in this exact format: "
                f"`https://www.reddit.com/r/democraciv/comments/ibr37f/introducing_the_bank_of_democraciv/`."
            )

        error_msg = (
            f"{config.NO} Something went wrong. Are you sure that you gave me "
            f"a real link to a press Reddit post?"
        )

        try:
            async with self.bot.session.get(f"{url}.json") as response:
                if response.status != 200:
                    return await ctx.send(error_msg)

                js = await response.json()
        except aiohttp.ClientError:
            return await ctx.send(error_msg)

        try:
            post = js[0]["data"]["children"][0]["data"]

            if (
                post["subreddit"].lower() != config.DEMOCRACIV_SUBREDDIT.lower()
                or post["author"].lower() != config.STARBOARD_REDDIT_USERNAME.lower()
            ):
                return await ctx.send(error_msg)

            # remove whitespace
            content = "".join(post["selftext"].split())
            post_id = post["name"]
        except (TypeError, KeyError, IndexError):
            return await ctx.send(error_msg)

        if f"!A_ID:{ctx.author.id}" not in content:
            return await ctx.send(
                f"{config.NO} You are not the author of that press article."
            )

        resp = await self.bot.api_request(
            "POST", "reddit/post/delete", json={"id": post_id}
        )

        if "error" in resp:
            return await ctx.send(error_msg)

        await ctx.send(f"{config.YES} Your press article was removed from Reddit.")

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

        percent_encoded = parse.quote(query.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{percent_encoded}"

        try:
            async with self.bot.session.get(url) as response:
                if response.status == 200:
                    return await response.json()

        except (ValueError, aiohttp.InvalidURL):
            return None

    async def get_wikipedia_suggested_articles(self, query):
        """This uses the older MediaWiki Action API to query their site.

        Used as a fallback when self.get_wikipedia_result_with_rest_api() returns None, i.e. there's a typo in the
        query string. Returns suggested articles from a 'disambiguation' article

        see: https://en.wikipedia.org/w/api.php"""

        async with self.bot.session.get(
            f"https://en.wikipedia.org/w/api.php?format=json&action=query&list=search"
            f"&srinfo=suggestion&srsearch={query}"
        ) as response:
            if response.status == 200:
                return await response.json()

    @commands.command(name="wikipedia", aliases=["define", "definition"])
    async def wikipedia(self, ctx, *, topic: str):
        """Search for an article on Wikipedia"""
        async with ctx.typing():  # Show typing status so that user knows that stuff is happening
            result = await self.get_wikipedia_result_with_rest_api(topic)

            if result is None or result["type"] == "disambiguation":

                # Fall back to MediaWiki Action API and ask for article suggestions as there's probably a typo in
                # 'topic'
                try:
                    suggested_pages = await self.get_wikipedia_suggested_articles(topic)
                    result = None

                    for suggested_page in suggested_pages["query"]["search"]:
                        page_info = await self.get_wikipedia_result_with_rest_api(
                            suggested_page["title"]
                        )

                        if page_info and page_info["type"] != "disambiguation":
                            result = page_info
                            break
                        else:
                            continue

                except (TypeError, KeyError):
                    return await ctx.send(
                        f"{config.NO} Wikipedia could not suggest me anything. "
                        "Did you search for something in a language other than English?"
                    )

                if not result:
                    return await ctx.send(
                        f"{config.NO} Wikipedia could not suggest me any articles that are "
                        f"related to `{topic}`."
                    )

            title = result["title"]
            summary = result["extract"]
            url = result["content_urls"]["desktop"]["page"]
            thumbnail_url = None

            try:
                thumbnail_url = result["thumbnail"]["source"]
            except KeyError:
                pass

            embed = text.SafeEmbed(
                description=textwrap.shorten(summary, 500, placeholder="...")
            )
            embed.set_author(
                url=url,
                name=title,
                icon_url="https://cdn.discordapp.com/attachments/738903909535318086/"
                "806577378314289162/Wikipedia-logo-v2.png",
            )

            embed.add_field(name="Link", value=self.percentage_encode_url(url))

            if isinstance(thumbnail_url, str):
                embed.set_thumbnail(url=thumbnail_url)

        await ctx.send(embed=embed)

    @commands.command(name="time", aliases=["clock", "tz", "timezone"])
    async def time(self, ctx, *, zone: str):
        """Displays the current time of a specified time zone"""

        # catch bird time - otherwise 'msk' would be matched to Asia/Omsk, not Moscow
        if zone.lower() == "msk":
            zone = "Europe/Moscow"

        try:
            tz = pytz.timezone(zone)
        except pytz.UnknownTimeZoneError:
            match = process.extract(zone, pytz.all_timezones, limit=5)

            menu = text.FuzzyChoose(
                ctx,
                question="Which time zone did you mean?",
                choices=[zone for zone, _ in match],
            )
            zone = await menu.prompt()

            if not zone:
                return

            tz = pytz.timezone(zone)

        title = str(tz)

        # blame POSIX for this
        # https://stackoverflow.com/a/4009126

        if "+" in zone:
            title = zone
            fixed = zone.replace("+", "-")
            tz = pytz.timezone(fixed)
        elif "-" in zone:
            title = zone
            fixed = zone.replace("-", "+")
            tz = pytz.timezone(fixed)

        utc_now = discord.utils.utcnow()
        date = utc_now.astimezone(tz)

        embed = text.SafeEmbed(title=f":clock1:  Current Time in {title}")
        embed.add_field(name="Date", value=date.strftime("%A, %B %d %Y"), inline=False)
        embed.add_field(
            name="Time (12-Hour Clock)",
            value=date.strftime("%I:%M:%S %p"),
            inline=False,
        )
        embed.add_field(
            name="Time (24-Hour Clock)", value=date.strftime("%H:%M:%S"), inline=False
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def original_join_position_listener(self, member):
        if member.guild.id != self.bot.dciv.id:
            return

        joined_on = member.joined_at or discord.utils.utcnow()
        joined_on = joined_on.astimezone(datetime.timezone.utc).replace(
            tzinfo=None
        )  # remove tz info since db doesnt care

        await self.bot.db.execute(
            "INSERT INTO original_join_date (member, join_date) VALUES ($1, $2) ON CONFLICT DO NOTHING",
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

    async def get_member_join_position(
        self, member: discord.Member, members: typing.List[discord.Member]
    ) -> typing.Tuple[typing.Optional[int], int]:

        if member.guild.id == self.bot.dciv.id:
            sql = """SELECT position.row_number FROM 
                       (SELECT member, ROW_NUMBER () OVER (ORDER BY join_date) AS row_number
                             FROM original_join_date
                       ) AS position
                      WHERE member = $1"""

            join_position = await self.bot.db.fetchval(sql, member.id)
            all_members = await self.bot.db.fetchval(
                "SELECT COUNT(member) FROM original_join_date"
            )

            if join_position:
                return join_position, all_members

        all_members = len(members)
        joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))

        if None in joins:
            return None, all_members

        try:
            return joins.index(member) + 1, all_members
        except ValueError:
            return None, all_members

    @commands.command(name="whois")
    @commands.guild_only()
    async def whois(
        self,
        ctx,
        *,
        person: Fuzzy[
            CaseInsensitiveMember,
            CaseInsensitiveUser,
            CaseInsensitiveRole,
            DemocracivCaseInsensitiveRole,
            PoliticalParty,
            FuzzySettings(weights=(5, 1, 2, 1, 1)),
        ] = None,
    ):
        """See detailed information about someone

        **Example**
         `{PREFIX}{COMMAND}`
         `{PREFIX}{COMMAND} Jonas - u/Jovanos`
         `{PREFIX}{COMMAND} @DerJonas`
         `{PREFIX}{COMMAND} DerJonas`
         `{PREFIX}{COMMAND} deRjoNAS`
         `{PREFIX}{COMMAND} DerJonas#8109`
         `{PREFIX}{COMMAND} 212972352890339328`
        """

        def _get_roles(roles):
            fmt = []

            for role in roles[::-1]:
                if not role.is_default():
                    fmt.append(role.mention)

            if not fmt:
                return "-"
            else:
                return ", ".join(fmt)

        if isinstance(person, discord.Role):
            return await self.role_info(ctx, person)

        elif isinstance(person, PoliticalParty):
            return await self.role_info(ctx, person.role)

        member = person or ctx.author
        embed = text.SafeEmbed()

        if isinstance(member, discord.User):
            embed.description = ":warning: This person is not here in this server."

        embed.add_field(name="Person", value=f"{member} {member.mention}", inline=False)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(
            name="Discord Registration",
            value=f'{member.created_at.strftime("%B %d, %Y")}',
            inline=True,
        )

        if isinstance(member, discord.Member):
            join_pos, max_members = await self.get_member_join_position(
                member, ctx.guild.members
            )

            if not join_pos:
                join_pos = "Unknown"

            embed.add_field(
                name="Joined",
                value=f'{(await self.get_member_join_date(member)).strftime("%B %d, %Y")}',
                inline=True,
            )
            embed.add_field(
                name="Join Position", value=f"{join_pos}/{max_members}", inline=True
            )
            embed.add_field(
                name=f"Roles ({len(member.roles) - 1})",
                value=_get_roles(member.roles),
                inline=False,
            )

        embed.set_thumbnail(url=member.avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="avatar", aliases=["pfp", "avy"])
    @commands.guild_only()
    async def avatar(
        self,
        ctx,
        *,
        person: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ] = None,
    ):
        """View someone's avatar in detail

        **Example**
             `{PREFIX}{COMMAND}`
             `{PREFIX}{COMMAND} @DerJonas`
             `{PREFIX}{COMMAND} DerJonas`
             `{PREFIX}{COMMAND} DerJonas#8109`
        """

        member: discord.Member = person or ctx.author
        avatar_png = member.avatar.with_size(4096).url
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
            if self.cached_sorted_veterans_on_democraciv:
                sorted_first_15_members = self.cached_sorted_veterans_on_democraciv
            else:
                vets = await self.bot.db.fetch(
                    "SELECT member FROM original_join_date ORDER BY join_date LIMIT 15"
                )

                self.cached_sorted_veterans_on_democraciv = sorted_first_15_members = [
                    self.bot.get_user(r["member"]) for r in vets
                ]

        # If cache is empty OR ctx not on democraciv guild, calculate & sort again
        else:
            guild_members_without_bots = [
                member for member in ctx.guild.members if not member.bot
            ]
            guild_members_without_bots.sort(key=lambda m: m.joined_at)
            sorted_first_15_members = guild_members_without_bots[:15]

        # Send veterans
        message = [
            "These are the first 15 people who joined this server.\nBot accounts are not counted.\n"
        ]

        for position, veteran in enumerate(sorted_first_15_members, start=1):
            fmt = f"{veteran.mention} {veteran}" if veteran else "*Unknown User*"
            message.append(f"{position}. {fmt}")

        embed = text.SafeEmbed(description="\n".join(message))
        embed.set_author(name=f"Veterans of {ctx.guild.name}", icon_url=ctx.guild_icon)
        await ctx.send(embed=embed)

    @commands.command()
    async def lyrics(self, ctx, *, query: str):
        """Find lyrics for a song

        **Usage**
            `{PREFIX}{COMMAND} <query>` to search for lyrics that match your query
        """

        if len(query) < 3:
            return await ctx.send(
                f"{config.NO} The query to search for has to be more than 3 characters!"
            )

        async with ctx.typing():
            async with self.bot.session.get(
                f"https://some-random-api.ml/lyrics?title={query}"
            ) as response:
                if response.status == 200:
                    lyrics = await response.json()
                else:
                    return await ctx.send(
                        f"{config.NO} Genius could not suggest me anything related to `{query}`."
                    )

        try:
            lyrics["lyrics"] = lyrics["lyrics"].replace("[", "**[").replace("]", "]**")

            if len(lyrics["lyrics"]) <= 2048:
                embed = text.SafeEmbed(
                    title=lyrics["title"],
                    description=lyrics["lyrics"],
                    colour=0x2F3136,
                    url=lyrics["links"]["genius"],
                )
                embed.set_author(name=lyrics["author"])
                embed.set_thumbnail(url=lyrics["thumbnail"]["genius"])
                return await ctx.send(embed=embed)

            pages = paginator.SimplePages(
                entries=lyrics["lyrics"].splitlines(),
                title=lyrics["title"],
                title_url=lyrics["links"]["genius"],
                author=lyrics["author"],
                thumbnail=lyrics["thumbnail"]["genius"],
                colour=0x2F3136,
            )

        except KeyError:
            return await ctx.send(
                f"{config.NO} Genius could not suggest me anything related to `{query}`."
            )

        await pages.start(ctx)

    @commands.command(name="shortenurl", aliases=["tiny", "tinyurl", "shortenlink"])
    async def tinyurl(self, ctx, *, url: str):
        """Shorten a link"""
        if len(url) <= 3:
            return await ctx.send(f"{config.NO} That doesn't look like a valid URL.")

        tiny_url = await self.bot.tinyurl(url)

        if tiny_url is None:
            return await ctx.send(
                f"{config.NO} The URL shortening service returned an error, "
                f"try again in a few minutes."
            )

        await ctx.send(f"<{tiny_url}>")

    @commands.command(name="whohas", aliases=["roleinfo"])
    @commands.guild_only()
    async def whohas(
        self,
        ctx,
        *,
        role: Fuzzy[
            CaseInsensitiveRole,
            DemocracivCaseInsensitiveRole,
            PoliticalParty,
            FuzzySettings(
                no_choice_exception=f"{config.NO} There is no role on this or the "
                f"Democraciv server that matches `{{argument}}`.",
                weights=(5, 2, 2),
            ),
        ],
    ):
        """Detailed information about a role"""

        if isinstance(role, PoliticalParty):
            role = role.role

        await self.role_info(ctx, role)

    async def role_info(self, ctx, role: discord.Role):
        if role is None:
            return await ctx.send(
                f"{config.NO} `role` is neither a role on this server, nor on the Democraciv server."
            )

        if role.guild.id != ctx.guild.id:
            description = f":warning:  This role is from the {self.bot.dciv.name} server, not from this server!"
            role_name = role.name
        else:
            description = ""
            role_name = f"{role.name} {role.mention}"

        if role != role.guild.default_role:
            role_members = (
                "\n".join([f"{member.mention} {member}" for member in role.members])
                or "-"
            )
        else:
            role_members = "*Too long to display.*"

        embed = text.SafeEmbed(
            title="Role Information", description=description, colour=role.colour
        )

        embed.add_field(name="Role", value=role_name, inline=False)
        embed.add_field(name="ID", value=role.id, inline=False)
        embed.add_field(
            name="Created on", value=role.created_at.strftime("%B %d, %Y"), inline=True
        )
        embed.add_field(name="Colour", value=role.colour, inline=True)
        embed.add_field(
            name=f"Members ({len(role.members)})", value=role_members, inline=False
        )
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

        await ctx.send(
            f":arrows_counterclockwise: Random number ({start} - {end}): **{result}**"
        )

    @random.command(name="choose", aliases=["choice"])
    async def random_choice(self, ctx, *choices):
        """Make me choose between things

        **Example**
          `{PREFIX}{COMMAND} "Civ 4" "Civ 5" "Civ 6" "Civ BE"`"""

        await ctx.send(f":tada: The winner is: **{random.choice(choices)}**")

    @random.command(name="coin", aliases=["flip", "coinflip"])
    async def random_coin(self, ctx):
        """Flip a coin"""

        coins = ["Heads", "Tails"]
        return await ctx.send(f":arrows_counterclockwise: **{random.choice(coins)}**")

    @commands.command(name="vibecheck", hidden=True)
    @commands.guild_only()
    async def vibecheck(
        self,
        ctx,
        *,
        person: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ] = None,
    ):
        """vibecheck"""

        member = person or ctx.author

        not_vibing = [
            "https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg",
            "https://s3.amazonaws.com/media.thecrimson.com/photos/2019/11/18/194724_1341037.png",
            "https://i.kym-cdn.com/photos/images/newsfeed/001/574/493/3ab.jpg",
            "https://i.imgflip.com/3ebtvt.jpg",
            "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT814jrNuqJsaVVHGqWw_0snlcysLN5fLpocEYrx6hzkgXYx7RV5w&s",
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
                            return await ctx.send(
                                f"{config.NO} Could not download dog video :("
                            )

                        if int(other.headers["Content-Length"]) >= filesize:
                            return await ctx.send(
                                f"{config.NO} Video was too big to upload, watch it here instead: {url}"
                            )

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

        async with self.bot.session.get(
            "https://api.thecatapi.com/v1/images/search"
        ) as response:
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

    @commands.command(name="roll", aliases=["r", "dice"])
    async def roll(self, ctx, *, dices="1d20"):
        """Roll some dice

        **Supported Notation**
        - Dice rolls take the form `NdX`, where `N` is the number of dice to roll, and `X` are the faces of the dice. For example, `1d6` is one six-sided die.

        - A dice roll can be followed by an `Ln` or `Hn`, where it will discard the lowest `n` rolls or highest `n` rolls, respectively. So `2d20L1` means to roll two `d20`s and discard the lower one (advantage).

        - A dice roll can be part of a mathematical expression, such as `1d4 + 5`.

        **Example**
          `{PREFIX}{COMMAND}` will roll 1d20
          `{PREFIX}{COMMAND} 1d6` will roll a d6
          `{PREFIX}{COMMAND} (2d20L1) + 1d4 + 5` will roll 2d20s, discard the lower one, and add 1d4 and 5 to the result

        *Full notation can be found [here.](https://xdice.readthedocs.io/en/latest/dice_notation.html)*
        """

        js = await self.bot.api_request("POST", "roll", json={"dices": dices})

        if "error" in js:
            raise commands.BadArgument()

        if "result" in js:
            await ctx.reply(js["result"])


def setup(bot):
    bot.add_cog(Utility(bot))
