from config import config
import psutil
import asyncio
import discord
import platform
import importlib
import traceback

import util.utils as utils
import util.exceptions as exceptions

from discord.ext import commands


# -- admin.py | module.admin --
#
# Commands that manage the bot. Requires administrator permissions.
#


class Admin(commands.Cog):
    """Administrative commands to manage this bot"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='load')
    @commands.is_owner()
    async def load(self, ctx, *, module):
        """Loads a module"""

        try:
            self.bot.load_extension(module)
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Loaded ' + module)

    @commands.command(name='unload')
    @commands.is_owner()
    async def unload(self, ctx, *, module):
        """Unloads a module"""

        try:
            self.bot.unload_extension(module)
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Unloaded ' + module)

    @commands.command(name='reload')
    @commands.is_owner()
    async def reload(self, ctx, *, module):
        """Reloads a module"""

        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(':white_check_mark: Reloaded ' + module)

    @commands.command(name='stop')
    @commands.has_permissions(administrator=True)
    @utils.is_democraciv_guild()
    async def stop(self, ctx):
        """Restarts the bot"""

        await ctx.send(':wave: Goodbye! Shutting down...')
        await self.bot.close()
        await self.bot.logout()

    @commands.command(name='reloadconfig', aliases=['rlc', 'rc', 'rlcfg'])
    @commands.is_owner()
    async def reloadconfig(self, ctx):
        """Reload all .json config files"""

        await ctx.send(':white_check_mark: Reloaded config.')
        await importlib.reload(config)

    @commands.has_permissions(manage_messages=True)
    @commands.command(name="clear")
    async def clear(self, ctx, amount: int, target: discord.Member = None):
        """Purge an amount of messages in the current channel"""
        if amount > 500 or amount < 0:
            await ctx.send(":x: Invalid amount, maximum is 500.")
            return

        def check(message):
            if target:
                return message.author.id == target.id
            return True

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(task="", detail=":x: I'm missing Administrator permissions to do this!")

        await ctx.send(f':white_check_mark: Deleted **{len(deleted)}** messages.', delete_after=5)

    @commands.command(name="tinyurl", aliases=["tiny"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def tinyurl(self, ctx, url: str):
        """Shorten a link with tinyurl"""

        if len(url) <= 3:
            await ctx.send(":x: That doesn't look like a valid URL!")
            return

        async with self.bot.session.get(f"https://tinyurl.com/api-create.php?url={url}") as response:
            tiny_url = await response.text()

        if tiny_url == "Error":
            await ctx.send(":x: tinyurl.com returned an error!")
            return

        await ctx.send(tiny_url)

    @commands.command(name='health', aliases=['status', 'diagnosis'])
    @commands.is_owner()
    async def health(self, ctx):
        """Run a diagnosis for this bot"""
        # Long & ugly function that spits out some debug information

        info = self.bot.embeds.embed_builder(title=":drop_of_blood: Health Diagnosis",
                                             description="Running diagnosis...")
        await ctx.send(embed=info)

        async with ctx.typing():
            await asyncio.sleep(1)

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
            config_embed.add_field(name="Connected Democraciv Guild", value=f"{self.bot.democraciv_guild_object.name}")
            config_embed.add_field(name="Democraciv Guild specified in config",
                                   value=f"{self.bot.get_guild(config.DEMOCRACIV_SERVER_ID)}",
                                   inline=False)

            await ctx.send(embed=config_embed)

            permission_embed = self.bot.embeds.embed_builder(title="Permission Diagnosis", description="")
            permission_embed.add_field(name="Administrator", value=str(ctx.guild.me.guild_permissions.administrator))
            permission_embed.add_field(name="Manage Guild", value=str(ctx.guild.me.guild_permissions.manage_guild))
            permission_embed.add_field(name="Manage Roles", value=str(ctx.guild.me.guild_permissions.manage_roles))
            permission_embed.add_field(name="Manage Channels", value=str(ctx.guild.me.guild_permissions.
                                                                         manage_channels), inline=False)
            permission_embed.add_field(name="Manage Messages", value=str(ctx.guild.me.guild_permissions.
                                                                         manage_messages), inline=False)
            permission_embed.add_field(name="Top Role", value=str(ctx.guild.me.top_role), inline=False)
            await ctx.send(embed=permission_embed)

            await asyncio.sleep(4)

            reddit_embed = self.bot.embeds.embed_builder(title="Reddit Diagnosis", description="")
            reddit_embed.add_field(name="Enabled", value=config.REDDIT_ENABLED)
            reddit_embed.add_field(name="Subreddit", value=config.REDDIT_SUBREDDIT, inline=True)
            reddit_embed.add_field(name="Discord Channel", value=self.bot.get_channel
                        (config.REDDIT_ANNOUNCEMENT_CHANNEL).mention, inline=True)
            await ctx.send(embed=reddit_embed)

            twitch_embed = self.bot.embeds.embed_builder(title="Twitch Diagnosis", description="")
            twitch_embed.add_field(name="Enabled", value=config.TWITCH_ENABLED)
            twitch_embed.add_field(name="Twitch Channel", value=config.TWITCH_CHANNEL)
            reddit_embed.add_field(name="Discord Channel", value=self.bot.get_channel
            (config.TWITCH_ANNOUCEMENT_CHANNEL).mention, inline=True)
            twitch_embed.add_field(name="Everyone Ping", value=config.TWITCH_ENABLED, inline=False)
            await ctx.send(embed=twitch_embed)


def setup(bot):
    bot.add_cog(Admin(bot))
