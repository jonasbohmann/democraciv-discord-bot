import json
import typing
import asyncio
import aiohttp
import discord

from discord.ext import tasks
from fastapi.logger import logger


class YouTubeManager:
    def __init__(self, db, *, token_path, reddit_manager):
        self.db = db
        self._token_path = token_path
        self.reddit_manager = reddit_manager
        self.session: typing.Optional[aiohttp.ClientSession] = None

        self._get_token()

        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.make_session())

        if (
                self.YOUTUBE_DATA_API_V3_KEY and self.YOUTUBE_CHANNEL_ID and
                self.YOUTUBE_CHANNEL_UPLOADS_PLAYLIST and self.YOUTUBE_WEBHOOK
        ):
            self.youtube_upload_tasks.start()

    def _get_token(self):
        with open(self._token_path, "r") as token_file:
            token_json = json.load(token_file)
            self.YOUTUBE_DATA_API_V3_KEY = token_json["youtube"]["api_key"]
            self.YOUTUBE_SUBREDDIT = token_json["youtube"]["subreddit"]
            self.YOUTUBE_CHANNEL_ID = token_json["youtube"]["channel_id"]
            self.YOUTUBE_CHANNEL_UPLOADS_PLAYLIST = token_json["youtube"]["channel_uploads_playlist_id"]
            self.YOUTUBE_VIDEO_UPLOADS_TO_REDDIT = token_json["youtube"]["post_to_subreddit"]
            self.YOUTUBE_WEBHOOK = token_json["youtube"]["webhook"]

    async def make_session(self):
        self.session = aiohttp.ClientSession()

    async def get_live_broadcast(self) -> typing.Optional[typing.Dict]:
        """If a YouTube channel is streaming a live broadcast, returns JSON of broadcast details. Else, returns None.
        The two API requests in this method are expensive and should only be called every 15 minutes for a standard
        API key."""

        async with self.session.get(
                f"https://www.googleapis.com/youtube/v3/search?"
                f"part=snippet&channelId={self.YOUTUBE_CHANNEL_ID}"
                f"&type=video&eventType=live&maxResults=1&key={self.YOUTUBE_DATA_API_V3_KEY}",
                headers={"Accept": "application/json"},
        ) as response:
            if response.status == 200:
                stream_data = await response.json()

        try:
            stream_id = stream_data["items"][0]["id"]["videoId"]
        except (IndexError, KeyError):
            return None

        status = await self.db.pool.execute(
            "INSERT INTO youtube_stream (id) VALUES ($1) ON CONFLICT DO NOTHING", stream_id
        )

        # ID already in database -> stream already announced
        if status == "INSERT 0 0":
            return None

        async with self.session.get(
                f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={stream_id}"
                f"&key={self.YOUTUBE_DATA_API_V3_KEY}",
                headers={"Accept": "application/json"},
        ) as response:
            if response.status == 200:
                return await response.json()

        return None

    @tasks.loop(minutes=15)
    async def youtube_stream_task(self):
        """Check every 15 minutes if a YouTube channel is streaming live. If it is, send an announcement to the
        specified Discord channel."""

        # A standard Google API key has 10.000 units per day
        #   This task, with the minutes set to 10, costs approx. 14.832 units per day
        #   This task, with the minutes set to 15, costs approx. 9.888 units per day

        stream_data = await self.get_live_broadcast()

        if stream_data is None:
            return

        try:
            video_data = stream_data["items"][0]
        except (KeyError, IndexError):
            return

        title = video_data["snippet"]["title"]
        channel_title = video_data["snippet"]["channelTitle"]
        description = video_data["snippet"]["description"]
        thumbnail = video_data["snippet"]["thumbnails"]["high"]["url"]
        video_url = f'https://youtube.com/watch?v={video_data["id"]}'

        embed = discord.Embed(title=title, url=video_url,
                              description=self.shorten_description(description), colour=0x1B1C20)

        embed.set_author(name=f"{channel_title} - Live on YouTube",
                         icon_url="https://cdn.discordapp.com/attachments/738903909535318086/"
                                  "833693607084818432/youtube_social_circle_red.png")

        if thumbnail.startswith("https://"):
            embed.set_image(url=thumbnail)

    async def get_newest_upload(self) -> typing.Optional[typing.Dict]:
        async with self.session.get(
                "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
                f"&maxResults=3&playlistId={self.YOUTUBE_CHANNEL_UPLOADS_PLAYLIST}"
                f"&key={self.YOUTUBE_DATA_API_V3_KEY}",
                headers={"Accept": "application/json"},
        ) as response:
            if response.status == 200:
                return await response.json()
        return None

    @staticmethod
    def shorten_description(description):
        if len(description) > 250:
            return f"{description[:250]}..."

        return description

    @tasks.loop(minutes=10)
    async def youtube_upload_tasks(self):
        """Check every 10 minutes if the 3 last uploads of a YouTube channel are new. If at least one is,
        send an announcement to the specified Discord channel."""

        # A standard Google API key has 10.000 units per day
        #   This task, with the minutes set to 10, costs approx. 2160 units per day

        youtube_data = await self.get_newest_upload()

        if youtube_data is None:
            return

        # Each check last 3 uploads in case we missed some in between
        for i in range(2, -1, -1):
            try:
                youtube_video = youtube_data["items"][i]
            except IndexError:
                continue

            video_id = youtube_video["snippet"]["resourceId"]["videoId"]

            # Try to add post id to database
            status = await self.db.pool.execute(
                "INSERT INTO youtube_upload (id) VALUES ($1) ON CONFLICT DO NOTHING", video_id
            )

            # ID already in database -> post already seen
            if status == "INSERT 0 0":
                continue

            title = youtube_video["snippet"]["title"]
            channel = youtube_video["snippet"]["channelTitle"]
            description = youtube_video["snippet"]["description"]
            thumbnail_url = youtube_video["snippet"]["thumbnails"]["high"]["url"]
            video_link = f"https://youtube.com/watch?v={video_id}"

            if self.YOUTUBE_VIDEO_UPLOADS_TO_REDDIT:
                await self.reddit_manager.post_to_reddit(subreddit=self.YOUTUBE_SUBREDDIT, title=title, url=video_link)

            embed = discord.Embed(title=title, description=self.shorten_description(description),
                                  url=video_link, colour=0x1B1C20)
            embed.set_author(name=f"{channel} - New YouTube Video Uploaded",
                             icon_url="https://cdn.discordapp.com/attachments/738903909535318086/"
                                      "833695619838640189/youtube_social_circle_white.png")
            embed.set_image(url=thumbnail_url)

            async with self.session.post(self.YOUTUBE_WEBHOOK, json={"embeds": [embed.to_dict()]}) as response:
                if response.status not in (200, 204):
                    logger.error(f"Error while sending Twitch webhook: {response.status} {await response.text()}")
