import textwrap
import typing
import asyncio
import aiohttp
import discord

from discord.ext import tasks

# todo post to reddit?


YOUTUBE_VIDEO_UPLOADS_TO_REDDIT = True
YOUTUBE_CHANNEL_ID = "UC-NukxPakwQIvx73VjtIPnw"
YOUTUBE_CHANNEL_UPLOADS_PLAYLIST = "UU-NukxPakwQIvx73VjtIPnw"
YOUTUBE_LOGO_UPLOAD = "<:youtubeiconwhite:660114810444447774>"
YOUTUBE_LOGO_STREAM = "<:youtubeiconred:660897027114401792>"


# todo fix

class YouTubeManager:

    def __init__(self, db):
        self.db = db
        self.header = {"Accept": "application/json"}
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.make_session())

    def _get_token(self):
        self.api_key = 1

    async def make_session(self):
        self.session = aiohttp.ClientSession()

    @staticmethod
    def reduce_youtube_description(string: str) -> str:
        return textwrap.shorten(string, 250)

    async def get_live_broadcast(self) -> typing.Optional[typing.Dict]:
        """If a YouTube channel is streaming a live broadcast, returns JSON of broadcast details. Else, returns None.
        The two API requests in this method are expensive and should only be called every 15 minutes for a standard
        API key."""

        async with self.session.get(
                f"https://www.googleapis.com/youtube/v3/search?"
                f"part=snippet&channelId={YOUTUBE_CHANNEL_ID}"
                f"&type=video&eventType=live&maxResults=1&key={self.api_key}",
                headers=self.header,
        ) as response:
            if response.status == 200:
                stream_data = await response.json()

        try:
            stream_id = stream_data["items"][0]["id"]["videoId"]
        except (IndexError, KeyError):
            return None

        status = await self.db.pool.execute("INSERT INTO youtube_stream (id) VALUES ($1) ON CONFLICT DO NOTHING",
                                            stream_id)

        # ID already in database -> stream already announced
        if status == "INSERT 0 0":
            return None

        async with self.session.get(
                f"https://www.googleapis.com/youtube/v3/videos?part=snippet&" f"id={stream_id}&key={self.api_key}",
                headers=self.header,
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

        video_data = stream_data["items"][0]

        title = video_data["snippet"]["title"]
        channel_title = video_data["snippet"]["channelTitle"]
        description = video_data["snippet"]["description"]
        thumbnail = video_data["snippet"]["thumbnails"]["high"]["url"]
        video_url = f'https://youtube.com/watch?v={video_data["id"]}'

        embed = discord.Embed(
            title=f"{YOUTUBE_LOGO_STREAM}  {channel_title} - Live on YouTube", description="", has_footer=False
        )
        embed.add_field(name="Title", value=f"[{title}]({video_url})", inline=False)
        embed.add_field(name="Description", value=self.reduce_youtube_description(description), inline=False)

        if thumbnail.startswith("https://"):
            embed.set_image(url=thumbnail)

    async def get_newest_upload(self) -> typing.Optional[typing.Dict]:
        async with self.session.get(
                "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
                f"&maxResults=3&playlistId={YOUTUBE_CHANNEL_UPLOADS_PLAYLIST}"
                f"&key={self.api_key}",
                headers=self.header,
        ) as response:
            if response.status == 200:
                return await response.json()
        return None

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
        for i in range(3):
            youtube_video = youtube_data["items"][i]

            _id = youtube_video["snippet"]["resourceId"]["videoId"]

            # Try to add post id to database
            status = await self.db.pool.execute(
                "INSERT INTO youtube_upload (id) VALUES ($1) ON CONFLICT DO NOTHING", _id
            )

            # ID already in database -> post already seen
            if status == "INSERT 0 0":
                continue

            title = youtube_video["snippet"]["title"]
            channel = youtube_video["snippet"]["channelTitle"]
            description = youtube_video["snippet"]["description"]
            thumbnail_url = youtube_video["snippet"]["thumbnails"]["high"]["url"]
            video_link = f"https://youtube.com/watch?v={_id}"

            """data = {
                "kind": "link",
                "nsfw": False,
                "sr": config.REDDIT_SUBREDDIT,
                "title": title,
                "spoiler": False,
                "url": video_link,
            }

            await self.bot.reddit_api.post_to_reddit(data)"""

            embed = discord.Embed(
                title=f"{YOUTUBE_LOGO_UPLOAD}  {channel} - New YouTube video uploaded",
                description="",
                has_footer=False,
                colour=0xFF001B,
            )
            embed.add_field(name="Title", value=f"[{title}]({video_link})", inline=False)
            embed.add_field(name="Description", value=self.reduce_youtube_description(description), inline=False)
            embed.set_image(url=thumbnail_url)
