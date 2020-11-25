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
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.make_aiohttp_session())
        self._scrapers: typing.Dict[str, SubredditScraper] = dict()
        self._loop.create_task(self._bulk_start_all_scraper())
        self._lock = asyncio.Lock()

    async def make_aiohttp_session(self):
        self.session = aiohttp.ClientSession()

    async def refresh_reddit_bearer_token(self):
        """Gets a new access_token for the Reddit API with a refresh token that was previously acquired by following
        this guide: https://github.com/reddit-archive/reddit/wiki/OAuth2"""

        auth = aiohttp.BasicAuth(login=token.REDDIT_CLIENT_ID, password=token.REDDIT_CLIENT_SECRET)
        post_data = {
            "grant_type": "refresh_token",
            "refresh_token": token.REDDIT_REFRESH_TOKEN,
        }
        headers = {"User-Agent": f"democraciv-discord-bot by DerJonas - u/Jovanos"}

        async with self.session.post(
                "https://www.reddit.com/api/v1/access_token",
                data=post_data,
                auth=auth,
                headers=headers,
        ) as response:
            if response.status == 200:
                r = await response.json()
                self.bearer_token = r["access_token"]

    async def post_to_reddit(self, data: dict) -> bool:
        """Submit post to specified subreddit"""

        await self.refresh_reddit_bearer_token()

        headers = {
            "Authorization": f"bearer {self.bearer_token}",
            "User-Agent": f"democraciv-discord-bot by DerJonas - u/Jovanos",
        }

        try:
            async with self.session.post(
                    "https://oauth.reddit.com/api/submit", data=data, headers=headers
            ) as response:
                if response.status != 200:
                    logging.error(f"Error while posting to Reddit, got status {response.status}.")
                    return False
                return True
        except Exception as e:
            logging.error(f"Error while posting to Reddit: {e}")
            return False

    @property
    def status(self):
        return len(self._scrapers)

    async def get_webhooks_per_guild(self, guild_id: int):
        records = await self.db.pool.fetch(
            "SELECT id, subreddit, webhook_id, webhook_url FROM reddit_webhook WHERE guild_id = $1", guild_id)
        return [dict(r) for r in records]

    def clear_scrapers(self):
        for scraper in self._scrapers.values():
            scraper.stop()
            del scraper

        self._scrapers = dict()

    async def clear_scraper_per_guild(self, guild_id: int):
        scraper = await self.get_webhooks_per_guild(guild_id)

        for scrap in scraper:
            self._loop.create_task(self.remove_scraper(scrap["id"], guild_id))

        return scraper

    async def _bulk_start_all_scraper(self):
        if not self.db.ready:
            await asyncio.sleep(5)

        scraper = await self.db.pool.fetch("SELECT subreddit, webhook_url FROM reddit_webhook")

        for scrap in scraper:
            self._loop.create_task(self.start_scraper(subreddit=scrap['subreddit'], webhook_url=scrap['webhook_url']))

        logging.info(f"started reddit {len(scraper)} scraper")

    async def start_scraper(self, *, subreddit: str, webhook_url: str):
        async with self._lock:
            if subreddit in self._scrapers:
                self._scrapers[subreddit].add_webhook(webhook_url)
            else:
                scraper = SubredditScraper(db=self.db, session=self.session, subreddit=subreddit)
                scraper.add_webhook(webhook_url)
                self._scrapers[subreddit] = scraper
                scraper.start()

            logging.info(f"Added subreddit scraper for r/{subreddit} to {webhook_url}")

    async def add_scraper(self, config):
        await self.db.pool.execute("INSERT INTO reddit_webhook "
                                   "(subreddit, webhook_id, webhook_url, guild_id, channel_id) "
                                   "VALUES ($1, $2, $3, $4, $5)",
                                   config.subreddit,
                                   config.webhook_id,
                                   config.webhook_url,
                                   config.guild_id,
                                   config.channel_id)

        await self.start_scraper(subreddit=config.subreddit, webhook_url=config.webhook_url)

    async def remove_scraper(self, scraper_id, guild_id):
        record = await self.db.pool.fetchrow(
            "DELETE FROM reddit_webhook WHERE id = $1 AND guild_id = $2 RETURNING subreddit, webhook_url, channel_id",
            scraper_id,
            guild_id,
        )

        if not record:
            return {"error": "scraper not found"}

        self._loop.create_task(self.stop_scraper(subreddit=record['subreddit'], webhook_url=record['webhook_url']))
        return dict(record)

    async def stop_scraper(self, *, subreddit: str, webhook_url: str):
        if subreddit not in self._scrapers:
            return

        async with self._lock:
            if len(self._scrapers[subreddit].webhook_urls) == 1 and webhook_url in self._scrapers[
                subreddit].webhook_urls:
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
            self._thumbnail = kwargs["preview"]["images"][0]["source"]["url"]
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

    def start(self):
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
                    logging.error(f"Error while sending reddit webhook: {response.status} {await response.text()}")

    async def get_newest_reddit_post(self) -> typing.Optional[typing.Dict]:
        async with self._session.get(
                f"https://www.reddit.com/r/{self.subreddit}/new.json?limit={self.post_limit}"
        ) as response:
            if response.status == 200:
                return await response.json()

    @tasks.loop(seconds=5)
    async def reddit_task(self):
        reddit_json = await self.get_newest_reddit_post()

        if reddit_json is None:
            return

        for post_json in reddit_json["data"]["children"]:
            reddit_post_json = post_json["data"]
            post_id = reddit_post_json["id"]

            status = await self.db.pool.execute("INSERT INTO reddit_post (id) VALUES ($1) ON CONFLICT DO NOTHING", post_id)
            is_new = False if status == "INSERT 0 0" else True

            if not is_new:
                continue

            reddit_post = RedditPost(**reddit_post_json)
            await self.send_webhook(reddit_post)
