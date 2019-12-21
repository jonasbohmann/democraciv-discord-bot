import time
import math
import discord
import aiohttp
import asyncio
import asyncpg
import logging
import datetime
import traceback
import discord.utils

import util.exceptions as exceptions

from discord.ext import commands

# Internal Imports
from event.twitch import Twitch
from event.reddit import Reddit
from config import config, token
from util.law_helper import LawUtils
from util.utils import CheckUtils, EmbedUtils

# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Library: discord.py 1.2.5
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- client.py --
#
# Main part of the bot. Loads all modules on startup and initializes PostgreSQL database.
# Remove or add new modules by adding or removing them to/from "initial_extensions".
#


# Set up logging for discord.py
logging.basicConfig(level=logging.INFO)

# List of cogs that will be loaded on startup
initial_extensions = ['event.logging',
                      'event.error_handler',
                      'module.link',
                      'module.about',
                      'module.time',
                      'module.fun',
                      'module.admin',
                      'module.help',
                      'module.roles',
                      'module.guild',
                      'module.debug',
                      'module.wikipedia',
                      'module.democraciv.parties',
                      'module.democraciv.legislature',
                      'module.democraciv.laws',
                      'module.democraciv.ministry',
                      'module.democraciv.supremecourt'
                      ]


class DemocracivBot(commands.Bot):

    def __init__(self):
        self.name = config.BOT_NAME
        self.description = config.BOT_DESCRIPTION
        self.version = config.BOT_VERSION
        self.icon = config.BOT_ICON_URL

        # Save the bot's start time for get_uptime()
        self.start_time = time.time()

        self.commands_cooldown = config.BOT_COMMAND_COOLDOWN
        self.commands_prefix = config.BOT_PREFIX

        # Initialize commands.Bot with prefix, description and disable case_sensitivity
        super().__init__(command_prefix=self.commands_prefix, description=self.description, case_insensitive=True)

        # Set up aiohttp.ClientSession() for usage in wikipedia, reddit & twitch API calls
        self.session = None
        self.loop.create_task(self.initialize_aiohttp_session())

        # PostgreSQL database connection
        self.db_ready = False
        self.db = self.loop.create_task(self.connect_to_db())

        # Create util objects from ./util/utils.py
        self.embeds = EmbedUtils()
        self.checks = CheckUtils(self)
        self.laws = LawUtils(self)

        # Attributes will be "initialized" in on_ready as they need a connection to Discord
        self.DerJonas_object = None
        self.democraciv_guild_object = None

        # Cache initialized guilds to limit database queries
        self.cached_initialized_guilds = []

        # Load the bot's cogs from ./event and ./module
        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                print(f'[BOT] Successfully loaded {extension}')
            except Exception:
                print(f'[BOT] Failed to load module {extension}.')
                traceback.print_exc()

        # Create twitch live notification task if enabled in config
        if config.TWITCH_ENABLED:
            Twitch(self)

        # Create reddit new post on subreddit notification task if enabled in config
        if config.REDDIT_ENABLED:
            Reddit(self)

    async def initialize_aiohttp_session(self):
        # Initialize a shared aiohttp ClientSession to be used for -wikipedia, -submit and reddit & twitch requests
        # aiohttp needs to have this in an async function, that's why it's separated from __init__()
        self.session = aiohttp.ClientSession()

    async def connect_to_db(self):
        # Attempt to connect to PostgreSQL database with specified credentials from token.py
        # This will also fill an empty database with tables needed by the bot

        try:
            self.db = await asyncpg.create_pool(user=token.POSTGRESQL_USER,
                                                password=token.POSTGRESQL_PASSWORD,
                                                database=token.POSTGRESQL_DATABASE,
                                                host=token.POSTGRESQL_HOST)
        except ConnectionRefusedError:
            print("[DATABASE] Connection to database was denied")
            self.db_ready = False
            return
        except Exception:
            print("[DATABASE] Unexpected error occurred while connecting to PostgreSQL database")
            self.db_ready = False
            return

        with open('db/schema.sql') as sql:
            await self.db.execute(sql.read())
            print("[DATABASE] Successfully initialised database")

        self.db_ready = True

    def initialize_democraciv_guild(self):
        # The bot needs a "main" guild object that will be used for reddit & twitch notifications, political parties and
        # admin commands. The bot will automatically pick a random guild that it can see if 'democracivServerID' from
        # config.py is invalid

        self.democraciv_guild_object = self.get_guild(config.DEMOCRACIV_SERVER_ID)

        if self.democraciv_guild_object is None:

            print("[BOT] Couldn't find guild with ID specified in config.py 'DEMOCRACIV_SERVER_ID'.\n"
                  "      I will use a random guild that I can see to be used for my Democraciv-specific features.")

            self.democraciv_guild_object = self.guilds[0]

            if self.democraciv_guild_object is None:
                raise exceptions.GuildNotFoundError(config.DEMOCRACIV_SERVER_ID)

            config.DEMOCRACIV_SERVER_ID = self.democraciv_guild_object.id

            print(f"[BOT] Using '{self.democraciv_guild_object.name}' as Democraciv guild.")

    def get_uptime(self):
        difference = int(round(time.time() - self.start_time))
        return str(datetime.timedelta(seconds=difference))

    def get_ping(self):
        return math.floor(self.latency * 1000)

    async def on_ready(self):
        if not self.db_ready:
            # If the connection to the database fails, stop the bot
            print("[DATABASE] Fatal error while connecting to database. Closing bot...")
            await self.close()
            await self.logout()
            return

        print(f"[BOT] Logged in as {self.user.name} with discord.py {discord.__version__}")
        print("------------------------------------------------------------")

        await asyncio.sleep(1)

        # The bot needs a "main" guild object that will be used for reddit & twitch notifications, political parties and
        # admin commands. The bot will automatically pick a random guild that it can see if 'democracivServerID' from
        # config.py is invalid
        self.initialize_democraciv_guild()

        # Set status on Discord
        await self.change_presence(activity=discord.Game(name=config.BOT_PREFIX + 'help | Watching over '
                                                                                  'the Democraciv community'))

        self.DerJonas_object = self.get_user(config.BOT_AUTHOR_ID)

    async def on_message(self, message):
        # Don't process message/command from DMs to prevent spamming
        if isinstance(message.channel, discord.DMChannel):
            return

        # Don't process message/command from other bots
        if message.author.bot:
            return

        # If, for whatever reason, the current guild does not have an entry in the bot's database, attempt to initialize
        # the default config
        if message.guild.id not in self.cached_initialized_guilds:
            if not await self.checks.is_guild_initialized(message.guild.id):
                print(f"[DATABASE] Guild {message.guild.name} ({message.guild.id}) was not initialized. "
                      f"Adding default entry to database... ")
                try:
                    await self.db.execute("INSERT INTO guilds (id, welcome, logging, logging_excluded, defaultrole) "
                                          "VALUES ($1, false, false, ARRAY[0], false)",
                                          message.guild.id)
                except Exception:
                    await self.DerJonas_object.send(
                        f":x: Fatal database error occurred while initializing new guild "
                        f"{message.guild.name} ({message.guild.id})")
                    print(
                        f"[DATABASE] Fatal error while initializing new guild {message.guild.name} ({message.guild.id})")
                    return

                print(f"[DATABASE] Successfully initialized guild {message.guild.name} ({message.guild.id})")

            self.cached_initialized_guilds.append(message.guild.id)

        # Relay message to discord.ext.commands cogs
        await self.process_commands(message)


# This will start the bot when you run this file
if __name__ == '__main__':
    DemocracivBot().run(token.TOKEN, reconnect=True, bot=True)
