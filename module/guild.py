import config
import discord
import importlib
import traceback

from discord.ext import commands
from util.embed import embed_builder
from util.checks import checkIfOnDemocracivGuild


# -- guild.py | module.guild --
#
# Commands that manage a guild's settings. Requires administrator permissions.
#


class Guild(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def guild(self, ctx):
        """Configure me for this guild."""

        configuration_list_message = "`-guild welcome` to enable/disable welcome messages for this guild\n" \
                                     "`-guild logs` to enable/disable logging for this guild\n" \
                                     "`-guild exclude [name]` to add a channel to be excluded from the logging channel\n"

        embed = embed_builder(title=f"Guild Configuration for {ctx.guild.name}",
                              description=f"Here is a list of things you can configure:\n\n{configuration_list_message}")
        await ctx.send(embed=embed)

    @guild.command(name='welcome')
    async def welcome(self, ctx):
        is_welcome_enabled = config.getGuildConfig(ctx.guild.id)['enableWelcomeMessage']
        current_welcome_channel = config.getGuildConfig(ctx.guild.id)['welcomeChannel']
        current_welcome_message = config.getStrings(ctx.guild.id)['welcomeMessage']

        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        embed = embed_builder(title=f":wave: Welcome Module for {ctx.guild.name}", description="")
        embed.add_field(name="Enabled", value=f"{str(is_welcome_enabled)}")
        embed.add_field(name="Channel", value=f"#{current_welcome_channel}")
        embed.add_field(name="Message", value=f"{current_welcome_message}", inline=False)

        # TODO

        await ctx.send(embed=embed)

    @guild.command(name='logs')
    async def logs(self, ctx):
        is_logging_enabled = config.getGuildConfig(ctx.guild.id)['enableLogging']
        current_logging_channel = config.getGuildConfig(ctx.guild.id)['logChannel']

        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        embed = embed_builder(title=f":spy: Logging Module for {ctx.guild.name}", description="")
        embed.add_field(name="Enabled", value=f"{str(is_logging_enabled)}")
        embed.add_field(name="Channel", value=f"#{current_logging_channel}")

        # TODO

        await ctx.send(embed=embed)

    @guild.command(name='exclude')
    async def exclude(self, ctx, channel: str):
        current_logging_channel = config.getGuildConfig(ctx.guild.id)['logChannel']

        def check(message):
            return message.author == ctx.message.author and message.channel == ctx.message.channel

        channel_object = discord.utils.get(ctx.guild.text_channels, name=channel)

        if not channel_object:
            await ctx.send(f":x: Couldn't find #{channel}!")
            return

        if config.addExcludedLogChannel(ctx.guild.id, str(channel_object.id)):
            await ctx.send(f":white_check_mark: Excluded channel #{channel} from showing up in "
                           f"#{current_logging_channel}!")
        else:
            await ctx.send(f":x: Unexpected error occurred.")
            return


def setup(bot):
    bot.add_cog(Guild(bot))
