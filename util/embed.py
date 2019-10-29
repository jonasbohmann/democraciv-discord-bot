import config
import discord


def embed_builder(title: str, description: str, colour: str = None):
    embed = discord.Embed(title=title, description=description, colour=0x7f0000)
    embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
    return embed


if __name__ == '__main__':
    pass
