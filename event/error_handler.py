import config
import discord
import datetime

from discord.ext import commands
from util.utils import CheckUtils, EmbedUtils


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.embeds = EmbedUtils()
        self.checks = CheckUtils()

    @commands.Cog.listener()
    async def on_error(self, ctx, error):
        # Alert owner of this bot that error occurred
        owner_user = self.bot.get_user(int(config.getConfig()['authorID']))
        await owner_user.create_dm()
        owner_dm_channel = owner_user.dm_channel
        await owner_dm_channel.send(
            f":x: An error occurred on {ctx.guild.name} at {datetime.datetime.now()}!\n\n{error}")

        raise error

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        ignored = (commands.CommandNotFound, commands.UserInputError)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(str(error))
            guild = ctx.guild
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.embeds.embed_builder(title=':x: Command Error', description="")
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Error', value='CommandOnCooldown')
            embed.add_field(name='Guild', value=ctx.guild)
            embed.add_field(name='Channel', value=ctx.channel.mention)
            embed.add_field(name='User', value=ctx.author.name)
            embed.add_field(name='Message', value=ctx.message.clean_content)
            embed.add_field(name='Severe', value='No')
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(str(error))
            guild = ctx.guild
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.embeds.embed_builder(title=':x: Command Error', description="")
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Error', value='MissingPermissions')
            embed.add_field(name='Guild', value=ctx.guild)
            embed.add_field(name='Channel', value=ctx.channel.mention)
            embed.add_field(name='User', value=ctx.author.name)
            embed.add_field(name='Message', value=ctx.message.clean_content)
            embed.add_field(name='Severe', value='No')
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
            guild = ctx.guild
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.embeds.embed_builder(title=':x: Command Error', description="")
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Error', value='MissingRequiredArgument')
            embed.add_field(name='Guild', value=ctx.guild)
            embed.add_field(name='Channel', value=ctx.channel.mention)
            embed.add_field(name='User', value=ctx.author.name)
            embed.add_field(name='Message', value=ctx.message.clean_content)
            embed.add_field(name='Severe', value='No')
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(str(error))


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
