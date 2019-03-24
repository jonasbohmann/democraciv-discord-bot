import twitch
import config
import discord

from discord.ext import commands


# TODO - Add Twitch Module

class Twitch:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="twitch")
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def twitch(self, ctx):
        client = twitch.TwitchClient(client_id='<my client id>')
        channel = client.channels.get_by_id(config.getConfig()['twitchChannelID'])
        twitch.TwitchHelix.get_streams(user_ids=config.getConfig()['twitchChannelID'])

        embed = discord.Embed(title=config.getConfig()['twitchChannelName'] + ' is live on Twitch!', description=config.getLinks()['importantLinks'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)


def setup(bot):
    bot.add_cog(Twitch(bot))
