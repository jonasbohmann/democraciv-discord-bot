import re
import discord

import util.utils as utils
import util.exceptions as exceptions

from config import config
from util.flow import Flow
from util.paginator import Pages
from discord.ext import commands


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
        current_welcome_channel = await utils.get_welcome_channel(self.bot, ctx.guild)
        current_welcome_message = await self.bot.db.fetchval("SELECT welcome_message FROM guilds WHERE id = $1",
                                                             ctx.guild.id)

        if current_welcome_channel is None:
            current_welcome_channel = "This guild currently has no welcome channel."
        else:
            current_welcome_channel = current_welcome_channel.mention

        if not current_welcome_message:
            current_welcome_message = "This guild currently has no welcome message."

        embed = self.bot.embeds.embed_builder(title=f":wave: Welcome Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change "
                                                          "the settings of this module.")
        embed.add_field(name="Enabled", value=str(is_welcome_enabled))
        embed.add_field(name="Channel", value=current_welcome_channel)
        embed.add_field(name="Message", value=current_welcome_message, inline=False)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):
            status_question = await ctx.send(
                "React with :white_check_mark: to enable the welcome module, or with :x: to disable the welcome module.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
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

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET welcome = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the welcome module.")

    @guild.command(name='logs')
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx):
        """Configure the logging module that logs every guild event to a specified channel"""

        is_logging_enabled = await self.bot.db.fetchval("SELECT logging FROM guilds WHERE id = $1", ctx.guild.id)

        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            current_logging_channel = "This guild currently has no logging channel."
        else:
            current_logging_channel = current_logging_channel.mention

        embed = self.bot.embeds.embed_builder(title=f":spy: Logging Module for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the "
                                                          "settings of this module.")

        embed.add_field(name="Enabled", value=str(is_logging_enabled))
        embed.add_field(name="Channel", value=current_logging_channel)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the logging module, or with :x: to disable the logging module.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
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

            elif not reaction:
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
        current_logging_channel = await utils.get_logging_channel(self.bot, ctx.guild)

        if current_logging_channel is None:
            return await ctx.send(":x: This guild currently has no logging channel. Please set one with `-guild logs`.")

        help_description = "Add/Remove a channel to the excluded channels with:\n`-guild exclude [channel_name]`\n"

        excluded_channels = await self.bot.db.fetchval("SELECT logging_excluded FROM guilds WHERE id = $1",
                                                       ctx.guild.id)
        if not channel:
            current_excluded_channels_by_name = ""

            if excluded_channels is None:
                return await ctx.send("There are no from logging excluded channels on this guild.")

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
                    return await ctx.send(f":white_check_mark: {channel_object.mention} is no longer excluded from"
                                          f" showing up in {current_logging_channel.mention}!")

                else:
                    return await ctx.send(f":x: Unexpected error occurred.")

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

        current_default_role = await self.bot.db.fetchval("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                          ctx.guild.id)

        current_default_role = ctx.guild.get_role(current_default_role)

        if current_default_role is None:
            current_default_role = "This guild currently has no default role."
        else:
            current_default_role = current_default_role.mention

        embed = self.bot.embeds.embed_builder(title=f":partying_face: Default Role for {ctx.guild.name}",
                                              description="React with the :gear: emoji to change the settings"
                                                          " of this module.")
        embed.add_field(name="Enabled", value=str(is_default_role_enabled))
        embed.add_field(name="Role", value=current_default_role)

        info_embed = await ctx.send(embed=embed)

        flow = Flow(self.bot, ctx)

        if await flow.gear_reaction_confirm(info_embed, 300):

            status_question = await ctx.send(
                "React with :white_check_mark: to enable the default role, or with :x: to disable the default role.")

            reaction = await flow.get_yes_no_reaction_confirm(status_question, 240)

            if reaction is None:
                return

            if reaction:
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

            elif not reaction:
                await self.bot.db.execute("UPDATE guilds SET defaultrole = false WHERE id = $1", ctx.guild.id)
                await ctx.send(":white_check_mark: Disabled the default role.")

    @commands.command(name='invite')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this guild"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)

    @commands.group(name="tags", aliases=['tag'], invoke_without_command=True, case_insensitive=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def tags(self, ctx):
        """See all tags on this guild"""

        global_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE global = true")
        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 AND global = false",
                                           ctx.guild.id)

        pretty_tags = []

        if global_tags:
            pretty_tags = ['**Global Tags**']

        for record in global_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if all_tags:
            pretty_tags.append('\n**Local Tags**')

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if len(pretty_tags) < 2:
            pretty_tags = ['There are no tags on this guild.']

        pages = Pages(ctx=ctx, entries=pretty_tags, show_entry_count=True, title=f"All Tags in {ctx.guild.name}"
                      , show_index=False, footer_text=config.BOT_NAME)
        await pages.paginate()

    @tags.command(name="addalias")
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

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send(":x: Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    status = await self.bot.db.execute("INSERT INTO guild_tags_alias (alias, tag_id, guild_id) VALUES "
                                                       "($1, $2, $3)", alias.lower(), tag_details['id'], ctx.guild.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Added the alias `{config.BOT_PREFIX}{alias}` to'
                           f'`{config.BOT_PREFIX}{tag_details["name"]}`.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @tags.command(name="removealias", aliases=['deletealias'])
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

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("DELETE FROM guild_tags_alias WHERE alias = $1 AND tag_id = $2",
                                                  alias.lower(), tag['id'])
                        await ctx.send(f":white_check_mark: Successfully removed the alias "
                                       f"`{config.BOT_PREFIX}{alias}` from `{config.BOT_PREFIX}{tag['name']}`.")
                    except Exception:
                        raise

    async def resolve_tag_name(self, query: str, guild: discord.Guild):
        tag_id = await self.bot.db.fetchval("SELECT id FROM guild_tags WHERE global = true AND name = $1",
                                            query.lower())

        if tag_id is None:
            tag_id = await self.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE alias = $1 AND guild_id = $2",
                query.lower(), guild.id)

        if tag_id is None:
            return None

        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        await self.bot.db.execute("UPDATE guild_tags SET uses = uses + 1 WHERE id = $1", tag_id)

        return tag_details

    async def validate_tag_name(self, ctx, tag_name: str) -> bool:
        tag_name = tag_name.lower()

        all_cmds = list(self.bot.commands)
        aliases = []

        for command in self.bot.commands:
            if isinstance(command, commands.Group):
                for c in command.commands:
                    all_cmds.append(c)
                    aliases.append(c.aliases)
            aliases.append(command.aliases)

        qualified_command_names = [c.qualified_name for c in all_cmds]

        if tag_name in qualified_command_names or any(tag_name in a for a in aliases):
            await ctx.send(":x: You can't create a tag with the same name of one of my commands!")
            return False

        global_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE global = true AND name = $1", tag_name)

        if len(global_tags) > 0:
            await ctx.send(":x: A global tag with that name already exists!")
            return False

        found_tag = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 AND name = $2",
                                            ctx.guild.id, tag_name)

        if len(found_tag) > 0:
            await ctx.send(":x: A tag with that name already exists on this guild!")
            return False

        return True

    @tags.command(name="add", aliases=['make'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def addtag(self, ctx):
        """Add a tag for this guild"""

        flow = Flow(self.bot, ctx)

        await ctx.send(":information_source: Reply with the name of the tag. This will be used to access the"
                       " tag via the bot's prefix.")

        name = await flow.get_text_input(300)

        if name is None:
            return

        if not await self.validate_tag_name(ctx, name.lower()):
            return

        await ctx.send(":information_source: Reply with the full title of the tag.")

        title = await flow.get_text_input(300)

        if title is None:
            return

        await ctx.send(":information_source: Reply with the content of the tag.")

        content = await flow.get_text_input(300)

        if content is None:
            return

        is_global = False

        if ctx.author.guild_permissions.administrator and ctx.guild.id == self.bot.democraciv_guild_object.id:
            is_global_msg = await ctx.send(":information_source: Should this tag be global?")

            reaction = await flow.get_yes_no_reaction_confirm(is_global_msg, 300)

            if reaction is None:
                return

            if reaction:
                is_global = False

            elif not reaction:
                is_global = True

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to add the tag "
                                      f"`{config.BOT_PREFIX}{name}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        _id = await self.bot.db.fetchval("INSERT INTO guild_tags (guild_id, name, content, title,"
                                                         " global, author) VALUES "
                                                         "($1, $2, $3, $4, $5, $6) RETURNING id",
                                                         ctx.guild.id, name.lower(), content, title, is_global,
                                                         ctx.author.id)
                        await self.bot.db.execute("INSERT INTO guild_tags_alias (tag_id, alias, guild_id) VALUES"
                                                  " ($1, $2, $3)", _id, name.lower(), ctx.guild.id)
                        await ctx.send(f":white_check_mark: The `{config.BOT_PREFIX}{name}` tag was added.")
                    except Exception:
                        raise

    @commands.command(name="addtag", hidden=True)
    async def oldaddtagwarning(self, ctx):
        await ctx.send("This was moved to `-tag add` :)\nTag creators can now remove their own "
                       "tags with `-tag remove <tagname>` and "
                       "`-tag info <tagname>` is new too! :)\nSee `-help tag` for more info.")

    @tags.command(name="info", aliases=['about'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def taginfo(self, ctx, name: str):
        """Info about a tag"""

        # Search for global tags first
        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND global = true",
                                         name.lower())

        if tag is None:
            # If no global tag exists with that name, search for local tags
            tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2", name.lower(),
                                             ctx.guild.id)
            if tag is None:
                return await ctx.send(f":x: This guild has no tag called `{name}`!")

        aliases = await self.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1 ", tag['id'])

        pretty_aliases = (', '.join([f"`{ctx.prefix}{record['alias']}`" for record in aliases])) or 'None'

        embed = self.bot.embeds.embed_builder(title="Tag Info", description="")
        embed.add_field(name="Name", value=tag['title'], inline=False)

        if tag['author'] is not None:
            member = self.bot.get_user(tag['author'])
            if member is not None:
                embed.add_field(name="Author", value=member.mention, inline=False)
                embed.set_thumbnail(url=member.avatar_url)

        embed.add_field(name="Global Tag", value=str(tag['global']), inline=True)
        embed.add_field(name="Emoji or Media Tag", value=str(self.is_emoji_or_media_url(tag['content'])),
                        inline=True)
        embed.add_field(name="Uses", value=str(tag['uses']), inline=False)
        embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
        await ctx.send(embed=embed)

    @tags.command(name="remove", aliases=['delete'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def removetag(self, ctx, name: str):
        """Remove a tag"""

        flow = Flow(self.bot, ctx)

        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2", name.lower(),
                                         ctx.guild.id)

        if tag is None:
            return await ctx.send(f":x: This guild has no tag called `{name}`!")

        if tag['author'] is not None:  # Handle tags before author column existed
            if tag['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
                return await ctx.send(f":x: This isn't your tag!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the tag "
                                      f"`{config.BOT_PREFIX}{tag['name']}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("DELETE FROM guild_tags_alias WHERE tag_id = $1", tag['id'])
                        await self.bot.db.execute("DELETE FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                  name.lower(), ctx.guild.id)
                        await ctx.send(f":white_check_mark: `{config.BOT_PREFIX}{name}` was removed.")
                    except Exception:
                        raise

    @staticmethod
    def is_emoji_or_media_url(tag_content: str) -> bool:
        emoji_pattern = re.compile("<(?P<animated>a)?:(?P<name>[0-9a-zA-Z_]{2,32}):(?P<id>[0-9]{15,21})>")
        discord_invite_pattern = re.compile("(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")

        url_pattern = re.compile(
            "((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*")
        url_endings = ('.jpeg', '.jpg', '.avi', '.png', '.gif', '.webp', '.mp4', '.mp3', '.bmp', '.img',
                       '.svg', '.mov', '.flv', '.wmv')

        if url_pattern.match(tag_content) and (tag_content.endswith(url_endings) or any(s in tag_content for
                                                                                        s in ['youtube', 'youtu.be'])):
            return True

        elif emoji_pattern.match(tag_content):
            return True

        elif discord_invite_pattern.match(tag_content):
            return True

        return False

    @commands.Cog.listener(name="on_message")
    async def guild_tags_listener(self, message):
        if not message.content.startswith(config.BOT_PREFIX):
            return

        if message.author.bot:
            return

        if message.guild is None:
            return

        if (await self.bot.get_context(message)).valid:
            return

        tag_details = await self.resolve_tag_name(message.content[len(config.BOT_PREFIX):], message.guild)

        if tag_details is None:
            return

        if self.is_emoji_or_media_url(tag_details['content']):
            return await message.channel.send(discord.utils.escape_mentions(tag_details['content']))

        embed = self.bot.embeds.embed_builder(title=tag_details['title'], description=tag_details['content'],
                                              has_footer=False)
        await message.channel.send(embed=embed)


def setup(bot):
    bot.add_cog(Guild(bot))
