import asyncio
import logging
import json
import aiohttp
import typing

from discord import Embed


class TwitchStream:
    def __init__(self, **kwargs):
        self.streamer: str = kwargs.get("user_name")
        self.title: str = kwargs.get("title")
        self._thumbnail: str = kwargs.get("thumbnail_url")
        self.link: str = f"https://twitch.tv/{self.streamer}"

    @property
    def thumbnail(self):
        return self._thumbnail.format(width=1280, height=720)


class TwitchManager:
    API_BASE = "https://api.twitch.tv/helix/"
    API_USER_ENDPOINT = API_BASE + "users?login="
    API_STREAM_ENDPOINT = API_BASE + "streams"
    TWITCH_CLIENT_ID = ""
    TWITCH_CLIENT_SECRET = ""
    TWITCH_OAUTH_APP_ACCESS_TOKEN = ""

    def __init__(self):
        self._session: aiohttp.ClientSession = None
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self._make_aiohttp_session())
        self._streams: typing.Dict[str, typing.Set[str]] = dict()

    def _get_token(self):
        with open("", "r") as token_file:
            token = json.load(token_file)

    def _save_token(self, data):
        with open("", "w") as token_file:
            json.dump(data, token_file)

    @property
    def _headers(self):
        return {'Client-ID': self.TWITCH_CLIENT_ID, 'Authorization': f'Bearer {self.TWITCH_OAUTH_APP_ACCESS_TOKEN}'}

    async def _refresh_twitch_oauth_token(self):
        """Gets a new app access_token for the Twitch Helix API"""

        post_data = {"client_id": self.TWITCH_CLIENT_ID, "client_secret": self.TWITCH_CLIENT_SECRET,
                     "grant_type": "client_credentials"}

        async with self._session.post("https://id.twitch.tv/oauth2/token", data=post_data) as response:
            if response.status == 200:
                r = await response.json()
                self.TWITCH_OAUTH_APP_ACCESS_TOKEN = r['access_token']

    async def _make_aiohttp_session(self):
        self._session = aiohttp.ClientSession()

    async def _get_user_id_from_username(self, username: str):
        async with self._session.get(f"{self.API_USER_ENDPOINT}{username}", headers=self._headers) as response:
            if response.status == 200:
                json = await response.json()
                return json["data"][0]["id"]

    async def add_stream(self, streamer: str, to_discord_webhook: str):
        streamer = streamer.lower()

        if streamer in self._streams:
            self._streams[streamer].add(to_discord_webhook)
            print(1)
            print(self._streams)
            return self._streams[streamer]
        else:
            result = await self.subscribe(streamer)
            self._streams[streamer] = {to_discord_webhook}
            print(2)
            print(self._streams)
            return result

    async def remove_stream(self, streamer: str, to_discord_webhook: str):
        streamer = streamer.lower()

        if streamer not in self._streams:
            return

        if len(self._streams[streamer]) == 1 and to_discord_webhook in self._streams[streamer]:
            del self._streams[streamer]
        else:
            self._streams[streamer].remove(to_discord_webhook)

    async def subscribe(self, stream: str):
        return await self._manage_subscription(stream=stream, mode="subscribe")

    async def unsubscribe(self, stream: str):
        return await self._manage_subscription(stream=stream, mode="unsubscribe")

    async def _manage_subscription(self, *, stream: str, mode: str):
        user_id = await self._get_user_id_from_username(stream)
        print(f"{mode} to ", stream)

        json = {
            "hub.callback": "http://138.68.80.72:8888/twitch/callback",
            "hub.mode": mode,
            "hub.topic": f"{self.API_STREAM_ENDPOINT}?user_id={user_id}",
            "hub.lease_seconds": 600
        }

        async with self._session.post("https://api.twitch.tv/helix/webhooks/hub", json=json,
                                      headers=self._headers) as response:
            j = await response.text()
            print(3)
            print(j)
            return j

    async def process_incoming_notification(self, request):
        json = await request.json()

        if not json['data']:
            # stream went from online to offline
            return

        self._loop.create_task(self.send_webhook(TwitchStream(**json['data'][0])))

    async def send_webhook(self, stream: TwitchStream):
        embed = Embed(title=f"<:twitch:660116652012077080> {stream.streamer} - Live on Twitch", colour=0x984efc)
        embed.add_field(name="Title", value=stream.title, inline=False)
        embed.add_field(name="Link", value=stream.link, inline=False)
        embed.set_image(url=stream.thumbnail)

        json = {"embeds": [embed.to_dict()]}

        streamer = stream.streamer.lower()

        if streamer not in self._streams:
            return  # ? how

        for discord_webhook in self._streams[streamer]:
            async with self._session.post(discord_webhook, json=json) as response:
                if response.status not in (200, 204):
                    logging.error(f"error while sending reddit webhook: {response.status} {await response.text()}")

