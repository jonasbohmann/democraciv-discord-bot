import config
import discord


class EmbedUtils:

    def __init__(self):
        self.footer_text = config.getConfig()['botName']
        self.footer_icon = config.getConfig()['botIconURL']
        self.embed_colour = 0x7f0000

    def embed_builder(self, title: str, description: str, colour: int = None):
        embed = discord.Embed(title=title, description=description, colour=self.embed_colour)
        embed.set_footer(text=self.footer_text, icon_url=self.footer_icon)
        return embed


class CheckUtils:

    def __init__(self):
        self.democraciv_guild_id = int(config.getConfig()["democracivServerID"])
        self.der_jonas_id = int(config.getConfig()['authorID'])

    def isDemocracivGuild(self, guild_id):
        return self.democraciv_guild_id == int(guild_id)

    def isDerJonas(self, member_id):
        return self.der_jonas_id == int(member_id)