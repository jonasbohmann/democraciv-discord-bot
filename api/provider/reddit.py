import asyncio
import copy
import datetime
import html
import logging
import typing
import aiohttp

from discord.ext import tasks
from discord import Embed


class RedditManager:
    def __init__(self, *, db):
        self.db = db
        self.session = None
        asyncio.get_event_loop().create_task(self.make_aiohttp_session())
        self._scrapers: typing.Dict[str, SubredditScraper] = dict()

    async def make_aiohttp_session(self):
        self.session = aiohttp.ClientSession()

    @property
    def status(self):
        return len(self._scrapers)

    async def get_webhooks_per_guild(self, guild_id: int):
        records = await self.db.get_reddit_webhooks_by_guild(guild_id)
        webhooks = []

        for record in records:
            webhooks.append({'id': record['id'],
                             'subreddit': record['subreddit'],
                             'webhook_id': record['webhook_id']})

        return webhooks

    def clear_scrapers(self):
        for scraper in self._scrapers.values():
            scraper.stop()
            del scraper

        self._scrapers = dict()

    async def start_scraper(self, *, subreddit: str, webhook_url: str):
        if subreddit in self._scrapers:
            self._scrapers[subreddit].add_webhook(webhook_url)
        else:
            scraper = SubredditScraper(db=self.db, session=self.session, subreddit=subreddit)
            scraper.add_webhook(webhook_url)
            self._scrapers[subreddit] = scraper
            await scraper.start()

        logging.info(f"added subreddit scraper for r/{subreddit} to {webhook_url}")

    async def add_scraper(self, config):
        await self.db.add_reddit_scraper(config)
        await self.start_scraper(subreddit=config.subreddit, webhook_url=config.webhook_url)

    async def remove_scraper(self, config):
        subreddit, webhook_url, channel_id = await self.db.remove_reddit_scraper(config.id)
        await self.stop_scraper(subreddit=subreddit, webhook_url=webhook_url)
        return {"subreddit": subreddit, "webhook_url": webhook_url, "channel_id": channel_id}

    async def stop_scraper(self, *, subreddit: str, webhook_url: str):
        if subreddit not in self._scrapers:
            return

        if len(self._scrapers[subreddit].webhook_urls) == 1 and webhook_url in self._scrapers[subreddit].webhook_urls:
            del self._scrapers[subreddit]
        else:
            self._scrapers[subreddit].webhook_urls.remove(webhook_url)


class RedditPost:
    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id")
        self.title: str = kwargs.get("title")
        self.author: str = kwargs.get("author")
        self._link: str = kwargs.get("permalink")
        self.subreddit: str = kwargs.get("subreddit")
        self._thumbnail: typing.Optional[str]

        try:
            self._thumbnail = kwargs['preview']['images'][0]['source']['url']
        except KeyError:
            self._thumbnail = None

        self._created_utc: float = kwargs.get("created_utc")

    def to_embed(self):
        e = Embed(title=f"<:reddit:660114002533285888>   New post on r/{self.subreddit}", colour=16723228)
        e.add_field(name="Thread", value=f"[{self.title}]({self.link})", inline=False)
        e.add_field(name="Author", value=f"u/{self.author}", inline=False)
        return e.to_dict()

    @property
    def link(self) -> str:
        return f"https://reddit.com/{self._link}"

    @property
    def short_link(self) -> str:
        return f"https://redd.it/{self.id}"

    @property
    def timestamp(self) -> datetime.datetime:
        return datetime.datetime.utcfromtimestamp(self._created_utc)

    @property
    def thumbnail(self) -> typing.Optional[str]:
        if self._thumbnail is None:
            return None

        return html.unescape(self._thumbnail)


class SubredditScraper:
    def __init__(self, *, db, subreddit: str, session: aiohttp.ClientSession, post_limit: typing.Optional[int] = 1):
        self.subreddit = subreddit
        self.webhook_urls = set()
        self.db = db
        self.post_limit = post_limit
        self._session = session
        self._task = None

    def __del__(self):
        self.stop()

    def add_webhook(self, webhook_url: str):
        self.webhook_urls.add(webhook_url)

    async def start(self):
        self._task = copy.copy(self.reddit_task)
        self._task.start()

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def send_webhook(self, reddit_post: RedditPost):
        post_data = {"embeds": [reddit_post.to_embed()]}

        for webhook in self.webhook_urls:
            async with self._session.post(url=webhook, json=post_data) as response:
                if response.status not in (200, 204):
                    logging.error(f"error while sending reddit webhook: {response.status} {await response.text()}")

    async def get_newest_reddit_post(self) -> typing.Optional[typing.Dict]:
        async with self._session.get(
                f"https://www.reddit.com/r/{self.subreddit}/new.json?limit={self.post_limit}") as response:
            if response.status == 200:
                return await response.json()

    @tasks.loop(seconds=5)
    async def reddit_task(self):
        reddit_json = await self.get_newest_reddit_post()

        if reddit_json is None:
            return

        for post_json in reddit_json["data"]["children"]:
            reddit_post_json = post_json["data"]
            post_id = reddit_post_json['id']

            if not await self.db.is_reddit_post_new(post_id):
                continue

            reddit_post = RedditPost(**reddit_post_json)
            await self.send_webhook(reddit_post)
