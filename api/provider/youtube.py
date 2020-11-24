import typing
import asyncio

from bot.utils import exceptions
from discord.ext import tasks, commands
from bot.config import token, config


class YouTube(context.CustomCog):
    """Announcements for new video uploads and live broadcasts from a YouTube Channel.
    Needs a valid YouTube Data V3 API key for the requests."""

    def __init__(self, bot):
        self.bot = bot
        self.youtube_channel = config.YOUTUBE_CHANNEL_ID
        self.api_key = token.YOUTUBE_DATA_V3_API_KEY
        self.header = {"Accept": "application/json"}

        if config.YOUTUBE_ENABLED and self.api_key:
            if config.YOUTUBE_VIDEO_UPLOADS_ENABLED:
                self.youtube_upload_tasks.start()
            if config.YOUTUBE_LIVESTREAM_ENABLED:
                self.youtube_stream_task.start()

    def cog_unload(self):
        self.youtube_upload_tasks.cancel()
        self.youtube_stream_task.cancel()

    @staticmethod
    def reduce_youtube_description(string: str) -> str:
        length = len(string)
        if length > 250:
            to_remove = length - 250
            return string[:-to_remove] + "..."
        else:
            return string

    async def get_live_broadcast(self) -> typing.Optional[typing.Dict]:
        """If a YouTube channel is streaming a live broadcast, returns JSON of broadcast details. Else, returns None.
        The two API requests in this method are expensive and should only be called every 15 minutes for a standard
        API key."""

        async with self.bot.session.get(
            f"https://www.googleapis.com/youtube/v3/search?"
            f"part=snippet&channelId={self.youtube_channel}"
            f"&type=video&eventType=live&maxResults=1&key={self.api_key}",
            headers=self.header,
        ) as response:
            if response.status == 200:
                stream_data = await response.json()

        try:
            _id = stream_data["items"][0]["id"]["videoId"]
        except (IndexError, KeyError):
            return None

        status = await self.bot.db.execute("INSERT INTO youtube_streams (id) VALUES ($1) ON CONFLICT DO NOTHING", _id)

        # ID already in database -> stream already announced
        if status == "INSERT 0 0":
            return None

        async with self.bot.session.get(
            f"https://www.googleapis.com/youtube/v3/videos?part=snippet&" f"id={_id}&key={self.api_key}",
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

        try:
            discord_channel = self.bot.dciv.get_channel(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)
        except AttributeError:
            print(
                f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "DEMOCRACIV_GUILD_ID" '
                f"in the config to a server I am in or disable YouTube Stream announcements."
            )
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_GUILD_ID)

        if discord_channel is None:
            print(
                "[BOT] ERROR - The YOUTUBE_ANNOUNCEMENT_CHANNEL id in config.py is not a channel on the"
                " specified Democraciv guild."
            )
            raise exceptions.ChannelNotFoundError(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        stream_data = await self.get_live_broadcast()

        if stream_data is None:
            return

        video_data = stream_data["items"][0]

        _title = video_data["snippet"]["title"]
        _channel_title = video_data["snippet"]["channelTitle"]
        _description = video_data["snippet"]["description"]
        _thumbnail = video_data["snippet"]["thumbnails"]["high"]["url"]
        _video_url = f'https://youtube.com/watch?v={video_data["id"]}'

        embed = text.SafeEmbed(
            title=f"{config.YOUTUBE_LOGO_STREAM}  {_channel_title} - Live on YouTube", description="", has_footer=False
        )
        embed.add_field(name="Title", value=f"[{_title}]({_video_url})", inline=False)
        embed.add_field(name="Description", value=self.reduce_youtube_description(_description), inline=False)

        if _thumbnail.startswith("https://"):
            embed.set_image(url=_thumbnail)

        if config.YOUTUBE_EVERYONE_PING_ON_STREAM:
            await discord_channel.send(f"@everyone {_channel_title} is live on YouTube!", embed=embed)
        else:
            await discord_channel.send(f"{_channel_title} is live on YouTube!", embed=embed)

    async def get_newest_upload(self) -> typing.Optional[typing.Dict]:
        async with self.bot.session.get(
            "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
            f"&maxResults=3&playlistId={config.YOUTUBE_CHANNEL_UPLOADS_PLAYLIST}"
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

        try:
            discord_channel = self.bot.dciv.get_channel(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)
        except AttributeError:
            print(
                f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "DEMOCRACIV_GUILD_ID" '
                f"in the config to a server I am in or disable YouTube Upload announcements."
            )
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_GUILD_ID)

        if discord_channel is None:
            print(
                "[BOT] ERROR - The YOUTUBE_ANNOUNCEMENT_CHANNEL id in config.py is not a channel on the"
                " specified Democraciv guild."
            )
            raise exceptions.ChannelNotFoundError(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        youtube_data = await self.get_newest_upload()

        if youtube_data is None:
            return

        # Each check last 3 uploads in case we missed some in between
        for i in range(3):
            youtube_video = youtube_data["items"][i]

            _id = youtube_video["snippet"]["resourceId"]["videoId"]

            # Try to add post id to database
            status = await self.bot.db.execute(
                "INSERT INTO youtube_uploads (id) VALUES ($1) ON CONFLICT DO NOTHING", _id
            )

            # ID already in database -> post already seen
            if status == "INSERT 0 0":
                continue

            title = youtube_video["snippet"]["title"]
            channel = youtube_video["snippet"]["channelTitle"]
            description = youtube_video["snippet"]["description"]
            thumbnail_url = youtube_video["snippet"]["thumbnails"]["high"]["url"]
            video_link = f"https://youtube.com/watch?v={_id}"

            if config.YOUTUBE_VIDEO_UPLOADS_TO_REDDIT:
                data = {
                    "kind": "link",
                    "nsfw": False,
                    "sr": config.REDDIT_SUBREDDIT,
                    "title": title,
                    "spoiler": False,
                    "url": video_link,
                }

                await self.bot.reddit_api.post_to_reddit(data)

            embed = text.SafeEmbed(
                title=f"{config.YOUTUBE_LOGO_UPLOAD}  {channel} - New YouTube video uploaded",
                description="",
                has_footer=False,
                colour=0xFF001B,
            )
            embed.add_field(name="Title", value=f"[{title}]({video_link})", inline=False)
            embed.add_field(name="Description", value=self.reduce_youtube_description(description), inline=False)
            embed.set_image(url=thumbnail_url)

            await discord_channel.send(embed=embed)

    @youtube_upload_tasks.before_loop
    async def before_upload_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.dciv is None:
            await asyncio.sleep(5)

    @youtube_stream_task.before_loop
    async def before_stream_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.dciv is None:
            await asyncio.sleep(5)


def setup(bot):
    if config.YOUTUBE_ENABLED:
        bot.add_cog(YouTube(bot))
