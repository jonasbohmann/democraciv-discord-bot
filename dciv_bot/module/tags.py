import re
import enum
import typing
import discord

import dciv_bot.util.utils as utils

from dciv_bot.util import mk
from dciv_bot.config import config
from dciv_bot.util.flow import Flow
from discord.ext import commands
from dciv_bot.util.paginator import AlternativePages
from dciv_bot.util.converter import Tag, OwnedTag, CaseInsensitiveMember


class TagContentType(enum.Enum):
    TEXT = 1
    IMAGE = 2
    INVITE = 3
    CUSTOM_EMOJI = 4
    YOUTUBE_TENOR_GIPHY = 5
    VIDEO = 6
    PARTIAL_IMAGE = 7


class Tags(commands.Cog):
    """Create tags for later retrieval of text, images & links. Tags are accessed with the bot's prefix. Server administrators can change who is allowed to create tags on their server with `-server tagcreation`."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="tag", aliases=['tags', 't'], invoke_without_command=True, case_insensitive=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def tags(self, ctx):
        """List all tags on this server"""

        global_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE global = true ORDER BY uses desc")
        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 AND global = false"
                                           " ORDER BY uses desc",
                                           ctx.guild.id)

        pretty_tags = []

        if global_tags:
            pretty_tags = ['**__Global Tags__**']

        for record in global_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if all_tags:
            pretty_tags.append('\n\n**__Local Tags__**')

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if len(pretty_tags) < 2:
            embed = self.bot.embeds.embed_builder(title="There are no tags on this server.",
                                                  description="",
                                                  has_footer=False)
            return await ctx.send(embed=embed)

        pages = AlternativePages(ctx=ctx, entries=pretty_tags, show_entry_count=True,
                                 a_title=f"All Tags in {ctx.guild.name}",
                                 a_icon=ctx.guild.icon_url_as(static_format='png'),
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @tags.command(name="local", aliases=['l'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def local(self, ctx):
        """List all non-global tags on this server"""

        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE guild_id = $1 AND global = false "
                                           "ORDER BY uses desc", ctx.guild.id)

        if not all_tags:
            embed = self.bot.embeds.embed_builder(title="There are no local tags on this server.",
                                                  description="",
                                                  has_footer=False)
            return await ctx.send(embed=embed)

        pretty_tags = []

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        pages = AlternativePages(ctx=ctx, entries=pretty_tags, show_entry_count=True,
                                 a_title=f"Local Tags in {ctx.guild.name}",
                                 a_icon=ctx.guild.icon_url_as(static_format='png'),
                                 show_index=False, show_amount_of_pages=True)
        await pages.paginate()

    @tags.command(name="from", aliases=['by'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def _from(self, ctx, *, member: typing.Union[discord.Member, CaseInsensitiveMember, discord.User] = None):
        """List the tags that someone made"""

        member = member or ctx.author

        all_tags = await self.bot.db.fetch("SELECT * FROM guild_tags WHERE author = $1 AND guild_id = $2"
                                           " ORDER BY uses desc",
                                           member.id, ctx.guild.id)

        if not all_tags:
            embed = self.bot.embeds.embed_builder(title=f"{member} hasn't made any tags on this server yet.",
                                                  description="",
                                                  has_footer=False)
            return await ctx.send(embed=embed)

        pretty_tags = []

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        pages = AlternativePages(ctx=ctx, entries=pretty_tags, show_entry_count=True,
                                 a_title=f"Tags from {member.display_name}",
                                 show_index=False, show_amount_of_pages=True,
                                 a_icon=member.avatar_url_as(static_format="png"))
        await pages.paginate()

    @tags.command(name="addalias")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def addtagalias(self, ctx, *, tag: OwnedTag):
        """Add a new alias to a tag"""

        flow = Flow(self.bot, ctx)

        await ctx.send(f":information_source: Reply with the new alias for `{config.BOT_PREFIX}{tag.name}`.")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        if not await self.validate_tag_name(ctx, alias.lower()):
            return

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to add the "
                                      f"`{config.BOT_PREFIX}{alias}` alias to `{config.BOT_PREFIX}{tag.name}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    status = await con.execute("INSERT INTO guild_tags_alias (alias, tag_id, guild_id, global)"
                                               " VALUES ($1, $2, $3, $4)", alias.lower(), tag.id,
                                               ctx.guild.id, tag.is_global)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: The `{config.BOT_PREFIX}{alias}` alias was added to '
                           f'`{config.BOT_PREFIX}{tag.name}`.')

    @tags.command(name="removealias", aliases=['deletealias', 'ra', 'da'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def removetagalias(self, ctx, *, alias: OwnedTag):
        """Remove an alias from a tag"""

        flow = Flow(self.bot, ctx)

        if alias.invoked_with == alias.name:
            return await ctx.send(f":x: That is not an alias, but the tag's name. "
                                  f"Try {config.BOT_PREFIX}tag delete {alias.invoked_with} instead!")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the alias "
                                      f"`{config.BOT_PREFIX}{alias.invoked_with}` "
                                      f"from `{config.BOT_PREFIX}{alias.name}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    await con.execute("DELETE FROM guild_tags_alias WHERE alias = $1 AND tag_id = $2",
                                      alias.invoked_with, alias.id)
                    await ctx.send(f":white_check_mark: Successfully removed the alias "
                                   f"`{config.BOT_PREFIX}{alias.invoked_with}` from "
                                   f"`{config.BOT_PREFIX}{alias.name}`.")

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
            await ctx.send(":x: A tag or alias with that name already exists on this server.")
            return False

        if len(tag_name) > 50:
            await ctx.send(":x: The name cannot be longer than 50 characters.")
            return False

        return True

    @tags.command(name="add", aliases=['make', 'create', 'a'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def addtag(self, ctx):
        """Add a tag for this server"""

        flow = Flow(self.bot, ctx)

        await ctx.send(":information_source: Reply with the **name** of the tag. This will be used to access the"
                       " tag via the bot's prefix.")

        name = await flow.get_text_input(300)

        if name is None:
            return

        if not await self.validate_tag_name(ctx, name.lower()):
            return

        embed_q = await ctx.send(":information_source: Should the tag be sent as an embed?")

        embed_bool = await flow.get_yes_no_reaction_confirm(embed_q, 300)

        if embed_bool is None:
            return

        if embed_bool:
            is_embedded = True
        else:
            is_embedded = False

        await ctx.send(":information_source: Reply with the **title** of the tag.")
        title = await flow.get_text_input(300)

        if title is None:
            return

        if len(title) > 256:
            return await ctx.send(":x: The title cannot be longer than 256 characters.")

        await ctx.send(":information_source: Reply with the **content** of the tag.")
        content = await flow.get_tag_content(300)

        if content is None:
            return

        if len(content) > 2048:
            return await ctx.send(":x: The content cannot be longer than 2048 characters.")

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
                    _id = await con.fetchval("INSERT INTO guild_tags (guild_id, name, content, title,"
                                             " global, author, is_embedded) VALUES "
                                             "($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                                             ctx.guild.id, name.lower(), content, title, is_global,
                                             ctx.author.id, is_embedded)
                    await con.execute("INSERT INTO guild_tags_alias (tag_id, alias, guild_id, global)"
                                      " VALUES ($1, $2, $3, $4)", _id, name.lower(),
                                      ctx.guild.id, is_global)
                    await ctx.send(f":white_check_mark: The `{config.BOT_PREFIX}{name}` tag was added.")

    @tags.command(name="info", aliases=['about', 'i'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def taginfo(self, ctx, *, tag: Tag):
        """Info about a tag"""

        pretty_aliases = (', '.join([f"`{config.BOT_PREFIX}{alias}`" for alias in tag.aliases])) or 'None'

        embed = self.bot.embeds.embed_builder(title="Tag Information", description="", has_footer=False)
        embed.add_field(name="Title", value=tag.title, inline=False)

        is_global = "Yes" if tag.is_global else "No"
        is_embedded = "Yes" if tag.is_embedded else "No"

        if isinstance(tag.author, discord.Member):
            embed.add_field(name="Author", value=tag.author.mention, inline=False)
            embed.set_author(name=tag.author.name, icon_url=tag.author.avatar_url_as(static_format="png"))

        elif isinstance(tag.author, discord.User):
            embed.add_field(name="Author", value=f"*The author of this tag left this server.*\n"
                                                 f"*You can claim this tag to make it yours with*\n"
                                                 f"`{config.BOT_PREFIX}tag claim {tag.name}`", inline=False)
            embed.set_author(name=tag.author.name, icon_url=tag.author.avatar_url_as(static_format="png"))

        elif tag.author is None:
            embed.add_field(name="Author", value=f"*The author of this tag left this server.*\n"
                                                 f"*You can claim this tag to make it yours with*\n"
                                                 f"`{config.BOT_PREFIX}tag claim {tag.name}`", inline=False)

        embed.add_field(name="Global Tag", value=is_global, inline=True)
        embed.add_field(name="Embedded Tag", value=is_embedded, inline=True)
        embed.add_field(name="Uses", value=str(tag.uses), inline=False)
        embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
        await ctx.send(embed=embed)

    @tags.command(name="claim")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def claim(self, ctx, *, tag: Tag):
        """Claim a tag if the original tag author left this server"""

        if tag.is_global:
            return await ctx.send(":x: Global tags cannot be claimed.")

        if tag.author == ctx.author:
            return await ctx.send(":x: You already own this tag.")

        if isinstance(tag.author, discord.Member):
            return await ctx.send(":x: The owner of this tag is still in this server.")

        await self.bot.db.execute("UPDATE guild_tags SET author = $1 WHERE id = $2", ctx.author.id, tag.id)

        return await ctx.send(f":white_check_mark: You are now the owner `{config.BOT_PREFIX}{tag.name}`.")

    @tags.command(name="transfer")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def transfer(self, ctx, to_person: typing.Union[discord.Member, CaseInsensitiveMember, discord.User], *,
                       tag: OwnedTag):
        """Transfer a tag of yours to someone else"""

        if to_person == ctx.author:
            return await ctx.send(":x: You cannot transfer your tag to yourself.")

        await self.bot.db.execute("UPDATE guild_tags SET author = $1 WHERE id = $2", to_person.id, tag.id)

        return await ctx.send(f":white_check_mark: {to_person} is now the owner of `{config.BOT_PREFIX}{tag.name}`.")

    @tags.command(name="raw")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def raw(self, ctx, *, tag: Tag):
        """Raw markdown of a tag

        Useful when you want to update a tag with -tag edit
        """
        return await ctx.send(f"```{tag.content}```")

    @tags.command(name="edit")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def edittag(self, ctx, *, tag: OwnedTag):
        """Edit one of your tags"""

        flow = Flow(self.bot, ctx)

        embed_q = await ctx.send(":information_source: Should the tag be sent as an embed?")

        embed_bool = await flow.get_yes_no_reaction_confirm(embed_q, 300)

        if embed_bool is None:
            return

        if embed_bool:
            is_embedded = True
        else:
            is_embedded = False

        await ctx.send(":information_source: Reply with the updated **title** of this tag.")
        new_title = await flow.get_text_input(300)

        if new_title is None:
            return

        if len(new_title) > 256:
            return await ctx.send(":x: The title cannot be longer than 256 characters.")

        await ctx.send(":information_source: Reply with the updated **content** of this tag.")
        new_content = await flow.get_tag_content(300)

        if new_content is None:
            return

        if len(new_content) > 2048:
            return await ctx.send(":x: The content cannot be longer than 2048 characters.")

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to edit your "
                                      f"`{config.BOT_PREFIX}{tag.name}` tag?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        else:
            await self.bot.db.execute("UPDATE guild_tags SET content = $1, title = $3, is_embedded = $4 WHERE id = $2",
                                      new_content, tag.id, new_title, is_embedded)
            await ctx.send(":white_check_mark: Your tag was edited.")

    @tags.command(name="search", aliases=['s'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    async def search(self, ctx, *, query: str):
        """Search for a global or local tag on this server"""

        db_query = """SELECT tag_id FROM guild_tags_alias
                      WHERE (global = true AND alias LIKE '%' || $1 || '%') OR 
                            (alias LIKE '%' || $1 || '%' AND guild_id = $2)
                      ORDER BY similarity(alias, $1) DESC
                      LIMIT 20
                    """

        tags = await self.bot.db.fetch(db_query, query.lower(), ctx.guild.id)
        pretty_names = dict()  # Abuse dict as ordered set since you can't use DISTINCT in above SQL query

        if not tags:
            pretty_names['Nothing found.'] = None

        else:
            for record in tags:
                details = await self.bot.db.fetchrow("SELECT name, title from guild_tags WHERE id = $1",
                                                     record['tag_id'])
                if details:
                    pretty_names[f"`{config.BOT_PREFIX}{details['name']}`  {details['title']}"] = None

        pages = AlternativePages(ctx=ctx, entries=list(pretty_names), show_entry_count=False,
                                 a_title=f"Tags matching '{query}'",
                                 a_icon=ctx.guild.icon_url_as(static_format='png'),
                                 show_index=False, show_amount_of_pages=True)

        await pages.paginate()

    @tags.command(name="toggleglobal")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def toggleglobal(self, ctx, *, tag: Tag):
        """Change a tag to be global/local"""

        if not tag.is_global:
            # Local -> Global
            await self.bot.db.execute("UPDATE guild_tags SET global = true WHERE id = $1", tag.id)
            await self.bot.db.execute("UPDATE guild_tags_alias SET global = true WHERE tag_id = $1", tag.id)
            await ctx.send(f":white_check_mark: `{config.BOT_PREFIX}{tag.name}` is now a global tag. ")

        else:
            # Global -> Local
            await self.bot.db.execute("UPDATE guild_tags SET global = false WHERE id = $1", tag.id)
            await self.bot.db.execute("UPDATE guild_tags_alias SET global = false WHERE tag_id = $1", tag.id)
            await ctx.send(f":white_check_mark: `{config.BOT_PREFIX}{tag.name}` is now a local tag.")

    @tags.command(name="remove", aliases=['delete'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.guild_only()
    @utils.tag_check()
    async def removetag(self, ctx, *, tag: OwnedTag):
        """Remove a tag"""

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to remove the tag "
                                      f"`{config.BOT_PREFIX}{tag.name}`?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with self.bot.db.acquire() as con:
                async with con.transaction():
                    await con.execute("DELETE FROM guild_tags_alias WHERE tag_id = $1", tag.id)
                    await con.execute("DELETE FROM guild_tags WHERE name = $1 AND guild_id = $2",
                                      tag.name, ctx.guild.id)
                    await ctx.send(f":white_check_mark: `{config.BOT_PREFIX}{tag.name}` was removed.")

    @staticmethod
    def get_tag_content_type(tag_content: str) -> TagContentType:
        emoji_pattern = re.compile(r"<(?P<animated>a)?:(?P<name>[0-9a-zA-Z_]{2,32}):(?P<id>[0-9]{15,21})>")
        discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
        url_pattern = re.compile(
            r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*")

        url_endings_image = ('.jpeg', '.jpg', '.png', '.gif', '.webp', '.bmp', '.img', '.svg')
        url_endings_video = ('.avi', '.mp4', '.mp3', '.mov', '.flv', '.wmv')

        if url_pattern.fullmatch(tag_content) and (tag_content.lower().endswith(url_endings_image)):
            return TagContentType.IMAGE

        elif url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_image)):
            return TagContentType.PARTIAL_IMAGE

        elif url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_video)):
            return TagContentType.VIDEO

        elif any(s in tag_content for s in ['youtube', 'youtu.be', 'tenor.com', 'gph.is', 'giphy.com']):
            return TagContentType.YOUTUBE_TENOR_GIPHY

        elif emoji_pattern.fullmatch(tag_content):
            return TagContentType.CUSTOM_EMOJI

        elif discord_invite_pattern.match(tag_content):
            return TagContentType.INVITE

        return TagContentType.TEXT

    async def resolve_tag_name(self, query: str, guild: discord.Guild):
        tag_id = await self.bot.db.fetchval("SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
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

    async def send_tag(self, message):
        """If the tag exists, the contents are sent. If the tag is exists returns True, otherwise returns False."""
        if not message.content.startswith(config.BOT_PREFIX):
            return False

        if message.author.bot:
            return False

        if (await self.bot.get_context(message)).valid:
            return False

        tag_name = message.content[len(config.BOT_PREFIX):]

        if message.guild is None:
            tag_id = await self.bot.db.fetchval(
                "SELECT tag_id FROM guild_tags_alias WHERE global = true AND alias = $1",
                tag_name.lower())

            if tag_id is None:
                return False

            tag_details = await self.bot.db.fetchrow("SELECT * FROM guild_tags WHERE id = $1", tag_id)

        else:
            tag_details = await self.resolve_tag_name(tag_name, message.guild)

        if tag_details is None:
            return False

        tag_content_type = self.get_tag_content_type(tag_details['content'])

        if tag_details['is_embedded']:
            if tag_content_type is TagContentType.IMAGE:
                embed = discord.Embed(colour=0x2F3136)
                embed.set_image(url=tag_details['content'])

                try:
                    await message.channel.send(embed=embed)
                    return True
                except discord.HTTPException:
                    await message.channel.send(discord.utils.escape_mentions(tag_details['content']))
                    return True

            embed = self.bot.embeds.embed_builder(title=tag_details['title'], description=tag_details['content'],
                                                  has_footer=False)
            await message.channel.send(embed=embed)

        else:
            await message.channel.send(discord.utils.escape_mentions(tag_details['content']))
        
        return True


def setup(bot):
    bot.add_cog(Tags(bot))
