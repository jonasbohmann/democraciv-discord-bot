import config
import psutil
import asyncio
import discord
import platform
import importlib
import traceback

import util.utils as utils

from discord.ext import commands


# -- admin.py | module.admin --
#
# Commands that manage the bot. Requires administrator permissions.
#


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='load', hidden=True)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def load(self, ctx, *, module):
        """Loads a module."""

        try:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Loaded ' + module)

    @commands.command(name='unload', hidden=True)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def unload(self, ctx, *, module):
        """Unloads a module."""

        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Unloaded ' + module)

    @commands.command(name='reload', hidden=True)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def reload(self, ctx, *, module):
        """Reloads a module."""

        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Reloaded ' + module)

    @commands.command(name='stop', hidden=True)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def stop(self, ctx):

        await ctx.send(':wave: Goodbye! Shutting down...')
        await self.bot.close()
        await self.bot.logout()

    @commands.command(name='reloadconfig', aliases=['rlc', 'rc', 'rlcfg'], hidden=True)
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def reloadConfig(self, ctx):

        await ctx.send(':white_check_mark: Reloaded config.')
        await importlib.reload(config)

    @commands.has_permissions(manage_messages=True)
    @commands.command(name="clear")
    async def clear(self, ctx, num: int, target: discord.Member = None):
        if num > 500 or num < 0:
            await ctx.send(":x: Invalid amount, maximum is 500.")
            return

        def check(message):
            if target:
                return message.author.id == target.id
            return True

        try:
            deleted = await ctx.channel.purge(limit=num, check=check)
        except discord.Forbidden:
            await ctx.send(":x: I'm missing Administrator permissions to do this!")
            return

        await ctx.send(f':white_check_mark: Deleted **{len(deleted)}** messages.', delete_after=5)

    @commands.command(name='health', aliases=['status', 'diagnosis'], hidden=True)
    @commands.is_owner()
    async def health(self, ctx):
        # Long & ugly function that spits out some debug information

        dciv_guild = self.bot.get_guild(int(config.getConfig()["democracivServerID"]))
        info = self.bot.embeds.embed_builder(title=":drop_of_blood: Health Diagnosis",
                                             description="Running diagnosis...")
        await ctx.send(embed=info)

        await asyncio.sleep(2)

        # Embed with debug information about host system
        system_embed = self.bot.embeds.embed_builder(title="System Diagnosis", description="")
        system_embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
        system_embed.add_field(name='Python', value=platform.python_version(), inline=True)
        system_embed.add_field(name='OS', value=f'{platform.system()} {platform.release()} {platform.version()}',
                               inline=False)
        system_embed.add_field(name="CPU Usage", value=f"{str(psutil.cpu_percent())}%", inline=False)
        system_embed.add_field(name="RAM Usage", value=f"{str(psutil.virtual_memory()[2])}%", inline=False)
        await ctx.send(embed=system_embed)

        discord_embed = self.bot.embeds.embed_builder(title="Discord Diagnosis", description="")
        discord_embed.add_field(name="Ping", value=f"{self.bot.get_ping()}ms", inline=False)
        discord_embed.add_field(name="Uptime", value=f"{self.bot.get_uptime()}", inline=False)
        discord_embed.add_field(name="Guilds", value=f"{len(self.bot.guilds)}")
        discord_embed.add_field(name="Users", value=f"{len(self.bot.users)}")
        discord_embed.add_field(name="Cache Ready", value=f"{str(self.bot.is_ready())}", inline=False)
        discord_embed.add_field(name="Asyncio Tasks", value=f"{len(asyncio.all_tasks())}", inline=False)
        await ctx.send(embed=discord_embed)

        config_embed = self.bot.embeds.embed_builder(title="Config Diagnosis", description="")
        config_embed.add_field(name="Connected Democraciv Guild", value=f"{dciv_guild}")
        await ctx.send(embed=config_embed)

        # Sleep for 3 seconds to avoid being rate-limited
        await asyncio.sleep(3)

        guild_embed = self.bot.embeds.embed_builder(title="Guild Diagnosis", description="")
        guild_embed.add_field(name="Guild Initialized", value=str(config.checkIfGuildExists(ctx.guild.id)))
        guild_embed.add_field(name="Name", value=f"{config.getGuilds()[str(ctx.guild.id)]['name']}")
        guild_embed.add_field(name="Config", value=f"```{config.getGuilds()[str(ctx.guild.id)]['config']}```", inline=False)
        guild_embed.add_field(name="Strings", value=f"```{config.getGuilds()[str(ctx.guild.id)]['strings']}```", inline=False)
        guild_embed.add_field(name="Roles", value=f"```{config.getGuilds()[str(ctx.guild.id)]['roles']}```", inline=False)
        await ctx.send(embed=guild_embed)

        permission_embed = self.bot.embeds.embed_builder(title="Permission Diagnosis", description="")
        permission_embed.add_field(name="Administrator", value=str(ctx.guild.me.guild_permissions.administrator))
        permission_embed.add_field(name="Manage Guild", value=str(ctx.guild.me.guild_permissions.manage_guild))
        permission_embed.add_field(name="Manage Roles", value=str(ctx.guild.me.guild_permissions.manage_roles))
        permission_embed.add_field(name="Manage Channels", value=str(ctx.guild.me.guild_permissions.manage_channels), inline=False)
        permission_embed.add_field(name="Manage Messages", value=str(ctx.guild.me.guild_permissions.manage_messages), inline=False)
        permission_embed.add_field(name="Top Role", value=str(ctx.guild.me.top_role), inline=False)
        await ctx.send(embed=permission_embed)

        reddit_embed = self.bot.embeds.embed_builder(title="Reddit Diagnosis", description="")
        reddit_embed.add_field(name="Enabled", value=config.getReddit()["enableRedditAnnouncements"])
        reddit_embed.add_field(name="Last Reddit Post", value=config.getLastRedditPost()['id'])
        reddit_embed.add_field(name="Subreddit", value=config.getReddit()["subreddit"], inline=True)
        reddit_embed.add_field(name="Discord Channel", value="#" + config.getReddit()["redditAnnouncementChannel"]
                               , inline=True)
        reddit_embed.add_field(name="User Agent", value=config.getReddit()["userAgent"], inline=False)
        await ctx.send(embed=reddit_embed)

        twitch_embed = self.bot.embeds.embed_builder(title="Twitch Diagnosis", description="")
        twitch_embed.add_field(name="Enabled", value=config.getTwitch()["enableTwitchAnnouncements"])
        twitch_embed.add_field(name="Twitch Channel", value=config.getTwitch()["twitchChannelName"])
        twitch_embed.add_field(name="Discord Channel", value="#" + config.getTwitch()["twitchAnnouncementChannel"]
                               , inline=False)
        twitch_embed.add_field(name="Everyone Ping", value=str(config.getTwitch()["everyonePingOnAnnouncement"])
                               , inline=False)
        await ctx.send(embed=twitch_embed)


def setup(bot):
    bot.add_cog(Admin(bot))
