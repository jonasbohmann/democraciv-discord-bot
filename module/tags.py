import re
import discord

import util.utils as utils

from config import config
from util import mk
from util.flow import Flow
from discord.ext import commands

from util.paginator import Pages


class Tags(commands.Cog):
    """Create tags for later retrieval of text, images & links and access them with just the bot's prefix"""

    def __init__(self, bot):
        self.bot = bot

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
                embed.set_thumbnail(url=member.avatar_url_as(static_format="png"))

        embed.add_field(name="Global Tag", value=str(tag['global']), inline=True)
        embed.add_field(name="Emoji or Media Tag", value=str(self.is_emoji_or_media_url(tag['content'])),
                        inline=True)
        embed.add_field(name="Uses", value=str(tag['uses']), inline=False)
        embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
        await ctx.send(embed=embed)

    @tags.command(name="edit")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def edittag(self, ctx, name: str):
        """Edit one of your tags"""

        flow = Flow(self.bot, ctx)

        # Search for global tags first
        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND global = true",
                                         name.lower())

        if tag is None:
            # If no global tag exists with that name, search for local tags
            tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2", name.lower(),
                                             ctx.guild.id)
            if tag is None:
                return await ctx.send(f":x: This guild has no tag called `{name}`!")

        if tag['author'] is not None:  # Handle tags before author column existed
            if tag['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
                return await ctx.send(f":x: This isn't your tag!")

        await ctx.send(":information_source: Reply with the updated content of the tag.")

        new_content = await flow.get_text_input(300)

        if new_content is None:
            return

        await self.bot.db.execute("UPDATE guild_tags SET content = $1 WHERE id = $2", new_content, tag['id'])
        await ctx.send(":white_check_mark: Your tag was edited.")

    @tags.command(name="toggleglobal")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.is_democraciv_guild()
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def toggleglobal(self, ctx, name: str):
        """Change a tag to be global/local"""

        # Search for global tags first
        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND global = true",
                                         name.lower())

        if tag is None:
            # Local -> Global
            tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2", name.lower(),
                                             ctx.guild.id)
            if tag is None:
                return await ctx.send(f":x: There is no global or local tag named `{name}`!")

            await self.bot.db.execute("UPDATE guild_tags SET global = true WHERE id = $1", tag['id'])
            await ctx.send(f":white_check_mark: `{name}` is now a global tag. ")

        else:
            # Global -> Local
            await self.bot.db.execute("UPDATE guild_tags SET global = false WHERE id = $1", tag['id'])
            await ctx.send(f":white_check_mark: `{name}` is now a local tag.")

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
    bot.add_cog(Tags(bot))
