import aiohttp
import asyncio

import util.exceptions as exceptions

from discord.ext import tasks
from config import config, token


# -- Twitch  --
# Background task that posts an alert if twitch.tv/democraciv is live

class Twitch:

    def __init__(self, bot):
        self.bot = bot
        self.streamer = config.TWITCH_CHANNEL
        self.twitch_API_url = "https://api.twitch.tv/helix/streams?user_login=" + self.streamer
        self.twitch_API_token = token.TWITCH_API_KEY
        self.http_header = {'Client-ID': self.twitch_API_token}
        self.active_stream = False
        self.first_run = True
        self.twitch_task.start()

    def __del__(self):
        self.twitch_task.cancel()

    async def streaming_rules_reminder(self):
        executive_channel = self.bot.get_channel(637051136955777049)  # #executive channel
        minister_role = self.bot.democraciv_guild_object.get_role(639438027852087297)  # 'Minister' role
        governor_role = self.bot.democraciv_guild_object.get_role(639438794239639573)  # 'Governor of Mecca' role
        executive_proxy_role = self.bot.democraciv_guild_object.get_role(643190277494013962)  # 'Executive Proxy' role

        if executive_channel is None:
            raise exceptions.ChannelNotFoundError("executive")

        embed = self.bot.embeds.embed_builder(title="Streaming Guidelines",
                                              description="Looks like you're starting another game session."
                                                          " Remember these guidelines!")

        embed.add_field(name="Don't show the stream key", value="Never show the stream key or the DMs with the "
                                                                "moderator that sent you the key on stream!",
                        inline=False)

        embed.add_field(name="Introduce yourself", value="No one knows which voice belongs to whom!"
                                                         " Introduce yourself with your name and position.",
                        inline=False)
        embed.add_field(name="Keep it short", value="In the past, streams often were too long. Keep the stream "
                                                    "short and don't waste time by starting the stream when not every "
                                                    "minister is ready or the game is not even started yet!",
                        inline=False)
        embed.add_field(name="Hand over the save-game", value="Remember to send the save-game to one of"
                                                              " the moderators after the stream!", inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        if minister_role is not None and governor_role is not None and executive_proxy_role is not None:
            await executive_channel.send(f"{minister_role.mention} {governor_role.mention} "
                                         f"{executive_proxy_role.mention}")

        await executive_channel.send(embed=embed)

    async def export_twitch_reminder(self):
        moderation_channel = self.bot.get_channel(209410498804973569)  # #moderation-team channel

        if moderation_channel is None:
            raise exceptions.ChannelNotFoundError("moderation-team")

        await asyncio.sleep(7200)  # Wait 2 hours, i.e. after the game session is done, before sending reminder to Mods

        embed = self.bot.embeds.embed_builder(title="Export the Game Session to YouTube",
                                              description="Looks like another game session was played!"
                                                          " Remember to export the Twitch "
                                                          "VOD to YouTube.")

        embed.add_field(name="Export to YouTube", value="Go to our [channel](https://www.twitch.tv/democraciv/manager),"
                                                        " select the last stream and hit 'Export'.", inline=False)

        embed.add_field(name="Set the title", value="Use this formatting for the title `Democraciv MK6 - "
                                                    "Game Session X`.", inline=False)

        embed.add_field(name="Set the description",
                        value="Use this formatting for the description: ```This is the Xth game session of the of "
                              "Democraciv MK6, where we play as Arabia in Sid Meier's Civilization 5.\n\nDemocraciv"
                              " is a community on Reddit dedicated to play a single-player game of Sid Meier's"
                              " Civilization 5 with a simulated, model government. We have a Legislature, a Supreme "
                              "Court and an executive branch, those wo can be seen playing the game here."
                              "\n\nDemocraciv: https://old.reddit.com/r/democraciv/```", inline=False)

        embed.add_field(name="Add some tags", value="Add some variations of `Democraciv`, `Civ 5`, `Game Politics`, "
                                                    "`Game Roleplay`, `Civ Politics`, `Civ Roleplay`,"
                                                    " `Reddit roleplay`, `Discord roleplay`, `parliament` "
                                                    "or whatever comes to your mind.", inline=False)

        embed.add_field(name="Set the visibility", value="Set the visibility of the VOD to 'Public' and hit"
                                                         " 'Start export'.", inline=False)

        embed.add_field(name="Add the new video to the playlist",
                        value="Don't forget this part! After the Twitch VOD was exported to YouTube, head over "
                              "[here](https://studio.youtube.com/channel/UC-NukxPakwQIvx73VjtIPnw/videos/) "
                              "and add the new video to the playlist named 'MK6 Game Sessions'.", inline=False)

        embed.add_field(name="Adjust description & tags on YouTube",
                        value="Twitch automatically adds a paragraph about Twitch to the end of the exported video's "
                              "description and the two tags 'twitch' & 'games'. Make sure to remove both things.",
                        inline=False)

        embed.add_field(name="Add Game Session to Wiki",
                        value="Add an entry for this new game session"
                              " [here](https://reddit.com/r/democraciv/wiki/game-sessions).",
                        inline=False)

        embed.add_field(name="Upload the save-game to Google Drive", value="Once a ministers sends you the save-game, "
                                                                           "upload it to our Google Drive under "
                                                                           "'Drive/Game/Savegames'.", inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        await moderation_channel.send("@here")
        await moderation_channel.send(embed=embed)

    async def check_twitch_livestream(self):
        try:
            async with self.bot.session.get(self.twitch_API_url, headers=self.http_header) as response:
                twitch = await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - ConnectionError in Twitch session.get()!")
            return False

        try:
            twitch['data'][0]['id']
        except (IndexError, KeyError):
            self.active_stream = False
            return False

        thumbnail = twitch['data'][0]['thumbnail_url'].replace('{width}', '720').replace('{height}', '380')
        return [twitch['data'][0]['title'], thumbnail]

    @tasks.loop(minutes=5)
    async def twitch_task(self):

        if self.first_run:
            self.first_run = False
            return

        try:
            channel = self.bot.democraciv_guild_object.get_channel(config.TWITCH_ANNOUCEMENT_CHANNEL)
        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable Twitch announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

        if channel is None:
            raise exceptions.ChannelNotFoundError(config.TWITCH_ANNOUCEMENT_CHANNEL)

        twitch_data = await self.check_twitch_livestream()
        if twitch_data is not False:
            if self.active_stream is False:
                self.active_stream = True

                embed = self.bot.embeds.embed_builder(title=f":satellite: {self.streamer} - Live on Twitch",
                                                      description="", time_stamp=True)
                embed.add_field(name="Title", value=twitch_data[0], inline=False)
                embed.add_field(name="Link", value=f"https://twitch.tv/{self.streamer}", inline=False)
                embed.set_image(url=twitch_data[1])

                if config.TWITCH_EVERYONE_PING_ON_ANNOUNCEMENT:
                    await channel.send(f'@everyone {self.streamer} is live on Twitch!')

                await channel.send(embed=embed)

                # Send reminder about streaming rules to executive channel
                await self.streaming_rules_reminder()

                # Send reminder to moderation to export Twitch VOD
                await self.export_twitch_reminder()

    @twitch_task.before_loop
    async def before_twitch_task(self):
        await self.bot.wait_until_ready()
