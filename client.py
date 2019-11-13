import time
import math
import config
import discord
import logging
import datetime
import traceback
import discord.utils
import pkg_resources

from discord.ext import commands

# Internal Imports
from event.twitch import Twitch
from event.reddit import Reddit
from util.utils import CheckUtils, EmbedUtils

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

logging.basicConfig(level=logging.INFO)

initial_extensions = ['module.link',
                      'module.about',
                      'module.legislature',
                      'module.time',
                      'module.fun',
                      'module.admin',
                      'module.parties',
                      'module.help',
                      'module.wikipedia',
                      'module.random',
                      'module.roles',
                      'module.guild',
                      'event.logging',
                      'event.error_handler']


class DemocracivBot(commands.Bot):

    def __init__(self):
        self.name = config.getConfig()["botName"]
        self.description = config.getConfig()["botDescription"]
        self.version = config.getConfig()["botVersion"]
        self.icon = config.getConfig()["botIconURL"]
        self.uptime = time.time()
        self.token = config.getToken()

        self.commands_cooldown = config.getCooldown()
        self.commands_prefix = config.getPrefix()

        self.checks = CheckUtils()
        self.embeds = EmbedUtils()

        self.DerJonas_object = None
        self.DerJonas_dm_channel = None

        super().__init__(command_prefix=self.commands_prefix, description=self.description, case_insensitive=True)

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                print(f'Successfully loaded {extension}')
            except Exception:
                print(f'Failed to load module {extension}.')
                traceback.print_exc()

    def get_uptime(self):
        difference = int(round(time.time() - self.uptime))
        return str(datetime.timedelta(seconds=difference))

    def get_ping(self):
        return math.floor(self.latency * 1000)

    async def on_ready(self):
        print(f"Logged in as {self.user.name} with discord.py"
              f" {str(pkg_resources.get_distribution('discord.py').version)}")
        print("-------------------------------------------------------")
        if config.getTwitch()['enableTwitchAnnouncements']:
            twitch = Twitch(self)
            self.loop.create_task(twitch.twitch_task())

        if config.getReddit()['enableRedditAnnouncements']:
            reddit = Reddit(self)
            self.loop.create_task(reddit.reddit_task())

        await self.change_presence(activity=discord.Game(name=config.getPrefix() + 'help | Watching over r/Democraciv'))

        self.DerJonas_object = self.get_user(int(config.getConfig()['authorID']))
        await self.DerJonas_object.create_dm()
        self.DerJonas_dm_channel = self.DerJonas_object.dm_channel

    async def on_message(self, message):
        if isinstance(message.channel, discord.DMChannel):
            return
        if message.author.bot:
            return

        await self.process_commands(message)


if __name__ == '__main__':
    DemocracivBot().run(config.getToken(), reconnect=True, bot=True)
