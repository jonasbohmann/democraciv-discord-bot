import aiohttp
import asyncio

import util.exceptions as exceptions

from discord.ext import tasks
from config import config, token, links
from util import mk


# -- Twitch  --
# Background task that posts an alert if twitch.tv/democraciv is live

class Twitch:

    def __init__(self, bot):
        self.bot = bot
        self.streamer = config.TWITCH_CHANNEL
        self.twitch_API_url = "https://api.twitch.tv/helix/streams?user_login=" + self.streamer
        self.twitch_API_token = token.TWITCH_API_KEY
        self.http_header = {'Client-ID': self.twitch_API_token}
        self.first_run = True

        if self.twitch_API_token != "" and self.twitch_API_token is not None:
            self.twitch_task.start()

    def __del__(self):
        self.twitch_task.cancel()

    async def check_twitch_livestream(self):
        try:
            async with self.bot.session.get(self.twitch_API_url, headers=self.http_header) as response:
                twitch = await response.json()
        except aiohttp.ClientConnectionError:
            print("[BOT] ERROR - aiohttp.ClientConnectionError in Twitch session.get()!")
            return 0

        try:
            _stream_id = twitch['data'][0]['id']
        except (IndexError, KeyError):
            # Streamer is not live
            return 0
        else:
            # Streamer is currently live
            status = await self.bot.db.execute("INSERT INTO twitch_streams (id) VALUES ($1) ON CONFLICT DO NOTHING",
                                               _stream_id)

            # ID already in database -> stream already announced
            if status == "INSERT 0 0":
                return [1, _stream_id]

            # Get thumbnail in right size
            thumbnail = twitch['data'][0]['thumbnail_url'].replace('{width}', '720').replace('{height}', '380')
            return [2, _stream_id, twitch['data'][0]['title'], thumbnail]

    @tasks.loop(minutes=3)
    async def twitch_task(self):

        if self.first_run:
            self.first_run = False
            return

        try:
            channel = self.bot.democraciv_guild_object.get_channel(config.TWITCH_ANNOUNCEMENT_CHANNEL)
        except AttributeError:
            print(f'[BOT] ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable Twitch announcements.')
            raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

        if channel is None:
            raise exceptions.ChannelNotFoundError(config.TWITCH_ANNOUNCEMENT_CHANNEL)

        twitch_data = await self.check_twitch_livestream()

        # 0 represents no active stream
        if twitch_data == 0:
            return

        # 1 represents active stream that we already announced
        elif twitch_data[0] == 1:

            # Check if we sent the streaming rules reminder
            sent_exec_reminder = await self.bot.db.fetchrow("SELECT has_sent_exec_reminder FROM twitch_streams"
                                                            " WHERE id = $1", twitch_data[1])

            if sent_exec_reminder is not None:
                sent_exec_reminder = sent_exec_reminder['has_sent_exec_reminder']

            if not sent_exec_reminder:
                await self.streaming_rules_reminder(twitch_data[1])

            # Check if we sent the mod reminder
            sent_mod_reminder = await self.bot.db.fetchrow("SELECT has_sent_mod_reminder FROM twitch_streams"
                                                           " WHERE id = $1", twitch_data[1])

            if sent_mod_reminder is not None:
                sent_mod_reminder = sent_mod_reminder['has_sent_mod_reminder']

            if not sent_mod_reminder:
                # TODO - This does not work how you want it to work
                # await self.export_twitch_reminder(twitch_data[1])

                pass

        # 2 represents active stream that we did not yet announce
        elif twitch_data[0] == 2:
            embed = self.bot.embeds.embed_builder(title=f"<:twitch:660116652012077080>  {self.streamer} - "
                                                        f"Live on Twitch",
                                                  description="", has_footer=False)
            embed.add_field(name="Title", value=twitch_data[2], inline=False)
            embed.add_field(name="Link", value=f"https://twitch.tv/{self.streamer}", inline=False)
            embed.set_image(url=twitch_data[3])

            if config.TWITCH_EVERYONE_PING_ON_ANNOUNCEMENT:
                await channel.send(f'@everyone {self.streamer} is live on Twitch!')
            else:
                await channel.send(f'{self.streamer} is live on Twitch!')

            await channel.send(embed=embed)

            # Send reminder about streaming rules to executive channel
            await self.streaming_rules_reminder(twitch_data[1])

            # Send reminder to moderation to export Twitch VOD
            await self.export_twitch_reminder(twitch_data[1])

    @twitch_task.before_loop
    async def before_twitch_task(self):
        await self.bot.wait_until_ready()

    async def streaming_rules_reminder(self, stream_id):
        executive_channel = mk.get_executive_channel(self.bot)
        minister_role = mk.get_minister_role(self.bot)
        governor_role = mk.get_governor_role(self.bot)
        executive_proxy_role = mk.get_executive_proxy_role(self.bot)

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

        await self.bot.db.execute("UPDATE twitch_streams SET has_sent_exec_reminder = true WHERE id = $1",
                                  stream_id)

    async def export_twitch_reminder(self, stream_id):
        moderation_channel = mk.get_moderation_team_channel(self.bot)

        if moderation_channel is None:
            raise exceptions.ChannelNotFoundError("moderation-team")

        await asyncio.sleep(7200)  # Wait 2 hours, i.e. after the game session is done, before sending reminder to Mods

        embed = self.bot.embeds.embed_builder(title="Export the Game Session to YouTube",
                                              description="Looks like another game session was played!"
                                                          " Remember to export the Twitch "
                                                          "VOD to YouTube.")

        embed.add_field(name="Export to YouTube", value="Go to our [channel](https://www.twitch.tv/democraciv/manager),"
                                                        " select the last stream and hit 'Export'.", inline=False)

        embed.add_field(name="Set the title", value=f"Use this formatting for the title `Democraciv MK{mk.MARK} - "
                                                    f"Game Session X: Turns A-B`.", inline=False)

        embed.add_field(name="Set the description",
                        value=f"Use this formatting for the description: ```This is the Xth game session of "
                              f"Democraciv MK{mk.MARK}, where we play as {mk.NATION_NAME} in {mk.CIV_GAME}.\n\n"
                              f"Democraciv is a community on Reddit dedicated to play a single-player game of"
                              f" {mk.CIV_GAME} with a simulated, model government. We have a Legislature, a Supreme "
                              f"Court and an executive branch, those wo can be seen playing the game here."
                              f"\n\nDemocraciv: https://old.reddit.com/r/democraciv/```", inline=False)

        embed.add_field(name="Add some tags", value="Add some variations of `Democraciv`, `Civ 5`, `Game Politics`, "
                                                    "`Game Roleplay`, `Civ Politics`, `Civ Roleplay`,"
                                                    " `Reddit roleplay`, `Discord roleplay`, `parliament` "
                                                    "or whatever comes to your mind.", inline=False)

        embed.add_field(name="Set the visibility", value="Set the visibility of the VOD to 'Public' and hit"
                                                         " 'Start export'.", inline=False)

        embed.add_field(name="Add the new video to the playlist",
                        value=f"Don't forget this part! After the Twitch VOD was exported to YouTube, head over "
                              f"[here](https://studio.youtube.com/channel/UC-NukxPakwQIvx73VjtIPnw/videos/) "
                              f"and add the new video to the playlist named 'MK{mk.MARK} Game Sessions'.", inline=False)

        embed.add_field(name="Adjust description & tags on YouTube",
                        value="Twitch automatically adds a paragraph about Twitch to the end of the exported video's "
                              "description and the two tags 'twitch' & 'games'. Make sure to remove both things.",
                        inline=False)

        embed.add_field(name="Add Game Session to Wiki",
                        value=f"Add an entry for this new game session"
                              f" [here]({links.gswiki}).",
                        inline=False)

        embed.add_field(name="Upload the save-game to Google Drive", value="Once a ministers sends you the save-game, "
                                                                           "upload it to our Google Drive under "
                                                                           "'Drive/Game/Savegames'.", inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        await moderation_channel.send(content='@here', embed=embed)

        await self.bot.db.execute("UPDATE twitch_streams SET has_sent_mod_reminder = true WHERE id = $1",
                                  stream_id)
