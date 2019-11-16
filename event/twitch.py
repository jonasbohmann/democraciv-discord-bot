import config
import aiohttp
import asyncio
import discord
import datetime

import util.exceptions as exceptions


# -- Twitch  --
# Background task that posts an alert if twitch.tv/democraciv is live

class Twitch:

    def __init__(self, bot):
        self.bot = bot
        self.twitch_API_url = "https://api.twitch.tv/helix/streams?user_login=" + config.getTwitch()[
            'twitchChannelName']
        self.twitch_API_token = config.getTokenFile()['twitchAPIKey']
        self.http_header = {'Client-ID': self.twitch_API_token}
        self.streamer = config.getTwitch()['twitchChannelName']
        self.active_stream = False

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
        embed.add_field(name="Hand over the savegame", value="Remember to send the savegame to one of"
                                                             " the moderators after the stream!", inline=False)

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/423938725525979146/"
                                "645394491133394966/01-twitch-logo.jpg")

        if minister_role is not None and governor_role is not None and executive_proxy_role is not None:
            await executive_channel.send(f"{minister_role.mention} {governor_role.mention} "
                                         f"{executive_proxy_role.mention}")

        await executive_channel.send(embed=embed)

    async def check_twitch_livestream(self):
        try:
            async with self.bot.session.get(self.twitch_API_url, headers=self.http_header) as response:
                twitch = await response.json()
        except aiohttp.ClientConnectionError as e:
            print("ERROR - ConnectionError in Twitch session.get()!\n")
            print(e)

        try:
            twitch['data'][0]['id']
        except (IndexError, KeyError):
            self.active_stream = False
            return False

        thumbnail = twitch['data'][0]['thumbnail_url'].replace('{width}', '720').replace('{height}', '380')
        return [twitch['data'][0]['title'], thumbnail]

    async def twitch_task(self):
        await self.bot.wait_until_ready()

        try:
            channel = discord.utils.get(self.bot.democraciv_guild_object.text_channels,
                                        name=config.getTwitch()['twitchAnnouncementChannel'])
        except AttributeError:
            print(f'ERROR - I could not find the Democraciv Discord Server! Change "democracivServerID" '
                  f'in the config to a server I am in or disable Twitch announcements.')
            raise exceptions.GuildNotFoundError(config.getConfig()["democracivServerID"])

        if channel is None:
            raise exceptions.ChannelNotFoundError(config.getReddit()['redditAnnouncementChannel'])

        while not self.bot.is_closed():
            twitch_data = await self.check_twitch_livestream()
            if twitch_data is not False:
                if self.active_stream is False:
                    self.active_stream = True

                    embed = self.bot.embeds.embed_builder(title=f":satellite: {self.streamer} - Live on Twitch",
                                                          description="", time_stamp=True)
                    embed.add_field(name="Title", value=twitch_data[0], inline=False)
                    embed.add_field(name="Link", value=f"https://twitch.tv/{self.streamer}", inline=False)
                    embed.set_image(url=twitch_data[1])

                    if config.getTwitch()['everyonePingOnAnnouncement']:
                        await channel.send(f'@everyone {self.streamer} is live on Twitch!')

                    await channel.send(embed=embed)

                    # Send reminder about streaming rules to executive channel
                    await self.streaming_rules_reminder()

            await asyncio.sleep(180)
