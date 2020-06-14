import enum
import typing
import asyncio

import util.exceptions as exceptions

from util import mk
from discord.ext import tasks, commands
from config import config, token


class Twitch(commands.Cog):
    """Announcements for new live streams on Twitch."""

    class StreamStatus(enum.Enum):
        OFFLINE = 0
        LIVE_AND_ANNOUNCED = 1
        LIVE_AND_NOT_ANNOUNCED = 2

    def __init__(self, bot):
        self.bot = bot
        self.streamer = config.TWITCH_CHANNEL
        self.twitch_API_url = "https://api.twitch.tv/helix/streams?user_login=" + self.streamer
        self.twitch_oauth_token = token.TWITCH_OAUTH_APP_ACCESS_TOKEN

        if config.TWITCH_ENABLED and self.twitch_oauth_token:
            self.twitch_task.start()

    def cog_unload(self):
        self.twitch_task.cancel()

    async def refresh_twitch_oauth_token(self):
        """Gets a new app access_token for the Twitch Helix API"""

        post_data = {"client_id": token.TWITCH_CLIENT_ID, "client_secret": token.TWITCH_CLIENT_SECRET,
                     "grant_type": "client_credentials"}

        async with self.bot.session.post("https://id.twitch.tv/oauth2/token", data=post_data) as response:
            if response.status == 200:
                r = await response.json()
                self.twitch_oauth_token = r['access_token']
                print(f"[BOT] - New Twitch Helix OAuth App Access Token received. Please add it to token.py."
                      f"\n{self.twitch_oauth_token}")
                await self.bot.owner.send("New Twitch Helix OAuth App Access Token received. "
                                          "See logs and replace in token.py")

    async def check_twitch_livestream(self) -> typing.Union[StreamStatus, typing.List]:
        """Checks if a streamer is live and returns the corresponding StreamStatus. If a stream has not yet been
        announced, also returns relevant stream data."""

        async with self.bot.session.get(self.twitch_API_url,
                                        headers={'Authorization': f"Bearer {self.twitch_oauth_token}",
                                                 'Client-ID': token.TWITCH_CLIENT_ID}) as response:
            if response.status == 200:
                twitch = await response.json()
            elif response.status == 401:
                await self.refresh_twitch_oauth_token()
                return self.StreamStatus.OFFLINE
            else:
                return self.StreamStatus.OFFLINE

        try:
            _stream_id = twitch['data'][0]['id']
        except (IndexError, KeyError):
            return self.StreamStatus.OFFLINE

        else:
            # Streamer is currently live
            status = await self.bot.db.execute("INSERT INTO twitch_streams (id) VALUES ($1) ON CONFLICT DO NOTHING",
                                               _stream_id)

            # ID already in database -> stream already announced
            if status == "INSERT 0 0":
                return self.StreamStatus.LIVE_AND_ANNOUNCED

            # Get thumbnail in right size
            thumbnail = twitch['data'][0]['thumbnail_url'].replace('{width}', '720').replace('{height}', '380')
            return [self.StreamStatus.LIVE_AND_NOT_ANNOUNCED, _stream_id, twitch['data'][0]['title'], thumbnail]

    @tasks.loop(seconds=30)
    async def twitch_task(self):
        """Checks every 30 seconds if a stream is live on Twitch. If it is and has not been announced yet, send
        announcement and mod/executive reminders to specified Discord channel."""

        try:
            channel = self.bot.democraciv_guild_object.get_channel(config.TWITCH_ANNOUNCEMENT_CHANNEL)
        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "DEMOCRACIV_GUILD_ID" '
                  f'in the config.py to a server I am in or disable Twitch announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_GUILD_ID)

        if channel is None:
            print("[BOT] ERROR - The TWITCH_ANNOUNCEMENT_CHANNEL id in config.py is not a channel on the"
                  " specified Democraciv guild.")
            raise exceptions.ChannelNotFoundError(config.TWITCH_ANNOUNCEMENT_CHANNEL)

        twitch_data = await self.check_twitch_livestream()

        if twitch_data == self.StreamStatus.OFFLINE:
            return

        elif twitch_data == self.StreamStatus.LIVE_AND_ANNOUNCED:
            return

        elif twitch_data[0] == self.StreamStatus.LIVE_AND_NOT_ANNOUNCED:
            embed = self.bot.embeds.embed_builder(title=f"{config.TWITCH_LOGO}  {self.streamer} - "
                                                        f"Live on Twitch",
                                                  description="", has_footer=False, colour=0x984efc)
            embed.add_field(name="Title", value=twitch_data[2], inline=False)
            embed.add_field(name="Link", value=f"https://twitch.tv/{self.streamer}", inline=False)
            embed.set_image(url=twitch_data[3])

            if config.TWITCH_EVERYONE_PING_ON_ANNOUNCEMENT:
                await channel.send(f'@everyone {self.streamer} is live on Twitch!', embed=embed)
            else:
                await channel.send(f'{self.streamer} is live on Twitch!', embed=embed)

            if config.TWITCH_ANNOUNCEMENT_TO_REDDIT:
                data = {
                    "kind": "link",
                    "nsfw": False,
                    "sr": config.REDDIT_SUBREDDIT,
                    "title": f"{self.streamer} is live on Twitch: {twitch_data[2]}",
                    "spoiler": False,
                    "resubmit": True,
                    "url": f"https://twitch.tv/{self.streamer}"
                }

                await self.bot.reddit_api.post_to_reddit(data)

            # Send reminder about streaming rules to executive channel
            await self.streaming_rules_reminder()

            # Send reminder to moderation to export Twitch VOD
            await self.export_twitch_reminder()

    @twitch_task.before_loop
    async def before_twitch_task(self):
        await self.bot.wait_until_ready()

        # Delay first run of task until Democraciv Guild has been found
        if self.bot.democraciv_guild_object is None:
            await asyncio.sleep(5)

    async def streaming_rules_reminder(self):
        executive_channel = mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.EXECUTIVE_CHANNEL)

        try:
            minister_role = mk.get_democraciv_role(self.bot, mk.DemocracivRole.MINISTER_ROLE)
            governor_role = mk.get_democraciv_role(self.bot, mk.DemocracivRole.GOVERNOR_ROLE)
            executive_proxy_role = mk.get_democraciv_role(self.bot, mk.DemocracivRole.EXECUTIVE_PROXY_ROLE)
        except exceptions.RoleNotFoundError:
            minister_role = governor_role = executive_proxy_role = None

        if executive_channel is None:
            raise exceptions.ChannelNotFoundError("executive")

        embed = self.bot.embeds.embed_builder(title="Streaming Guidelines",
                                              description="Looks like you're starting another game session. "
                                                          "Remember these guidelines!")

        embed.add_field(name="Don't show the stream key",
                        value="Never show the stream key or the DMs with the "
                              "moderator that sent you the key on stream!",
                        inline=False)

        embed.add_field(name="Introduce yourself",
                        value="No one knows which voice belongs to whom! "
                              "Introduce yourself with your name and position.",
                        inline=False)

        embed.add_field(name="Keep it short",
                        value="In the past, streams often were too long. Keep the stream "
                              "short and don't waste time by starting the stream when not everyone "
                              "is ready or the game is not even started yet!",
                        inline=False)

        embed.add_field(name="Hand over the save-game",
                        value="Remember to send the save-game to one of "
                              "the moderators after the stream!",
                        inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        if minister_role is not None and governor_role is not None and executive_proxy_role is not None:
            await executive_channel.send(f"{minister_role.mention} {governor_role.mention} "
                                         f"{executive_proxy_role.mention}")

        await executive_channel.send(embed=embed)

    async def export_twitch_reminder(self):
        moderation_channel = mk.get_democraciv_channel(self.bot, mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL)

        await asyncio.sleep(7200)  # Wait 2 hours, i.e. after the game session is done, before sending reminder to Mods

        mark = self.bot.mk.MARK
        game = self.bot.mk.CIV_GAME
        nation = self.bot.mk.NATION_NAME

        embed = self.bot.embeds.embed_builder(title="Export the Game Session to YouTube",
                                              description="Looks like another game session was played! "
                                                          "Remember to export the Twitch VOD to YouTube.")

        embed.add_field(name="Export to YouTube",
                        value="Go to our [channel](https://www.twitch.tv/democraciv/manager), "
                              "select the last stream and hit 'Export'.",
                        inline=False)

        embed.add_field(name="Set the title",
                        value=f"Use this formatting for the title `Democraciv MK{mark} - "
                              f"Game Session X: Turns A-B`.",
                        inline=False)

        embed.add_field(name="Set the description",
                        value=f"Use this formatting for the description: ```This is the Xth game session of "
                              f"Democraciv MK{mark}, where we play as {nation} in {game}.\n\n"
                              f"Democraciv is a community on Reddit dedicated to play a game of "
                              f"{game} with a simulated, model government. We have a Legislature, a Supreme "
                              f"Court and an executive branch, those who can be seen playing the game here."
                              f"\n\nDemocraciv: https://reddit.com/r/democraciv/```",
                        inline=False)

        embed.add_field(name="Add some tags",
                        value=f"Add some variations of `Democraciv`, `Civ {game}`, `Game Politics`, "
                              f"`Game Roleplay`, `Civ Politics`, `Civ Roleplay`, "
                              f"`Reddit roleplay`, `Discord roleplay`, `parliament` "
                              f"or whatever comes to your mind.",
                        inline=False)

        embed.add_field(name="Set the visibility",
                        value="Set the visibility of the VOD to 'Public' and hit 'Start export'.",
                        inline=False)

        embed.add_field(name="Update the stream title",
                        value="Edit the title of our stream on Twitch for the next game "
                              "session by incrementing the number.",
                        inline=False)

        embed.add_field(name="Add the new video to the playlist",
                        value=f"Don't forget this part! After the Twitch VOD was exported to YouTube, head over "
                              f"[here](https://studio.youtube.com/channel/UC-NukxPakwQIvx73VjtIPnw/videos/) "
                              f"and add the new video to the playlist named 'MK{mark} Game Sessions'.",
                        inline=False)

        embed.add_field(name="Adjust description & tags on YouTube",
                        value="Twitch automatically adds a paragraph about Twitch to the end of the exported video's "
                              "description and the two tags 'twitch' & 'games'. Make sure to remove both things.",
                        inline=False)

        embed.add_field(name="Add Game Session to Wiki",
                        value=f"Add an entry for this new game session to the wiki.",
                        inline=False)

        embed.add_field(name="Upload the save-game to Google Drive",
                        value="Once someone sends you the save-game, "
                              "upload it to our Google Drive under "
                              "'Drive/Game/Savegames'.",
                        inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        await moderation_channel.send(content='@here', embed=embed)


def setup(bot):
    if config.TWITCH_ENABLED:
        bot.add_cog(Twitch(bot))
