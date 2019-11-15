import html
import config
import asyncio
import discord

import util.exceptions as exceptions


class Reddit:

    def __init__(self, bot):
        self.bot = bot
        self.subreddit = config.getReddit()['subreddit']

    async def get_newest_reddit_post(self):
        async with self.bot.session.get(f"https://www.reddit.com/r/{self.subreddit}/new.json?limit=1") as response:
            return await response.json()

    async def reddit_task(self):
        last_reddit_post = config.getLastRedditPost()

        await self.bot.wait_until_ready()

        channel = discord.utils.get(self.bot.democraciv_guild_object.text_channels,
                                    name=config.getReddit()['redditAnnouncementChannel'])
        if channel is None:
            raise exceptions.ChannelNotFoundError(config.getReddit()['redditAnnouncementChannel'])

        while not self.bot.is_closed():

            reddit_post_json = await self.get_newest_reddit_post()
            reddit_post_json = reddit_post_json["data"]["children"][0]["data"]

            _id = reddit_post_json["id"]
            _title = reddit_post_json['title']
            _author = f"u/{reddit_post_json['author']}"
            _comments_link = f"https://old.reddit.com{reddit_post_json['permalink']}"

            try:
                _thumbnail_url = reddit_post_json['preview']['images'][0]['source']['url']
            except KeyError:
                _thumbnail_url = reddit_post_json['thumbnail']

            if not last_reddit_post['id'] == _id:
                # Set new last_reddit_post
                config.getLastRedditPost()['id'] = _id
                config.setLastRedditPost()

                embed = self.bot.embeds.embed_builder(
                    title=f":mailbox_with_mail: New post on r/{self.subreddit}",
                    description="", time_stamp=True)
                embed.add_field(name="Thread", value=f"[{_title}]({_comments_link})", inline=False)
                embed.add_field(name="Author", value=f"{_author}", inline=False)

                if _thumbnail_url.startswith("https://"):
                    _thumbnail_url = html.unescape(_thumbnail_url)
                    embed.set_thumbnail(url=_thumbnail_url)

                await channel.send(embed=embed)
            await asyncio.sleep(60)
