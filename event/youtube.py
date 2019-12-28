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
                            f"&key={token.YOUTUBE_DATA_V3_API_KEY}"
        self.first_run = True

        if self.api_key != "" and self.api_key is not None:
            self.youtube_upload_tasks.start()

    def __del__(self):
        self.youtube_upload_tasks.cancel()

    async def get_newest_upload(self):
        try:
            async with self.bot.session.get(f"{self.playlist_url}", headers=self.header) as response:
                return await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in YouTube session.get()!")
            return None

    @tasks.loop(minutes=5)
    async def youtube_upload_tasks(self):

        if self.first_run:
            self.first_run = False
            return

        youtube_data = await self.get_newest_upload()

        if youtube_data is None:
            return

        try:
            discord_channel = self.bot.democraciv_guild_object.get_channel(config.YOUTUBE_ANNOUNCEMENT_CHANNEL)

        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable YouTube announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

        if discord_channel is None:
            raise exceptions.ChannelNotFoundError(config.REDDIT_ANNOUNCEMENT_CHANNEL)

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
                title=f"<:youtube:660114810444447774>  {channel} - New YouTube video uploaded",
                description="", has_footer=False)
            embed.add_field(name="Title", value=f"[{title}]({video_link})", inline=False)
            embed.add_field(name="Description", value=f"{description}", inline=False)
            embed.set_image(url=thumbnail_url)

            await discord_channel.send(embed=embed)

    @youtube_upload_tasks.before_loop
    async def before_youtube_task(self):
        await self.bot.wait_until_ready()




