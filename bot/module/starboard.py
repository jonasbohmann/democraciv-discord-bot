# Some parts of this were adapted from R.Danny's starboard. Credit goes to Rapptz:
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

import typing
import asyncpg
import discord
import asyncio
import datetime
import logging
import itertools

from bot.config import token, config
from discord.ext import commands, tasks

from bot.utils import context
from bot.utils.converter import CaseInsensitiveMember, CaseInsensitiveUser
from bot.utils import text


class Starboard(context.CustomCog):
    """The Starboard. If a message on the {democraciv} Server has at least 5 :star: reactions,
    it will be posted to the Starboard channel and in a weekly summary to the subreddit every Saturday."""

    def __init__(self, bot):
        super().__init__(bot)
        self.star_emoji = config.STARBOARD_STAR_EMOJI
        self.star_threshold = config.STARBOARD_MIN_STARS

        if config.STARBOARD_ENABLED and config.STARBOARD_REDDIT_SUMMARY_ENABLED:
            if not config.STARBOARD_REDDIT_SUBREDDIT:
                logging.warning(
                    "Starboard Reddit post is enabled but no subreddit was provided in config.py!"
                )
            else:
                self.weekly_starboard_to_reddit_task.start()

    def cog_unload(self):
        self.weekly_starboard_to_reddit_task.cancel()

    @staticmethod
    def group_starred_messages_by_day(
        starred_messages: typing.List[asyncpg.Record],
    ) -> typing.List[typing.List[asyncpg.Record]]:
        """Groups a list of records of starboard_entries by the message_creation_date row."""

        def get_date(item):
            date_identifier = (
                f"{item['message_creation_date'].year}"
                f"{item['message_creation_date'].month}"
                f"{item['message_creation_date'].day}"
            )
            return date_identifier

        groups = []

        for k, g in itertools.groupby(starred_messages, get_date):
            groups.append(list(g))

        return groups

    async def get_starred_from_last_week(self) -> typing.List[asyncpg.Record]:
        """Returns all rows from starboard_entries that are from last week and have enough stars."""

        today = datetime.datetime.utcnow().today()
        start_of_last_week = today - datetime.timedelta(days=7)

        starred_messages = await self.bot.db.fetch(
            "SELECT * FROM starboard_entry "
            "WHERE starboard_message_created_at >= $1 "
            "AND starboard_message_created_at < $2 "
            "AND is_posted_to_reddit = FALSE "
            "ORDER BY message_creation_date",
            start_of_last_week,
            today,
        )

        return starred_messages

    async def get_reddit_post_content(self, starred_messages: typing.List[typing.List[asyncpg.Record]]) -> str:
        """Formats the starred messages that are about to be posted to Reddit into raw markdown."""

        intro = f"""**This is a list of messages from our [Discord](https://discord.gg/AK7dYMG) that at least
                {self.star_threshold} people marked as newsworthy.**\n\nShould there be messages that 
                break the content policy of Reddit or are against the rules of this subreddit, then please contact 
                the Moderators.\n\nIf you don't want your Discord messages being shown here,
                contact the Moderators.\n\n&nbsp;\n\n"""

        markdown = [intro]

        for group in starred_messages:
            title = group[0]["message_creation_date"].strftime("##%A, %B %d")
            markdown.append(title)

            for record in group:
                channel = self.bot.dciv.get_channel(record["channel_id"])

                if not channel:
                    continue

                message = await channel.fetch_message(record["message_id"])

                if not message:
                    continue

                author = self.bot.dciv.get_member(record["author_id"])
                author = (
                    f"**{author.display_name}** ({str(author)})" if author is not None else f"_Author left {self.bot.dciv.name}_"
                )

                fmt_channel = f"**#{channel.name}**" if channel is not None else "_channel was deleted_"
                pretty_time = record["message_creation_date"].strftime("%H:%M")
                quote = [f"> {line}" for line in message.clean_content.splitlines()]

                image_url = None

                if message.embeds:
                    data = message.embeds[0]
                    if data.type == "image":
                        image_url = data.url

                if message.attachments:
                    file = message.attachments[0]
                    if file.url.lower().endswith(("png", "jpeg", "jpg", "gif", "webp")):
                        image_url = file.url

                if image_url:
                    quote.append(f"> [Attached Image]({image_url})")

                content = "\n".join(quote)

                markdown.append(
                    f"{author} [said]({message.jump_url}) in "
                    f"{fmt_channel} at {pretty_time} UTC:\n{content}\n\n---\n\n"
                )

            markdown.append("\n\n&nbsp;\n\n")

        outro = """\n\n &nbsp; \n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/) and this is
        an automated service. Contact u/Jovanos (DerJonas#8036 on Discord) for further questions or bug reports.* """
        markdown.append(outro)

        return "\n\n".join(markdown)

    async def has_posted_to_reddit_today(self) -> bool:
        async with self.bot.session.get(f"https://www.reddit.com/user/{token.REDDIT_USERNAME}.json?limit=15") as resp:
            if resp.status == 200:
                json_data = await resp.json()
            else:
                return False

            for post in json_data["data"]["children"]:
                try:
                    if (
                        post["data"]["title"].startswith("Weekly Discord News")
                        and post["data"]["subreddit"] == config.STARBOARD_REDDIT_SUBREDDIT
                    ):
                        time = datetime.date.fromtimestamp(post["data"]["created_utc"])
                        if time == datetime.date.today():
                            return True
                except KeyError:
                    continue

        return False

    @tasks.loop(hours=24)
    async def weekly_starboard_to_reddit_task(self):
        """If today is Monday, post all entries of last week's starboard to r/Democraciv"""

        if datetime.datetime.utcnow().weekday() != 0:
            return

        if await self.has_posted_to_reddit_today():
            return

        new_starred_messages = await self.get_starred_from_last_week()

        if not new_starred_messages:
            return

        grouped_stars = self.group_starred_messages_by_day(new_starred_messages)

        msg = "Posting last week's starboard to Reddit..."
        channel = await self.bot.get_channel(config.BOT_TECHNICAL_NOTIFICATIONS_CHANNEL)

        if channel:
            await channel.send(embed=text.SafeEmbed(title=msg))

        logging.info(msg)

        today = datetime.datetime.utcnow().today()
        start_of_last_week = today - datetime.timedelta(days=7)

        post_content = await self.get_reddit_post_content(grouped_stars)
        title = f"Weekly Discord News - {start_of_last_week.strftime('%B %d')} to {today.strftime('%B %d')}"

        js = {
            "subreddit": config.STARBOARD_REDDIT_SUBREDDIT,
            "title": title,
            "content": post_content
        }

        await self.bot.api_request("POST", "reddit/post", json=js)

        await self.bot.db.execute(
            "UPDATE starboard_entry SET is_posted_to_reddit = true "
            "WHERE starboard_message_created_at >= $1 AND starboard_message_created_at < $2",
            start_of_last_week,
            today,
        )

    @weekly_starboard_to_reddit_task.before_loop
    async def before_starboard_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.dciv is None:
            await asyncio.sleep(5)

    @property
    def starboard_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.dciv.get_channel(config.STARBOARD_CHANNEL)

    def get_starboard_embed(self, message: discord.Message, stars: int) -> discord.Embed:
        """Returns the embed to be posted to the Starboard channel"""

        footer_text = f"{stars} star" if stars == 1 else f"{stars} stars"

        embed = text.SafeEmbed(description=message.content, colour=0xFFAC33)
        embed.set_footer(
            text=footer_text,
            icon_url="https://cdn.discordapp.com/attachments/" "639549494693724170/679824104190115911/star.png",
        )
        embed.timestamp = message.created_at
        embed.set_author(
            name=f"{message.author.display_name} in #{message.channel.name}",
            icon_url=message.author.avatar_url_as(static_format="png"),
        )
        embed.add_field(name="Original", value=f"[Jump]({message.jump_url})", inline=False)

        if message.embeds:
            data = message.embeds[0]
            if data.type == "image":
                embed.set_image(url=data.url)

        if message.attachments:
            file = message.attachments[0]
            if file.url.lower().endswith(("png", "jpeg", "jpg", "gif", "webp")):
                embed.set_image(url=file.url)
            else:
                embed.add_field(
                    name="Attachment",
                    value=f"[{file.filename}]({file.url})",
                    inline=False,
                )

        return embed

    async def verify_reaction(self, payload: discord.RawReactionActionEvent, channel: discord.abc.GuildChannel) -> bool:
        """Checks if a reaction in on_raw_reaction_add is valid for the Starboard"""

        if not config.STARBOARD_ENABLED:
            return False

        if str(payload.emoji) != self.star_emoji:
            return False

        if payload.guild_id != self.bot.dciv.id:
            return False

        if payload.channel_id == self.starboard_channel.id:
            return False

        if await self.bot.is_channel_excluded(self.bot.dciv.id, payload.channel_id):
            return False

        if not isinstance(channel, discord.TextChannel):
            return False

        return True

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def star_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.dciv.get_channel(payload.channel_id)

        if not await self.verify_reaction(payload, channel):
            return

        message = await channel.fetch_message(payload.message_id)

        # Do this check here instead of in verify_reaction() to not waste a possibly useless API call
        if payload.user_id == message.author.id:
            return

        max_age = datetime.datetime.utcnow() - datetime.timedelta(days=config.STARBOARD_MAX_AGE)

        if message.created_at < max_age:
            return

        if (not message.content and len(message.attachments) == 0) or message.type is not discord.MessageType.default:
            return

        starrer = self.bot.dciv.get_member(payload.user_id)
        await self.star_message(message, starrer)

    @commands.Cog.listener(name="on_raw_reaction_remove")
    async def unstar_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.dciv.get_channel(payload.channel_id)

        if not await self.verify_reaction(payload, channel):
            return

        message = await channel.fetch_message(payload.message_id)

        # Do this check here instead of in verify_reaction() to not waste a possibly useless API call
        if payload.user_id == message.author.id:
            return

        starrer = self.bot.dciv.get_member(payload.user_id)
        await self.unstar_message(message, starrer)

    async def star_message(self, message: discord.Message, starrer: discord.Member):
        """Star a message"""

        query = """INSERT INTO starboard_entry (author_id, message_id, channel_id, guild_id,
                   message_creation_date, message_jump_url) VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT DO NOTHING RETURNING id"""

        entry_id = await self.bot.db.fetchval(
            query,
            message.author.id,
            message.id,
            message.channel.id,
            message.guild.id,
            message.created_at,
            message.jump_url,
        )

        if entry_id is None:
            entry_id = await self.bot.db.fetchval("SELECT id FROM starboard_entry WHERE message_id = $1", message.id)

        try:
            await self.bot.db.execute(
                "INSERT INTO starboard_starrer (entry_id, starrer_id) VALUES ($1, $2)",
                entry_id,
                starrer.id,
            )
        except asyncpg.UniqueViolationError:
            return

        amount_of_stars = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_starrer WHERE entry_id = $1", entry_id
        )

        if amount_of_stars < self.star_threshold:
            return

        # Send embed to starboard channel or update amount of stars in existing embed
        bot_message = await self.bot.db.fetchval(
            "SELECT starboard_message_id FROM starboard_entry " "WHERE id = $1",
            entry_id,
        )

        embed = self.get_starboard_embed(message, amount_of_stars)

        if bot_message is None:
            # Send new message
            new_bot_message = await self.starboard_channel.send(embed=embed)
            await self.bot.db.execute(
                "UPDATE starboard_entry SET starboard_message_id = $1,"
                " starboard_message_created_at = $3 WHERE id = $2",
                new_bot_message.id,
                entry_id,
                new_bot_message.created_at,
            )

        else:
            # Update star amount
            try:
                old_bot_message = await self.starboard_channel.fetch_message(bot_message)
            except discord.NotFound:
                await self.bot.db.execute("DELETE FROM starboard_entry WHERE id = $1", entry_id)
            else:
                await old_bot_message.edit(embed=embed)

    async def unstar_message(self, message: discord.Message, starrer: discord.Member):
        """Unstars a message"""

        query = """DELETE FROM starboard_starrer USING starboard_entry
                   WHERE starboard_entry.message_id = $1 AND starboard_entry.id = starboard_starrer.entry_id 
                   AND starboard_starrer.starrer_id = $2 RETURNING starboard_starrer.entry_id,
                    starboard_entry.starboard_message_id"""

        entry = await self.bot.db.fetchrow(query, message.id, starrer.id)

        if entry is None:
            # Starboard message was removed and database entry cleared
            return

        entry_id = entry[0]
        bot_message = entry[1]

        if bot_message is None:
            return

        amount_of_stars = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_starrer WHERE entry_id = $1", entry_id
        )

        try:
            old_bot_message = await self.starboard_channel.fetch_message(bot_message)
        except discord.NotFound:
            await self.bot.db.execute("DELETE FROM starboard_entry WHERE id = $1", entry_id)
            return

        if amount_of_stars < self.star_threshold:
            # Delete starboard message if too few stars
            await old_bot_message.delete()
            await self.bot.db.execute(
                "UPDATE starboard_entry SET starboard_message_id = NULL,"
                " starboard_message_created_at = NULL WHERE id = $1",
                entry_id,
            )

        else:
            # Update star amount
            embed = self.get_starboard_embed(message, amount_of_stars)
            await old_bot_message.edit(embed=embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if self.starboard_channel and self.starboard_channel.id != payload.channel_id:
            return

        await self.bot.db.execute(
            "DELETE FROM starboard_entry WHERE starboard_message_id = $1",
            payload.message_id,
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        if self.starboard_channel and self.starboard_channel.id != payload.channel_id:
            return

        messages = list(payload.message_ids)

        await self.bot.db.execute(
            "DELETE FROM starboard_entry WHERE starboard_message_id = ANY($1::bigint[]);",
            messages,
        )

    @commands.group(
        name="stars",
        aliases=["starboard", "star", "starstats", "starsstats"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def starboard(
        self,
        ctx,
        *,
        member: typing.Union[CaseInsensitiveMember, CaseInsensitiveUser] = None,
    ):
        """Statistics about our Starboard

        **Usage**
             `{PREFIX}{COMMAND}` for statistics on the general starboard usage
             `{PREFIX}{COMMAND} <member>` for statistics on the starboard usage of a specific member"""
        if member is None:
            await self.star_overall_stats(ctx)
        else:
            await self.star_member_stats(ctx, member)

    @staticmethod
    def records_to_value(records, fmt=None, default="-"):
        if not records:
            return default

        emoji = 0x1F947  # :first_place:
        fmt = fmt or (lambda o: o)
        return "\n".join(f'{chr(emoji + i)} {fmt(r["ID"])} ({r["Stars"]} stars)' for i, r in enumerate(records))

    async def star_member_stats(self, ctx, member):
        embed = text.SafeEmbed(colour=0xFFAC33)
        embed.set_author(name=member.display_name, icon_url=member.avatar_url_as(static_format="png"))

        stars_received = await self.bot.db.fetchval(
            """SELECT COUNT(*)
                                                    FROM starboard_starrer
                                                    INNER JOIN starboard_entry entry
                                                    ON entry.id=starboard_starrer.entry_id
                                                    WHERE entry.author_id=$1;""",
            member.id,
        )

        stars_given = await self.bot.db.fetchval(
            """SELECT COUNT(*)
                                                    FROM starboard_starrer
                                                    INNER JOIN starboard_entry entry
                                                    ON entry.id=starboard_starrer.entry_id
                                                    WHERE starboard_starrer.starrer_id=$1;""",
            member.id,
        )

        top_three_starred = await self.bot.db.fetch(
            """SELECT starboard_entry.message_jump_url, COUNT(*) AS "stars"
                                                            FROM starboard_starrer
                                                            INNER JOIN starboard_entry 
                                                            ON starboard_entry.id=starboard_starrer.entry_id
                                                            WHERE starboard_entry.author_id=$1
                                                            GROUP BY starboard_entry.message_jump_url
                                                            ORDER BY "stars" DESC
                                                            LIMIT 3;""",
            member.id,
        )

        top_three_starred_fmt = []

        for record in top_three_starred:
            top_three_starred_fmt.append(
                {
                    "ID": f"[Jump to Message]({record['message_jump_url']})",
                    "Stars": record["stars"],
                }
            )

        query = """SELECT COUNT(*) FROM starboard_entry WHERE starboard_message_id IS NOT NULL AND author_id = $1;"""
        messages_starred = await self.bot.db.fetchval(query, member.id)

        embed.add_field(name="Messages on the Starboard", value=messages_starred, inline=False)
        embed.add_field(name="Stars Received", value=stars_received, inline=True)
        embed.add_field(name="Stars Given", value=stars_given, inline=True)
        embed.add_field(
            name="Top Starred Messages",
            value=self.records_to_value(top_three_starred_fmt),
            inline=False,
        )
        await ctx.send(embed=embed)

    async def star_overall_stats(self, ctx):
        total_starred_messages = await self.bot.db.fetchval("SELECT COUNT(*) FROM starboard_entry")
        total_stars = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_starrer INNER JOIN starboard_entry "
            "entry ON entry.id = starboard_starrer.entry_id;"
        )

        embed = text.SafeEmbed(
            title="Starboard Stats",
            description=f"So far, there are {total_starred_messages} messages starred"
            f" with a total of {total_stars} stars.",
            colour=0xFFAC33,
        )

        # this big query fetches 3 things:
        # top 3 starred posts (Type 3)
        # top 3 most starred authors  (Type 1)
        # top 3 star givers (Type 2)
        query = """WITH t AS (
                           SELECT
                               entry.author_id AS entry_author_id,
                               starboard_starrer.starrer_id,
                               entry.starboard_message_id
                           FROM starboard_starrer
                           INNER JOIN starboard_entry entry
                           ON entry.id = starboard_starrer.entry_id
                       )
                       (
                           SELECT t.entry_author_id AS "ID", 1 AS "Type", COUNT(*) AS "Stars"
                           FROM t
                           WHERE t.entry_author_id IS NOT NULL
                           GROUP BY t.entry_author_id
                           ORDER BY "Stars" DESC
                           LIMIT 3
                       )
                       UNION ALL
                       (
                           SELECT t.starrer_id AS "ID", 2 AS "Type", COUNT(*) AS "Stars"
                           FROM t
                           GROUP BY t.starrer_id
                           ORDER BY "Stars" DESC
                           LIMIT 3
                       )
                       UNION ALL
                       (
                           SELECT t.starboard_message_id AS "ID", 3 AS "Type", COUNT(*) AS "Stars"
                           FROM t
                           WHERE t.starboard_message_id IS NOT NULL
                           GROUP BY t.starboard_message_id
                           ORDER BY "Stars" DESC
                           LIMIT 3
                       );"""

        records = await self.bot.db.fetch(query)
        starred_posts = [r for r in records if r["Type"] == 3]
        starred_posts_with_link = []

        for post in starred_posts:
            record = await self.bot.db.fetchval(
                "SELECT message_jump_url FROM starboard_entry " "WHERE starboard_message_id = $1",
                post["ID"],
            )
            starred_posts_with_link.append({"ID": f"[Jump to Message]({record})", "Stars": post["Stars"]})

        embed.add_field(
            name="Top Starred Messages",
            value=self.records_to_value(starred_posts_with_link),
            inline=False,
        )

        to_mention = lambda o: f"<@{o}>"

        star_receivers = [r for r in records if r["Type"] == 1]
        value = self.records_to_value(star_receivers, to_mention, default="No one!")
        embed.add_field(name="Top Star Receivers", value=value, inline=False)

        star_givers = [r for r in records if r["Type"] == 2]
        value = self.records_to_value(star_givers, to_mention, default="No one!")
        embed.add_field(name="Top Star Givers", value=value, inline=False)

        if self.starboard_channel is not None:
            embed.set_footer(
                text="Collecting stars since",
                icon_url="https://cdn.discordapp.com/attachments/" "639549494693724170/679824104190115911/star.png",
            )
            embed.timestamp = self.starboard_channel.created_at
        await ctx.send(embed=embed)


def setup(bot):
    if config.STARBOARD_ENABLED:
        bot.add_cog(Starboard(bot))
