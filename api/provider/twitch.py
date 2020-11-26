import asyncio
import logging
import json
import aiohttp
import typing
from discord import Embed

from provider.abc import ProviderManager


class TwitchStream:
    def __init__(self, **kwargs):
        self.streamer_id: str = kwargs.get("broadcaster_user_id")
        self.streamer: str = kwargs.get("broadcaster_user_name")
        self.title: str = kwargs.get("title", None)
        self.thumbnail: str = kwargs.get("thumbnail_url", None)
        self.game: str = kwargs.get("game_name", None)

        if self.thumbnail:
            self.thumbnail = self.thumbnail.format(width=1280, height=720)

        self.link: str = f"https://twitch.tv/{self.streamer}"


class TwitchManager(ProviderManager):
    provider = "Twitch"
    target = "streamer"
    table = "twitch_webhook"

    API_BASE = "https://api.twitch.tv/helix/"
    API_USER_ENDPOINT = API_BASE + "users?login="
    API_STREAM_ENDPOINT = API_BASE + "streams?user_id="
    API_EVENTSUB_ENDPOINT = API_BASE + "eventsub/subscriptions"
    API_TOKEN_ENDPOINT = "https://id.twitch.tv/oauth2/token"
    TWITCH_CLIENT_ID: str
    TWITCH_CLIENT_SECRET: str
    TWITCH_OAUTH_APP_ACCESS_TOKEN: str
    TWITCH_CALLBACK = "https://keinerosen.requestcatcher.com/test"

    def __init__(self, db):
        super().__init__(db=db)
        self._get_token()

    def _get_token(self):
        with open("api/token.json", "r") as token_file:
            token_json = json.load(token_file)
            self.TWITCH_CLIENT_ID = token_json['twitch']['client_id']
            self.TWITCH_CLIENT_SECRET = token_json['twitch']['client_secret']
            self.TWITCH_OAUTH_APP_ACCESS_TOKEN = token_json['twitch']['oauth_token']

    def _save_token(self):
        with open("api/token.json", "r") as token_file:
            js = json.load(token_file)

        js['twitch']['oauth_token'] = self.TWITCH_OAUTH_APP_ACCESS_TOKEN

        with open("api/token.json", "w") as token_file:
            json.dump(js, token_file)

    @property
    def _headers(self):
        return {"Client-ID": self.TWITCH_CLIENT_ID, "Authorization": f"Bearer {self.TWITCH_OAUTH_APP_ACCESS_TOKEN}",
                "Content-Type": "application/json"}

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
        async with self._session.get(f"{self.API_USER_ENDPOINT}{username}", headers=self._headers) as response:
            if response.status == 200:
                js = await response.json()
                try:
                    return js["data"][0]["id"]
                except (KeyError, IndexError):
                    return None

    async def add_stream(self, config):
        await self.db.pool.execute("INSERT INTO twitch_webhook (streamer, webhook_id, webhook_url, "
                                   "guild_id, channel_id, everyone_ping)"
                                   "VALUES ($1, $2, $3, $4, $5, $6)",
                                   config.streamer, config.webhook_id, config.webhook_url,
                                   config.guild_id, config.channel_id, config.everyone_ping)
        return await self._start_webhook(target=config.streamer, webhook_url=config.webhook_url)

    async def twitch_request(self, method, url, *, retry=False, **kwargs):
        async with self._session.request(method, url, **kwargs, headers=self._headers) as resp:
            if resp.status == 403:
                if not retry:
                    await self._refresh_twitch_oauth_token()
                    await self.twitch_request(method, url, retry=True, **kwargs)

            elif resp.status == 200:
                return await resp.json()

            else:
                return {}

    async def new_webhook_for_target(self, *, target: str, webhook_url: str):
        return await self.subscribe(target)

    async def no_more_webhooks_for_target(self, *, target: str, webhook_url: str):
        return await self.unsubscribe(target)

    async def subscribe(self, stream: str):
        return await self._manage_subscription(stream=stream, mode="subscribe")

    async def unsubscribe(self, stream: str):
        return await self._manage_subscription(stream=stream, mode="unsubscribe")

    async def _manage_subscription(self, *, stream: str, mode: str):
        user_id = await self._get_user_id_from_username(stream)

        if not user_id:
            return {"error": "invalid streamer name"}

        logging.info(f"[Twitch] {mode} to {stream}")

        js = {
            "type": "stream.online",
            "version": "1",
            "condition": {
                "broadcaster_user_id": user_id
            },
            "transport": {
                "method": "webhook",
                "callback": self.TWITCH_CALLBACK,
                "secret": "thisismysecrettwitchthanks"
            }
        }

        j = await self.twitch_request("POST", self.API_EVENTSUB_ENDPOINT, json=js)
        j['ok'] = "ok"
        return j

    async def process_incoming_notification(self, event: typing.Dict):
        js = await self.twitch_request("GET", f"{self.API_STREAM_ENDPOINT}{event['broadcaster_user_id']}")

        if js['data']:
            event['title'] = js['data'][0]['title']
            event['thumbnail_url'] = js['data'][0]['thumbnail_url']
            event['game_name'] = js['data'][0]['game_name']

        await self.send_webhook(TwitchStream(**event))

    async def send_webhook(self, stream: TwitchStream):
        embed = Embed(title=f"<:twitch:660116652012077080> {stream.streamer} - Live on Twitch", colour=0x984EFC)
        embed.add_field(name="Title", value=stream.title, inline=False)
        embed.add_field(name="Link", value=stream.link, inline=False)
        embed.set_image(url=stream.thumbnail)

        js = {"embeds": [embed.to_dict()]}

        streamer = stream.streamer.lower()

        if streamer not in self._webhooks:
            return  # ? how

        for discord_webhook in self._webhooks[streamer]:
            async with self._session.post(discord_webhook, json=js) as response:
                if response.status not in (200, 204):
                    logging.error(f"Error while sending reddit webhook: {response.status} {await response.text()}")
