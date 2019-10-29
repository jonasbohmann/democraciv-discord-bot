import praw
import config
import asyncio
import discord
import datetime


class Reddit:

    def __init__(self, bot):
        self.bot = bot
        self.redditClient = praw.Reddit(client_id=config.getTokenFile()['redditClientID'],
                                        client_secret=config.getTokenFile()['redditClientSecret'],
                                        user_agent=config.getReddit()['userAgent'])
        self.subreddit = self.redditClient.subreddit(config.getReddit()['subreddit'])

    async def reddit_task(self):
        last_reddit_post = config.getLastRedditPost()

        await self.bot.wait_until_ready()

        try:
            dcivGuild = self.bot.get_guild(int(config.getConfig()["homeServerID"]))
            channel = discord.utils.get(dcivGuild.text_channels, name=config.getReddit()['redditAnnouncementChannel'])
        except AttributeError:
            print(
                f'ERROR - I could not find the Democraciv Discord Server! Change "homeServerID" '
                f'in the config to a server I am in or disable Reddit announcements.')
            return

        while not self.bot.is_closed():
            for submission in self.subreddit.new(limit=1):
                reddit_post = submission
                title = submission.title
                author = submission.author
                comments_link = submission.permalink

            if not last_reddit_post['id'] == submission.id:
                # Set new last_reddit_post
                config.getLastRedditPost()['id'] = submission.id
                config.setLastRedditPost()

                embed = discord.Embed(title=f":mailbox_with_mail: New post on r/{config.getReddit()['subreddit']}",
                                      colour=0x7f0000)
                embed.add_field(name="Thread", value=f"[{title}](https://reddit.com{comments_link})", inline=False)
                embed.add_field(name="Author", value=f"u/{author}", inline=False)

                # Fetch image of post if it has one
                index = 4
                image_link = None
                for x in range(3):
                    if image_link is not None:
                        embed.set_thumbnail(url=image_link)
                        break
                    try:
                        image_link = reddit_post.preview['images'][0]['resolutions'][index]['url']
                    except (AttributeError, UnboundLocalError, IndexError) as e:
                        index = index - 1

                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.timestamp = datetime.datetime.utcnow()

                await channel.send(embed=embed)
            await asyncio.sleep(60)