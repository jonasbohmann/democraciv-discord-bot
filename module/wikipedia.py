import config
import discord
import wikipedia

from discord.ext import commands
from util.embed import embed_builder

wikipedia.set_lang('en')


class Wikipedia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for a topic on Wikipedia\nUse quotes for topics that consist of multiple words!"""
        page = wikipedia.page(topic)
        embed = embed_builder(title=page.title, description=wikipedia.summary(topic, sentences=2), colour=0x7f0000)
        embed.add_field(name='Link', value=page.url)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)


def setup(bot):
    bot.add_cog(Wikipedia(bot))
