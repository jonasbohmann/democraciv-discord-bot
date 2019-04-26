import sys
import json
import config
import discord
import asyncio
import datetime
import requests
import traceback
import discord.utils
import pkg_resources

from discord.ext import commands

# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Interpreter: Python3.7
# Library: discord.py 1.0.0a
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- client.py --
#
# Main part of the bot. Loads all modules on startup. Remove or add new modules by adding or removing them to/from
# "initial_extensions".
#
# All things relevant to event logging are handled here as well.
#

client = commands.Bot(command_prefix=config.getPrefix(), description=config.getConfig()['botDescription'],
                      case_insensitive=True)
author = discord.AppInfo.owner

# Twitch
activeStream = False

initial_extensions = ['module.link',
                      'module.about',
                      'module.vote',
                      'module.time',
                      'module.fun',
                      'module.admin',
                      'module.parties',
                      'module.help',
                      'module.wikipedia',
                      'module.random',
                      'module.role',
                      'event.logging',
                      'event.error_handler']

if __name__ == '__main__':
    for extension in initial_extensions:
        try:
            client.load_extension(extension)
            print('Successfully loaded ' + extension)
        except Exception as e:
            print(f'Failed to load module {extension}.', file=sys.stderr)
            traceback.print_exc()


def checkTwitchLivestream():
    twitchAPIUrl = "https://api.twitch.tv/kraken/streams/" + config.getTwitch()['twitchChannelName'] + "?client_id=" + \
                   config.getTokenFile()['twitchAPIKey']
    twitchRequest = requests.get(twitchAPIUrl)
    twitch = json.loads(twitchRequest.content)
    global activeStream

    if twitch['stream'] is not None:
        return [twitch['stream']['channel']['status'], twitch['stream']['preview']['medium']]
    else:
        activeStream = False
        return False


@client.event
async def twitch_task():
    await client.wait_until_ready()
    global activeStream
    streamer = config.getTwitch()['twitchChannelName']

    try:
        dcivGuild = client.get_guild(int(config.getConfig()["homeServerID"]))
        channel = discord.utils.get(dcivGuild.text_channels, name=config.getTwitch()['twitchAnnouncementChannel'])
    except AttributeError:
        print(
            f'ERROR - I could not find the Democraciv Discord Server! Change "homeServerID" '
            f'in the config to a server I am in or disable Twitch announcements.')
        return

    while not client.is_closed():
        twitch_data = checkTwitchLivestream()
        if twitch_data is not False:
            if activeStream is False:
                activeStream = True
                embed = discord.Embed(title=f":satellite: {streamer} - Live on Twitch", colour=0x7f0000)
                embed.add_field(name="Title", value=twitch_data[0], inline=False)
                embed.add_field(name="Link", value=f"https://twitch.tv/{streamer}", inline=False)
                embed.set_image(url=twitch_data[1])
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.timestamp = datetime.datetime.utcnow()
                if config.getTwitch()['everyonePingOnAnnouncement']:
                    await channel.send(f'@everyone {streamer} is live on Twitch!')
                await channel.send(embed=embed)
        await asyncio.sleep(30)


@client.event
async def on_ready():
    print('Logged in as ' + client.user.name + ' with discord.py ' + str(
        pkg_resources.get_distribution('discord.py').version))
    print('-------------------------------------------------------')
    if config.getTwitch()['enableTwitchAnnouncements']:
        client.bg_task = client.loop.create_task(twitch_task())
    await client.change_presence(
        activity=discord.Game(name=config.getPrefix() + 'help | Watching over r/Democraciv'))


@client.event
async def on_message(message):
    if isinstance(message.channel, discord.DMChannel):
        await message.author.send(':x: Sorry, but I don\'t accept commands through direct messages!')
        return
    if message.author.bot:
        return
    await client.process_commands(message)


try:
    client.run(config.getToken(), reconnect=True, bot=True, timeout=3600)
except asyncio.TimeoutError:
    print('ERROR - TimeoutError')
