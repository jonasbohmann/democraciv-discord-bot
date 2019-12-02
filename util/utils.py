import config
import discord
import datetime
import util.exceptions as exceptions

from discord.ext import commands

DEMOCRACIV_GUILD_ID = int(config.getConfig()["democracivServerID"])


def is_democraciv_guild():
    """Wrapper for a discord.ext.commands decorator to check if command is used on the Democraciv guild"""

    def check(ctx):
        if DEMOCRACIV_GUILD_ID != ctx.guild.id:
            raise exceptions.NotDemocracivGuildError()
        return True

    return commands.check(check)


async def get_logging_channel(bot, guild_id):
    logging_channel = (await bot.db.fetchrow("SELECT logging_channel FROM guilds WHERE id = $1",
                                             guild_id))['logging_channel']
    return bot.get_channel(logging_channel)


async def get_welcome_channel(bot, guild_id):
    welcome_channel = (await bot.db.fetchrow("SELECT welcome_channel FROM guilds WHERE id = $1",
                                             guild_id))['welcome_channel']
    return bot.get_channel(welcome_channel)


class EmbedUtils:
    """Utils to assist with discord.Embed objects"""

    def __init__(self):
        self.footer_text = config.getConfig()['botName']
        self.footer_icon = config.getConfig()['botIconURL']
        self.embed_colour = 0x7f0000

    def embed_builder(self, title: str, description: str, colour: int = None, time_stamp: bool = None):
        embed = discord.Embed(title=title, description=description, colour=self.embed_colour)
        embed.set_footer(text=self.footer_text, icon_url=self.footer_icon)

        if time_stamp:
            embed.timestamp = datetime.datetime.utcnow()

        return embed


class CheckUtils:
    """Utils to assist with discord.ext.commands checks"""

    def __init__(self, db):
        self.db = db
        self.democraciv_guild_id = int(config.getConfig()["democracivServerID"])
        self.der_jonas_id = int(config.getConfig()['authorID'])

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
        try:
            return_bool = (await self.db.fetchrow("SELECT logging FROM guilds WHERE id = $1", guild_id))['logging']
        except TypeError:
            return False

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_welcome_message_enabled(self, guild_id):
        """Returns true if welcome messages are enabled for this guild."""
        try:
            return_bool = (await self.db.fetchrow("SELECT welcome FROM guilds WHERE id = $1", guild_id))['welcome']
        except TypeError:
            return False

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_default_role_enabled(self, guild_id):
        """Returns true if a default role is enabled for this guild."""
        try:
            return_bool = (await self.db.fetchrow("SELECT defaultrole FROM guilds WHERE id = $1", guild_id))[
                'defaultrole']
        except TypeError:
            return False

        if return_bool is None:
            return False
        else:
            return return_bool

    async def is_guild_initialized(self, guild_id):
        """Returns true if the guild has an entry in the bot's database."""
        try:
            return_bool = (await self.db.fetchrow("SELECT id FROM guilds WHERE id = $1", guild_id))[
                'id']
        except TypeError:
            return False

        if return_bool is None:
            return False
        else:
            return True
