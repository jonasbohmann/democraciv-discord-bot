import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import tags as tags_presenter, tag_forms
from bot.services.tags import TagService
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import forms, transformers, ui
from bot.utils import converter
from bot.utils import paginator

TagOption = app_commands.Transform[converter.Tag, transformers.TagTransformer]
OwnedTagOption = app_commands.Transform[
    converter.OwnedTag,
    transformers.OwnedTagTransformer,
]
CollaboratorTagOption = app_commands.Transform[
    converter.CollaboratorOfTag,
    transformers.CollaboratorTagTransformer,
]


class TagsSlash(commands.Cog):
    tag = app_commands.Group(
        name="tag",
        description="Show, create, and manage tags.",
    )
    tag_alias = app_commands.Group(
        name="alias",
        description="Manage tag aliases.",
        parent=tag,
    )
    tag_collaborator = app_commands.Group(
        name="collaborator",
        description="Manage tag collaborators.",
        parent=tag,
    )
    tag_global = app_commands.Group(
        name="global",
        description="Manage global tag status.",
        parent=tag,
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = TagService(bot)

    def can_make_global(self, interaction: discord.Interaction) -> bool:
        ctx = slash_context.from_interaction(interaction, command_name="tag")
        return self.service.can_make_global(ctx, include_owner=True)

    async def create_tag(
        self,
        ctx: slash_context.InteractionContext,
        *,
        name: str,
        title: str,
        content: str,
        is_embedded: bool,
        is_global: bool,
    ):
        result = await self.service.create_tag(
            ctx,
            name=name,
            title=title,
            content=content,
            is_embedded=is_embedded,
            is_global=is_global,
            allow_owner_global=True,
        )
        await ctx.send(result.message)

    async def edit_tag(
        self,
        ctx: slash_context.InteractionContext,
        *,
        tag: converter.Tag,
        title: str,
        content: str,
        is_embedded: bool,
        is_global: bool,
    ):
        result = await self.service.edit_tag(
            ctx,
            tag=tag,
            title=title,
            content=content,
            is_embedded=is_embedded,
            is_global=is_global,
            allow_owner_global=True,
        )
        await ctx.send(result.message)

    async def update_collaborators(
        self,
        ctx: slash_context.InteractionContext,
        *,
        tag: converter.Tag,
        people,
        add: bool,
    ):
        result = await self.service.update_collaborators(
            tag=tag,
            people=people,
            add=add,
        )
        await ctx.send(result.message)

    async def _handle_create_modal(
        self,
        interaction: discord.Interaction,
        form: tag_forms.TagFormResult,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag create")
        await ctx.defer()
        await self.create_tag(
            ctx,
            name=form.name,
            title=form.title,
            content=form.content,
            is_embedded=form.is_embedded,
            is_global=form.is_global,
        )

    async def _handle_edit_modal(
        self,
        interaction: discord.Interaction,
        form: tag_forms.TagFormResult,
        *,
        tag: converter.Tag,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag edit")
        await ctx.defer()
        await self.edit_tag(
            ctx,
            tag=tag,
            title=form.title,
            content=form.content,
            is_embedded=form.is_embedded,
            is_global=form.is_global,
        )

    async def _handle_people_modal(
        self,
        interaction: discord.Interaction,
        form: tag_forms.TagFormResult,
        *,
        tag: converter.Tag,
        add: bool,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=(
                "tag collaborator bulk-add" if add else "tag collaborator bulk-remove"
            ),
        )
        await ctx.defer()
        people = await forms.resolve_members(
            ctx,
            form.people_text,
            exclude_ids={tag.author_id},
        )
        await self.update_collaborators(ctx, tag=tag, people=people, add=add)

    def content_type(self, tag: converter.Tag):
        return self.service.get_tag_content_type(tag.content)

    async def send_tag_content(
        self,
        ctx: slash_context.InteractionContext,
        tag: converter.Tag,
    ):
        display = tags_presenter.build_tag_display(tag, self.content_type(tag))

        if display.embed is not None:
            try:
                return await ctx.send(embed=display.embed)
            except discord.HTTPException:
                return await ctx.send(display.fallback_content or tag.clean_content)

        await ctx.send(display.content)

    @tag.command(name="list", description="List global and local tags.")
    async def list_tags(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag list")
        await ctx.defer()
        result = await self.service.list_tags(ctx)

        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            per_page=result.per_page,
            empty_message=result.empty_message,
        )
        await pages.start(ctx)

    @tag.command(name="show", description="Show a tag.")
    async def show(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag show")
        await ctx.defer()

        await self.send_tag_content(ctx, tag)

    @tag.command(name="local", description="List local tags on this server.")
    @app_commands.guild_only()
    async def local(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag local")
        await ctx.defer()
        result = await self.service.list_local_tags(ctx)

        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            per_page=result.per_page,
            empty_message=result.empty_message,
        )
        await pages.start(ctx)

    @tag.command(name="from", description="List tags created by someone.")
    @app_commands.guild_only()
    async def from_member(
        self,
        interaction: discord.Interaction,
        person: discord.Member = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag from")
        await ctx.defer()
        member = person or ctx.author
        result = await self.service.list_tags_from_member(ctx, member)

        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            per_page=result.per_page,
            empty_message=result.empty_message,
        )
        await pages.start(ctx)

    @tag.command(name="search", description="Search for a tag.")
    async def search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="tag search")
        await ctx.defer()
        result = await self.service.search_tags(ctx, query)

        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            per_page=result.per_page,
            empty_message=result.empty_message,
        )
        await pages.start(ctx)

    @tag.command(name="random", description="Show a random available tag.")
    async def random(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag random")
        await ctx.defer()
        tag_name = await self.service.get_random_tag_name(ctx)
        if tag_name is None:
            return await ctx.send(f"{config.NO} There are no tags here.")

        tag = await converter.Tag.convert(ctx, tag_name)
        await ctx.send(
            f"{config.HINT} Showing random tag `{config.BOT_PREFIX}{tag_name}`"
        )
        await self.send_tag_content(ctx, tag)

    @tag.command(name="info", description="Show metadata about a tag.")
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag info")
        await ctx.defer()

        embed = tags_presenter.build_info_embed(tag)
        await ctx.send(embed=embed)

    @tag.command(name="raw", description="Show the raw markdown of one tag.")
    @app_commands.guild_only()
    async def raw(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="tag raw",
        )
        await ctx.defer()
        safe_content = tag.clean_content.replace("```", "'")
        await ctx.send(f"```{safe_content[:1900]}```")

    @tag.command(name="stats", description="Show tag statistics.")
    @app_commands.guild_only()
    async def stats(
        self,
        interaction: discord.Interaction,
        person: discord.Member = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag stats")
        await ctx.defer()
        member = person

        if member:
            stats = await self.service.get_person_stats(ctx, member)
            embed = tags_presenter.build_person_stats_embed(stats)
            return await ctx.send(embed=embed)

        stats = await self.service.get_overview_stats(ctx)
        embed = tags_presenter.build_overview_stats_embed(stats)
        await ctx.send(embed=embed)

    @tag.command(name="create", description="Create a tag.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            tag_forms.TagCreateModal(
                can_make_global=self.can_make_global(interaction),
                on_submit_callback=self._handle_create_modal,
            )
        )

    @tag.command(name="edit", description="Edit a tag you own or collaborate on.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def edit(self, interaction: discord.Interaction, tag: CollaboratorTagOption):
        async def handle_edit(
            modal_interaction: discord.Interaction,
            form: tag_forms.TagFormResult,
        ):
            await self._handle_edit_modal(modal_interaction, form, tag=tag)

        await interaction.response.send_modal(
            tag_forms.TagEditModal(
                tag=tag,
                can_make_global=self.can_make_global(interaction),
                on_submit_callback=handle_edit,
            )
        )

    @tag.command(name="delete", description="Delete a tag you own.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def delete(self, interaction: discord.Interaction, tag: OwnedTagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag delete")
        await ctx.defer()
        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {config.BOT_PREFIX}{tag.name}",
            body=f"Are you sure that you want to remove `{config.BOT_PREFIX}{tag.name}`?",
            confirm_label="Delete",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.delete_tag(ctx, tag=tag)
        await ctx.send(result.message)

    @tag.command(name="claim", description="Claim a tag whose owner left this server.")
    @app_commands.guild_only()
    async def claim(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag claim")
        await ctx.defer()

        result = await self.service.claim_tag(ctx, tag=tag)
        await ctx.send(result.message)

    @tag.command(name="transfer", description="Transfer one of your tags.")
    @app_commands.guild_only()
    async def transfer(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
        to_person: discord.User,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag transfer")
        await ctx.defer()

        result = await self.service.transfer_tag(
            ctx,
            tag=tag,
            to_person=to_person,
        )
        await ctx.send(result.message)

    @tag_alias.command(name="add", description="Add an alias to a tag.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def add_alias(
        self,
        interaction: discord.Interaction,
        tag: CollaboratorTagOption,
        alias: str,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag alias add")
        await ctx.defer()
        result = await self.service.add_alias(ctx, tag=tag, alias=alias)
        await ctx.send(result.message)

    @tag_alias.command(name="remove", description="Remove one tag alias.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def remove_alias(
        self,
        interaction: discord.Interaction,
        alias: CollaboratorTagOption,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag alias remove"
        )
        await ctx.defer()

        if alias.invoked_with == alias.name:
            return await ctx.send(
                f"{config.NO} That is not an alias, but the tag's name.",
                ephemeral=True,
            )

        confirmed = await ui.confirm(
            ctx,
            title=f"Remove {config.BOT_PREFIX}{alias.invoked_with}",
            body=(
                f"Remove the alias `{config.BOT_PREFIX}{alias.invoked_with}` "
                f"from `{config.BOT_PREFIX}{alias.name}`?"
            ),
            confirm_label="Remove",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        result = await self.service.remove_alias(alias=alias)
        await ctx.send(result.message)

    @tag_collaborator.command(name="add", description="Add one collaborator to a tag.")
    @app_commands.guild_only()
    async def collaborator_add(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
        person: discord.Member,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag collaborator add"
        )
        await ctx.defer()
        await self.update_collaborators(ctx, tag=tag, people=[person], add=True)

    @tag_collaborator.command(
        name="remove", description="Remove one collaborator from a tag."
    )
    @app_commands.guild_only()
    async def collaborator_remove(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
        person: discord.Member,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag collaborator remove"
        )
        await ctx.defer()
        await self.update_collaborators(ctx, tag=tag, people=[person], add=False)

    @tag_collaborator.command(
        name="bulk-add", description="Add multiple collaborators."
    )
    @app_commands.guild_only()
    async def collaborator_bulk_add(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
    ):
        async def handle_people(
            modal_interaction: discord.Interaction,
            form: tag_forms.TagFormResult,
        ):
            await self._handle_people_modal(modal_interaction, form, tag=tag, add=True)

        await interaction.response.send_modal(
            tag_forms.TagPeopleModal(add=True, on_submit_callback=handle_people)
        )

    @tag_collaborator.command(
        name="bulk-remove", description="Remove multiple collaborators."
    )
    @app_commands.guild_only()
    async def collaborator_bulk_remove(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
    ):
        async def handle_people(
            modal_interaction: discord.Interaction,
            form: tag_forms.TagFormResult,
        ):
            await self._handle_people_modal(modal_interaction, form, tag=tag, add=False)

        await interaction.response.send_modal(
            tag_forms.TagPeopleModal(add=False, on_submit_callback=handle_people)
        )

    @tag_global.command(
        name="toggle", description="Toggle one tag between global and local."
    )
    @app_commands.guild_only()
    @slash_checks.moderation_or_nation_leader()
    async def global_toggle(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag global toggle"
        )
        await ctx.defer()

        result = await self.service.toggle_global_tag(tag=tag)
        await ctx.send(result.message)

    @app_commands.command(name="tags", description="List global and local tags.")
    async def tags_alias(self, interaction: discord.Interaction):
        await self.list_tags.callback(self, interaction)


async def setup(bot):
    await bot.add_cog(TagsSlash(bot))
