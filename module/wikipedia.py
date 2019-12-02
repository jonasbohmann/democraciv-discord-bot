import re
from config import config

from discord.ext import commands


class Wikipedia(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def get_wikipedia_result_with_rest_api(self, query):

        # This uses the newer REST API that MediaWiki offers to query their site.
        #   advantages: newer, cleaner, faster, gets thumbnail + URL
        #   disadvantages: doesn't work with typos in attr: query
        #   see: https://www.mediawiki.org/wiki/REST_API

        async with self.bot.session.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}") as response:
            if response.status == 200:
                return await response.json()
            else:
                return None

    async def get_wikipedia_suggested_articles(self, query):

        # This uses the older MediaWiki Action API to query their site.
        #
        #    Used as a fallback when self.get_wikipedia_result_with_rest_api() returns None, i.e. there's a typo in the
        #    query string. Returns suggested articles from a 'disambiguation' article
        #
        #   see: https://en.wikipedia.org/w/api.php

        async with self.bot.session.get(f"https://en.wikipedia.org/w/api.php?format=json&action=query&list=search"
                                        f"&srinfo=suggestion&srprop&srsearch={query}") as response:
            if response.status == 200:
                return await response.json()
            else:
                return None

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for a topic on Wikipedia\nUse quotes for topics that consist of multiple words!"""
        async with ctx.typing():  # Show typing status so that user knows that stuff is happening
            result = await self.get_wikipedia_result_with_rest_api(topic)

            if result is None or result['type'] == 'disambiguation':

                # Fall back to MediaWiki Action API and ask for article suggestions as there's probably a typo 'topic'
                suggested_pages = await self.get_wikipedia_suggested_articles(topic)

                try:
                    suggested_query_name = suggested_pages['query']['search'][0]['title']
                except Exception:
                    await ctx.send(":x: Unexpected error occurred.")
                    return

                # Retry with new suggested article title
                result = await self.get_wikipedia_result_with_rest_api(suggested_query_name)

                if result is None or not result:
                    await ctx.send(":x: Unexpected error occurred.")
                    return

            _title = result['title']
            _summary = result['extract']
            _summary_in_2_sentences = ' '.join(re.split(r'(?<=[.?!])\s+', _summary, 2)[:-1])
            _url = result['content_urls']['desktop']['page']
            _thumbnail_url = ''

            try:
                _thumbnail_url = result['thumbnail']['source']
            except KeyError:
                pass

            embed = self.bot.embeds.embed_builder(title=_title, description=_summary_in_2_sentences)
            embed.add_field(name='Link', value=_url)

            if _thumbnail_url.startswith('https://'):
                embed.set_thumbnail(url=_thumbnail_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Wikipedia(bot))
