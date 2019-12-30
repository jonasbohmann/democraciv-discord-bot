import aiohttp

from util import exceptions
from config import config, token

from discord.ext import tasks


class YouTube:

    def __init__(self, bot):
        self.bot = bot
        self.youtube_channel = config.YOUTUBE_CHANNEL_ID
        self.api_key = token.YOUTUBE_DATA_V3_API_KEY
        self.header = {'Accept': 'application/json'}

        self.playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet" \
                            f"&maxResults=3&playlistId={config.YOUTUBE_CHANNEL_UPLOADS_PLAYLIST}" \
                            f"&key={self.api_key}"
        self.stream_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={self.youtube_channel}"\
                          f"&type=video&eventType=live&maxResults=1&key={self.api_key}"

        self.first_run = True

        if self.api_key != "" and self.api_key is not None:
            if config.YOUTUBE_VIDEO_UPLOADS_ENABLED:
                self.youtube_upload_tasks.start()
            if config.YOUTUBE_LIVESTREAM_ENABLED:
                self.youtube_stream_task.start()

    def __del__(self):
        self.youtube_upload_tasks.cancel()
        self.youtube_stream_task.cancel()

    @staticmethod
    def reduce_youtube_description(string: str) -> str:
        length = len(string)
        if length > 250:
            to_remove = length - 250
            return string[:-to_remove] + '...'
        else:
            return string

    async def get_live_broadcast(self):

        try:
            async with self.bot.session.get(self.stream_url, headers=self.header) as response:
                stream_data = await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in YouTube session.get()!")
            return None

        try:
            _id = stream_data['items'][0]['id']['videoId']
        except (IndexError, KeyError):
            return None

        status = await self.bot.db.execute("INSERT INTO youtube_streams (id) VALUES ($1) ON CONFLICT DO NOTHING",
                                           _id)

        # ID already in database -> stream already announced
        if status == "INSERT 0 0":
            return None

        try:
            async with self.bot.session.get(f"https://www.googleapis.com/youtube/v3/videos?part=snippet&"
                                            f"id={_id}&key={self.api_key}", headers=self.header) as response:
                return await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in YouTube session.get()!")
            return None

    @tasks.loop(minutes=15)
    async def youtube_stream_task(self):

        # A standard Google API key has 10.000 units per day

        # This task, with the minutes set to 10, costs approx. 14.832 units per day
        # This task, with the minutes set to 15, costs approx. 9.888 units per day

        if self.first_run:
            self.first_run = False
            return

        try:
            discord_channel = self.bot.democraciv_guild_object.get_channel(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable YouTube announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

        if discord_channel is None:
            raise exceptions.ChannelNotFoundError(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        stream_data = await self.get_live_broadcast()

        if stream_data is None:
            return

        video_data = stream_data["items"][0]

        _title = video_data['snippet']['title']
        _channel_title = video_data['snippet']['channelTitle']
        _description = video_data['snippet']['description']
        _thumbnail = video_data['snippet']['thumbnails']['high']['url']
        _video_url = f'https://youtube.com/watch?v={video_data["id"]}'

        embed = self.bot.embeds.embed_builder(
            title=f"<:youtubeiconred:660897027114401792>  {_channel_title} - Live on YouTube",
            description="", has_footer=False)
        embed.add_field(name="Title", value=f"[{_title}]({_video_url})", inline=False)
        embed.add_field(name="Description", value=self.reduce_youtube_description(_description), inline=False)

        if _thumbnail.startswith('https://'):
            embed.set_image(url=_thumbnail)

        if config.YOUTUBE_EVERYONE_PING_ON_STREAM:
            await discord_channel.send(f'@everyone {_channel_title} is live on YouTube!', embed=embed)
        else:
            await discord_channel.send(f'{_channel_title} is live on YouTube!', embed=embed)

    async def get_newest_upload(self):
        try:
            async with self.bot.session.get(self.playlist_url, headers=self.header) as response:
                return await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in YouTube session.get()!")
            return None

    @tasks.loop(minutes=10)
    async def youtube_upload_tasks(self):

        # A standard Google API key has 10.000 units per day
        # This task, with the minutes set to 10, costs approx. 2160 units per day

        if self.first_run:
            self.first_run = False
            return

        try:
            discord_channel = self.bot.democraciv_guild_object.get_channel(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable YouTube announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

        if discord_channel is None:
            raise exceptions.ChannelNotFoundError(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        youtube_data = await self.get_newest_upload()

        if youtube_data is None:
            return

        # Each check last 3 uploads in case we missed some in between
        for i in range(3):
            youtube_video = youtube_data["items"][i]

            _id = youtube_video["snippet"]["resourceId"]["videoId"]

            # Try to add post id to database
            status = await self.bot.db.execute("INSERT INTO youtube_uploads (id) VALUES ($1) ON CONFLICT DO NOTHING",
                                               _id)

            # ID already in database -> post already seen
            if status == "INSERT 0 0":
                continue

            title = youtube_video['snippet']['title']
            channel = youtube_video['snippet']['channelTitle']
            description = youtube_video['snippet']['description']
            thumbnail_url = youtube_video['snippet']['thumbnails']['high']['url']
            video_link = f"https://youtube.com/watch?v={_id}"

            embed = self.bot.embeds.embed_builder(
                title=f"<:youtubeiconwhite:660114810444447774>  {channel} - New YouTube video uploaded",
                description="", has_footer=False)
            embed.add_field(name="Title", value=f"[{title}]({video_link})", inline=False)
            embed.add_field(name="Description", value=self.reduce_youtube_description(description), inline=False)
            embed.set_image(url=thumbnail_url)

            await discord_channel.send(embed=embed)

    @youtube_upload_tasks.before_loop
    async def before_youtube_task(self):
        await self.bot.wait_until_ready()
