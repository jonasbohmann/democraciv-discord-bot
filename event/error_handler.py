import config
import discord
import datetime
import util.exceptions as exceptions

from discord.ext import commands


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def log_error(self, ctx, error, severe: bool = False, to_log_channel: bool = True, to_owner: bool = False):
        log_channel = discord.utils.get(ctx.guild.text_channels, name=config.getGuildConfig(ctx.guild.id)['logChannel'])

        embed = self.bot.embeds.embed_builder(title=':x: Command Error', description="", time_stamp=True)
        embed.add_field(name='Error', value=error.__class__.__name__)
        embed.add_field(name='Channel', value=ctx.channel.mention)
        embed.add_field(name='User', value=ctx.author.name)
        embed.add_field(name='Message', value=ctx.message.clean_content)

        if severe:
            embed.add_field(name='Severe', value='Yes')

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
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(str(error))
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(str(error))
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            return

        if isinstance(error, exceptions.RoleNotFoundError):
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(f":x: Couldn't find a role named '{error.role}' on this guild!")
            return

        if isinstance(error, exceptions.MemberNotFoundError):
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(f":x: Couldn't find a member named {error.member} on this guild!")
            return

        if isinstance(error, exceptions.NoOneHasRoleError):
            self.log_error(ctx, error, severe=False, to_log_channel=True, to_owner=False)
            await ctx.send(f":x: No one on this guild has the role named '{error.role}'!")
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send(str(error))


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
