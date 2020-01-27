import discord
import datetime
import util.exceptions as exceptions

from config import config
from discord.ext import commands

"""Various utility classes and functions that the bot regular uses."""


class AddTagCheckError(commands.CheckFailure):

    def __init__(self, message):
        self.message = message


def is_democraciv_guild():
    """Wrapper for a discord.ext.commands decorator to check if command is used on the Democraciv guild"""

    def check(ctx):
        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()
        return True

    return commands.check(check)


def add_tag_check():
    """Wrapper for a discord.ext.commands decorator to check if the -addtag command is used on the Democraciv guild"""

    def check(ctx):
        if config.DEMOCRACIV_GUILD_ID != ctx.guild.id:
            if ctx.author.guild_permissions.administrator:
                return True
            else:
                raise AddTagCheckError(message=":x: Only Administrators can add tags on this guild!")
        else:
            return True

    return commands.check(check)


async def get_logging_channel(bot, guild_id):
    logging_channel = await bot.db.fetchval("SELECT logging_channel FROM guilds WHERE id = $1",
                                            guild_id)
    return bot.get_channel(logging_channel)


async def get_welcome_channel(bot, guild_id):
    welcome_channel = await bot.db.fetchval("SELECT welcome_channel FROM guilds WHERE id = $1",
                                            guild_id)
    return bot.get_channel(welcome_channel)


class EmbedUtils:
    """Utils to assist with discord.Embed objects"""

    def __init__(self):
        self.footer_text = config.BOT_NAME
        self.footer_icon = config.BOT_ICON_URL
        self.embed_colour = 0x7f0000

    def embed_builder(self, title: str, description: str, time_stamp: bool = None,
                      has_footer: bool = True, footer: str = None, colour: int = None):
        """Creates discord.Embed object and adds the bot's signature footer to it as well as a UTC timestamp if
         required."""

        embed = discord.Embed(title=title, description=description)

        if has_footer:
            if footer:
                embed.set_footer(text=footer, icon_url=self.footer_icon)
            else:
                embed.set_footer(text=self.footer_text, icon_url=self.footer_icon)

        if time_stamp:
            embed.timestamp = datetime.datetime.utcnow()

        if colour:
            embed.colour = colour
        else:
            embed.colour = self.embed_colour

        return embed


class CheckUtils:
    """Utils to assist with discord.ext.commands checks"""

    def __init__(self, bot):
        self.bot = bot

    def wait_for_message_check(self, ctx):
        """Wrapper function for a client.wait_for('message') check"""

        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        return check

    def wait_for_reaction_check(self, ctx, original_message):
        """Wrapper function for a client.wait_for('reaction_add') check"""

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == original_message.id

        return check

    def wait_for_gear_reaction_check(self, ctx, original_message):
        """Wrapper function for a client.wait_for('reaction_add') check.
            Also checks if reaction.emoji == ⚙"""

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == original_message.id \
                   and str(reaction.emoji) == "\U00002699"

        return check

    async def is_logging_enabled(self, guild_id):
        """Returns true if logging is enabled for this guild."""
        return_bool = await self.bot.db.fetchval("SELECT logging FROM guilds WHERE id = $1", guild_id)

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_welcome_message_enabled(self, guild_id):
        """Returns true if welcome messages are enabled for this guild."""
        return_bool = await self.bot.db.fetchval("SELECT welcome FROM guilds WHERE id = $1", guild_id)

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_default_role_enabled(self, guild_id):
        """Returns true if a default role is enabled for this guild."""
        return_bool = await self.bot.db.fetchval("SELECT defaultrole FROM guilds WHERE id = $1", guild_id)

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_guild_initialized(self, guild_id):
        """Returns true if the guild has an entry in the bot's database."""
        return_bool = await self.bot.db.fetchval("SELECT id FROM guilds WHERE id = $1", guild_id)

        if return_bool is None:
            return False
        else:
            return True
