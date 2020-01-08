import discord

from config import config
from util.flow import Flow
import util.utils as utils
from util.paginator import Pages
import util.exceptions as exceptions

from discord.ext import commands


# -- guild.py | module.guild --
#
# Commands that manage a guild's settings. Requires administrator permissions.
#


class Guild(commands.Cog):
    """Commands regarding this guild"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='guild', case_insensitive=True, invoke_without_command=True)
    @commands.guild_only()
    async def guild(self, ctx):
        """Configure various features of this bot for this guild"""

        configuration_list_message = "`-guild welcome` to enable/disable welcome messages for this guild\n" \
                                     "`-guild logs` to enable/disable logging for this guild\n" \
                                     "`-guild exclude [name]` to add a channel to be excluded from " \
                                     "the logging channel\n" \
                                     "`-guild defaultrole` to enable/disable a default role that every new member gets"

        embed = self.bot.embeds.embed_builder(title=f"Guild Configuration for {ctx.guild.name}",
                                              description=f"Here is a list of things you can configure:"
                                                          f"\n\n{configuration_list_message}")
        await ctx.send(embed=embed)

    @guild.command(name='welcome')
    @commands.has_permissions(administrator=True)
    async def welcome(self, ctx):
        """Configure a welcome message that every new member will see once they join this guild"""

        is_welcome_enabled = await self.bot.checks.is_welcome_message_enabled(ctx.guild.id)

        current_welcome_channel = (await self.bot.db.fetchrow("SELECT welcome_channel FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['welcome_channel']
        current_welcome_channel = self.bot.get_channel(current_welcome_channel)

        current_welcome_message = (await self.bot.db.fetchrow("SELECT welcome_message FROM guilds WHERE id = $1",
                                                              ctx.guild.id))['welcome_message']

        if current_welcome_channel is None:
            current_welcome_channel = "This guild currently has no welcome channel."
        else:
            current_welcome_channel = current_welcome_channel.mention

        if current_welcome_message is None or current_welcome_message == "":
            current_welcome_message = "This guild currently has no welcome message."

        embed = self.bot.embeds.embed_builder(title=f":wave: Welcome Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change "
                                                          "the settings of this module.")
        embed.add_field(name="Enabled", value=f"{str(is_welcome_enabled)}")
        embed.add_field(name="Channel", value=f"{current_welcome_channel}")
        embed.add_field(name="Message", value=f"{current_welcome_message}", inline=False)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):
            status_question = await ctx.send(
                "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")

            reaction, user = await flow.yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET welcome = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the welcome module.")

                # Get new welcome channel
                await ctx.send(
                    ":information_source: Answer with the name of the channel the welcome module should use:")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET welcome_channel = $2 WHERE id = $1",
                                                   ctx.guild.id, channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the welcome channel to {channel_object.mention}.")

                # Get new welcome message
                await ctx.send(
                    f":information_source: Answer with the message that should be sent to {channel_object.mention} "
                    f"every time a new member joins.\n\nWrite '{{member}}' "
                    f"to make the Bot mention the user!")

                welcome_message = await flow.get_text_input(300)

                if welcome_message:
                    status = await self.bot.db.execute("UPDATE guilds SET welcome_message = $2 WHERE id = $1",
                                                       ctx.guild.id, welcome_message)

                    if status == "UPDATE 1":
                        await ctx.send(f":white_check_mark: Set welcome message to '{welcome_message}'.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET welcome = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the welcome module.")

    @guild.command(name='logs')
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx):
        """Configure the logging module that logs every guild event to a specified channel"""

        is_logging_enabled = (await self.bot.db.fetchrow("SELECT logging FROM guilds WHERE id = $1", ctx.guild.id))[
            'logging']

        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild.id)

        if current_logging_channel is None:
            current_logging_channel = "This guild currently has no logging channel."
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy: Logging Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the "
                                                          "settings of this module.")

        embed.add_field(name="Enabled", value=f"{str(is_logging_enabled)}")
        embed.add_field(name="Channel", value=f"{current_logging_channel}")

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")

            reaction, user = await flow.yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET logging = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the logging module.")

                await ctx.send(
                    ":information_source: Answer with the name of the channel the logging module should use:")

                channel_object = await flow.get_new_channel(240)

                if isinstance(channel_object, str):
                    raise exceptions.ChannelNotFoundError(channel_object)

                status = await self.bot.db.execute("UPDATE guilds SET logging_channel = $2 WHERE id = $1", ctx.guild.id,
                                                   channel_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the logging channel to {channel_object.mention}.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET logging = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the logging module.")

    @guild.command(name='exclude')
    @commands.has_permissions(administrator=True)
    async def exclude(self, ctx, channel: str = None):
        """
        Configure the channels that should be excluded from the logging module on this guild

            Usage:
                `-guild exclude` to see all excluded channels
                `-guild exclude <channel>` too add/remove a channel to/from the excluded channels list
        """
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild.id)

        if current_logging_channel is None:
            await ctx.send(":x: This guild currently has no logging channel. Please set one with `-guild logs`.")
            return

        help_description = "Add/Remove a channel to the excluded channels with:\n`-guild exclude [channel_name]`\n"

        excluded_channels = (await self.bot.db.fetchrow("SELECT logging_excluded FROM guilds WHERE id = $1"
                                                        , ctx.guild.id))['logging_excluded']
        if not channel:
            current_excluded_channels_by_name = ""

            if excluded_channels is None:
                await ctx.send("There are no from logging excluded channels on this guild.")
                return

            for channel in excluded_channels:
                channel = self.bot.get_channel(channel)
                if channel is not None:
                    current_excluded_channels_by_name += f"{channel.mention}\n"

            if current_excluded_channels_by_name == "":
                current_excluded_channels_by_name = "There are no from logging excluded channels on this guild."

            embed = self.bot.embeds.embed_builder(title=f"Logging-Excluded Channels on {ctx.guild.name}",
                                                  description=help_description)
            embed.add_field(name="Currently Excluded Channels", value=current_excluded_channels_by_name)
            await ctx.send(embed=embed)
            return

        else:
            try:
                channel_object = await commands.TextChannelConverter().convert(ctx, channel)
            except commands.BadArgument:
                raise exceptions.ChannelNotFoundError(channel)

            if not channel_object:
                raise exceptions.ChannelNotFoundError(channel)

            # Remove channel
            if channel_object.id in excluded_channels:
                remove_status = await self.bot.db.execute(
                    "UPDATE guilds SET logging_excluded = array_remove(logging_excluded, $2 ) WHERE id = $1",
                    ctx.guild.id, channel_object.id)

                if remove_status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: {channel_object.mention} is no longer excluded from"
                                   f" showing up in {current_logging_channel.mention}!")
                    return
                else:
                    await ctx.send(f":x: Unexpected error occurred.")
                    return

            # Add channel
            add_status = await self.bot.db.execute("UPDATE guilds SET logging_excluded = array_append(logging_excluded,"
                                                   " $2) WHERE id = $1"
                                                   , ctx.guild.id, channel_object.id)

            if add_status == "UPDATE 1":
                await ctx.send(f":white_check_mark: Excluded channel {channel_object.mention} from showing up in "
                               f"{current_logging_channel.mention}!")
            else:
                await ctx.send(f":x: Unexpected error occurred.")

            return

    @guild.command(name='defaultrole')
    @commands.has_permissions(administrator=True)
    async def defaultrole(self, ctx):
        """Configure a default role that every new member will get once they join this guild"""

        is_default_role_enabled = await self.bot.checks.is_default_role_enabled(ctx.guild.id)

        current_default_role = (await self.bot.db.fetchrow("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                           ctx.guild.id))['defaultrole_role']
        current_default_role = ctx.guild.get_role(current_default_role)

        if current_default_role is None:
            current_default_role = "This guild currently has no default role."
        else:
            current_default_role = current_default_role.mention

        embed = self.bot.embeds.embed_builder(title=f":partying_face: Default Role for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the settings"
                                                          " of this module.")
        embed.add_field(name="Enabled", value=f"{str(is_default_role_enabled)}")
        embed.add_field(name="Role", value=f"{current_default_role}")

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the default role, or with :x: to disable the default role.")

            reaction, user = await flow.yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if str(reaction.emoji) == "\U00002705":
                await self.bot.db.execute("UPDATE guilds SET defaultrole = true WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Enabled the default role.")

                await ctx.send(
                    ":information_source: What's the name of the role that every "
                    "new member should get once they join?")

                new_default_role = await flow.get_new_role(240)

                if isinstance(new_default_role, str):
                    await ctx.send(
                        f":white_check_mark: I will **create a new role** on this guild named '{new_default_role}'"
                        f" for the default role.")
                    try:
                        new_default_role_object = await ctx.guild.create_role(name=new_default_role)
                    except discord.Forbidden:
                        raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, new_default_role)

                else:
                    new_default_role_object = new_default_role

                    await ctx.send(
                        f":white_check_mark: I'll use the **pre-existing role** named "
                        f"'{new_default_role_object.name}' for the default role.")

                status = await self.bot.db.execute("UPDATE guilds SET defaultrole_role = $2 WHERE id = $1",
                                                   ctx.guild.id, new_default_role_object.id)

                if status == "UPDATE 1":
                    await ctx.send(f":white_check_mark: Set the default role to '{new_default_role_object.name}'.")

            elif str(reaction.emoji) == "\U0000274c":
                await self.bot.db.execute("UPDATE guilds SET defaultrole = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the default role.")

    @commands.command(name='invite')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this guild"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)

    @commands.command(name="tags", aliases=["alltags"])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def tags(self, ctx):
        """See all tags on this guild"""

        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1", ctx.guild.id)

        pretty_tags = []

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}\n")

        if not pretty_tags or len(pretty_tags) == 0:
            pretty_tags = ['There are no tags on this guild.']

        pages = Pages(ctx=ctx, entries=pretty_tags, show_entry_count=False, title=f"All tags in {ctx.guild.name}"
                      , show_index=False, footer_text=config.BOT_NAME)
        await pages.paginate()

    @commands.command(name="addtagalias")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def addtagalias(self, ctx):
        """Add a new alias to a tag"""

        flow = Flow(self.bot, ctx)

        await ctx.send(":information_source: Reply with the name of the tag that the new alias should belong to.")

        tag = await flow.get_text_input(240)

        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                 tag.lower(), ctx.guild.id)

        if tag_details is None:
            return await ctx.send(f":x: This guild has no tag called `{tag}`!")

        await ctx.send(f":information_source: Reply with the alias for `{config.BOT_PREFIX}{tag}`.")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to add the alias "
                                      f"`{config.BOT_PREFIX}{alias}` to "
                                      f"`{config.BOT_PREFIX}{tag_details['name']}`?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    status = await self.bot.db.execute("INSERT INTO guild_tags_alias (alias, guild_tag_id) VALUES "
                                                       "($1, $2)", alias.lower(), tag_details['id'])

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Added the alias `{config.BOT_PREFIX}{alias}` to'
                           f'`{config.BOT_PREFIX}{tag_details["name"]}`.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name="removetagalias")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def removetagalias(self, ctx, alias: str):
        """Remove a alias from a tag"""

        flow = Flow(self.bot, ctx)

        tag = await self.resolve_tag_name(alias.lower(), ctx.guild)

        if tag is None:
            return await ctx.send(f":x: This guild has no tag with the associated alias `{alias}`!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the alias "
                                      f"`{config.BOT_PREFIX}{alias}` from `{config.BOT_PREFIX}{tag['name']}`?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("DELETE FROM guild_tags_alias WHERE alias = $1 AND guild_tag_id = $2",
                                                  alias.lower(), tag['id'])
                        await ctx.send(f":white_check_mark: Successfully removed the alias "
                                       f"`{config.BOT_PREFIX}{alias}` from `{config.BOT_PREFIX}{tag['name']}`.")
                    except Exception:
                        await ctx.send(f":x: Unexpected error occurred.")
                        raise

    async def resolve_tag_name(self, query: str, guild: discord.Guild):

        tag_id = await self.bot.db.fetchval("SELECT guild_tag_id FROM guild_tags_alias WHERE alias = $1", query.lower())

        if tag_id is None:
            return None

        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1 AND guild_id = $2", tag_id,
                                                 guild.id)

        return tag_details

    @commands.command(name="addtag")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def addtag(self, ctx):
        """Add a tag for this guild"""

        flow = Flow(self.bot, ctx)

        await ctx.send(":information_source: Reply with the name of the tag. This will be used to access the"
                       " tag via the bot's prefix.")

        name = await flow.get_text_input(300)

        if name is None:
            return

        await ctx.send(":information_source: Reply with the full title of the tag.")

        title = await flow.get_text_input(300)

        if title is None:
            return

        await ctx.send(":information_source: Reply with the content of the tag.")

        content = await flow.get_text_input(300)

        if content is None:
            return

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to add the tag "
                                      f"`{config.BOT_PREFIX}{name}`?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("INSERT INTO guild_tags (guild_id, name, content, title) VALUES "
                                                  "($1, $2, $3, $4)",
                                                  ctx.guild.id, name.lower(), content, title)
                        _id = await self.bot.db.fetchval("SELECT id FROM guild_tags WHERE name = $1 AND guild_id "
                                                         "= $2 AND "
                                                         "content = $3", name.lower(), ctx.guild.id, content)
                        await self.bot.db.execute("INSERT INTO guild_tags_alias (guild_tag_id, alias) VALUES ($1, $2)",
                                                  _id, name.lower())
                        await ctx.send(f":white_check_mark: Successfully added `{config.BOT_PREFIX}{name}`!")
                    except Exception:
                        await ctx.send(f":x: Unexpected error occurred.")
                        raise

    @commands.command(name="removetag", aliases=['deletetag'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def removetag(self, ctx, name: str):
        """Remove a tag"""

        flow = Flow(self.bot, ctx)

        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2", name.lower(),
                                         ctx.guild.id)

        if tag is None:
            return await ctx.send(f":x: This guild has no tag called `{name}`!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the tag "
                                      f"`{config.BOT_PREFIX}{tag['name']}`?")

        reaction, user = await flow.yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if str(reaction.emoji) == "\U0000274c":
            return await ctx.send("Aborted.")

        elif str(reaction.emoji) == "\U00002705":
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("DELETE FROM guild_tags_alias WHERE guild_tag_id = $1", tag['id'])
                        await self.bot.db.execute("DELETE FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                  name.lower(), ctx.guild.id)
                        await ctx.send(f":white_check_mark: Successfully removed `{config.BOT_PREFIX}{name}`!")
                    except Exception:
                        await ctx.send(f":x: Unexpected error occurred.")
                        raise

    @commands.Cog.listener(name="on_message")
    async def guild_tags_listener(self, message):
        if message.author.bot:
            return

        if (await self.bot.get_context(message)).valid:
            return

        if message.guild is None:
            return

        if not message.content.startswith(config.BOT_PREFIX):
            return

        tag_details = await self.resolve_tag_name(message.content[len(config.BOT_PREFIX):], message.guild)

        if tag_details is None:
            return

        embed = self.bot.embeds.embed_builder(title=tag_details['title'], description=tag_details['content'],
                                              has_footer=False)
        await message.channel.send(embed=embed)


def setup(bot):
    bot.add_cog(Guild(bot))
