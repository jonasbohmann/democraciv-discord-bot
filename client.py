import sys
import config
import discord
import asyncio
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


client = commands.Bot(command_prefix=config.getPrefix(), description=config.getConfig()['botDescription'])
author = discord.AppInfo.owner

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


@client.event
async def on_ready():
    print('Logged in as ' + client.user.name + ' with discord.py ' + str(
        pkg_resources.get_distribution('discord.py').version))
    print('-------------------------------------------------------')
    await client.change_presence(activity=discord.Game(name=config.getPrefix() + 'help | Watching over r/Democraciv'))


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
