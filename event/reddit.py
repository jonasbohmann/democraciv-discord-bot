import html
import typing
import asyncio

import util.exceptions as exceptions

from config import config
from discord.ext import tasks, commands


class Reddit(commands.Cog):
    """Announcements for new posts on a subreddit. Does not need any API key or tokens."""

    def __init__(self, bot):
        self.bot = bot
        self.subreddit = config.REDDIT_SUBREDDIT

        if config.REDDIT_ENABLED and self.subreddit and config.REDDIT_ANNOUNCEMENT_CHANNEL:
            self.reddit_task.start()

    def __del__(self):
        self.reddit_task.cancel()

    async def get_newest_reddit_post(self) -> typing.Optional[typing.Mapping]:
        """Gets the 5 newest reddit posts."""

        async with self.bot.session.get(f"https://www.reddit.com/r/{self.subreddit}/new.json?limit=5") as response:
            if response.status == 200:
                return await response.json()

        return None

    @tasks.loop(seconds=60)
    async def reddit_task(self):
        """Checks every 60 seconds if the 5 newest reddit posts of a subreddit are new. If at least one is, send
        announcement to the specified Discord channel."""

        try:
            channel = self.bot.democraciv_guild_object.get_channel(config.REDDIT_ANNOUNCEMENT_CHANNEL)
        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "DEMOCRACIV_GUILD_ID" '
                  f'in config.py to a server I am in or disable Reddit announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_GUILD_ID)

        if channel is None:
            print("[BOT] ERROR - The REDDIT_ANNOUNCEMENT_CHANNEL id in config.py is not a channel on the"
                  " specified Democraciv guild.")
            raise exceptions.ChannelNotFoundError(config.REDDIT_ANNOUNCEMENT_CHANNEL)

        reddit_post_json = await self.get_newest_reddit_post()

        if reddit_post_json is None:
            return

        # Each check last 5 reddit posts in case we missed some in between
        for i in range(5):
            reddit_post = reddit_post_json["data"]["children"][i]["data"]

            _id = reddit_post['id']

            # Try to add post id to database
            status = await self.bot.db.execute("INSERT INTO reddit_posts (id) VALUES ($1) ON CONFLICT DO NOTHING", _id)

            # ID already in database -> post already seen
            if status == "INSERT 0 0":
                continue

            _title = reddit_post['title']
            _author = f"u/{reddit_post['author']}"
            _comments_link = f"https://reddit.com{reddit_post['permalink']}"

            try:
                _thumbnail_url = reddit_post['preview']['images'][0]['source']['url']
            except KeyError:
                _thumbnail_url = reddit_post['thumbnail']

            embed = self.bot.embeds.embed_builder(
                title=f"{config.REDDIT_LOGO}  New post on r/{self.subreddit}",
                description="", has_footer=False)
            embed.add_field(name="Thread", value=f"[{_title}]({_comments_link})", inline=False)
            embed.add_field(name="Author", value=f"{_author}", inline=False)

            if _thumbnail_url.startswith("https://"):
                _thumbnail_url = html.unescape(_thumbnail_url)
                embed.set_thumbnail(url=_thumbnail_url)

            await channel.send(embed=embed)

    @reddit_task.before_loop
    async def before_reddit_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.democraciv_guild_object is None:
            await asyncio.sleep(5)


def setup(bot):
    if config.REDDIT_ENABLED:
        bot.add_cog(Reddit(bot))
