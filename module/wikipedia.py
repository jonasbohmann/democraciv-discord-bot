import re
import config
import aiohttp

from discord.ext import commands


class Wikipedia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_wikipedia_result(self, query):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}") as response:
                wikipedia_result_json_dump = await response.json()
                if response.status == 200:
                    return wikipedia_result_json_dump
                else:
                    return None

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for a topic on Wikipedia\nUse quotes for topics that consist of multiple words!"""
        result = await self.get_wikipedia_result(topic)

        if result is None:
            await ctx.send(f":x: Couldn't find a Wikipedia page named '{topic}'.")
            return

        _title = result['displaytitle']
        _summary = result['extract']
        _summary_in_2_sentences = ' '.join(re.split(r'(?<=[.?!])\s+', _summary, 2)[:-1])
        _url = result['content_urls']['desktop']['page']
        _thumbnail_url = ''

        try:
            _thumbnail_url = result['thumbnail']['source']
        except KeyError:
            pass

        if _summary_in_2_sentences == '' or not _summary_in_2_sentences:
            await ctx.send(f':x: There are multiple pages named {topic}! Please try again with a more specifc query.')
            return

        embed = self.bot.embeds.embed_builder(title=_title, description=_summary_in_2_sentences)
        embed.add_field(name='Link', value=_url)

        if _thumbnail_url.startswith('https://'):
            embed.set_thumbnail(url=_thumbnail_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Wikipedia(bot))
