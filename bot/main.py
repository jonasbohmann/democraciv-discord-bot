import io
import os
import pathlib
import re
import sys
import time
import math
import asyncio
import typing
import pickle

try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

import discord
import aiohttp
import asyncpg
import logging
import datetime
import traceback

from typing import Optional, Union
from discord.ext import commands, tasks
from googleapiclient import errors
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport import requests
from async_lru import alru_cache

sys.path.append(str(pathlib.Path(__file__).parent.parent))

from bot.utils import exceptions, text, context
from bot.config import token, config, mk

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BOT] %(message)s', datefmt='%d.%m.%Y %H:%M:%S')

# List of cogs that will be loaded on startup
initial_extensions = [
    "bot.module.logging",
    "bot.module.meta",
    "bot.module.utility",
    "bot.module.roles",
    "bot.module.guild",
    "bot.module.admin",
    "bot.module.nation",
    "bot.module.tags",
    "bot.module.parties",
    "bot.module.legislature",
    "bot.module.laws",
    "bot.module.ministry",
    "bot.module.supremecourt"
]

# monkey patch dpy's send
_old_send = discord.abc.Messageable.send


async def safe_send(self, content=None, **kwargs) -> discord.Message:
    embed = kwargs.pop("embed", None)
    content = str(content) if content is not None else None

    if content == "":
        content = None

    if isinstance(embed, text.SafeEmbed):
        embed.clean()

    if content and len(content) > 2000:
        split_messages = text.split_string(content, 1800)

        for index in split_messages:
            if index == len(split_messages) - 1:
                return await _old_send(self, index, embed=embed, **kwargs)
            else:
                await _old_send(self, index, **kwargs)

    else:
        return await _old_send(self, content, embed=embed, **kwargs)


discord.abc.Messageable.send = safe_send


def get_prefix(bot, msg):
    for prefix in config.BOT_ADDITIONAL_PREFIXES:
        r = re.compile(f'^({prefix}).*', flags=re.I)
        m = r.match(msg.content)
        if m:
            return commands.when_mentioned_or(m.group(1))(bot, msg)

    return commands.when_mentioned_or(config.BOT_PREFIX)(bot, msg)


class DemocracivBot(commands.Bot):
    BASE_API = config.API_URL

    def __init__(self):
        self.start_time = time.time()

        intents = discord.Intents.default()
        intents.typing = False
        intents.voice_states = False
        intents.members = True

        super().__init__(
            max_messages=100,
            command_prefix=get_prefix,
            case_insensitive=True,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
            activity=discord.Game(
                name=f"{config.BOT_PREFIX}help | {config.BOT_PREFIX}commands | {config.BOT_PREFIX}about"
            ),
        )

        self._BotBase__cogs = commands.core._CaseInsensitiveDict()  # case-insensitive cog names

        self.loop.create_task(self.initialize_aiohttp_session())

        self.db_ready = False
        self.loop.create_task(self.connect_to_db())

        if config.DATABASE_DAILY_BACKUP_ENABLED:
            self.daily_db_backup.start()

        self.loop.create_task(self.initialize_democraciv_guild())
        self.mk = mk.MarkConfig(self)

        self.loop.create_task(self.check_custom_emoji_availability())
        self.loop.create_task(self.fetch_owner())
        self.loop.create_task(self.update_guild_config_cache())

        self.is_api_running = False
        self.loop.create_task(self.check_api_running(first_time=True))

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                logging.info(f"Successfully loaded {extension}")
            except Exception:
                logging.error(f"Failed to load module {extension}.")
                traceback.print_exc()

    async def check_api_running(self, first_time=False):
        if first_time:
            await asyncio.sleep(5)

        try:
            async with self.session.get(self.BASE_API) as response:
                if response.status == 200:
                    self.is_api_running = True
        except aiohttp.ClientConnectionError:
            logging.warning(f"Internal api at {self.BASE_API} is not running, bot is running "
                            f"with limited functionality.")

    async def api_request(self, method: str, route: str, **kwargs):
        if not self.is_api_running:
            self.loop.create_task(self.check_api_running())
            raise exceptions.DemocracivBotAPIError(f"{config.NO} Internal API is not running, try again later.")

        async with self.session.request(method, f"{self.BASE_API}/{route}", **kwargs) as response:
            response.raise_for_status()

            if response.status == 200:
                return await response.json()

            raise exceptions.DemocracivBotAPIError(f"{config.NO} Something went wrong.")

    async def get_context(self, message, *, cls=None):
        return await super().get_context(message, cls=cls or context.CustomContext)

    async def avatar_bytes(self):
        try:
            return self._avatar_bytes
        except AttributeError:
            self._avatar_bytes = avatar = await self.user.avatar_url_as().read()
            return avatar

    def get_democraciv_role(self, role: mk.DemocracivRole) -> typing.Optional[discord.Role]:
        to_return = self.dciv.get_role(role.value)

        if to_return is None:
            raise exceptions.RoleNotFoundError(role.name.replace("_", " ").title())

        return to_return

    async def log_error(
            self,
            ctx,
            error,
            to_log_channel: bool = True,
            to_owner: bool = False,
            to_context: bool = False,
    ):
        if ctx.guild is None:
            return

        embed = text.SafeEmbed(title=f"{config.NO}  Command Error")

        embed.add_field(name="Error", value=f"```{error.__class__.__name__}: {error}```", inline=False)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Context", value=f"[Jump]({ctx.message.jump_url})", inline=True)
        caused_by = ctx.message.clean_content if len(ctx.message.clean_content) < 500 else "*too long*"
        embed.add_field(name="Caused by", value=caused_by, inline=False)

        if to_context:
            local_embed = text.SafeEmbed(
                title=":warning:  Something went wrong",
                description=f"An unexpected error occurred while performing this command. "
                            f"The developer has been notified. Sorry!\n\n"
                            f"```{error.__class__.__name__}: {error}```",
            )
            await ctx.send(embed=local_embed)

        if to_log_channel:
            log_channel = await self.get_logging_channel(ctx.guild)

            if log_channel is not None and await self.get_guild_setting(ctx.guild.id, "logging_enabled"):
                await log_channel.send(embed=embed)

        if to_owner:
            embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=False)
            pretty_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            embed.add_field(name="Traceback", value=f"```py\n{pretty_traceback}```")
            await self.owner.send(embed=embed)

    @staticmethod
    def format_permissions(missing_perms: list) -> str:
        """
        The MIT License (MIT)

        Copyright (c) 2015-2019 Rapptz

        Permission is hereby granted, free of charge, to any person obtaining a
        copy of this software and associated documentation files (the "Software"),
        to deal in the Software without restriction, including without limitation
        the rights to use, copy, modify, merge, publish, distribute, sublicense,
        and/or sell copies of the Software, and to permit persons to whom the
        Software is furnished to do so, subject to the following conditions:

        The above copyright notice and this permission notice shall be included in
        all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
        OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
        FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
        DEALINGS IN THE SOFTWARE.
        """
        missing = [f"`{perm.replace('_', ' ').replace('guild', 'server').title()}`" for perm in missing_perms]

        if len(missing) > 2:
            fmt = "{}, and {}".format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = " and ".join(missing)

        return fmt

    @staticmethod
    def format_roles(ctx, missing_roles: list) -> str:
        """
        The MIT License (MIT)

        Copyright (c) 2015-2019 Rapptz

        Permission is hereby granted, free of charge, to any person obtaining a
        copy of this software and associated documentation files (the "Software"),
        to deal in the Software without restriction, including without limitation
        the rights to use, copy, modify, merge, publish, distribute, sublicense,
        and/or sell copies of the Software, and to permit persons to whom the
        Software is furnished to do so, subject to the following conditions:

        The above copyright notice and this permission notice shall be included in
        all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
        OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
        FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
        DEALINGS IN THE SOFTWARE.
        """

        def safe_get_role(r) -> typing.Optional[discord.Role]:
            if isinstance(r, str):
                found = discord.utils.get(ctx.guild.roles, name=r) or discord.utils.get(ctx.bot.dciv.roles, name=r)
                if found:
                    return found
            elif isinstance(r, int):
                found = ctx.guild.get_role(r) or ctx.bot.dciv.get_role(r)
                if found:
                    return found

        missing = [f"`{safe_get_role(role).name}`" for role in missing_roles]

        if len(missing) > 2:
            fmt = "{}, or {}".format(", ".join(missing[:-1]), missing[-1])
        else:
            fmt = " or ".join(missing)

        return fmt

    async def on_command_error(self, ctx, error):
        error = getattr(error, "original", error)
        ignored = (commands.CommandNotFound,)

        if ctx.command is not None:
            ctx.command.reset_cooldown(ctx)

        # This prevents any commands with local handlers being handled here
        if hasattr(ctx.command, "on_error") and (isinstance(error, (commands.BadArgument, commands.BadUnionArgument))):
            return

        # Anything in ignored will return
        if isinstance(error, ignored):
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{config.NO} You forgot to give me the `{error.param.name}` argument.")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.TooManyArguments):
            await ctx.send(f"{config.NO} You gave me too many arguments.")
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.BadArgument):
            if error.args and not str(error).startswith("Convert"):  # catching default BadArgument message
                return await ctx.send(error)

            await ctx.send(
                f"{config.NO} There was an error with the argument you provided, take a look at the help page:"
            )
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.BadUnionArgument):
            first_error = error.errors[0]

            if first_error.args and not str(first_error).startswith("Convert"):  # catching default BadArgument message
                return await ctx.send(first_error)

            await ctx.send(
                f"{config.NO} There was an error with the `{error.param.name}` argument you provided,"
                f" take a look at the help page:"
            )
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"{config.NO} You are on cooldown! Try again in {error.retry_after:.2f} seconds.")

        elif isinstance(error, commands.MaxConcurrencyReached):
            return await ctx.send(f"{config.NO} This command can only be used by one person at the same time, and it "
                                  f"is already being used right now. Try again later.")

        elif isinstance(error, commands.MissingPermissions):
            return await ctx.send(
                f"{config.NO} You need {self.format_permissions(error.missing_perms)} permission(s) to use this command."
            )

        elif isinstance(error, commands.MissingRole):
            role = ctx.guild.get_role(error.missing_role) or ctx.bot.dciv.get_role(error.missing_role)
            return await ctx.send(f"{config.NO} You need the `{role.name}` role in order to use this command.")

        elif isinstance(error, commands.MissingAnyRole):
            return await ctx.send(
                f"{config.NO} You need at least one of these roles in order to use this command: "
                f"{self.format_roles(ctx, error.missing_roles)}"
            )

        elif isinstance(error, commands.BotMissingPermissions):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(
                f"{config.NO} I don't have {self.format_permissions(error.missing_perms)} permission(s)"
                f" to perform this action for you."
            )

        elif isinstance(error, commands.BotMissingRole):
            role = ctx.guild.get_role(error.missing_role) or ctx.bot.dciv.get_role(error.missing_role)
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(
                f"{config.NO} I need the `{role.name}` role in order to perform this" f" action for you.")

        elif isinstance(error, commands.BotMissingAnyRole):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(
                f"{config.NO} I need at least one of these roles in order to perform this action for you: "
                f"{self.format_roles(ctx, error.missing_roles)}"
            )

        elif isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(f"{config.NO} This command cannot be used in DMs.")

        elif isinstance(error, commands.PrivateMessageOnly):
            return await ctx.send(f"{config.NO} This command can only be used in DMs with me.")

        elif isinstance(error, commands.DisabledCommand):
            return await ctx.send(f"{config.NO} This command has been disabled.")

        # This includes all exceptions declared in utils.exceptions.py
        elif isinstance(error, exceptions.DemocracivBotException):
            return await ctx.send(error.message)

        else:
            await self.log_error(ctx, error, to_log_channel=False, to_owner=True, to_context=True)
            logging.error(f'Ignoring exception in command {ctx.command}:')
            traceback.print_exception(type(error), error, error.__traceback__)

    def get_democraciv_channel(self, channel: mk.DemocracivChannel) -> typing.Optional[discord.TextChannel]:
        to_return = self.dciv.get_channel(channel.value)

        if to_return is None:
            raise exceptions.ChannelNotFoundError(channel.name)

        return to_return

    async def _populate_guild_config_cache(self, record: asyncpg.Record):
        settings = dict(record)
        settings.pop("id")

        private_channels = await self.db.fetch(
            "SELECT channel_id FROM guild_private_channel WHERE guild_id = $1",
            record["id"],
        )

        settings["private_channels"] = [r["channel_id"] for r in private_channels]
        return settings

    async def update_guild_config_cache(self):
        await self.wait_until_ready()

        records = await self.db.fetch("SELECT * FROM guild")
        guild_config = {}

        for record in records:
            guild_config[record["id"]] = await self._populate_guild_config_cache(record)

        for guild in self.guilds:
            if guild.id not in guild_config:
                settings = await self.db.fetchrow("INSERT INTO guild (id) VALUES ($1) RETURNING *", guild.id)
                guild_config[settings["id"]] = await self._populate_guild_config_cache(settings)

        self.guild_config = guild_config
        logging.info("Guild config cache was updated.")
        return guild_config

    @alru_cache(cache_exceptions=False)
    async def make_file_from_image_link(self, url: str):
        async with self.session.get(url) as response:
            image = await response.read()
            return io.BytesIO(image)

    async def get_guild_setting(self, guild_id: int, setting: str) -> typing.Union[typing.Any, typing.List]:
        if not self.is_ready():
            await self.wait_until_ready()

        try:
            return self.guild_config[guild_id][setting]
        except (TypeError, KeyError, AttributeError):
            if setting == "private_channels":
                private_channels = await self.db.fetch(
                    "SELECT channel_id FROM guild_private_channel WHERE guild_id = $1",
                    guild_id,
                )
                return [record["channel_id"] for record in private_channels]
            else:
                return await self.db.fetchval(f"SELECT {setting} FROM guild WHERE id = $1", guild_id)

    async def fetch_owner(self):
        await self.wait_until_ready()
        self.owner: discord.User = (await self.application_info()).owner
        self.owner_id: int = self.owner.id

    async def initialize_aiohttp_session(self):
        self.session: aiohttp.ClientSession = aiohttp.ClientSession()

    async def check_custom_emoji_availability(self):
        # If these custom emoji are not set in config.py, -help and -leg submit will break.
        # Convert to Unicode emoji if that's the case.

        await self.wait_until_ready()

        def check_custom_emoji(em):
            emoji_id = [int(s) for s in re.findall(r"\b\d+\b", em)]

            if emoji_id:
                emoji_id = emoji_id.pop()
                emoj = self.get_emoji(emoji_id)

                if emoj is not None:
                    return True

            return False

        # alternative has to be unicode endpoint

        emojis = {
            "HELP_FIRST": "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}",
            "HELP_PREVIOUS": "\N{BLACK LEFT-POINTING TRIANGLE}",
            "HELP_NEXT": "\N{BLACK RIGHT-POINTING TRIANGLE}",
            "HELP_LAST": "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}",
            "HELP_BOT_HELP": "\N{WHITE QUESTION MARK ORNAMENT}",
            "LEG_SUBMIT_BILL": "\U0001f1e7",
            "LEG_SUBMIT_MOTION": "\U0001f1f2",
            "GUILD_SETTINGS_GEAR": "\U00002699",
            "NO": "\U0000274c",
            "YES": "\U00002705",
            "USER_INTERACTION_REQUIRED": "\U0001f4ac",
            "HINT": "\U00002139"
        }

        for attr, default in emojis.items():
            emoji = getattr(config, attr)
            emoji_availability = check_custom_emoji(emoji)
            if not emoji_availability:
                setattr(config, attr, default)
                logging.warning(f"Reverting to standard Unicode emoji for {emoji}. "
                                f"Menus, paginator and ctx.confirm & ctx.choose might not work correctly unless "
                                f"you replace the emojis in /bot/config/config.py/ to emojis that exist!")

    async def connect_to_db(self):
        """Attempt to connect to PostgreSQL database with specified credentials from token.py.
        This will also fill an empty database with tables needed by the bot"""

        try:
            self.db: asyncpg.pool.Pool = await asyncpg.create_pool(
                user=token.POSTGRESQL_USER,
                password=token.POSTGRESQL_PASSWORD,
                database=token.POSTGRESQL_DATABASE,
                host=token.POSTGRESQL_HOST,
            )
        except Exception:
            logging.error("Unexpected error occurred while connecting to PostgreSQL database.")
            self.db_ready = False
            raise

        with open("bot/db/schema.sql") as sql:
            try:
                await self.db.execute(sql.read())
            except asyncpg.InsufficientPrivilegeError:
                logging.error("Could not create extension 'pg_trgm' as this user. Login as the"
                              " postgres user and manually create extension on database."
                              )
                self.db_ready = False
                raise
            except Exception:
                logging.error("Unexpected error occurred while executing default schema on PostgreSQL database")
                self.db_ready = False
                raise

        logging.info("Successfully initialised database")
        self.db_ready = True

    async def initialize_democraciv_guild(self):
        """Saves the Democraciv guild object (main guild) as a class attribute. If config.DEMOCRACIV_GUILD_ID is
        not a guild, the first guild in self.guilds will be used instead."""

        await self.wait_until_ready()

        dciv_guild = self.get_guild(config.DEMOCRACIV_GUILD_ID)

        if dciv_guild is None:

            logging.warning(
                "Couldn't find guild with ID specified in config.py 'DEMOCRACIV_GUILD_ID'.\n"
                "      I will use the first guild that I can see to be used for my Democraciv-specific features."
            )

            try:
                dciv_guild = self.guilds[0]
            except IndexError:
                raise RuntimeError("no guild to use as Democraciv Guild")

        config.DEMOCRACIV_GUILD_ID = dciv_guild.id
        self.democraciv_guild_id = dciv_guild.id
        logging.info(f"Using '{dciv_guild.name}' ({dciv_guild.id}) as Democraciv guild.")

    @property
    def uptime(self):
        difference = int(round(time.time() - self.start_time))
        return str(datetime.timedelta(seconds=difference))

    @property
    def ping(self):
        return math.floor(self.latency * 1000)

    @property
    def dciv(self) -> Optional[discord.Guild]:
        return self.get_guild(self.democraciv_guild_id)

    async def run_apps_script(self, script_id, function, parameters):
        try:
            result = await self.loop.run_in_executor(None, self._execute_apps_script, script_id, function,
                                                     parameters)

            if "error" in result:
                raise exceptions.GoogleAPIError()

            return result

        except errors.HttpError as e:
            logging.error(f"Error while executing Apps Script {script_id}: {e.content}")
            raise exceptions.GoogleAPIError() from e

    def _execute_apps_script(self, script_id, function, parameters):
        google_credentials = None

        if os.path.exists('bot/config/google_oauth_token.pickle'):
            with open('bot/config/google_oauth_token.pickle', 'rb') as google_token:
                google_credentials = pickle.load(google_token)

        if not google_credentials or not google_credentials.valid:
            if google_credentials and google_credentials.expired and google_credentials.refresh_token:
                google_credentials.refresh(requests.Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    config.GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE,
                    config.GOOGLE_CLOUD_PLATFORM_OAUTH_SCOPES)
                google_credentials = flow.run_local_server(port=0)

            with open('bot/config/google_oauth_token.pickle', 'wb') as google_token:
                pickle.dump(google_credentials, google_token)

        service = build("script", "v1", credentials=google_credentials, cache_discovery=False)
        request = {"function": function, "parameters": parameters, "devMode": True}
        return service.scripts().run(body=request, scriptId=script_id).execute()

    async def safe_send_dm(
            self,
            target: Union[discord.User, discord.Member],
            reason: str = None,
            message: str = None,
            embed: discord.Embed = None,
    ):
        dm_settings = await self.db.fetchrow("SELECT * FROM dm_setting WHERE user_id = $1", target.id)
        p = config.BOT_PREFIX
        if not dm_settings:
            dm_settings = await self.db.fetchrow("INSERT INTO dm_setting (user_id) VALUES ($1) RETURNING *", target.id)

        try:
            is_enabled = dm_settings[reason]
        except (KeyError, TypeError):
            is_enabled = True

        if not is_enabled:
            return

        base_msg = f"{config.HINT} *You can enable and disable these DM notifications based on their subject. " \
                   f"Check `{p}dms` for more information.*"

        if message:
            message = f"{message}\n\n{base_msg}"
        else:
            message = base_msg

        try:
            await target.send(content=message, embed=embed)
        except discord.Forbidden:
            pass

    async def close(self):
        """Closes the aiohttp ClientSession, the connection pool to the PostgreSQL database and the bot itself."""
        logging.info("Closing bot...")
        channel = self.get_channel(config.BOT_TECHNICAL_NOTIFICATIONS_CHANNEL)

        if channel:
            embed = text.SafeEmbed(title=f"{config.YES}  Bot is shutting down...")
            await channel.send(embed=embed)

        await super().close()
        await self.session.close()
        await self.db.close()

    async def on_ready(self):
        if not self.db_ready:
            logging.error("Fatal error while connecting to database. Closing bot...")
            # return await self.close()

        logging.info(f"Logged in as {self.user.name} with discord.py {discord.__version__}")

        channel = self.get_channel(config.BOT_TECHNICAL_NOTIFICATIONS_CHANNEL)

        if channel:
            embed = text.SafeEmbed(title=f"{config.YES}  Bot is ready")
            await channel.send(embed=embed)

    async def on_resumed(self):
        logging.info("Resumed connection to Discord")
        channel = self.get_channel(config.BOT_TECHNICAL_NOTIFICATIONS_CHANNEL)

        if channel:
            embed = text.SafeEmbed(title=f"{config.YES}  Resumed connection to Discord")
            await channel.send(embed=embed)

    async def on_message(self, message: discord.Message):
        # Don't process message/command from other bots
        if message.author.bot:
            return

        if self.user.id in message.raw_mentions and len(message.content) in (
                20,
                21,
                22,
        ):
            await message.channel.send(
                f"Hey! :wave:\nMy prefix is: `{config.BOT_PREFIX}`\n"
                f"Try `{config.BOT_PREFIX}help`, `{config.BOT_PREFIX}commands`"
                f" or `{config.BOT_PREFIX}about` to learn more about me!"
            )

        await self.process_commands(message)

    async def on_message_edit(self, before, after):
        if before.author.bot:
            return

        if before.content and after.content and before.content != after.content:
            await self.process_commands(after)

    async def on_guild_join(self, guild: discord.Guild):
        if len(self.guilds) >= 70:
            if guild.system_channel:
                embed = text.SafeEmbed(title=":pensive:  Sorry!",
                                       description="Discord requires bot developers to hand over their passport "
                                                   "once their bot reaches about ~75 servers. If they refuse to, "
                                                   f"the bot cannot be invited anymore and Discord takes away some "
                                                   f"critical features that the Democraciv Bot needs in order "
                                                   f"to work properly. I **do not want to give Discord my "
                                                   f"passport.**\n\nThis is the 70th server the bot is in, "
                                                   f"and as a precaution **the bot is leaving this server** again.")

                await guild.system_channel.send(embed=embed)

            await guild.leave()
            return

        introduction_channel = guild.system_channel or guild.text_channels[0]

        # Alert owner of this bot that the bot was invited to some place
        await self.owner.send(f"{config.HINT} I was added to {guild.name} ({guild.id}).")
        p = config.BOT_PREFIX

        introduction_message = (
            f"You can check `{p}help` or `{p}commands` to get more "
            f"information about me.\nUse the `{p}server` command to configure me for this server."
            f"\n\n__**Icon Guide**__\n"
            f"{config.YES} - Confirm, Accept or \"Success\"\n"
            f"{config.NO} - Cancel, Decline or \"Error\"\n"
            f"{config.HINT} - Hint, Tip or additional information to explain something\n"
            f"{config.USER_INTERACTION_REQUIRED} - User reply is needed. You should reply with something, or confirm something"
            f"\n\nIf you have any questions or suggestions, send a DM to {self.owner.mention} ({self.owner})."
        )

        # Send introduction message to random guild channel
        embed = text.SafeEmbed(title="Thanks for inviting me!", description=introduction_message)

        # Add new guild to database
        await self.db.execute("INSERT INTO guild (id) VALUES ($1) ON CONFLICT DO NOTHING ", guild.id)
        await self.update_guild_config_cache()

        try:
            await introduction_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    async def do_db_backup(self, database_name: str):
        now = time.time()
        pretty_time = datetime.datetime.utcfromtimestamp(now).strftime("%A, %B %d %Y %H:%M:%S")
        file_name = f"{database_name}-backup-{now}"

        command = (
            f'PGPASSWORD="{token.POSTGRESQL_PASSWORD}" pg_dump -Fc {database_name} > '
            f"bot/db/backup/{database_name}/{file_name} -U {token.POSTGRESQL_USER} "
            f"-h {token.POSTGRESQL_HOST} -w"
        )

        if not os.path.isdir(f"bot/db/backup"):
            os.mkdir(f"bot/db/backup")

        if not os.path.isdir(f"bot/db/backup/{database_name}"):
            os.mkdir(f"bot/db/backup/{database_name}")

        await asyncio.create_subprocess_shell(command)
        await asyncio.sleep(20)

        file = discord.File(f"bot/db/backup/{database_name}/{file_name}")

        backup_channel = self.get_channel(config.DATABASE_DAILY_BACKUP_DISCORD_CHANNEL)

        if backup_channel is None:
            logging.warning(
                f"Couldn't find Backup Discord channel for database backup 'bot/db/backup/{database_name}/{file_name}'")
            return

        await backup_channel.send(f"---- Database Backup from {pretty_time} (UTC) ----", file=file)

    @tasks.loop(hours=config.DATABASE_DAILY_BACKUP_INTERVAL)
    async def daily_db_backup(self):
        """This task makes a backup of the bot's PostgreSQL database every 24hours and uploads
        that backup to the #backup channel to the Democraciv Discord guild."""
        await self.do_db_backup(token.POSTGRESQL_DATABASE)

    async def get_logging_channel(self, guild: discord.Guild) -> typing.Optional[discord.TextChannel]:
        channel = await self.get_guild_setting(guild.id, "logging_channel")

        if channel:
            return guild.get_channel(channel)

    async def get_welcome_channel(self, guild: discord.Guild) -> typing.Optional[discord.TextChannel]:
        channel = await self.get_guild_setting(guild.id, "welcome_channel")

        if channel:
            return guild.get_channel(channel)

    async def is_channel_excluded(self, guild_id: int, channel_id: int) -> bool:
        """Returns true if the channel is excluded from logging. This is used for the Starboard too."""
        excluded_channels = await self.get_guild_setting(guild_id, "private_channels")

        if excluded_channels is None:
            return False

        channel: discord.TextChannel = self.get_guild(guild_id).get_channel(channel_id)
        return channel_id in excluded_channels or channel.category_id in excluded_channels

    async def make_paste(self, txt: str) -> typing.Optional[str]:
        """Post text to mystb.in"""

        async with self.session.post("https://mystb.in/documents", data=txt) as response:
            if response.status == 200:
                data = await response.json()

                try:
                    key = data["key"]
                except KeyError:
                    return None

                return f"https://mystb.in/{key}"

    @alru_cache(cache_exceptions=False)
    async def tinyurl(self, url: str) -> typing.Optional[str]:
        async with self.session.get(f"https://tinyurl.com/api-create.php?url={url}") as response:
            if response.status == 200:
                tiny_url = await response.text()

                if tiny_url == "Error":
                    raise exceptions.DemocracivBotException(
                        f"{config.NO} tinyurl.com returned an error, try again later.")

                return tiny_url


if __name__ == "__main__":
    dciv = DemocracivBot()
    dciv.run(token.TOKEN)
