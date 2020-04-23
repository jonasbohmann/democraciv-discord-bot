import os
import re
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

from typing import Optional
from util.cache import Cache
from config import config, token
from util.law_helper import LawUtils
from discord.ext import commands, tasks
from util.reddit_api import RedditAPIWrapper
from util.utils import CheckUtils, EmbedUtils

logging.basicConfig(level=logging.INFO)

# List of cogs that will be loaded on startup
initial_extensions = ['event.logging',
                      'event.error_handler',
                      'event.reddit',
                      'event.youtube',
                      'event.twitch',
                      'module.meta',
                      'module.time',
                      'module.misc',
                      'module.roles',
                      'module.guild',
                      'module.admin',
                      'module.wiki',
                      'module.tags',
                      'module.starboard',
                      'module.democraciv.moderation',
                      'module.democraciv.parties',
                      'module.democraciv.elections',
                      'module.democraciv.legislature',
                      'module.democraciv.laws',
                      'module.democraciv.ministry',
                      'module.democraciv.supremecourt']


class DemocracivBot(commands.Bot):

    def __init__(self):
        self.description = config.BOT_DESCRIPTION
        self.commands_prefix = config.BOT_PREFIX

        # Save the bot's start time for self.uptime
        self.start_time = time.time()

        # Initialize commands.Bot with prefix, description and disable case_sensitivity
        super().__init__(command_prefix=commands.when_mentioned_or(config.BOT_PREFIX),
                         description=self.description, case_insensitive=True,
                         activity=discord.Game(name=f"{config.BOT_PREFIX}help | {config.BOT_PREFIX}commands |"
                                                    f" {config.BOT_PREFIX}about"))

        # Set up aiohttp.ClientSession() for usage in wikipedia, reddit & twitch API calls
        self.session = None
        self.loop.create_task(self.initialize_aiohttp_session())

        # PostgreSQL database connection
        self.db_ready = False
        self.db = None
        self.loop.create_task(self.connect_to_db())

        self.embeds = EmbedUtils()
        self.checks = CheckUtils(self)
        self.laws = LawUtils(self)
        self.cache = Cache(self)

        # Attributes will be "initialized" in on_ready as they need a connection to Discord
        self.owner = None
        self.democraciv_guild_id = None

        # Load the bot's cogs from ./event and ./module
        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                print(f'[BOT] Successfully loaded {extension}')
            except Exception:
                print(f'[BOT] Failed to load module {extension}.')
                traceback.print_exc()

        if config.DATABASE_DAILY_BACKUP_ENABLED:
            self.daily_db_backup.start()

        # The bot needs a "main" guild that will be used for Reddit, Twitch & Youtube notifications, political
        # parties, legislature & ministry organization, the starboard and other admin commands.
        # The bot will automatically pick the first guild that it can see if 'DEMOCRACIV_GUILD_ID' from
        # config.py is invalid
        self.loop.create_task(self.initialize_democraciv_guild())

        self.loop.create_task(self.check_custom_emoji_availability())

        self.reddit_api = RedditAPIWrapper(self)

    async def initialize_aiohttp_session(self):
        """Initialize a shared aiohttp ClientSession to be used for -wikipedia, -leg submit and reddit & twitch requests
        aiohttp needs to have this in an async function, that's why it's separated from __init__()"""

        self.session = aiohttp.ClientSession()

    async def check_custom_emoji_availability(self):
        # If these custom emoji are not set in config.py, -help and -leg submit will break.
        # Convert to Unicode emoji if that's the case.

        await self.wait_until_ready()

        def check_custom_emoji(emoji):
            emoji_id = [int(s) for s in re.findall(r'\b\d+\b', emoji)]

            if emoji_id:
                emoji_id = emoji_id.pop()
                emoji = self.get_emoji(emoji_id)

                if emoji is not None:
                    return True

            return False

        emojis = [config.HELP_FIRST,
                  config.HELP_PREVIOUS,
                  config.HELP_NEXT,
                  config.HELP_LAST,
                  config.HELP_BOT_HELP,
                  config.LEG_SUBMIT_BILL,
                  config.LEG_SUBMIT_MOTION,
                  config.GUILD_SETTINGS_GEAR]

        emoji_availability = [check_custom_emoji(emoji) for emoji in emojis]

        if False in emoji_availability:
            print("[BOT] Reverting to standard Unicode emojis for Paginator and -leg submit"
                  " as at least one emoji from config.py cannot be seen/used by me or does not exist.")
            config.HELP_FIRST = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            config.HELP_PREVIOUS = "\N{BLACK LEFT-POINTING TRIANGLE}"
            config.HELP_NEXT = "\N{BLACK RIGHT-POINTING TRIANGLE}"
            config.HELP_LAST = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            config.HELP_BOT_HELP = "\N{WHITE QUESTION MARK ORNAMENT}"
            config.LEG_SUBMIT_BILL = "\U0001f1e7"
            config.LEG_SUBMIT_MOTION = "\U0001f1f2"
            config.GUILD_SETTINGS_GEAR = "\U00002699"

    async def connect_to_db(self):
        """Attempt to connect to PostgreSQL database with specified credentials from token.py.
        This will also fill an empty database with tables needed by the bot"""

        try:
            self.db = await asyncpg.create_pool(user=token.POSTGRESQL_USER,
                                                password=token.POSTGRESQL_PASSWORD,
                                                database=token.POSTGRESQL_DATABASE,
                                                host=token.POSTGRESQL_HOST)
        except Exception as e:
            print("[DATABASE] Unexpected error occurred while connecting to PostgreSQL database.")
            print(f"[DATABASE] {e}")
            self.db_ready = False
            return

        with open('db/schema.sql') as sql:
            try:
                await self.db.execute(sql.read())
            except asyncpg.InsufficientPrivilegeError:
                print("[DATABASE] Could not create extension 'pg_trgm' as this user. Login as the"
                      " postgres user and manually create extension on database.")
                self.db_ready = False
                await asyncio.sleep(5)
                return
            except Exception as e:
                print("[DATABASE] Unexpected error occurred while executing default schema on PostgreSQL database")
                print(f"[DATABASE] {e}")
                self.db_ready = False
                return

        print("[DATABASE] Successfully initialised database")
        self.db_ready = True

    async def initialize_democraciv_guild(self):
        """Saves the Democraciv guild object (main guild) as a class attribute. If config.DEMOCRACIV_GUILD_ID is
        not a guild, the first guild in self.guilds will be used instead."""

        await self.wait_until_ready()

        dciv_guild = self.get_guild(config.DEMOCRACIV_GUILD_ID)

        if dciv_guild is None:

            print("[BOT] Couldn't find guild with ID specified in config.py 'DEMOCRACIV_GUILD_ID'.\n"
                  "      I will use the first guild that I can see to be used for my Democraciv-specific features.")

            dciv_guild = self.guilds[0]

            if dciv_guild is None:
                raise exceptions.GuildNotFoundError(config.DEMOCRACIV_GUILD_ID)

        config.DEMOCRACIV_GUILD_ID = dciv_guild.id
        self.democraciv_guild_id = dciv_guild.id

        print(f"[BOT] Using '{dciv_guild.name}' as Democraciv guild.")

    @property
    def uptime(self):
        difference = int(round(time.time() - self.start_time))
        return str(datetime.timedelta(seconds=difference))

    @property
    def ping(self):
        return math.floor(self.latency * 1000)

    @property
    def democraciv_guild_object(self) -> Optional[discord.Guild]:
        return self.get_guild(self.democraciv_guild_id)

    async def close(self):
        """Closes the aiohttp ClientSession, the connection pool to the PostgreSQL database and the bot itself."""
        await self.session.close()
        await self.db.close()
        await super().close()

    async def on_ready(self):
        if not self.db_ready:
            print("[DATABASE] Fatal error while connecting to database. Closing bot...")
            return await self.close()

        print(f"[BOT] Logged in as {self.user.name} with discord.py {discord.__version__}")
        print("------------------------------------------------------------")

        self.owner = (await self.application_info()).owner
        self.owner_id = self.owner.id

    async def on_message(self, message):
        # Don't process message/command from other bots
        if message.author.bot:
            return

        for user in message.mentions:
            if user.id == self.user.id and len(message.content) in (20, 21, 22):
                await message.channel.send(f"Hey! :wave:\nMy prefix is: `{config.BOT_PREFIX}`\n"
                                           f"Try `{config.BOT_PREFIX}help`, `{config.BOT_PREFIX}commands`"
                                           f" or `{config.BOT_PREFIX}about` to learn more about me!")
                break

        await self.cache.verify_guild_config_cache(message)
        await self.process_commands(message)

    @tasks.loop(hours=12)
    async def daily_db_backup(self):
        """This task makes a backup of the bot's PostgreSQL database every 24hours and uploads
        that backup to the #backup channel to the Democraciv Discord guild."""

        # Unique filenames with current UNIX timestamp
        now = time.time()
        pretty_time = datetime.datetime.utcfromtimestamp(now).strftime("%A, %B %d %Y %H:%M:%S")
        file_name = f'democraciv-bot-db-backup-{now}'

        # Use pg_dump to dumb the database as raw SQL
        # Login with credentials provided in token.py
        command = f'PGPASSWORD="{token.POSTGRESQL_PASSWORD}" pg_dump {token.POSTGRESQL_DATABASE} > ' \
                  f'db/backup/{file_name} -U {token.POSTGRESQL_USER} ' \
                  f'-h {token.POSTGRESQL_HOST} -w'

        # Check if backup dir exists
        if not os.path.isdir('./db/backup'):
            os.mkdir('./db/backup')

        # Run the command and save the backup files in db/backup/
        await asyncio.create_subprocess_shell(command)

        # Make sure that pg_dump is finished before loading the backup
        await asyncio.sleep(20)

        # Upload the file to the #backup channel in the Moderation category on the Democraciv server
        file = discord.File(f'db/backup/{file_name}')
        backup_channel = self.get_channel(config.DATABASE_DAILY_BACKUP_DISCORD_CHANNEL)

        if backup_channel is None:
            print(f"[DATABASE] Couldn't find Backup Discord channel for database backup 'db/backup/{file_name}'.")
            return

        await backup_channel.send(f"---- Database Backup from {pretty_time} (UTC) ----", file=file)


# This will start the bot when you run this file
if __name__ == '__main__':
    dciv = DemocracivBot()

    try:
        dciv.run(token.TOKEN)
    except KeyboardInterrupt:
        asyncio.create_task(dciv.close())
