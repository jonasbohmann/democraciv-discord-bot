import config
import discord
import datetime
import util.exceptions as exceptions

from discord.ext import commands


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_error(self, ctx, error, severe: bool = False, to_log_channel: bool = True, to_owner: bool = False):
        log_channel = discord.utils.get(ctx.guild.text_channels, name=config.getGuildConfig(ctx.guild.id)['logChannel'])

        embed = self.bot.embeds.embed_builder(title=':x: Command Error', description="", time_stamp=True)
        embed.add_field(name='Error', value=error.__class__.__name__, inline=False)

        try:
            embed.add_field(name='Error Message', value=error.message, inline=False)
        except AttributeError:
            pass

        embed.add_field(name='Channel', value=ctx.channel.mention, inline=True)
        embed.add_field(name='User', value=ctx.author.name, inline=True)

        if severe:
            embed.add_field(name='Severe', value='Yes', inline=True)

        embed.add_field(name='Caused by', value=ctx.message.clean_content, inline=False)

        if to_owner:
            embed.add_field(name='Guild', value=ctx.guild.name)

            await self.bot.DerJonas_dm_channel.send(
                f":x: An error occurred on {ctx.guild.name} at {datetime.datetime.now()}!\n\n{error}")
            await self.bot.DerJonas_dm_channel.send(embed=embed)

        if to_log_channel:
            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_error(self, ctx, error):
        raise error

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        ignored = (commands.CommandNotFound, commands.UserInputError)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return

        if isinstance(error, commands.CommandOnCooldown):
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(str(error))
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(str(error))
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            return

        if isinstance(error, exceptions.RoleNotFoundError):
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(error.message)

        if isinstance(error, exceptions.MemberNotFoundError):
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(error.message)
            return

        if isinstance(error, exceptions.NoOneHasRoleError):
            await self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(error.message)
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(str(error))


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
