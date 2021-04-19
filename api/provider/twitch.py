import collections
import datetime
import hashlib
import hmac
import json
import typing
import discord

from collections import namedtuple
from fastapi.logger import logger
from fastapi import Request

from api.provider.abc import ProviderManager

StreamContext = namedtuple("StreamContext", "webhook_url everyone_ping")


# todo post to reddit?


class TwitchStream:
    def __init__(self, **kwargs):
        self.streamer_id: str = kwargs.get("broadcaster_user_id")
        self.streamer: str = kwargs.get("broadcaster_user_name")
        self.title: str = kwargs.get("title")
        self.thumbnail: str = kwargs.get("thumbnail_url")
        self.game: str = kwargs.get("game_name")

        if self.thumbnail:
            self.thumbnail = self.thumbnail.format(width=1280, height=720)

        self.link: str = f"https://twitch.tv/{self.streamer}"


class TwitchManager(ProviderManager):
    provider = "Twitch"
    target = "streamer"
    table = "twitch_webhook"

    API_BASE = "https://api.twitch.tv/helix/"
    API_USER_ENDPOINT = API_BASE + "users"
    API_STREAM_ENDPOINT = API_BASE + "streams?user_id="
    API_EVENTSUB_ENDPOINT = API_BASE + "eventsub/subscriptions"
    API_TOKEN_ENDPOINT = "https://id.twitch.tv/oauth2/token"
    TWITCH_CLIENT_ID: str
    TWITCH_CLIENT_SECRET: str
    TWITCH_OAUTH_APP_ACCESS_TOKEN: str
    TWITCH_CALLBACK = "https://keinerosen.requestcatcher.com/test"

    def __init__(self, db, token_path):
        super().__init__(db=db)
        self._webhooks: typing.Dict[str, set] = {}
        self._token_path = token_path
        self._get_token()

        self.seen_notifications = collections.deque(maxlen=100)

    def _get_token(self):
        with open(self._token_path, "r") as token_file:
            token_json = json.load(token_file)
            self.TWITCH_CLIENT_ID = token_json["twitch"]["client_id"]
            self.TWITCH_CLIENT_SECRET = token_json["twitch"]["client_secret"]
            self.TWITCH_OAUTH_APP_ACCESS_TOKEN = token_json["twitch"]["oauth_token"]
            self.TWITCH_CALLBACK_SECRET = token_json["twitch"]["callback_secret"]
            self.TWITCH_CALLBACK_SECRET_BYTES = self.TWITCH_CALLBACK_SECRET.encode()

    def _save_token(self):
        with open(self._token_path, "r") as token_file:
            js = json.load(token_file)

        js["twitch"]["oauth_token"] = self.TWITCH_OAUTH_APP_ACCESS_TOKEN

        with open(self._token_path, "w") as token_file:
            json.dump(js, token_file)

    @property
    def _headers(self):
        return {
            "Client-ID": self.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.TWITCH_OAUTH_APP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    async def _refresh_twitch_oauth_token(self):
        """Gets a new app access_token for the Twitch Helix API"""

        post_data = {
            "client_id": self.TWITCH_CLIENT_ID,
            "client_secret": self.TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        async with self._session.post(self.API_TOKEN_ENDPOINT, data=post_data) as response:
            if response.status == 200:
                r = await response.json()
                self.TWITCH_OAUTH_APP_ACCESS_TOKEN = r["access_token"]
                self._save_token()

    async def _get_user_id_from_username(self, username: str):
        response = await self.twitch_request("GET", f"{self.API_USER_ENDPOINT}?login={username}")

        if response:
            try:
                return response["data"][0]["id"]
            except (KeyError, IndexError):
                return None

    async def add_webhook(self, config):
        await self.db.pool.execute(
            "INSERT INTO twitch_webhook (streamer, webhook_id, webhook_url, "
            "guild_id, channel_id, everyone_ping)"
            "VALUES ($1, $2, $3, $4, $5, $6)",
            config.target,
            config.webhook_id,
            config.webhook_url,
            config.guild_id,
            config.channel_id,
            config.everyone_ping,
        )
        return await self._start_webhook(target=config.target, webhook_url=config.webhook_url)

    async def twitch_request(self, method, url, *, retry=False, **kwargs):
        async with self._session.request(method, url, **kwargs, headers=self._headers) as resp:
            print(f"method {method} to {url}", resp.status, await resp.json())
            if resp.status in (401, 403):
                if not retry:
                    await self._refresh_twitch_oauth_token()
                    await self.twitch_request(method, url, retry=True, **kwargs)

            elif resp.status == 200:
                return await resp.json()

            else:
                return {}

    async def _start_webhook(self, *, target: str, webhook_url: str):
        async with self._lock:
            if target in self._webhooks:
                self._webhooks[target].add(webhook_url)
                return self._webhooks[target]
            else:
                result = await self.subscribe(target)
                self._webhooks[target] = {webhook_url}
                return result

    async def no_more_webhooks_for_target(self, *, target: str, webhook_url: str):
        return await self.unsubscribe(target)

    async def subscribe(self, stream: str):
        user_id = await self._get_user_id_from_username(stream)

        if not user_id:
            return {"error": "invalid streamer name"}

        logger.info(f"[Twitch] subscribing to {stream}")

        js = {
            "type": "stream.online",
            "version": "1",
            "condition": {"broadcaster_user_id": user_id},
            "transport": {
                "method": "webhook",
                "callback": self.TWITCH_CALLBACK,
                "secret": self.TWITCH_CALLBACK_SECRET,
            },
        }

        j = await self.twitch_request("POST", self.API_EVENTSUB_ENDPOINT, json=js)
        j["ok"] = "ok"
        return j

    async def unsubscribe(self, streamer: str):
        subscription_id = await self.db.pool.fetchval(
            "SELECT twitch_subscription_id FROM " "twitch_eventsub_subscription WHERE streamer = $1", streamer
        )

        if not subscription_id:
            return

        await self.twitch_request("DELETE", f"{self.API_EVENTSUB_ENDPOINT}?id={subscription_id}")

    async def add_twitch_subscription_id(self, streamer_id: str, subscription_id: str):
        response = await self.twitch_request("GET", f"{self.API_USER_ENDPOINT}?id={streamer_id}")
        streamer = response["data"][0]["login"]

        await self.db.pool.execute(
            "INSERT INTO twitch_eventsub_subscription "
            "(twitch_subscription_id, streamer, streamer_id) "
            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING ",
            subscription_id,
            streamer,
            streamer_id,
        )

    async def handle_twitch_callback(self, request: Request):
        headers = request.headers
        notification_id = headers['Twitch-Eventsub-Message-Id']

        if notification_id in self.seen_notifications:
            return

        self.seen_notifications.append(notification_id)
        timestamp = headers['Twitch-Eventsub-Message-Timestamp']

        if (datetime.datetime.now(tz=datetime.timezone.utc) -
                datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                > datetime.timedelta(minutes=10)):
            return

        body = await request.body()
        hmac_message = notification_id.encode() + timestamp.encode() + body
        digester = hmac.new(self.TWITCH_CALLBACK_SECRET_BYTES, hmac_message, hashlib.sha256)
        expected_signature_header = f"sha256={digester.hexdigest()}"

        if headers['Twitch-Eventsub-Message-Signature'] != expected_signature_header:
            return

        js = await request.json()

        if "challenge" in js:
            await self.add_twitch_subscription_id(
                js["subscription"]["condition"]["broadcaster_user_id"],
                js["subscription"]["id"],
            )

        elif "event" in js:
            await self.process_incoming_notification(js["event"])

    async def process_incoming_notification(self, event: typing.Dict):
        js = await self.twitch_request("GET", f"{self.API_STREAM_ENDPOINT}{event['broadcaster_user_id']}")

        if js["data"]:
            event["title"] = js["data"][0]["title"]
            event["thumbnail_url"] = js["data"][0]["thumbnail_url"]
            event["game_name"] = js["data"][0]["game_name"]

        streamer = event["broadcaster_user_name"].lower()
        record = await self.db.pool.fetch(
            "SELECT webhook_url, everyone_ping FROM " "twitch_webhook WHERE streamer = $1", streamer
        )

        for row in record:
            context = StreamContext(webhook_url=row["webhook_url"], everyone_ping=row["everyone_ping"])
            await self.send_webhook(context, TwitchStream(**event))

    async def send_webhook(self, context: StreamContext, stream: TwitchStream):
        embed = discord.Embed(title=stream.title, url=stream.link, colour=0x1B1C20)
        embed.set_author(name=f"{stream.streamer} - Live on Twitch",
                         icon_url="https://cdn.discordapp.com/attachments/730898526040752291/"
                                  "781547042471149598/TwitchGlitchPurple.png")
        embed.set_image(url=stream.thumbnail)

        js = {"embeds": [embed.to_dict()]}

        if context.everyone_ping:
            js["content"] = f"@everyone **{stream.streamer}** just went live on Twitch!"

        async with self._session.post(context.webhook_url, json=js) as response:
            if response.status not in (200, 204):
                logger.error(f"Error while sending Twitch webhook: {response.status} {await response.text()}")

            if response.status == 404:
                # webhook was deleted
                await self._remove_webhook(target=stream.streamer, webhook_url=context.webhook_url)
                await self.db.pool.execute(f"DELETE FROM {self.table} WHERE webhook_url = $1", context.webhook_url)
                logger.info(f"removed deleted webhook_url {context.webhook_url} for {stream.streamer}")
