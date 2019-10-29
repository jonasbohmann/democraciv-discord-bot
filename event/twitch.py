import json
import config
import asyncio
import discord
import requests
import datetime


# -- Twitch  --
# Background task that posts an alert if twitch.tv/democraciv is live

class Twitch:

    def __init__(self, bot):
        self.bot = bot
        self.twitchAPIUrl = "https://api.twitch.tv/helix/streams?user_login=" + config.getTwitch()['twitchChannelName']
        self.newTwitchAPIToken = config.getTokenFile()['twitchAPIKey']
        self.httpHeader = {'Client-ID': self.newTwitchAPIToken}
        self.streamer = config.getTwitch()['twitchChannelName']
        self.activeStream = False

    def checkTwitchLivestream(self):
        try:
            twitchRequest = requests.get(self.twitchAPIUrl, headers=self.httpHeader)
        except ConnectionError as e:
            print("ERROR - ConnectionError in Twitch requests.get()!\n")
            print(e)

        twitch = json.loads(twitchRequest.content)

        try:
            twitch['data'][0]['id']
        except (IndexError, KeyError) as e:
            self.activeStream = False
            return False

        thumbnail = twitch['data'][0]['thumbnail_url'].replace('{width}', '720').replace('{height}', '380')
        return [twitch['data'][0]['title'], thumbnail]

    async def twitch_task(self):
        await self.bot.wait_until_ready()

        try:
            dcivGuild = self.bot.get_guild(int(config.getConfig()["homeServerID"]))
            channel = discord.utils.get(dcivGuild.text_channels, name=config.getTwitch()['twitchAnnouncementChannel'])
        except AttributeError:
            print(
                f'ERROR - I could not find the Democraciv Discord Server! Change "homeServerID" '
                f'in the config to a server I am in or disable Twitch announcements.')
            return

        while not self.bot.is_closed():
            twitch_data = self.checkTwitchLivestream()
            if twitch_data is not False:
                if self.activeStream is False:
                    self.activeStream = True
                    embed = discord.Embed(title=f":satellite: {self.streamer} - Live on Twitch", colour=0x7f0000)
                    embed.add_field(name="Title", value=twitch_data[0], inline=False)
                    embed.add_field(name="Link", value=f"https://twitch.tv/{self.streamer}", inline=False)
                    embed.set_image(url=twitch_data[1])
                    embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                    embed.timestamp = datetime.datetime.utcnow()
                    if config.getTwitch()['everyonePingOnAnnouncement']:
                        await channel.send(f'@everyone {self.streamer} is live on Twitch!')
                    await channel.send(embed=embed)
            await asyncio.sleep(180)
