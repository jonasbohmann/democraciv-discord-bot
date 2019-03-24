import praw
import config
import discord

from discord.ext import commands

reddit = praw.Reddit(client_id=config.getReddit()['clientID'],
                     client_secret=config.getReddit()['clientSecret'],
                     user_agent=config.getReddit()['userAgent'])


# TODO - Add Reddit Module

class Reddit:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reddit")
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def reddit(self, ctx):
        pass


def setup(bot):
    bot.add_cog(Reddit(bot))
