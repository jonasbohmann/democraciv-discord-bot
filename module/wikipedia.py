import config
import wikipedia

from discord.ext import commands

wikipedia.set_lang('en')


class Wikipedia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for a topic on Wikipedia\nUse quotes for topics that consist of multiple words!"""
        page = wikipedia.page(topic)
        embed = self.bot.embeds.embed_builder(title=page.title, description=wikipedia.summary(topic, sentences=2),
                                              colour=0x7f0000)
        embed.add_field(name='Link', value=page.url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Wikipedia(bot))
