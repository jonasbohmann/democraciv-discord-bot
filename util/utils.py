import config
import discord
import datetime


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

    def __init__(self):
        self.democraciv_guild_id = int(config.getConfig()["democracivServerID"])
        self.der_jonas_id = int(config.getConfig()['authorID'])

    def is_democraciv_guild(self, guild_id):
        return self.democraciv_guild_id == int(guild_id)

    def is_DerJonas(self, member_id):
        return self.der_jonas_id == int(member_id)

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
