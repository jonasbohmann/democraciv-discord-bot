import asyncio

import config
import discord
import psutil
import importlib
import traceback
import pkg_resources

from discord.ext import commands
from util.checks import isDemocracivGuild
from util.embed import embed_builder


# -- admin.py | module.admin --
#
# Commands that manage the bot. Requires administrator permissions.
#


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='load', hidden=True)
    @commands.has_permissions(administrator=True)
    async def load(self, ctx, *, module):
        """Loads a module."""
        if not isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Loaded ' + module)

    @commands.command(name='unload', hidden=True)
    @commands.has_permissions(administrator=True)
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        if not isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Unloaded ' + module)

    @commands.command(name='reload', hidden=True)
    @commands.has_permissions(administrator=True)
    async def reload(self, ctx, *, module):
        """Reloads a module."""
        if not isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Reloaded ' + module)

    @commands.command(name='stop', hidden=True)
    @commands.has_permissions(administrator=True)
    async def stop(self, ctx):
        if not isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

        await ctx.send(':wave: Goodbye! Shutting down...')
        await self.bot.close()
        await self.bot.logout()

    @commands.command(name='reloadconfig', aliases=['rlc', 'rc', 'rlcfg'], hidden=True)
    @commands.has_permissions(administrator=True)
    async def reloadConfig(self, ctx):
        if not isDemocracivGuild(ctx.guild.id):
            await ctx.send(":x: You're not allowed to use this command on this server!")
            return

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
    async def health(self, ctx):
        # Long & ugly function that spits out some debug information

        if ctx.message.author.id != int(config.getConfig()['authorID']):
            return

        my_member_object = ctx.guild.me
        my_permissions = my_member_object.guild_permissions
        my_top_role = my_member_object.top_role
        is_guild_initialized = config.checkIfGuildExists(ctx.guild.id)
        guild_payload = config.getGuilds()[str(ctx.guild.id)]
        guild_config = guild_payload['config']
        guild_name = guild_payload['name']
        guild_strings = guild_payload['strings']
        guild_roles = guild_payload['roles']
        dciv_guild = self.bot.get_guild(int(config.getConfig()["democracivServerID"]))

        info = embed_builder(title=":drop_of_blood: Health Diagnosis", description="Running diagnosis...")
        await ctx.send(embed=info)

        await asyncio.sleep(2)

        system_embed = embed_builder(title="System Diagnosis", description="")
        system_embed.add_field(name="Library", value=f"discord.py "
                                                     f"{str(pkg_resources.get_distribution('discord.py').version)}"
                               , inline=False)
        system_embed.add_field(name="CPU Usage", value=f"{str(psutil.cpu_percent())}%", inline=False)
        system_embed.add_field(name="RAM Usage", value=f"{str(psutil.virtual_memory()[2])}%", inline=False)
        await ctx.send(embed=system_embed)

        discord_embed = embed_builder(title="Discord Diagnosis", description="")
        discord_embed.add_field(name="Guilds", value=f"{len(self.bot.guilds)}")
        discord_embed.add_field(name="Users", value=f"{len(self.bot.users)}")
        discord_embed.add_field(name="Cache Ready", value=f"{str(self.bot.is_ready())}", inline=False)
        await ctx.send(embed=discord_embed)

        config_embed = embed_builder(title="Config Diagnosis", description="")
        config_embed.add_field(name="Connected Democraciv Guild", value=f"{dciv_guild}")
        await ctx.send(embed=config_embed)

        guild_embed = embed_builder(title="Guild Diagnosis", description="")
        guild_embed.add_field(name="Guild Initialized", value=str(is_guild_initialized))
        guild_embed.add_field(name="Name", value=f"{guild_name}")
        guild_embed.add_field(name="Config", value=f"```{guild_config}```", inline=False)
        guild_embed.add_field(name="Strings", value=f"```{guild_strings}```", inline=False)
        guild_embed.add_field(name="Roles", value=f"```{guild_roles}```", inline=False)
        await ctx.send(embed=guild_embed)

        permission_embed = embed_builder(title="Permission Diagnosis", description="")
        permission_embed.add_field(name="Administrator", value=str(my_permissions.administrator))
        permission_embed.add_field(name="Manage Guild", value=str(my_permissions.manage_guild))
        permission_embed.add_field(name="Manage Roles", value=str(my_permissions.manage_roles))
        permission_embed.add_field(name="Manage Channels", value=str(my_permissions.manage_channels), inline=False)
        permission_embed.add_field(name="Manage Messages", value=str(my_permissions.manage_messages), inline=False)
        permission_embed.add_field(name="Top Role", value=str(my_top_role), inline=False)
        await ctx.send(embed=permission_embed)

        reddit_embed = embed_builder(title="Reddit Diagnosis", description="")
        reddit_embed.add_field(name="Enabled", value=config.getReddit()["enableRedditAnnouncements"])
        reddit_embed.add_field(name="Last Reddit Post", value=config.getLastRedditPost()['id'])
        reddit_embed.add_field(name="Subreddit", value=config.getReddit()["subreddit"], inline=True)
        reddit_embed.add_field(name="Discord Channel", value="#" + config.getReddit()["redditAnnouncementChannel"]
                               , inline=True)
        reddit_embed.add_field(name="User Agent", value=config.getReddit()["userAgent"], inline=False)
        await ctx.send(embed=reddit_embed)

        twitch_embed = embed_builder(title="Twitch Diagnosis", description="")
        twitch_embed.add_field(name="Enabled", value=config.getTwitch()["enableTwitchAnnouncements"])
        twitch_embed.add_field(name="Twitch Channel", value=config.getTwitch()["twitchChannelName"])
        twitch_embed.add_field(name="Discord Channel", value="#" + config.getTwitch()["twitchAnnouncementChannel"]
                               , inline=False)
        twitch_embed.add_field(name="Everyone Ping", value=str(config.getTwitch()["everyonePingOnAnnouncement"])
                               , inline=False)
        await ctx.send(embed=twitch_embed)


def setup(bot):
    bot.add_cog(Admin(bot))
