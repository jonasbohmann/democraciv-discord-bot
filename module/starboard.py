import typing
import aiohttp
import asyncpg
import discord
import asyncio
import datetime
import itertools

from config import config, token
from discord.ext import commands, tasks

from util import mk


class Starboard(commands.Cog):
    """The Starboard. If a message on the Democraciv Guild has at least 4 :star: reactions,
    it will be posted to the Starboard channel and in a weekly summary to the subreddit every Saturday."""

    def __init__(self, bot):
        self.bot = bot
        self.star_emoji = config.STARBOARD_STAR_EMOJI
        self.star_threshold = config.STARBOARD_MIN_STARS
        self.bearer_token = None

        if config.STARBOARD_ENABLED and config.STARBOARD_REDDIT_SUMMARY_ENABLED:
            if not config.REDDIT_SUBREDDIT:
                print("[BOT] ERROR - Starboard Reddit post is enabled but no subreddit was provided in config.py!")
            elif not token.REDDIT_CLIENT_ID:
                print("[BOT] ERROR - Starboard Reddit post is enabled but no Reddit Client ID "
                      "was provided in token.py!")
            elif not token.REDDIT_CLIENT_SECRET:
                print("[BOT] ERROR - Starboard Reddit post is enabled but no Reddit Client Secret was provided "
                      "in token.py!")
            elif not token.REDDIT_REFRESH_TOKEN:
                print("[BOT] ERROR - Starboard Reddit post is enabled but no Reddit Refresh Token was provided"
                      " in token.py!")
            else:
                self.weekly_starboard_to_reddit_task.start()

    def __del__(self):
        self.weekly_starboard_to_reddit_task.cancel()

    async def refresh_reddit_bearer_token(self):
        """Gets a new access_token for the Reddit API with a refresh token that was previously acquired by following
         this guide: https://github.com/reddit-archive/reddit/wiki/OAuth2"""

        auth = aiohttp.BasicAuth(login=token.REDDIT_CLIENT_ID, password=token.REDDIT_CLIENT_SECRET)
        post_data = {"grant_type": "refresh_token", "refresh_token": token.REDDIT_REFRESH_TOKEN}
        headers = {"User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos"}

        async with self.bot.session.post("https://www.reddit.com/api/v1/access_token",
                                         data=post_data, auth=auth, headers=headers) as response:
            r = await response.json()
            self.bearer_token = r['access_token']

    async def post_to_reddit(self, data: dict) -> bool:
        """Submits weekly starboard to r/Democraciv"""

        await self.refresh_reddit_bearer_token()

        headers = {"Authorization": f"bearer {self.bearer_token}",
                   "User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos"}

        try:
            async with self.bot.session.post("https://oauth.reddit.com/api/submit", data=data,
                                             headers=headers) as response:
                if response.status != 200:
                    print(f"[BOT] ERROR - Error while posting Starboard to Reddit, got status {response.status}.")
                    return False
                return True
        except Exception as e:
            print(f"[BOT] ERROR - Error while posting Starboard to Reddit: {e}")
            return False

    @staticmethod
    def group_starred_messages_by_day(starred_messages: typing.List[asyncpg.Record]) -> typing.List[
        typing.List[asyncpg.Record]]:
        """Groups a list of records of starboard_entries by the message_creation_date row."""

        def get_date(item):
            date_identifier = f"{item['message_creation_date'].year}" \
                              f"{item['message_creation_date'].month}" \
                              f"{item['message_creation_date'].day}"
            return int(date_identifier)

        groups = []

        for k, g in itertools.groupby(starred_messages, get_date):
            groups.append(list(g))

        return groups

    async def get_starred_from_last_week(self) -> typing.List[asyncpg.Record]:
        """Returns all rows from starboard_entries that are from last week and have enough stars."""

        today = datetime.datetime.utcnow().today()
        start_of_last_week = today - datetime.timedelta(days=7)

        starred_messages = await self.bot.db.fetch("SELECT * FROM starboard_entries "
                                                   "WHERE starboard_message_created_at >= $1 "
                                                   "AND starboard_message_created_at < $2 "
                                                   "AND is_posted_to_reddit = FALSE "
                                                   "ORDER BY message_creation_date",
                                                   start_of_last_week, today)

        return starred_messages

    async def get_reddit_post_content(self, starred_messages: typing.List[typing.List[asyncpg.Record]]) -> str:
        """Formats the starred messages that are about to be posted to Reddit into raw markdown."""

        intro = """ **This is a list of messages from our [Discord](https://discord.gg/AK7dYMG) that at least 4
         people marked as newsworthy.**\n\nShould there be messages that break the content policy of Reddit or are 
         against the rules of this subreddit, then please contact the Moderators.\n\nIf you don't want your Discord 
         messages being shown here, contact the Moderators.\n\n&nbsp;\n\n"""

        markdown = [intro]

        for group in starred_messages:
            title = group[0]['message_creation_date'].strftime("##%A, %B %d")
            markdown.append(title)

            for record in group:
                author = self.bot.democraciv_guild_object.get_member(record['author_id'])
                author = f"**{author.display_name}** ({str(author)})" if author is not None else "_Author left " \
                                                                                                 "Democraciv_ "

                channel = self.bot.democraciv_guild_object.get_channel(record['channel_id'])
                channel = f"**#{channel.name}**" if channel is not None else "_channel was deleted_"

                pretty_time = record['message_creation_date'].strftime("%H:%M")

                quote = [f"> {line}" for line in record['message_content'].splitlines()]

                if record['message_image_url']:
                    quote.append(f"> [Attached Image]({record['message_image_url']})")

                content = '\n'.join(quote)

                markdown.append(f"{author} [said]({record['message_jump_url']}) in "
                                f"{channel} at {pretty_time} UTC:\n{content}\n\n---\n\n")

            markdown.append("\n\n&nbsp;\n\n")

        outro = """\n\n &nbsp; \n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/) and this is 
        an automated service. Contact u/Jovanos (DerJonas#8109 on Discord) for further questions or bug reports.* """
        markdown.append(outro)

        return "\n\n".join(markdown)

    @tasks.loop(hours=12)
    async def weekly_starboard_to_reddit_task(self):
        """If today is Monday, post all entries of last week's starboard to r/Democraciv"""

        if datetime.datetime.utcnow().weekday() != 0:
            return

        new_starred_messages = await self.get_starred_from_last_week()

        if not new_starred_messages:
            return

        grouped_stars = self.group_starred_messages_by_day(new_starred_messages)

        msg = "[BOT] Posting last week's starboard to Reddit..."
        await mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL).send(msg)
        print(msg)

        today = datetime.datetime.utcnow().today()
        start_of_last_week = today - datetime.timedelta(days=7)

        post_content = await self.get_reddit_post_content(grouped_stars)
        title = f"Weekly Discord News - {start_of_last_week.strftime('%B %d')} to {today.strftime('%B %d')}"

        data = {
            "kind": "self",
            "nsfw": False,
            "sr": config.REDDIT_SUBREDDIT,
            "title": title,
            "text": post_content,
            "spoiler": False,
            "ad": False
        }

        if await self.post_to_reddit(data):
            await self.bot.db.execute("UPDATE starboard_entries SET is_posted_to_reddit = true "
                                      "WHERE starboard_message_created_at >= $1 AND starboard_message_created_at < $2",
                                      start_of_last_week, today)

    @weekly_starboard_to_reddit_task.before_loop
    async def before_starboard_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.democraciv_guild_object is None:
            await asyncio.sleep(5)

    @property
    def starboard_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.democraciv_guild_object.get_channel(config.STARBOARD_CHANNEL)

    def get_starboard_embed(self, message: discord.Message, stars: int) -> discord.Embed:
        """Returns the embed to be posted to the Starboard channel"""

        footer_text = f"{stars} star" if stars == 1 else f"{stars} stars"

        embed = self.bot.embeds.embed_builder(title="", description=message.content,
                                              colour=0xFFAC33, has_footer=False)
        embed.set_footer(text=footer_text, icon_url="https://cdn.discordapp.com/attachments/"
                                                    "639549494693724170/679824104190115911/star.png")
        embed.timestamp = message.created_at
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar_url_as(format='png'))
        embed.add_field(name="Original", value=f"[Jump]({message.jump_url})", inline=False)

        if message.embeds:
            data = message.embeds[0]
            if data.type == 'image':
                embed.set_image(url=data.url)

        if message.attachments:
            file = message.attachments[0]
            if file.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            else:
                embed.add_field(name='Attachment', value=f'[{file.filename}]({file.url})', inline=False)

        return embed

    async def verify_reaction(self, payload: discord.RawReactionActionEvent, channel: discord.abc.GuildChannel) -> bool:
        """Checks if a reaction in on_raw_reaction_add is valid for the Starboard"""

        if not config.STARBOARD_ENABLED:
            return False

        if str(payload.emoji) != self.star_emoji:
            return False

        if payload.guild_id != self.bot.democraciv_guild_object.id:
            return False

        if payload.channel_id == self.starboard_channel.id:
            return False

        if await self.bot.checks.is_channel_excluded(self.bot.democraciv_guild_object.id, payload.channel_id):
            return False

        if not isinstance(channel, discord.TextChannel):
            return False

        return True

    @commands.Cog.listener(name='on_raw_reaction_add')
    async def star_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.democraciv_guild_object.get_channel(payload.channel_id)

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

        starrer = self.bot.democraciv_guild_object.get_member(payload.user_id)

        await self.star_message(message, starrer)

    @commands.Cog.listener(name='on_raw_reaction_remove')
    async def unstar_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.democraciv_guild_object.get_channel(payload.channel_id)

        if not await self.verify_reaction(payload, channel):
            return

        message = await channel.fetch_message(payload.message_id)

        # Do this check here instead of in verify_reaction() to not waste a possibly useless API call
        if payload.user_id == message.author.id:
            return

        starrer = self.bot.democraciv_guild_object.get_member(payload.user_id)

        await self.unstar_message(message, starrer)

    async def star_message(self, message: discord.Message, starrer: discord.Member):
        """Star a message"""

        query = """INSERT INTO starboard_entries (author_id, message_id, message_content, channel_id, guild_id, 
                   message_creation_date, message_jump_url, message_image_url) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   ON CONFLICT DO NOTHING RETURNING id"""

        image_url = None

        if message.embeds:
            data = message.embeds[0]
            if data.type == 'image':
                image_url = data.url

        if message.attachments:
            file = message.attachments[0]
            if file.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                image_url = file.url

        entry_id = await self.bot.db.fetchval(query,
                                              message.author.id, message.id, message.clean_content,
                                              message.channel.id, message.guild.id, message.created_at,
                                              message.jump_url, image_url)

        if entry_id is None:
            entry_id = await self.bot.db.fetchval("SELECT id FROM starboard_entries WHERE message_id = $1", message.id)

        try:
            await self.bot.db.execute("INSERT INTO starboard_starrers (entry_id, starrer_id) VALUES ($1, $2)",
                                      entry_id, starrer.id)
        except asyncpg.UniqueViolationError:
            return

        amount_of_stars = await self.bot.db.fetchval("SELECT COUNT(*) FROM starboard_starrers WHERE entry_id = $1",
                                                     entry_id)

        if amount_of_stars < self.star_threshold:
            return

        # Send embed to starboard channel or update amount of stars in existing embed
        bot_message = await self.bot.db.fetchval("SELECT starboard_message_id FROM starboard_entries "
                                                 "WHERE id = $1", entry_id)

        embed = self.get_starboard_embed(message, amount_of_stars)

        if bot_message is None:
            # Send new message
            new_bot_message = await self.starboard_channel.send(embed=embed)
            await self.bot.db.execute("UPDATE starboard_entries SET starboard_message_id = $1,"
                                      " starboard_message_created_at = $3 WHERE id = $2",
                                      new_bot_message.id, entry_id, new_bot_message.created_at)

        else:
            # Update star amount
            try:
                old_bot_message = await self.starboard_channel.fetch_message(bot_message)
            except discord.NotFound:
                await self.bot.db.execute("DELETE FROM starboard_entries WHERE id = $1", entry_id)
            else:
                await old_bot_message.edit(embed=embed)

    async def unstar_message(self, message: discord.Message, starrer: discord.Member):
        """Unstars a message"""

        query = """DELETE FROM starboard_starrers USING starboard_entries starboard_entry
                   WHERE starboard_entry.message_id = $1 AND starboard_entry.id = starboard_starrers.entry_id 
                   AND starboard_starrers.starrer_id = $2 RETURNING starboard_starrers.entry_id,
                    starboard_entry.starboard_message_id"""

        entry = await self.bot.db.fetchrow(query, message.id, starrer.id)

        if entry is None:
            # Starboard message was removed and database entry cleared
            return

        entry_id = entry[0]
        bot_message = entry[1]

        if bot_message is None:
            return

        amount_of_stars = await self.bot.db.fetchval("SELECT COUNT(*) FROM starboard_starrers WHERE entry_id = $1",
                                                     entry_id)

        try:
            old_bot_message = await self.starboard_channel.fetch_message(bot_message)
        except discord.NotFound:
            await self.bot.db.execute("DELETE FROM starboard_entries WHERE id = $1", entry_id)
            return

        if amount_of_stars < self.star_threshold:
            # Delete starboard message if too few stars
            await old_bot_message.delete()
            await self.bot.db.execute("UPDATE starboard_entries SET starboard_message_id = NULL,"
                                      " starboard_message_created_at = NULL WHERE id = $1",
                                      entry_id)

        else:
            # Update star amount
            embed = self.get_starboard_embed(message, amount_of_stars)
            await old_bot_message.edit(embed=embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if self.starboard_channel.id != payload.channel_id:
            return

        await self.bot.db.execute("DELETE FROM starboard_entries WHERE starboard_message_id = $1", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        if self.starboard_channel.id != payload.channel_id:
            return

        messages = list(payload.message_ids)

        await self.bot.db.execute("DELETE FROM starboard_entries WHERE starboard_message_id = ANY($1::bigint[]);",
                                  messages)


def setup(bot):
    bot.add_cog(Starboard(bot))
