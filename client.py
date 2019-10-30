import sys
import config
import discord
import asyncio
import traceback
import discord.utils
import pkg_resources

from event.twitch import Twitch
from event.reddit import Reddit
from discord.ext import commands

# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Interpreter: Python3.7
# Library: discord.py
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- client.py --
#
# Main part of the bot. Loads all modules on startup. Remove or add new modules by adding or removing them to/from
# "initial_extensions".
#


client = commands.Bot(command_prefix=config.getPrefix(), description=config.getConfig()['botDescription'],
                      case_insensitive=True)
author = discord.AppInfo.owner

# -- Cogs --
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


@client.event
async def on_ready():
    print('Logged in as ' + client.user.name + ' with discord.py ' + str(
        pkg_resources.get_distribution('discord.py').version))
    print('-------------------------------------------------------')
    if config.getTwitch()['enableTwitchAnnouncements']:
        twitch = Twitch(client)
        client.loop.create_task(twitch.twitch_task())

    if config.getReddit()['enableRedditAnnouncements']:
        reddit = Reddit(client)
        client.loop.create_task(reddit.reddit_task())

    await client.change_presence(
        activity=discord.Game(name=config.getPrefix() + 'help | Watching over r/Democraciv'))


@client.event
async def on_message(message):
    if isinstance(message.channel, discord.DMChannel):
        return
    if message.author.bot:
        return

    await client.process_commands(message)


if __name__ == '__main__':
    for extension in initial_extensions:
        try:
            client.load_extension(extension)
            print('Successfully loaded ' + extension)
        except Exception as e:
            print(f'Failed to load module {extension}.', file=sys.stderr)
            traceback.print_exc()

try:
    client.run(config.getToken(), reconnect=True, bot=True)
except asyncio.TimeoutError as e:
    print(f'ERROR - TimeoutError\n{e}')
