import copy
import datetime
import html
import json
import traceback
import typing
import aiohttp

from discord.ext import tasks
from discord import Embed

from api.provider.abc import ProviderManager

from fastapi.logger import logger


class RedditManager(ProviderManager):
    provider = "Reddit"
    target = "subreddit"
    table = "reddit_webhook"

    def __init__(self, *, db, token_path, **kwargs):
        super().__init__(db=db, **kwargs)
        self._webhooks: typing.Dict[str, SubredditScraper] = {}
        self._token_path = token_path
        self._get_token()
        self._loop.create_task(self.refresh_reddit_bearer_token())

    def _get_token(self):
        with open(self._token_path, "r") as token_file:
            token_json = json.load(token_file)
            self.REDDIT_CLIENT_ID: str = token_json["reddit"]["client_id"]
            self.REDDIT_CLIENT_SECRET: str = token_json["reddit"]["client_secret"]
            self.REDDIT_REFRESH_TOKEN: str = token_json["reddit"]["refresh_token"]
            self.REDDIT_BEARER_TOKEN: str = token_json["reddit"]["bearer_token"]

    def _save_token(self):
        with open(self._token_path, "r") as token_file:
            js = json.load(token_file)

        js["reddit"]["bearer_token"] = self.REDDIT_BEARER_TOKEN

        with open(self._token_path, "w") as token_file:
            json.dump(js, token_file)

    async def refresh_reddit_bearer_token(self):
        """Gets a new access_token for the Reddit API with a refresh token that was previously acquired by following
        this guide: https://github.com/reddit-archive/reddit/wiki/OAuth2"""

        auth = aiohttp.BasicAuth(
            login=self.REDDIT_CLIENT_ID, password=self.REDDIT_CLIENT_SECRET
        )

        post_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.REDDIT_REFRESH_TOKEN,
        }

        headers = {"User-Agent": "democraciv-discord-bot by DerJonas - u/Jovanos"}

        async with self._session.post(
            "https://www.reddit.com/api/v1/access_token",
            data=post_data,
            auth=auth,
            headers=headers,
        ) as response:
            if response.status == 200:
                r = await response.json()
                self.REDDIT_BEARER_TOKEN = r["access_token"]
                self._save_token()

    async def post_to_reddit(
        self,
        *,
        subreddit: str,
        title: str,
        content: str = None,
        url: str = None,
        retry=False,
    ):
        """Submit post to specified subreddit"""

        headers = {
            "Authorization": f"bearer {self.REDDIT_BEARER_TOKEN}",
            "User-Agent": "democraciv-discord-bot by DerJonas - u/Jovanos",
        }

        data = {
            "nsfw": False,
            "sr": subreddit,
            "title": title,
            "spoiler": False,
            "ad": False,
            "api_type": "json",
            "resubmit": True,
        }

        if content and url:
            raise RuntimeError("can only post either content or url, not both")

        if content:
            data["text"] = content
            data["kind"] = "self"

        if url:
            data["url"] = url
            data["kind"] = "link"

        async with self._session.post(
            "https://oauth.reddit.com/api/submit?raw_json=1", data=data, headers=headers
        ) as response:
            try:
                js = await response.json()
            except aiohttp.ContentTypeError:
                js = None

            if js and js["json"]["errors"]:
                logger.warning(f"got error while posting to reddit: {js}")
                return {"error": js}

            if response.status in (401, 403):

                if not retry:
                    await self.refresh_reddit_bearer_token()
                    return await self.post_to_reddit(
                        subreddit=subreddit,
                        title=title,
                        content=content,
                        url=url,
                        retry=True,
                    )

                logger.warning("got 403 while posting to reddit")
                return {"error": js}

            return js

    async def delete_reddit_post(self, *, post_id: str, retry=False):
        headers = {
            "Authorization": f"bearer {self.REDDIT_BEARER_TOKEN}",
            "User-Agent": "democraciv-discord-bot by DerJonas - u/Jovanos",
        }

        data = {"id": post_id}

        async with self._session.post(
            "https://oauth.reddit.com/api/del?raw_json=1", data=data, headers=headers
        ) as response:

            if response.status in (401, 403):
                if not retry:
                    await self.refresh_reddit_bearer_token()
                    return await self.delete_reddit_post(post_id=post_id, retry=True)

                logger.warning("got 403 while deleting reddit post")
                return {"error": await response.json()}

            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                return {"error": "error"}

    async def _start_webhook(self, *, target: str, webhook_url: str):
        async with self._lock:
            if target in self._webhooks:
                self._webhooks[target].webhook_urls.add(webhook_url)
            else:
                scraper = SubredditScraper(
                    db=self.db, session=self._session, subreddit=target, manager=self
                )
                scraper.webhook_urls.add(webhook_url)
                self._webhooks[target] = scraper
                scraper.start()

            logger.info(f"Added subreddit scraper for r/{target} to {webhook_url}")

    async def _remove_webhook(self, *, target: str, webhook_url: str):
        if target not in self._webhooks:
            return

        async with self._lock:
            if (
                len(self._webhooks[target].webhook_urls) == 1
                and webhook_url in self._webhooks[target].webhook_urls
            ):
                self._webhooks[target].stop()
                logger.info(
                    f"stopping {self._webhooks[target]} ({self._webhooks[target].subreddit})"
                )
                del self._webhooks[target]
            else:
                self._webhooks[target].webhook_urls.remove(webhook_url)


class RedditPost:
    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id")
        self.title: str = kwargs.get("title")
        self.author: str = kwargs.get("author")
        self._link: str = kwargs.get("permalink")
        self.link: str = f"https://reddit.com{self._link}"
        self.short_link: str = f"https://redd.it/{self.id}"
        self.subreddit: str = kwargs.get("subreddit")
        self._thumbnail: typing.Optional[str]

        try:
            self._thumbnail = kwargs["preview"]["images"][0]["source"]["url"]
        except (KeyError, IndexError):
            self._thumbnail = None

        self._created_utc: float = kwargs.get("created_utc")
        self.timestamp = datetime.datetime.utcfromtimestamp(self._created_utc)

    def to_embed(self):
        # old colour 16723228
        e = Embed(title=self.title, url=self.link, colour=0x1B1C20)
        e.set_author(
            name=f"New post on r/{self.subreddit}",
            icon_url="https://cdn.discordapp.com/attachments/730898526040752291/781547428087201792/Reddit_Mark_OnWhite.png",
        )
        e.add_field(name="Author", value=f"u/{self.author}", inline=False)
        return e.to_dict()

    @property
    def thumbnail(self) -> typing.Optional[str]:
        if self._thumbnail is None:
            return None

        return html.unescape(self._thumbnail)


class SubredditScraper:
    def __init__(
        self,
        *,
        db,
        subreddit: str,
        session: aiohttp.ClientSession,
        post_limit: int = 1,
        manager: RedditManager,
    ):
        self.subreddit = subreddit
        self.webhook_urls = set()
        self.db = db
        self.post_limit = post_limit
        self._session = session
        self._task = None
        self.manager = manager

    def __del__(self):
        self.stop()

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
                    logger.error(
                        f"Error while sending reddit webhook: {response.status} {await response.text()}"
                    )

                if response.status == 404:
                    # webhook was deleted
                    await self.manager._remove_webhook(
                        target=self.subreddit, webhook_url=webhook
                    )
                    try:
                        await self.db.pool.execute(
                            f"DELETE FROM {self.manager.table} WHERE webhook_url = $1",
                            webhook,
                        )
                        logger.info(
                            f"removed deleted webhook_url {webhook} for r/{self.subreddit}"
                        )
                    except Exception as e:
                        traceback.print_exception(type(e), e, e.__traceback__)

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

            status = await self.db.pool.execute(
                "INSERT INTO reddit_post (id) VALUES ($1) ON CONFLICT DO NOTHING",
                post_id,
            )
            is_new = False if status == "INSERT 0 0" else True

            if not is_new:
                continue

            reddit_post = RedditPost(**reddit_post_json)
            await self.send_webhook(reddit_post)
