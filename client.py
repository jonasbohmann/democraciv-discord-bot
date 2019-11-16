import time
import math
import config
import discord
import aiohttp
import asyncio
import logging
import datetime
import traceback
import discord.utils

import util.exceptions as exceptions

from discord.ext import commands

# Internal Imports
from event.twitch import Twitch
from event.reddit import Reddit
from util.utils import CheckUtils, EmbedUtils

# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Library: discord.py 1.0.0+
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- client.py --
#
# Main part of the bot. Loads all modules on startup. Remove or add new modules by adding or removing them to/from
# "initial_extensions".
#


# Set up logging for discord.py
logging.basicConfig(level=logging.INFO)

# List of cogs that will be loaded on startup
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

        # Save the bot's start time for get_uptime()
        self.start_time = time.time()

        self.token = config.getToken()

        self.commands_cooldown = config.getCooldown()
        self.commands_prefix = config.getPrefix()

        # Initialize commands.Bot with prefix, description and disable case_sensitivity
        super().__init__(command_prefix=self.commands_prefix, description=self.description, case_insensitive=True)

        # Set up aiohttp.ClientSession() for usage in wikipedia, reddit & twitch API calls
        self.session = None
        self.task = self.loop.create_task(self.initialize_aiohttp_session())

        # Create util objects from ./util/utils.py
        self.checks = CheckUtils()
        self.embeds = EmbedUtils()

        # Attributes will be "initialized" in on_ready as they need a connection to Discord
        self.DerJonas_object = None
        self.DerJonas_dm_channel = None

        # Attribute will be "initialized" in on_ready as they need a connection to Discord
        self.democraciv_guild_object = None

        # Load the bot's cogs from ./event and ./module
        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                print(f'Successfully loaded {extension}')
            except Exception:
                print(f'Failed to load module {extension}.')
                traceback.print_exc()

        # Load jishaku
        self.load_extension("jishaku")

    async def initialize_aiohttp_session(self):
        self.session = aiohttp.ClientSession()

    def initialize_democraciv_guild(self):
        # Get Democraciv guild object
        self.democraciv_guild_object = self.get_guild(int(config.getConfig()["democracivServerID"]))

        if self.democraciv_guild_object is None:

            logging.log(logging.WARNING, "Couldn't find guild with ID specified in config.json 'democracivServerID'.\n"
                                         "I will use a random guild that I can see that will use my Democraciv-specific"
                                         " features like: parties.py, reddit.py, twitch.py and admin.py")
            for guild in self.guilds:
                self.democraciv_guild_object = guild
                break

            if self.democraciv_guild_object is None:
                raise exceptions.GuildNotFoundError(config.getConfig()["democracivServerID"])

            logging.log(logging.WARNING, f"Using '{self.democraciv_guild_object.name}' as Democraciv guild.\n"
                                         f"Note that some features will still not work unless you change "
                                         f"'democracivServerID' in config.json to a guild ID that I am in.")

    def get_uptime(self):
        difference = int(round(time.time() - self.start_time))
        return str(datetime.timedelta(seconds=difference))

    def get_ping(self):
        return math.floor(self.latency * 1000)

    async def on_ready(self):
        print(f"Logged in as {self.user.name} with discord.py {discord.__version__}")
        print("-------------------------------------------------------")

        await asyncio.sleep(1)

        self.initialize_democraciv_guild()

        # Set status on Discord
        await self.change_presence(activity=discord.Game(name=config.getPrefix() + 'help | Watching over '
                                                                                   'the Democraciv community'))

        # Create DM_channel with author and save dm_channel object for further use
        self.DerJonas_object = self.get_user(int(config.getConfig()['authorID']))
        await self.DerJonas_object.create_dm()
        self.DerJonas_dm_channel = self.DerJonas_object.dm_channel

        # Create twitch live notification task if enabled in config
        if config.getTwitch()['enableTwitchAnnouncements']:
            twitch = Twitch(self)
            self.loop.create_task(twitch.twitch_task())

        # Create reddit new post on subreddit notification task if enabled in config
        if config.getReddit()['enableRedditAnnouncements']:
            reddit = Reddit(self)
            self.loop.create_task(reddit.reddit_task())

    async def on_message(self, message):
        # Don't process message/command from DMs to prevent spamming
        if isinstance(message.channel, discord.DMChannel):
            return

        # Don't process message/command from other bots
        if message.author.bot:
            return

        # Relay message to discord.ext.commands cogs
        await self.process_commands(message)


if __name__ == '__main__':
    DemocracivBot().run(config.getToken(), reconnect=True, bot=True)
