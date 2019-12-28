import re

from config import config
from discord.ext import commands


class Wiki(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def get_wikipedia_result_with_rest_api(self, query):

        # This uses the newer REST API that MediaWiki offers to query their site.
        #   advantages: newer, cleaner, faster, gets thumbnail + URL
        #   disadvantages: doesn't work with typos in attr: query
        #
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

    async def get_civilization_fandom_suggested_article(self, query: str) -> int:

        async with self.bot.session.get(f"https://civilization.fandom.com/api/v1/SearchSuggestions"
                                        f"/List?query={query}") as response:
            if response.status == 200:
                suggested_json = await response.json()

        try:
            suggested_article = suggested_json['items'][0]['title']
        except (IndexError, KeyError):
            return -1

        async with self.bot.session.get(f"https://civilization.fandom.com/api/v1/Search/List?query={suggested_article}"
                                        f"&rank=most-viewed&limit=1&minArticleQuality=10&"
                                        f"batch=1&namespaces=0%2C14") as response:
            if response.status == 200:
                search_json = await response.json()

        try:
            article_id = search_json['items'][0]['id']
        except (IndexError, KeyError):
            return -1

        return article_id

    async def get_civilization_fandom_article_details(self, article_id: int) -> list:

        if article_id == -1:
            return [None]

        async with self.bot.session.get(f"https://civilization.fandom.com/api/v1/Articles/Details?ids={article_id}"
                                        f"&abstract=100&width=200&height=200") as response:

            if response.status == 200:
                article = await response.json()

        article_id = str(article_id)

        _title = article['items'][article_id]['title'] or None
        _description = article['items'][article_id]['abstract'] or None
        _thumbnail = article['items'][article_id]['thumbnail'] or None
        _url = f"https://civilization.fandom.com{article['items'][article_id]['url']}" or None

        return [_title, _description, _thumbnail, _url]

    @commands.command(name='civwiki', aliases=['cw'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def civwiki(self, ctx, *, topic: str):
        """Search for an article on the Civilization Fandom Wiki"""

        async with ctx.typing():
            article = await self.get_civilization_fandom_article_details(
                                                    await self.get_civilization_fandom_suggested_article(topic))

        if not article[0]:
            return await ctx.send(f":x: Couldn't find any article that's related to '{topic}'.")

        embed = self.bot.embeds.embed_builder(title=f"<:fandom:660488383855984640>  {article[0]}",
                                              description=article[1], has_footer=False)
        embed.add_field(name='Link', value=article[3])

        if article[2] is not None and article[2].startswith('https://'):
            embed.set_thumbnail(url=article[2])

        await ctx.send(embed=embed)

    @commands.command(name='wikipedia')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def wikipedia(self, ctx, *, topic: str):
        """Search for an article on Wikipedia"""
        async with ctx.typing():  # Show typing status so that user knows that stuff is happening
            result = await self.get_wikipedia_result_with_rest_api(topic)

            if result is None or result['type'] == 'disambiguation':

                # Fall back to MediaWiki Action API and ask for article suggestions as there's probably a typo in
                # 'topic'
                suggested_pages = await self.get_wikipedia_suggested_articles(topic)

                try:
                    suggested_query_name = suggested_pages['query']['search'][0]['title']
                except (IndexError, KeyError):
                    await ctx.send(":x: Unexpected error occurred.")
                    return

                # Retry with new suggested article title
                result = await self.get_wikipedia_result_with_rest_api(suggested_query_name)

                if result is None or not result:
                    return await ctx.send(f":x: Didn't find any article that's related to '{topic}'")

            _title = result['title']
            _summary = result['extract']
            _summary_in_2_sentences = ' '.join(re.split(r'(?<=[.?!])\s+', _summary, 2)[:-1])
            _url = result['content_urls']['desktop']['page']
            _thumbnail_url = ''

            try:
                _thumbnail_url = result['thumbnail']['source']
            except KeyError:
                pass

            embed = self.bot.embeds.embed_builder(title=f"<:wikipedia:660487143856275497>  {_title}",
                                                  description=_summary_in_2_sentences, has_footer=False)
            embed.add_field(name='Link', value=_url)

            if _thumbnail_url.startswith('https://'):
                embed.set_thumbnail(url=_thumbnail_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Wiki(bot))
