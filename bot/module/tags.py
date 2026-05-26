import typing
import discord

from discord.ext import commands

from bot.config import config
from bot.presenters import tags as tags_presenter, tag_forms
from bot.services.tags import TagContentType, TagService
from bot.utils.converter import (
    Tag,
    OwnedTag,
    CollaboratorOfTag,
    CaseInsensitiveMember,
    CaseInsensitiveUser,
    Fuzzy,
    FuzzySettings,
)
from bot.utils import text, paginator, context, checks


def _split_lines(value: str) -> typing.List[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class Tags(context.CustomCog):
    """Create tags for later retrieval of text, images & links. Tags are accessed with the bot's prefix."""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = TagService(bot)

    async def _send_tag_content(self, ctx: context.CustomContext, tag: Tag):
        display = tags_presenter.build_tag_display(
            tag,
            self.service.get_tag_content_type(tag.content),
        )

        if display.embed is not None:
            try:
                return await ctx.send(embed=display.embed)
            except discord.HTTPException:
                return await ctx.send(display.fallback_content or tag.clean_content)

        await ctx.send(display.content)

    async def _send_pages(self, ctx: context.CustomContext, result):
        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            empty_message=result.empty_message,
            per_page=result.per_page,
        )
        await pages.start(ctx)

    async def _prompt_tag_form(
        self,
        ctx: context.CustomContext,
        *,
        modal_factory: typing.Callable[[], tag_forms.TagModal],
        button_label: str,
        prompt: str,
    ) -> typing.Optional[tag_forms.TagFormResult]:
        view = text.ModalPromptView(
            ctx,
            modal_factory=modal_factory,
            button_label=button_label,
            timeout=300,
        )
        return await view.prompt_message(prompt)

    @commands.group(
        name="tag",
        aliases=["tags", "t"],
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def tags(self, ctx: context.CustomContext, *, tag: Fuzzy[Tag] = None):
        """Access a tag or list all tags on this server

        **Example**
            `{PREFIX}{COMMAND}` to get a list of all tags on this server
            `{PREFIX}{COMMAND} constitution` to see the {PREFIX}constitution tag"""

        if tag:
            return await self._send_tag_content(ctx, tag)

        result = await self.service.list_tags(ctx)
        await self._send_pages(ctx, result)

    @tags.command(name="local", aliases=["l"])
    @commands.guild_only()
    async def local(self, ctx: context.CustomContext):
        """List all non-global tags on this server"""

        result = await self.service.list_local_tags(ctx)
        await self._send_pages(ctx, result)

    @tags.command(name="from", aliases=["by", "f"])
    @commands.guild_only()
    async def _from(
        self,
        ctx: context.CustomContext,
        *,
        person: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ] = None,
    ):
        """List the tags that someone made on this server"""

        member = person or ctx.author
        result = await self.service.list_tags_from_member(ctx, member)
        await self._send_pages(ctx, result)

    @tags.command(name="addalias", aliases=["alias"])
    @commands.guild_only()
    @checks.tag_check()
    async def addtagalias(
        self, ctx: context.CustomContext, *, tag: Fuzzy[CollaboratorOfTag]
    ):
        """Add a new alias to a tag"""

        p = config.BOT_PREFIX

        form = await self._prompt_tag_form(
            ctx,
            modal_factory=lambda: tag_forms.TagAliasModal(tag=tag),
            button_label="Add Alias",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Add an alias for `{p}{tag.name}` in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        alias = form.alias

        if alias.startswith(p):
            alias = alias[len(p) :]
            await ctx.send(
                f"*Note: The leading `{p}` was automatically removed from the alias.*"
            )

        result = await self.service.add_alias(ctx, tag=tag, alias=alias)
        await ctx.send(result.message)

    @tags.command(name="deletealias", aliases=["removealias", "ra", "da"])
    @commands.guild_only()
    @checks.tag_check()
    async def removetagalias(
        self, ctx: context.CustomContext, *, alias: Fuzzy[CollaboratorOfTag]
    ):
        """Delete a tag alias"""

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

        result = await self.service.remove_alias(alias=alias)
        await ctx.send(result.message)

    @tags.command(name="add", aliases=["make", "create", "a"])
    @commands.guild_only()
    @checks.tag_check()
    async def addtag(self, ctx: context.CustomContext):
        """Add a tag for this server"""

        p = config.BOT_PREFIX

        if "alias" in ctx.message.content.lower():
            return await ctx.send(
                f"{config.HINT} Did you mean the `{p}tag addalias` command?"
            )

        form = await self._prompt_tag_form(
            ctx,
            modal_factory=lambda: tag_forms.TagCreateModal(
                can_make_global=self.service.can_make_global(ctx)
            ),
            button_label="Create Tag",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Fill out the tag details in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        name = form.name
        if name.startswith(p):
            await ctx.send(
                f"*Note: The leading `{p}` was automatically removed from your tag name.*"
            )

        name = self.service.normalize_tag_name(name)

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to add the tag "
            f"`{config.BOT_PREFIX}{name}`?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        result = await self.service.create_tag(
            ctx,
            name=name,
            title=form.title,
            content=form.content,
            is_embedded=form.is_embedded,
            is_global=form.is_global,
        )
        await ctx.send(result.message)

    @tags.command(name="info", aliases=["about", "i"])
    @commands.guild_only()
    async def taginfo(self, ctx: context.CustomContext, *, tag: Fuzzy[Tag]):
        """Info about a tag"""

        embed = tags_presenter.build_info_embed(tag)
        await ctx.send(embed=embed)

    @tags.command(name="claim")
    @commands.guild_only()
    async def claim(self, ctx: context.CustomContext, *, tag: Fuzzy[Tag]):
        """Claim a tag if the original tag author left this server"""

        result = await self.service.claim_tag(ctx, tag=tag)
        await ctx.send(result.message)

    @tags.command(name="transfer")
    @commands.guild_only()
    async def transfer(
        self,
        ctx: context.CustomContext,
        to_person: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ],
        *,
        tag: OwnedTag,
    ):
        """Transfer a tag of yours to someone else"""

        result = await self.service.transfer_tag(ctx, tag=tag, to_person=to_person)
        await ctx.send(result.message)

    @tags.command(name="raw")
    @commands.guild_only()
    async def raw(self, ctx: context.CustomContext, *, tag: Fuzzy[Tag]):
        """Raw markdown of a tag

        Useful when you want to update a tag with `-tag edit`
        """
        safe_content = tag.clean_content.replace("```", "'")
        return await ctx.send(f"```{safe_content}```")

    @tags.command(name="random")
    async def random(self, ctx: context.CustomContext):
        """Trigger a random tag"""

        tag_name = await self.service.get_random_tag_name(ctx)
        if tag_name is None:
            return await ctx.send(f"{config.NO} There are no tags here.")

        tag = await Tag.convert(ctx, tag_name)

        await ctx.send(
            f"{config.HINT} Showing random tag `{config.BOT_PREFIX}{tag_name}`"
        )
        await self._send_tag_content(ctx, tag)

    @tags.command(name="edit", aliases=["change"])
    @commands.guild_only()
    @checks.tag_check()
    async def edittag(
        self, ctx: context.CustomContext, *, tag: Fuzzy[CollaboratorOfTag]
    ):
        """Edit one of your tags"""

        form = await self._prompt_tag_form(
            ctx,
            modal_factory=lambda: tag_forms.TagEditModal(
                tag=tag,
                can_make_global=self.service.can_make_global(ctx),
            ),
            button_label="Edit Tag",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Update `{config.BOT_PREFIX}{tag.name}` "
                "in the form. Leave pre-filled values unchanged to keep them."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit the "
            f"`{config.BOT_PREFIX}{tag.name}` tag?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        result = await self.service.edit_tag(
            ctx,
            tag=tag,
            title=form.title,
            content=form.content,
            is_embedded=form.is_embedded,
            is_global=form.is_global,
        )
        await ctx.send(result.message)

    @tags.command(name="search", aliases=["s"])
    async def search(self, ctx: context.CustomContext, *, query: str):
        """Search for a global or local tag on this server"""

        result = await self.service.search_tags(ctx, query)
        await self._send_pages(ctx, result)

    async def _person_stats(self, ctx, person):
        stats = await self.service.get_person_stats(ctx, person)
        embed = tags_presenter.build_person_stats_embed(stats)
        await ctx.send(embed=embed)

    @tags.command(name="stats", aliases=["statistics"])
    @commands.guild_only()
    async def stats(
        self,
        ctx: context.CustomContext,
        *,
        person: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ] = None,
    ):
        """View general statistics or statistics about a specific person

        **Example**
            `{PREFIX}{COMMAND}` to view general statistics
            `{PREFIX}{COMMAND} DerJonas` to view statistics specific to that person"""

        if person:
            return await self._person_stats(ctx, person)

        stats = await self.service.get_overview_stats(ctx)
        embed = tags_presenter.build_overview_stats_embed(stats)
        await ctx.send(embed=embed)

    @tags.command(name="toggleglobal")
    @commands.guild_only()
    @checks.moderation_or_nation_leader()
    async def toggleglobal(self, ctx: context.CustomContext, *, tag: Fuzzy[Tag]):
        """Change a tag to be global/local"""

        result = await self.service.toggle_global_tag(tag=tag)
        await ctx.send(result.message)

    @tags.command(name="delete", aliases=["remove"])
    @commands.guild_only()
    @checks.tag_check()
    async def removetag(self, ctx: context.CustomContext, *, tag: Fuzzy[OwnedTag]):
        """Delete a tag"""

        if "alias" in ctx.message.content.lower():
            return await ctx.send(
                f"{config.HINT} Did you mean the `{config.BOT_PREFIX}tag deletealias` command?"
            )

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to remove the tag "
            f"`{config.BOT_PREFIX}{tag.name}`?"
        )
        if not are_you_sure:
            return await ctx.send("Cancelled.")

        result = await self.service.delete_tag(ctx, tag=tag)
        await ctx.send(result.message)

    async def _get_people_input(
        self,
        ctx: context.CustomContext,
        tag: Tag,
        people_text: str,
    ):
        people = []
        conv = Fuzzy[CaseInsensitiveMember]

        for line in _split_lines(people_text):
            try:
                converted = await conv.convert(ctx, line)
            except commands.BadArgument:
                continue

            if not converted.bot and converted.id != tag.author_id:
                people.append(converted)

        return people

    @tags.command(name="share", aliases=["allow"])
    @commands.guild_only()
    async def allow(self, ctx, *, tag: Fuzzy[OwnedTag]):
        """Allow other people on this server to edit and add & remove aliases to one of your tags

        Note that only the owner of a Tag can delete it or transfer ownership of it to somebody else.

        **Example**
           `{PREFIX}{COMMAND} const`
           `{PREFIX}{COMMAND} sue`"""

        form = await self._prompt_tag_form(
            ctx,
            modal_factory=lambda: tag_forms.TagPeopleModal(add=True),
            button_label="Add Collaborators",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Add collaborators for "
                f"`{config.BOT_PREFIX}{tag.name}` in the form."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        people = await self._get_people_input(ctx, tag, form.people_text)

        result = await self.service.update_collaborators(
            tag=tag,
            people=people,
            add=True,
        )
        await ctx.send(result.message)

    @tags.command(name="unshare", aliases=["deny"])
    @commands.guild_only()
    async def deny(self, ctx, *, tag: Fuzzy[OwnedTag]):
        """Remove access to one of your tags from someone that you previously have shared

        **Example**
           `{PREFIX}{COMMAND} const`
           `{PREFIX}{COMMAND} sue`"""

        form = await self._prompt_tag_form(
            ctx,
            modal_factory=lambda: tag_forms.TagPeopleModal(add=False),
            button_label="Remove Collaborators",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Remove collaborators from "
                f"`{config.BOT_PREFIX}{tag.name}` in the form."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        people = await self._get_people_input(ctx, tag, form.people_text)

        result = await self.service.update_collaborators(
            tag=tag,
            people=people,
            add=False,
        )
        await ctx.send(result.message)

    def get_tag_content_type(self, tag_content: str) -> TagContentType:
        return self.service.get_tag_content_type(tag_content)

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
        if (
            not before.author.bot
            and before.content
            and after.content
            and before.content != after.content
        ):
            await self.tag_listener(after)

    @commands.Cog.listener(name="on_message")
    async def tag_listener(self, message):
        if message.author.bot:
            return

        ctx: context.CustomContext = await self.bot.get_context(message)

        if ctx.valid or not ctx.prefix:
            return

        tag_name = message.content[len(ctx.prefix) :]
        tag_details = await self.resolve_tag_name(tag_name, message.guild)
        easter_egg_sue_rest = None

        if tag_details is None:

            # todo nov 2024
            # too hacky and code duplicate
            if tag_name.lower().startswith("sue "):
                tag_details = await self.resolve_tag_name("sue", message.guild)
                easter_egg_sue_rest = f"<:loredana:772446083891593246> {discord.utils.escape_markdown(tag_name[4:])} had it coming."

                if not tag_details:
                    return

            else:
                return

        tag_content_type = self.get_tag_content_type(tag_details["content"])

        if tag_details["is_embedded"]:
            if tag_content_type is TagContentType.IMAGE:
                # invisible colour=0x2F3136
                embed = text.SafeEmbed(title=tag_details["title"])
                embed.set_image(url=tag_details["content"])

                try:
                    await message.channel.send(embed=embed)
                except discord.HTTPException:
                    await message.channel.send(
                        discord.utils.escape_mentions(tag_details["content"])
                    )

            elif tag_content_type is TagContentType.VIDEO:
                # discord doesn't allow videos in embeds
                await message.channel.send(
                    discord.utils.escape_mentions(tag_details["content"])
                )

            else:
                embed = text.SafeEmbed(
                    title=tag_details["title"], description=tag_details["content"]
                )

                await message.channel.send(content=easter_egg_sue_rest, embed=embed)

        else:
            await message.channel.send(
                discord.utils.escape_mentions(tag_details["content"])
            )


async def setup(bot):
    await bot.add_cog(Tags(bot))
