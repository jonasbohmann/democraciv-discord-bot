import asyncio
import html

import aiohttp

import config
import discord

import util.exceptions as exceptions

from discord.ext import tasks


class Reddit:

    def __init__(self, bot):
        self.bot = bot
        self.subreddit = config.getReddit()['subreddit']
        self.reddit_task.start()

    def __del__(self):
        self.reddit_task.cancel()

    async def get_newest_reddit_post(self):
        try:
            async with self.bot.session.get(f"https://www.reddit.com/r/{self.subreddit}/new.json?limit=5") as response:
                return await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in Reddit session.get()!\n")
            return None

    @tasks.loop(seconds=30)
    async def reddit_task(self):

        try:
            channel = discord.utils.get(self.bot.democraciv_guild_object.text_channels,
                                        name=config.getReddit()['redditAnnouncementChannel'])
        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable Twitch announcements.')
            raise exceptions.GuildNotFoundError(config.getConfig()["democracivServerID"])

        if channel is None:
            raise exceptions.ChannelNotFoundError(config.getReddit()['redditAnnouncementChannel'])

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
                title=f":mailbox_with_mail: New post on r/{self.subreddit}",
                description="", time_stamp=True)
            embed.add_field(name="Thread", value=f"[{_title}]({_comments_link})", inline=False)
            embed.add_field(name="Author", value=f"{_author}", inline=False)

            if _thumbnail_url.startswith("https://"):
                _thumbnail_url = html.unescape(_thumbnail_url)
                embed.set_thumbnail(url=_thumbnail_url)

            await channel.send(embed=embed)

    @reddit_task.before_loop
    async def before_reddit_task(self):
        await self.bot.wait_until_ready()
