import io
import os
import re
import time
import math
import asyncio
import typing

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

from bot.utils import exceptions, text, context
from bot.config import token, config, mk


from bot.utils.api_wrapper import RedditAPIWrapper, GoogleAPIWrapper

logging.basicConfig(level=logging.INFO)

# List of cogs that will be loaded on startup
initial_extensions = [
    "bot.module.logging",
    "bot.module.meta",
    "bot.module.misc",
    "bot.module.roles",
    "bot.module.guild",
    "bot.module.admin",
    "bot.module.profile",
    "bot.module.tags",
    "bot.module.starboard",
    "bot.module.moderation",
    "bot.module.parties",
    "bot.module.legislature",
    "bot.module.laws",
    "bot.module.ministry",
    "bot.module.supremecourt",
    "bot.ext.democracivbank.bank",
]

# monkey patch dpy's send
_old_send = discord.abc.Messageable.send


# todo on_resume


async def safe_send(self, content=None, **kwargs) -> discord.Message:
    embed = kwargs.pop("embed", None)
    content = str(content) if content is not None else None

    if content == "":
        content = None

    if isinstance(embed, text.SafeEmbed):
        embed.clean()

    if content and len(content) > 2000:
        split_messages = text.split_string_by_paragraphs(content, 1800)

        for index in split_messages:
            if index == len(split_messages) - 1:
                return await _old_send(self, split_messages[index], embed=embed, **kwargs)
            else:
                await _old_send(self, split_messages[index], **kwargs)

    else:
        return await _old_send(self, content, embed=embed, **kwargs)


discord.abc.Messageable.send = safe_send


class DemocracivBot(commands.Bot):
    BASE_API = "http://127.0.0.1:8000"

    def __init__(self):
        self.start_time = time.time()

        intents = discord.Intents.default()
        intents.typing = False
        intents.voice_states = False
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(config.BOT_PREFIX),
            description=config.BOT_DESCRIPTION,
            case_insensitive=True,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
            activity=discord.Game(
                name=f"{config.BOT_PREFIX}help | {config.BOT_PREFIX}commands |" f" {config.BOT_PREFIX}about"
            ),
        )

        self._BotBase__cogs = commands.core._CaseInsensitiveDict()  # case-insensitive cog names

        self.loop.create_task(self.initialize_aiohttp_session())

        self.db_ready = False
        self.loop.create_task(self.connect_to_db())

        # if config.DATABASE_DAILY_BACKUP_ENABLED:
        #    self.daily_db_backup.start()

        self.loop.create_task(self.initialize_democraciv_guild())
        self.mk = mk.MarkConfig(self)

        self.loop.create_task(self.check_custom_emoji_availability())
        self.loop.create_task(self.fetch_owner())

        self.reddit_api = RedditAPIWrapper(self)
        self.google_api = GoogleAPIWrapper(self)

        self.loop.create_task(self.update_guild_config_cache())

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
                print(f"[BOT] Successfully loaded {extension}")
            except Exception:
                print(f"[BOT] Failed to load module {extension}.")
                traceback.print_exc()

    async def api_request(self, method: str, route: str, **kwargs):
        async with self.session.request(method, f"{self.BASE_API}/{route}", **kwargs) as response:
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

        embed = text.SafeEmbed(title="{config.NO}  Command Error")

        embed.add_field(name="Error", value=f"{error.__class__.__name__}: {error}", inline=False)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Context", value=f"[Jump]({ctx.message.jump_url})", inline=True)
        embed.add_field(name="Caused by", value=ctx.message.clean_content, inline=False)

        if to_context:
            local_embed = text.SafeEmbed(
                title=":warning:  Something went wrong",
                description=f"An unexpected error occurred while"
                f" performing this command. The developer"
                f" has been notified."
                f"\n\n```{error.__class__.__name__}:"
                f" {error}```",
            )
            await ctx.send(embed=local_embed)

        if to_log_channel:
            log_channel = await self.get_logging_channel(ctx.guild)

            if log_channel is not None and await self.get_guild_setting(ctx.guild.id, "logging_enabled"):
                await log_channel.send(embed=embed)

        if to_owner:
            embed.add_field(name="Guild", value=ctx.guild.name, inline=False)
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
            await ctx.send(
                f"{config.NO} There was an error with one of the arguments you provided," f" take a look at the help page:"
            )
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.BadUnionArgument):
            await ctx.send(
                f"{config.NO} There was an error with the `{error.param.name}` argument you provided,"
                f" take a look at the help page:"
            )
            return await ctx.send_help(ctx.command)

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"{config.NO} You are on cooldown! Try again in {error.retry_after:.2f} seconds.")

        elif isinstance(error, commands.MaxConcurrencyReached):
            return await ctx.send(f"{config.NO} This command is already being used right now, try again later.")

        elif isinstance(error, commands.MissingPermissions):
            return await ctx.send(
                f"{config.NO} You need {self.format_permissions(error.missing_perms)} permission(s) to use" f" this command."
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
            return await ctx.send(f"{config.NO} I need the `{role.name}` role in order to perform this" f" action for you.")

        elif isinstance(error, commands.BotMissingAnyRole):
            await self.log_error(ctx, error, to_log_channel=True, to_owner=False)
            return await ctx.send(
                f"{config.NO} I need at least one of these roles in order to perform this action for you: "
                f"{self.format_roles(ctx, error.missing_roles)}"
            )

        elif isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("{config.NO} This command cannot be used in DMs.")

        elif isinstance(error, commands.PrivateMessageOnly):
            return await ctx.send("{config.NO} This command can only be used in DMs.")

        elif isinstance(error, commands.DisabledCommand):
            return await ctx.send("{config.NO} This command has been disabled.")

        elif isinstance(error, exceptions.PartyNotFoundError):
            await ctx.send(f"{config.NO} There is no political party named `{error.party}`.")

            parties = await self.db.fetch("SELECT id FROM party")
            parties = [record["id"] for record in parties]

            msg = ["**Try one of these:**"]
            for party in parties:
                role = self.dciv.get_role(party)
                if role is not None:
                    msg.append(role.name)

            if len(msg) > 1:
                await ctx.send("\n".join(msg))
            return

        # This includes all exceptions declared in utils.exceptions.py
        elif isinstance(error, exceptions.DemocracivBotException):
            return await ctx.send(error.message)

        else:
            await self.log_error(ctx, error, to_log_channel=False, to_owner=True, to_context=True)
            raise error

    def get_democraciv_channel(self, channel: mk.DemocracivChannel) -> typing.Optional[discord.TextChannel]:
        to_return = self.dciv.get_channel(channel.value)

        if to_return is None:
            raise exceptions.ChannelNotFoundError(channel.name)

        return to_return

    async def _populate_guild_config_cache(self, record: asyncpg.Record):
        settings = {k: v for k, v in record.items() if k != "id"}
        private_channels = await self.db.fetch(
            "SELECT channel_id FROM guild_private_channels WHERE guild_id = $1",
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
        logging.info("[CACHE] Guild config cache was updated.")
        return guild_config

    async def make_file_from_image_link(self, url: str):
        async with self.session.get(url) as response:
            image = await response.read()
            return discord.File(io.BytesIO(image), filename="image.png")

    async def get_guild_setting(self, guild_id: int, setting: str) -> typing.Union[typing.Any, typing.List]:
        if not self.is_ready():
            await self.wait_until_ready()

        try:
            return self.guild_config[guild_id][setting]
        except (TypeError, KeyError, AttributeError):
            if setting == "private_channels":
                private_channels = await self.db.fetch(
                    "SELECT channel_id FROM guild_private_channels WHERE guild_id = $1",
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
        """Initialize a shared aiohttp ClientSession to be used for -wikipedia, -leg submit and reddit & twitch requests
        aiohttp needs to have this in an async function, that's why it's separated from __init__()"""

        self.session: aiohttp.ClientSession = aiohttp.ClientSession()

    async def check_custom_emoji_availability(self):
        # If these custom emoji are not set in config.py, -help and -leg submit will break.
        # Convert to Unicode emoji if that's the case.

        await self.wait_until_ready()

        def check_custom_emoji(emoji):
            emoji_id = [int(s) for s in re.findall(r"\b\d+\b", emoji)]

            if emoji_id:
                emoji_id = emoji_id.pop()
                emoji = self.get_emoji(emoji_id)

                if emoji is not None:
                    return True

            return False

        emojis = [
            config.HELP_FIRST,
            config.HELP_PREVIOUS,
            config.HELP_NEXT,
            config.HELP_LAST,
            config.HELP_BOT_HELP,
            config.LEG_SUBMIT_BILL,
            config.LEG_SUBMIT_MOTION,
            config.GUILD_SETTINGS_GEAR,
        ]

        emoji_availability = [check_custom_emoji(emoji) for emoji in emojis]

        if False in emoji_availability:
            print(
                "[BOT] Reverting to standard Unicode emojis for Paginator and -leg submit"
                " as at least one emoji from config.py cannot be seen/used by me or does not exist."
            )
            config.HELP_FIRST = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            config.HELP_PREVIOUS = "\N{BLACK LEFT-POINTING TRIANGLE}"
            config.HELP_NEXT = "\N{BLACK RIGHT-POINTING TRIANGLE}"
            config.HELP_LAST = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
            config.HELP_BOT_HELP = "\N{WHITE QUESTION MARK ORNAMENT}"
            config.LEG_SUBMIT_BILL = "\U0001f1e7"
            config.LEG_SUBMIT_MOTION = "\U0001f1f2"
            config.GUILD_SETTINGS_GEAR = "\U00002699"
            config.NO = ":x:"
            config.YES = ":white_check_mark:"
            config.USER_INTERACTION_REQUIRED = ":information_source:"

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
        except Exception as e:
            print("[DATABASE] Unexpected error occurred while connecting to PostgreSQL database.")
            self.db_ready = False
            raise e

        with open("db/schema.sql") as sql:
            try:
                await self.db.execute(sql.read())
            except asyncpg.InsufficientPrivilegeError as e:
                print(
                    "[DATABASE] Could not create extension 'pg_trgm' as this user. Login as the"
                    " postgres user and manually create extension on database."
                )
                self.db_ready = False
                await asyncio.sleep(5)
                raise e

            except Exception as e:
                print("[DATABASE] Unexpected error occurred while executing default schema on PostgreSQL database")
                self.db_ready = False
                raise e

        print("[DATABASE] Successfully initialised database")
        self.db_ready = True

    async def initialize_democraciv_guild(self):
        """Saves the Democraciv guild object (main guild) as a class attribute. If config.DEMOCRACIV_GUILD_ID is
        not a guild, the first guild in self.guilds will be used instead."""

        await self.wait_until_ready()

        dciv_guild = self.get_guild(config.DEMOCRACIV_GUILD_ID)

        if dciv_guild is None:

            print(
                "[BOT] Couldn't find guild with ID specified in config.py 'DEMOCRACIV_GUILD_ID'.\n"
                "      I will use the first guild that I can see to be used for my Democraciv-specific features."
            )

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
    def dciv(self) -> Optional[discord.Guild]:
        return self.get_guild(self.democraciv_guild_id)

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

        if message:
            message = f"{message}\n\n*If you want to enable or disable specific DMs from me, check `{p}help dms`.*"
        else:
            message = f"*If you want to enable or disable specific DMs from me, check `{p}help dms`.*"

        try:
            await target.send(content=message, embed=embed)
        except discord.Forbidden:
            pass

    async def close(self):
        """Closes the aiohttp ClientSession, the connection pool to the PostgreSQL database and the bot itself."""
        await super().close()
        await self.session.close()
        await self.db.close()

    async def on_ready(self):
        if not self.db_ready:
            print("[DATABASE] Fatal error while connecting to database. Closing bot...")
            return await self.close()

        print(f"[BOT] Logged in as {self.user.name} with discord.py {discord.__version__}")
        print("------------------------------------------------------------")

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

    @tasks.loop(hours=config.DATABASE_DAILY_BACKUP_INTERVAL)
    async def daily_db_backup(self):
        """This task makes a backup of the bot's PostgreSQL database every 24hours and uploads
        that backup to the #backup channel to the Democraciv Discord guild."""

        # Unique filenames with current UNIX timestamp
        now = time.time()
        pretty_time = datetime.datetime.utcfromtimestamp(now).strftime("%A, %B %d %Y %H:%M:%S")
        file_name = f"democraciv-bot-database-backup-{now}"
        bank_backup_too = False

        # Use pg_dump to dumb the database as raw SQL
        # Login with credentials provided in token.py
        command = (
            f'PGPASSWORD="{token.POSTGRESQL_PASSWORD}" pg_dump -Fc {token.POSTGRESQL_DATABASE} > '
            f"bot/database/backup/{file_name} -U {token.POSTGRESQL_USER} "
            f"-h {token.POSTGRESQL_HOST} -w"
        )

        # Check if backup dir exists
        if not os.path.isdir("bot/database/backup"):
            os.mkdir("db/backup")

        # Run the command and save the backup files in database/backup/
        await asyncio.create_subprocess_shell(command)

        backup_channel = self.get_channel(config.DATABASE_DAILY_BACKUP_DISCORD_CHANNEL)

        if config.DATABASE_DAILY_BACKUP_BANK_OF_DEMOCRACIV_BACKUP:
            if not os.path.isdir("bot/database/backup/democracivbank"):
                os.mkdir("db/backup/democracivbank")

            fn = f"democracivbank-of-democraciv-backup-{now}"
            bn = config.DATABASE_DAILY_BACKUP_BANK_OF_DEMOCRACIV_DATABASE

            command = (
                f'PGPASSWORD="{token.POSTGRESQL_PASSWORD}" pg_dump -Fc {bn} > bot/database/backup/democracivbank/{fn} '
                f"-U {token.POSTGRESQL_USER} -h {token.POSTGRESQL_HOST} -w"
            )

            await asyncio.create_subprocess_shell(command)
            bank_backup_too = True

        await asyncio.sleep(20)

        file = discord.File(f"bot/database/backup/{file_name}")

        if backup_channel is None:
            print(f"[DATABASE] Couldn't find Backup Discord channel for database backup 'database/backup/{file_name}'.")
            return

        await backup_channel.send(f"---- Database Backup from {pretty_time} (UTC) ----", file=file)

        if bank_backup_too:
            file = discord.File(f"bot/database/backup/democracivbank/{fn}")
            await backup_channel.send(
                f"---- democracivbank.com Database Backup from {pretty_time} (UTC) ----",
                file=file,
            )

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

    async def tinyurl(self, url: str) -> typing.Optional[str]:
        async with self.session.get(f"https://tinyurl.com/api-create.php?url={url}") as response:
            if response.status == 200:
                tiny_url = await response.text()

                if tiny_url == "Error":
                    raise exceptions.DemocracivBotException("{config.NO} tinyurl.com returned an error, try again later.")

                return tiny_url


if __name__ == "__main__":
    dciv = DemocracivBot()
    dciv.run(token.TOKEN)
