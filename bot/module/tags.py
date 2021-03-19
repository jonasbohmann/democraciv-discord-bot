import re
import enum
import typing
import discord

from bot.config import config, mk
from discord.ext import commands
from bot.utils import context, checks
from bot.utils.converter import (
    Tag,
    OwnedTag,
    CaseInsensitiveMember,
    CaseInsensitiveUser,
    FuzzyCIMember,
)
from bot.utils import text, paginator, exceptions


class TagContentType(enum.Enum):
    TEXT = 1
    IMAGE = 2
    INVITE = 3
    CUSTOM_EMOJI = 4
    YOUTUBE_TENOR_GIPHY = 5
    VIDEO = 6
    PARTIAL_IMAGE = 7


class Tags(context.CustomCog):
    """Create tags for later retrieval of text, images & links. Tags are accessed with the bot's prefix."""

    def __init__(self, bot):
        super().__init__(bot)
        self.emoji_pattern = re.compile(r"<(?P<animated>a)?:(?P<name>[0-9a-zA-Z_]{2,32}):(?P<id>[0-9]{15,21})>")
        self.discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
        self.url_pattern = re.compile(
            r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
        )

    @commands.group(
        name="tag",
        aliases=["tags", "t"],
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def tags(self, ctx: context.CustomContext, *, tag: Tag = None):
        """Access a tag or list all tags on this server

        **Example**
            `{PREFIX}{COMMAND}` to get a list of all tags on this server
            `{PREFIX}{COMMAND} constitution` to see the {PREFIX}constitution tag"""

        if tag:
            tag_content_type = self.get_tag_content_type(tag.content)

            if tag.is_embedded:
                if tag_content_type is TagContentType.IMAGE:
                    embed = discord.Embed(title=tag.title, colour=0x2F3136)
                    embed.set_image(url=tag.content)

                    try:
                        return await ctx.send(embed=embed)
                    except discord.HTTPException:
                        return await ctx.send(tag.clean_content)
                elif tag_content_type is TagContentType.VIDEO:
                    # discord doesn't allow videos in embeds
                    return await ctx.send(tag.clean_content)

                embed = text.SafeEmbed(title=tag.title, description=tag.content)
                return await ctx.send(embed=embed)

            else:
                return await ctx.send(tag.clean_content)

        global_tags = await self.bot.db.fetch("SELECT * FROM tag WHERE global = true ORDER BY uses desc")
        pretty_tags = []

        if global_tags:
            pretty_tags = [
                f"**__Global Tags__**\n*Tags can only be made global by {self.bot.dciv.name} "
                f"Moderation and Nation Admins. Global tags work in every server I am in, as well as in DMs with me.*\n"
            ]

        for record in global_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        if ctx.guild:
            all_tags = await self.bot.db.fetch(
                "SELECT * FROM tag WHERE guild_id = $1 AND global = false" " ORDER BY uses desc",
                ctx.guild.id,
            )
            if all_tags:
                pretty_tags.append(
                    f"\n\n**__Local Tags__**\n*Every Tag that was not explicitly made global by "
                    f"{self.bot.dciv.name} Moderation or a Nation Admin is a local tag, "
                    f"and only works in the server it was made in.*\n"
                )

            for record in all_tags:
                pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

            author = f"All Tags in {ctx.guild.name}"
            icon = ctx.guild_icon
            empty_message = "There are no tags on this server."
        else:
            author = "All Global Tags"
            icon = self.bot.user.avatar_url_as(static_format="png")
            empty_message = "There are no global tags yet."

        if len(pretty_tags) < 2:
            pretty_tags = []

        pages = paginator.SimplePages(entries=pretty_tags, author=author, icon=icon, empty_message=empty_message)
        await pages.start(ctx)

    @tags.command(name="local", aliases=["l"])
    @commands.guild_only()
    async def local(self, ctx: context.CustomContext):
        """List all non-global tags on this server"""

        all_tags = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE guild_id = $1 AND global = false " "ORDER BY uses desc",
            ctx.guild.id,
        )
        pretty_tags = []

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        pages = paginator.SimplePages(
            entries=pretty_tags,
            author=f"Local Tags in {ctx.guild.name}",
            icon=ctx.guild_icon,
            empty_message="There are no local tags on this server.",
        )
        await pages.start(ctx)

    @tags.command(name="from", aliases=["by", "f"])
    @commands.guild_only()
    async def _from(
            self,
            ctx: context.CustomContext,
            *,
            member: typing.Union[CaseInsensitiveMember, CaseInsensitiveUser, FuzzyCIMember] = None,
    ):
        """List the tags that someone made"""

        member = member or ctx.author
        all_tags = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE author = $1 AND guild_id = $2 ORDER BY uses desc",
            member.id,
            ctx.guild.id,
        )

        pretty_tags = []

        for record in all_tags:
            pretty_tags.append(f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}")

        pages = paginator.SimplePages(
            entries=pretty_tags,
            author=f"Tags from {member.display_name}",
            icon=member.avatar_url_as(static_format="png"),
            empty_message=f"{member} hasn't made any tags on this server yet.",
        )
        await pages.start(ctx)

    @tags.command(name="addalias", aliases=['alias'])
    @commands.guild_only()
    @checks.tag_check()
    async def addtagalias(self, ctx: context.CustomContext, *, tag: OwnedTag):
        """Add a new alias to a tag"""

        alias = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the new alias for `{config.BOT_PREFIX}{tag.name}`."
        )

        if not await self.validate_tag_name(ctx, alias.lower()):
            return

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "INSERT INTO tag_lookup (alias, tag_id) VALUES ($1, $2)",
                    alias.lower(),
                    tag.id,
                )

        await ctx.send(
            f"{config.YES} The `{config.BOT_PREFIX}{alias}` alias was added to " f"`{config.BOT_PREFIX}{tag.name}`."
        )

    @tags.command(name="removealias", aliases=["deletealias", "ra", "da"])
    @commands.guild_only()
    @checks.tag_check()
    async def removetagalias(self, ctx: context.CustomContext, *, alias: OwnedTag):
        """Remove an alias from a tag"""

        if alias.invoked_with == alias.name:
            return await ctx.send(
                f"{config.NO} That is not an alias, but the tag's name. "
                f"Try `{config.BOT_PREFIX}tag delete {alias.invoked_with}` instead."
            )

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to remove the alias "
            f"`{config.BOT_PREFIX}{alias.invoked_with}` "
            f"from `{config.BOT_PREFIX}{alias.name}`?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "DELETE FROM tag_lookup WHERE alias = $1 AND tag_id = $2",
                    alias.invoked_with,
                    alias.id,
                )

        await ctx.send(
            f"{config.YES} The alias "
            f"`{config.BOT_PREFIX}{alias.invoked_with}` from "
            f"`{config.BOT_PREFIX}{alias.name}` was removed."
        )

    async def validate_tag_name(self, ctx: context.CustomContext, tag_name: str) -> bool:
        tag_name = tag_name.lower()

        if not tag_name:
            await ctx.send(f"{config.NO} The name of your tag cannot be empty.")
            return False

        ctx.message.content = f"{config.BOT_PREFIX}{tag_name}"
        maybe_context: context.CustomContext = await self.bot.get_context(ctx.message)

        if maybe_context.valid:
            await ctx.send(f"{config.NO} You can't create a tag with the same name of one of my commands.")
            return False

        tags = await self.bot.db.fetch(
            "SELECT tag_lookup.tag_id FROM tag_lookup "
            "JOIN tag t on tag_lookup.tag_id = t.id "
            "WHERE "
            "(t.global = true AND tag_lookup.alias = $1) "
            "OR "
            "(t.guild_id = $2 AND tag_lookup.alias = $1)",
            tag_name,
            ctx.guild.id,
        )

        if tags:
            if ctx.guild.id == self.bot.dciv.id:
                msg = f"{config.NO} A tag or tag alias from this server with that name already exists."
            else:
                msg = (
                    f"{config.NO} A global tag from the {self.bot.dciv.name} server with that name, or a local "
                    f"tag or tag alias from this server with that name, already exists."
                )

            await ctx.send(msg)
            return False

        if len(tag_name) > 50:
            await ctx.send(f"{config.NO} The name cannot be longer than 50 characters.")
            return False

        return True

    @tags.command(name="add", aliases=["make", "create", "a"])
    @commands.guild_only()
    @checks.tag_check()
    async def addtag(self, ctx: context.CustomContext):
        """Add a tag for this server"""

        p = config.BOT_PREFIX

        if "alias" in ctx.message.content.lower():
            return await ctx.send(f"{config.HINT} Did you mean the `{p}tag addalias` command?")

        name = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **name** of the tag.\n{config.HINT} *This will be "
            f"used to access the tag via my `{p}` prefix, so you do __not__ have to add "
            f"`{p}` in front of it.*"
        )

        if name.startswith(p):
            name = name[len(p):]
            await ctx.send(f"*Note: The leading `{p}` was automatically removed from your tag name.*")

        if not await self.validate_tag_name(ctx, name.lower()):
            return

        img = await self.bot.make_file_from_image_link(
            "https://cdn.discordapp.com/attachments/499669824847478785/784226879149834282/em_vs_plain2.png"
        )
        img.seek(0)
        file = discord.File(img, filename="image.png")

        embed_q = await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Should the tag be sent as an embed?"
            f"\n{config.HINT} *Embeds behave differently than plain text, see the image below "
            f"for the key differences.*",
            file=file,
        )

        is_embedded = await ctx.confirm(message=embed_q)

        title = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **title** of the tag."
            f"\n{config.HINT} *This will be displayed next to the tag's name, "
            f"`{name}`, in the `{p}tags`, `{p}tags search` and `{p}tags from` commands. It will "
            f"also be the title of the embed, if you decided to send this tag as an embed.*"
        )

        if len(title) > 256:
            return await ctx.send(f"{config.NO} The title cannot be longer than 256 characters.")

        content = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **content** of the tag.", image_allowed=True
        )

        if len(content) > 2000:
            return await ctx.send(f"{config.NO} The content cannot be longer than 2000 characters.")

        is_global = False

        if ctx.guild.id == self.bot.dciv.id:
            try:
                nation_admin = self.bot.get_democraciv_role(mk.DemocracivRole.NATION_ADMIN)
            except exceptions.RoleNotFoundError:
                nation_admin = None

            if ctx.author.guild_permissions.administrator or (
                    self.bot.mk.IS_NATION_BOT and nation_admin and nation_admin in ctx.author.roles
            ):
                is_global = await ctx.confirm(
                    f"{config.USER_INTERACTION_REQUIRED} Should this tag be global?"
                    f"\n{config.HINT} *Only {self.bot.dciv.name} Moderators and Nation "
                    f"Admins can make global tags. If a tag is global, it can be used "
                    f"in every server I am in, as well as in "
                    f"DMs with me. If a tag is not global, called a 'local' tag, "
                    f"it can only be used in the server it was made in.*"
                )

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to add the tag "
            f"`{config.BOT_PREFIX}{name}`?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                tag_id = await con.fetchval(
                    "INSERT INTO tag (guild_id, name, content, title,"
                    " global, author, is_embedded) VALUES "
                    "($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                    ctx.guild.id,
                    name.lower(),
                    content,
                    title,
                    is_global,
                    ctx.author.id,
                    is_embedded,
                )
                await con.execute(
                    "INSERT INTO tag_lookup (tag_id, alias)" " VALUES ($1, $2)",
                    tag_id,
                    name.lower(),
                )

        await ctx.send(f"{config.YES} The `{config.BOT_PREFIX}{name}` tag was added.")

    @tags.command(name="info", aliases=["about", "i"])
    @commands.guild_only()
    async def taginfo(self, ctx: context.CustomContext, *, tag: Tag):
        """Info about a tag"""

        pretty_aliases = (", ".join([f"`{config.BOT_PREFIX}{alias}`" for alias in tag.aliases])) or "None"

        embed = text.SafeEmbed(title=tag.title)

        is_global = "Yes" if tag.is_global else "No"
        is_embedded = "Embed" if tag.is_embedded else "Plain Text"

        if isinstance(tag.author, discord.Member):
            embed.add_field(name="Author", value=tag.author.mention, inline=False)
            embed.set_author(
                name=tag.author.name,
                icon_url=tag.author.avatar_url_as(static_format="png"),
            )

        elif isinstance(tag.author, discord.User):
            embed.add_field(
                name="Author",
                value=f"*The author of this tag left this server.*\n"
                      f"*You can claim this tag to make it yours with*\n"
                      f"`{config.BOT_PREFIX}tag claim {tag.name}`",
                inline=False,
            )
            embed.set_author(
                name=tag.author.name,
                icon_url=tag.author.avatar_url_as(static_format="png"),
            )

        elif tag.author is None:
            embed.add_field(
                name="Author",
                value=f"*The author of this tag left this server.*\n"
                      f"*You can claim this tag to make it yours with*\n"
                      f"`{config.BOT_PREFIX}tag claim {tag.name}`",
                inline=False,
            )

        embed.add_field(name="Global Tag", value=is_global, inline=True)
        embed.add_field(name="Tag Format", value=is_embedded, inline=True)
        embed.add_field(name="Uses", value=tag.uses, inline=False)
        embed.add_field(name="Aliases", value=pretty_aliases, inline=False)
        await ctx.send(embed=embed)

    @tags.command(name="claim")
    @commands.guild_only()
    async def claim(self, ctx: context.CustomContext, *, tag: Tag):
        """Claim a tag if the original tag author left this server"""

        if tag.is_global:
            return await ctx.send(f"{config.NO} Global tags cannot be claimed.")

        if tag.author == ctx.author:
            return await ctx.send(f"{config.NO} You already own this tag.")

        if isinstance(tag.author, discord.Member):
            return await ctx.send(f"{config.NO} The owner of this tag is still in this server.")

        await self.bot.db.execute("UPDATE tag SET author = $1 WHERE id = $2", ctx.author.id, tag.id)
        return await ctx.send(f"{config.YES} You are now the owner `{config.BOT_PREFIX}{tag.name}`.")

    @tags.command(name="transfer")
    @commands.guild_only()
    async def transfer(
            self,
            ctx: context.CustomContext,
            to_person: typing.Union[CaseInsensitiveMember, CaseInsensitiveUser, FuzzyCIMember],
            *,
            tag: OwnedTag,
    ):
        """Transfer a tag of yours to someone else"""

        if to_person == ctx.author:
            return await ctx.send(f"{config.NO} You cannot transfer your tag to yourself.")

        await self.bot.db.execute("UPDATE tag SET author = $1 WHERE id = $2", to_person.id, tag.id)
        return await ctx.send(f"{config.YES} {to_person} is now the owner of `{config.BOT_PREFIX}{tag.name}`.")

    @tags.command(name="raw")
    @commands.guild_only()
    async def raw(self, ctx: context.CustomContext, *, tag: Tag):
        """Raw markdown of a tag

        Useful when you want to update a tag with `-tag edit`
        """
        safe_content = tag.clean_content.replace("```", "'")
        return await ctx.send(f"```{safe_content}```")

    @tags.command(name="edit", aliases=["change"])
    @commands.guild_only()
    @checks.tag_check()
    async def edittag(self, ctx: context.CustomContext, *, tag: OwnedTag):
        """Edit one of your tags"""

        menu = text.EditModelMenu(choices_with_formatted_explanation={"embed": "Send Tag as embed or plain text",
                                                                      "title": "Tag Title", "content": "Tag Content"})
        result = await menu.prompt(ctx)
        p = config.BOT_PREFIX

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        to_change = result.choices

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        if to_change["embed"]:
            img = await self.bot.make_file_from_image_link(
                "https://cdn.discordapp.com/attachments/499669824847478785/784226879149834282/em_vs_plain2.png"
            )
            img.seek(0)

            file = discord.File(img, filename="image.png")

            embed_q = await ctx.send(
                f"{config.USER_INTERACTION_REQUIRED} Should the tag be sent as an embed?"
                f"\n{config.HINT} *Embeds behave differently than plain text, see the image below "
                f"for the key differences.*",
                file=file,
            )
            is_embedded = await ctx.confirm(message=embed_q)
        else:
            is_embedded = tag.is_embedded

        if to_change["title"]:
            new_title = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the updated **title** of the tag."
                f"\n{config.HINT} *This will be displayed next to the tag's name, "
                f"`{tag.name}`, in the `{p}tags`, `{p}tags search` and `{p}tags from` commands. It will "
                f"also be the title of the embed, if you decided to send this tag as an embed.*"
            )

            if len(new_title) > 256:
                return await ctx.send(f"{config.NO} The title cannot be longer than 256 characters.")

        else:
            new_title = tag.title

        if to_change["content"]:
            new_content = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the updated **content** of this tag.",
                image_allowed=True,
            )

            if len(new_content) > 2000:
                return await ctx.send(f"{config.NO} The content cannot be longer than 2000 characters.")
        else:
            new_content = tag.content

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit your `{config.BOT_PREFIX}{tag.name}` tag?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        await self.bot.db.execute(
            "UPDATE tag SET content = $1, title = $3, is_embedded = $4 WHERE id = $2",
            new_content,
            tag.id,
            new_title,
            is_embedded,
        )
        await ctx.send(f"{config.YES} Your tag was edited.")

    @tags.command(name="search", aliases=["s"])
    async def search(self, ctx: context.CustomContext, *, query: str):
        """Search for a global or local tag on this server"""

        db_query = """SELECT tag.name, tag.title FROM tag
                      JOIN tag_lookup l on l.tag_id = tag.id
                      WHERE (tag.global = true OR tag.guild_id = $2)
                      AND (lower(l.alias) % $1 OR lower(l.alias) LIKE '%' || $1 || '%' OR lower(tag.title) LIKE '%' || $1 || '%' 
                          OR lower(tag.content) LIKE '%' || $1 || '%')
                      ORDER BY similarity(l.alias, $1) DESC
                      LIMIT 20
                    """

        guild_id = 0 if not ctx.guild else ctx.guild.id
        icon = self.bot.user.avatar_url_as(static_format="png") if not ctx.guild else ctx.guild_icon
        tags = await self.bot.db.fetch(db_query, query.lower(), guild_id)
        pretty_names = {}  # Abuse dict as ordered set since you can't use DISTINCT in above SQL query

        for record in tags:
            pretty_names[f"`{config.BOT_PREFIX}{record['name']}`  {record['title']}"] = None

        pages = paginator.SimplePages(
            entries=list(pretty_names),
            author=f"Tags matching '{query}'",
            icon=icon,
            empty_message="Nothing found.",
        )

        await pages.start(ctx)

    @tags.command(name="toggleglobal")
    @commands.guild_only()
    @checks.moderation_or_nation_leader()
    async def toggleglobal(self, ctx: context.CustomContext, *, tag: Tag):
        """Change a tag to be global/local"""

        if not tag.is_global:
            # Local -> Global
            await self.bot.db.execute("UPDATE tag SET global = true WHERE id = $1", tag.id)
            await ctx.send(f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is now a global tag. ")

        else:
            # Global -> Local
            await self.bot.db.execute("UPDATE tag SET global = false WHERE id = $1", tag.id)
            await ctx.send(f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is no longer a global tag.")

    @tags.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @checks.tag_check()
    async def removetag(self, ctx: context.CustomContext, *, tag: OwnedTag):
        """Remove a tag"""

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to remove the tag "
            f"`{config.BOT_PREFIX}{tag.name}`?"
        )
        if not are_you_sure:
            return await ctx.send("Cancelled.")

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("DELETE FROM tag_lookup WHERE tag_id = $1", tag.id)
                await con.execute(
                    "DELETE FROM tag WHERE name = $1 AND guild_id = $2",
                    tag.name,
                    ctx.guild.id,
                )
                await ctx.send(f"{config.YES} `{config.BOT_PREFIX}{tag.name}` was removed.")

    def get_tag_content_type(self, tag_content: str) -> TagContentType:
        url_endings_image = (
            ".jpeg",
            ".jpg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".img",
            ".svg",
        )
        url_endings_video = (".avi", ".mp4", ".mp3", ".mov", ".flv", ".wmv")

        if self.url_pattern.fullmatch(tag_content) and (tag_content.lower().endswith(url_endings_image)):
            return TagContentType.IMAGE

        elif self.url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_image)):
            return TagContentType.PARTIAL_IMAGE

        elif self.url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_video)):
            return TagContentType.VIDEO

        elif any(s in tag_content for s in ["youtube", "youtu.be", "tenor.com", "gph.is", "giphy.com"]):
            return TagContentType.YOUTUBE_TENOR_GIPHY

        elif self.emoji_pattern.fullmatch(tag_content):
            return TagContentType.CUSTOM_EMOJI

        elif self.discord_invite_pattern.match(tag_content):
            return TagContentType.INVITE

        return TagContentType.TEXT

    async def _update_tag_uses(self, tag_id: int):
        await self.bot.db.execute("UPDATE tag SET uses = uses +1 WHERE id = $1", tag_id)

    async def resolve_tag_name(self, query: str, guild: typing.Optional[discord.Guild]):
        query = query.lower()

        sql = """SELECT
                    tag.id, tag.is_embedded, tag.title, tag.content
                 FROM tag
                 INNER JOIN
                  tag_lookup look ON look.tag_id = tag.id 
                 WHERE
                  (tag.global = true AND look.alias = $1) 
                 OR
                  (look.alias = $1 AND tag.guild_id = $2)
               """

        guild_id = 0 if not guild else guild.id
        tag_record = await self.bot.db.fetchrow(sql, query, guild_id)

        if not tag_record:
            return

        self.bot.loop.create_task(self._update_tag_uses(tag_record["id"]))
        return tag_record

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.author.bot and before.content and after.content and before.content != after.content:
            await self.tag_listener(after)

    @commands.Cog.listener(name="on_message")
    async def tag_listener(self, message):
        if message.author.bot:
            return

        ctx: context.CustomContext = await self.bot.get_context(message)

        if ctx.valid or not ctx.prefix:
            return

        tag_name = message.content[len(ctx.prefix):]
        tag_details = await self.resolve_tag_name(tag_name, message.guild)

        if tag_details is None:
            return

        tag_content_type = self.get_tag_content_type(tag_details["content"])

        if tag_details["is_embedded"]:
            if tag_content_type is TagContentType.IMAGE:
                embed = text.SafeEmbed(title=tag_details['title'], colour=0x2F3136)
                embed.set_image(url=tag_details["content"])

                try:
                    await message.channel.send(embed=embed)
                except discord.HTTPException:
                    await message.channel.send(discord.utils.escape_mentions(tag_details["content"]))

            elif tag_content_type is TagContentType.VIDEO:
                # discord doesn't allow videos in embeds
                await message.channel.send(discord.utils.escape_mentions(tag_details["content"]))

            else:
                embed = text.SafeEmbed(title=tag_details["title"], description=tag_details["content"])

                await message.channel.send(embed=embed)

        else:
            await message.channel.send(discord.utils.escape_mentions(tag_details["content"]))


def setup(bot):
    bot.add_cog(Tags(bot))
