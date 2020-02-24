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

        global_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE global = true ORDER BY uses desc")
        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 AND global = false"
                                           " ORDER BY uses desc",
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

    @tags.command(name="local")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def local(self, ctx):
        """See just the local tags on this guild"""

        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 ORDER BY uses desc",
                                           ctx.guild.id)

        pretty_tags = ['\n**Local Tags**']

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if len(pretty_tags) < 2:
            pretty_tags = ['There are no local tags on this guild.']

        pages = Pages(ctx=ctx, entries=pretty_tags, show_entry_count=True, title=f"Local Tags in {ctx.guild.name}"
                      , show_index=False, footer_text=config.BOT_NAME)
        await pages.paginate()

    @tags.command(name="addalias")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def addtagalias(self, ctx, tag: str):
        """Add a new alias to a tag"""

        flow = Flow(self.bot, ctx)

        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                 tag.lower(), ctx.guild.id)

        if tag_details is None:
            return await ctx.send(f":x: This guild has no tag called `{tag.lower()}`!")

        await ctx.send(f":information_source: Reply with the new alias for `{config.BOT_PREFIX}{tag.lower()}`.")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        if not await self.validate_tag_name(ctx, alias.lower()):
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
                    status = await self.bot.db.execute("INSERT INTO guild_tags_alias (alias, tag_id, guild_id, global)"
                                                       " VALUES ($1, $2, $3, $4)", alias.lower(), tag_details['id'],
                                                       ctx.guild.id, tag_details['global'])

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
        """Remove an alias from a tag"""

        flow = Flow(self.bot, ctx)

        tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags_alias WHERE alias = $1 AND guild_id = $2",
                                         alias.lower(), ctx.guild.id)

        if tag is None:
            return await ctx.send(f":x: This guild has no tag with the associated alias `{alias}`!")

        guild_tag = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag['tag_id'])

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the alias "
                                      f"`{config.BOT_PREFIX}{alias}` from `{config.BOT_PREFIX}{guild_tag['name']}`?")

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
                                                  alias.lower(), guild_tag['id'])
                        await ctx.send(f":white_check_mark: Successfully removed the alias "
                                       f"`{config.BOT_PREFIX}{alias}` from `{config.BOT_PREFIX}{guild_tag['name']}`.")
                    except Exception:
                        raise

    async def resolve_tag_name(self, query: str, guild: discord.Guild, update_uses: bool = True):
        tag_id = await self.bot.db.fetchval("SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
                                            query.lower())

        if tag_id is None:
            tag_id = await self.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE alias = $1 AND guild_id = $2",
                query.lower(), guild.id)

        if tag_id is None:
            return None

        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        if update_uses:
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

        global_tags = await self.bot.db.fetch("SELECT * FROM guild_tags_alias WHERE global = true AND alias = $1",
                                              tag_name)

        if len(global_tags) > 0:
            await ctx.send(":x: A global tag with that name already exists!")
            return False

        found_alias = await self.bot.db.fetch("SELECT * FROM guild_tags_alias WHERE guild_id = $1 AND alias = $2",
                                              ctx.guild.id, tag_name)

        if len(found_alias) > 0:
            await ctx.send(":x: A tag or alias with that name already exists on this guild!")
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
                is_global = True

            elif not reaction:
                is_global = False

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
                        await self.bot.db.execute("INSERT INTO guild_tags_alias (tag_id, alias, guild_id, global)"
                                                  " VALUES ($1, $2, $3, $4)", _id, name.lower(),
                                                  ctx.guild.id, is_global)
                        await ctx.send(f":white_check_mark: The `{config.BOT_PREFIX}{name}` tag was added.")
                    except Exception:
                        raise

    @commands.command(name="addtag", hidden=True)
    async def oldaddtagwarning(self, ctx):
        await ctx.send("This was moved to `-tag add` :)\nTag creators can now remove their own "
                       "tags with `-tag remove <tagname>` and "
                       "`-tag info <tagname>` is new too! :)\nSee `-help Tag` for more info.")

    @tags.command(name="info", aliases=['about'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def taginfo(self, ctx, tag: str):
        """Info about a tag"""

        tag_details = await self.resolve_tag_name(tag, ctx.guild, update_uses=False)

        if tag_details is None:
            return await ctx.send(f":x: This guild has no tag called `{tag}`!")

        aliases = await self.bot.db.fetch("SELECT alias FROM guild_tags_alias WHERE tag_id = $1 ", tag_details['id'])

        pretty_aliases = (', '.join([f"`{ctx.prefix}{record['alias']}`" for record in aliases])) or 'None'

        embed = self.bot.embeds.embed_builder(title="Tag Info", description="")
        embed.add_field(name="Name", value=tag_details['title'], inline=False)

        if tag_details['author'] is not None:
            member = self.bot.get_user(tag_details['author'])
            if member is not None:
                embed.add_field(name="Author", value=member.mention, inline=False)
                embed.set_thumbnail(url=member.avatar_url_as(static_format="png"))

        embed.add_field(name="Global Tag", value=str(tag_details['global']), inline=True)
        embed.add_field(name="Emoji or Media Tag", value=str(self.is_emoji_or_media_url(tag_details['content'])),
                        inline=True)
        embed.add_field(name="Uses", value=str(tag_details['uses']), inline=False)
        embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
        await ctx.send(embed=embed)

    @tags.command(name="edit")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def edittag(self, ctx, tag: str):
        """Edit one of your tags"""

        flow = Flow(self.bot, ctx)

        tag_details = await self.resolve_tag_name(tag, ctx.guild, update_uses=False)

        if tag_details is None:
            return await ctx.send(f":x: This guild has no tag called `{tag}`!")

        if tag_details['global'] and tag_details['guild_id'] != ctx.guild.id:
            return await ctx.send(f":x: Global tags can only be edited on the guild they were originally created!")

        if tag_details['author'] is not None:  # Handle tags before author column existed
            if tag_details['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
                return await ctx.send(f":x: This isn't your tag!")

        await ctx.send(":information_source: Reply with the updated **title** of this tag.")
        new_title = await flow.get_text_input(300)

        if new_title is None:
            return

        await ctx.send(":information_source: Reply with the updated **content** of this tag.")
        new_content = await flow.get_text_input(300)

        if new_content is None:
            return

        await self.bot.db.execute("UPDATE guild_tags SET content = $1, title = $3 WHERE id = $2", new_content,
                                  tag_details['id'], new_title)
        await ctx.send(":white_check_mark: Your tag was edited.")

    @tags.command(name="toggleglobal")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.is_democraciv_guild()
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def toggleglobal(self, ctx, tag: str):
        """Change a tag to be global/local"""

        # Search for global tags first
        tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND global = true",
                                                 tag.lower())

        if tag_details is None:
            # Local -> Global
            tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                     tag.lower(), ctx.guild.id)
            if tag_details is None:
                return await ctx.send(f":x: There is no global or local tag named `{tag}`!")

            await self.bot.db.execute("UPDATE guild_tags SET global = true WHERE id = $1", tag_details['id'])
            await self.bot.db.execute("UPDATE guild_tags_alias SET global = true WHERE tag_id = $1", tag_details['id'])
            await ctx.send(f":white_check_mark: `{ctx.prefix}{tag}` is now a global tag. ")

        else:
            # Global -> Local
            await self.bot.db.execute("UPDATE guild_tags SET global = false WHERE id = $1", tag_details['id'])
            await self.bot.db.execute("UPDATE guild_tags_alias SET global = false WHERE tag_id = $1", tag_details['id'])
            await ctx.send(f":white_check_mark: `{ctx.prefix}{tag}` is now a local tag.")

    @tags.command(name="remove", aliases=['delete'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def removetag(self, ctx, tag: str):
        """Remove a tag"""

        flow = Flow(self.bot, ctx)

        tag_details = await self.resolve_tag_name(tag, ctx.guild, update_uses=False)

        if tag_details is None:
            return await ctx.send(f":x: This guild has no tag called `{tag}`!")

        if tag_details['global'] and tag_details['guild_id'] != ctx.guild.id:
            return await ctx.send(f":x: Global tags can only be edited on the guild they were originally created!")

        if tag_details['author'] is not None:  # Handle tags before author column existed
            if tag_details['author'] != ctx.author.id and not ctx.author.guild_permissions.administrator:
                return await ctx.send(f":x: This isn't your tag!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the tag "
                                      f"`{config.BOT_PREFIX}{tag_details['name']}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    try:
                        await self.bot.db.execute("DELETE FROM guild_tags_alias WHERE tag_id = $1", tag_details['id'])
                        await self.bot.db.execute("DELETE FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                                  tag.lower(), ctx.guild.id)
                        await ctx.send(f":white_check_mark: `{config.BOT_PREFIX}{tag}` was removed.")
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

        if (await self.bot.get_context(message)).valid:
            return

        tag_name = message.content[len(config.BOT_PREFIX):]

        if message.guild is None:
            tag_id = await self.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
                tag_name.lower())

            if tag_id is None:
                return

            tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        else:
            tag_details = await self.resolve_tag_name(tag_name, message.guild)

        if tag_details is None:
            return

        if self.is_emoji_or_media_url(tag_details['content']):
            return await message.channel.send(discord.utils.escape_mentions(tag_details['content']))

        embed = self.bot.embeds.embed_builder(title=tag_details['title'], description=tag_details['content'],
                                              has_footer=False)
        await message.channel.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
