import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from bot.config import config, mk
from bot.module.tags import TagContentType
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import forms, transformers, ui
from bot.utils import converter, exceptions

TagOption = app_commands.Transform[converter.Tag, transformers.TagTransformer]
OwnedTagOption = app_commands.Transform[
    converter.OwnedTag,
    transformers.OwnedTagTransformer,
]
CollaboratorTagOption = app_commands.Transform[
    converter.CollaboratorOfTag,
    transformers.CollaboratorTagTransformer,
]


class TagCreateModal(forms.ErrorHandledModal):
    def __init__(self, cog: "TagsSlash", *, can_make_global: bool):
        super().__init__(title="Create Tag")
        self.cog = cog
        self.can_make_global = can_make_global
        self.name = forms.text_label(
            label="Name",
            description=f"Do not include the `{config.BOT_PREFIX}` prefix.",
            max_length=50,
        )
        self.title_field = forms.text_label(
            label="Title",
            max_length=256,
        )
        self.content = forms.text_label(
            label="Content",
            max_length=2000,
            style=discord.TextStyle.long,
        )
        self.is_embedded = forms.checkbox_label(
            label="Send as Embed",
            description="Use an embed-like layout when the tag is shown.",
            default=False,
        )
        self.is_global = (
            forms.checkbox_label(
                label="Global Tag",
                description="Works in every server and in DMs.",
                default=False,
            )
            if can_make_global
            else None
        )

        self.add_item(self.name)
        self.add_item(self.title_field)
        self.add_item(self.content)
        self.add_item(self.is_embedded)
        if self.is_global is not None:
            self.add_item(self.is_global)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag create")
        await ctx.defer()
        await self.cog.create_tag(
            ctx,
            name=self.name.component.value,
            title=self.title_field.component.value,
            content=self.content.component.value,
            is_embedded=self.is_embedded.component.value,
            is_global=bool(self.is_global and self.is_global.component.value),
        )


class TagEditModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "TagsSlash",
        *,
        tag: converter.Tag,
        can_make_global: bool,
    ):
        super().__init__(title=f"Edit {ui.shorten(tag.name, width=35)}")
        self.cog = cog
        self.tag = tag
        self.can_make_global = can_make_global
        self.title_field = forms.text_label(
            label="Title",
            default=tag.title,
            max_length=256,
        )
        self.content = forms.text_label(
            label="Content",
            default=tag.content,
            max_length=2000,
            style=discord.TextStyle.long,
        )
        self.is_embedded = forms.checkbox_label(
            label="Send as Embed",
            default=tag.is_embedded,
        )
        self.is_global = (
            forms.checkbox_label(
                label="Global Tag",
                description="Works in every server and in DMs.",
                default=tag.is_global,
            )
            if can_make_global
            else None
        )

        self.add_item(self.title_field)
        self.add_item(self.content)
        self.add_item(self.is_embedded)
        if self.is_global is not None:
            self.add_item(self.is_global)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag edit")
        await ctx.defer()
        await self.cog.edit_tag(
            ctx,
            tag=self.tag,
            title=self.title_field.component.value,
            content=self.content.component.value,
            is_embedded=self.is_embedded.component.value,
            is_global=(
                self.is_global.component.value if self.is_global else self.tag.is_global
            ),
        )


class TagPeopleModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "TagsSlash",
        *,
        tag: converter.Tag,
        add: bool,
    ):
        super().__init__(title=f"{'Add' if add else 'Remove'} Collaborators")
        self.cog = cog
        self.tag = tag
        self.add = add
        self.people = forms.text_label(
            label="People",
            description="Mentions, IDs, names, or nicknames. One per line.",
            style=discord.TextStyle.long,
        )
        self.add_item(self.people)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=(
                "tag collaborator bulk-add"
                if self.add
                else "tag collaborator bulk-remove"
            ),
        )
        await ctx.defer()
        people = await forms.resolve_members(
            ctx,
            self.people.component.value,
            exclude_ids={self.tag.author_id},
        )
        await self.cog.update_collaborators(
            ctx,
            tag=self.tag,
            people=people,
            add=self.add,
        )


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

    def tag_cog(self):
        return self.bot.get_cog("Tags")

    def can_make_global(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.bot.dciv.id:
            return False

        user = interaction.user
        if not isinstance(user, discord.Member):
            return False

        if user.guild_permissions.administrator or user.id == self.bot.owner_id:
            return True

        if self.bot.mk.IS_NATION_BOT:
            try:
                nation_admin = self.bot.get_democraciv_role(
                    mk.DemocracivRole.NATION_ADMIN
                )
            except exceptions.RoleNotFoundError:
                nation_admin = None

            return nation_admin is not None and nation_admin in user.roles

        return False

    async def validate_tag_name(
        self,
        ctx: slash_context.InteractionContext,
        name: str,
    ) -> str:
        name = forms.strip_prefix(name).lower()

        if not name:
            raise exceptions.TagError(f"{config.NO} The name cannot be empty.")

        if self.bot.get_command(name):
            raise exceptions.TagError(
                f"{config.NO} You can't create a tag or alias with the same name as one of my commands."
            )

        if len(name) > 50:
            raise exceptions.TagError(
                f"{config.NO} The name or alias cannot be longer than 50 characters."
            )

        tags = await self.bot.db.fetch(
            "SELECT tag_lookup.tag_id FROM tag_lookup "
            "JOIN tag t on tag_lookup.tag_id = t.id "
            "WHERE "
            "(t.global = true AND tag_lookup.alias = $1) "
            "OR "
            "(t.guild_id = $2 AND tag_lookup.alias = $1)",
            name,
            ctx.guild.id,
        )
        if tags:
            raise exceptions.TagError(
                f"{config.NO} A tag or tag alias with that name already exists."
            )

        return name

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
        name = await self.validate_tag_name(ctx, name)

        if is_global and not self.can_make_global(ctx.interaction):
            return await ctx.send(
                f"{config.NO} Only {self.bot.dciv.name} Moderators and Nation Admins can make global tags.",
                ephemeral=True,
            )

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                tag_id = await con.fetchval(
                    "INSERT INTO tag (guild_id, name, content, title,"
                    " global, author, is_embedded) VALUES "
                    "($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                    ctx.guild.id,
                    name,
                    content,
                    title,
                    is_global,
                    ctx.author.id,
                    is_embedded,
                )
                await con.execute(
                    "INSERT INTO tag_lookup (tag_id, alias) VALUES ($1, $2)",
                    tag_id,
                    name,
                )

        await ctx.send(
            f"{config.YES} The `{config.BOT_PREFIX}{name}` tag was added.",
        )

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
        if is_global != tag.is_global and not self.can_make_global(ctx.interaction):
            return await ctx.send(
                f"{config.NO} Only {self.bot.dciv.name} Moderators and Nation Admins can change global tag status.",
                ephemeral=True,
            )

        await self.bot.db.execute(
            "UPDATE tag SET content = $1, title = $3, is_embedded = $4, global = $5 WHERE id = $2",
            content,
            tag.id,
            title,
            is_embedded,
            is_global,
        )
        await ctx.send(f"{config.YES} The tag was edited.")

    async def update_collaborators(
        self,
        ctx: slash_context.InteractionContext,
        *,
        tag: converter.Tag,
        people,
        add: bool,
    ):
        if not people:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anybody.",
                ephemeral=True,
            )

        people = [
            person
            for person in people
            if not getattr(person, "bot", False) and person.id != tag.author_id
        ]
        if not people:
            return await ctx.send(
                f"{config.NO} No valid collaborators were specified.",
                ephemeral=True,
            )

        for person in people:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO tag_collaborator (tag_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    tag.id,
                    person.id,
                )
            else:
                await self.bot.db.execute(
                    "DELETE FROM tag_collaborator WHERE tag_id = $1 AND user_id = $2",
                    tag.id,
                    person.id,
                )

        action = "can now edit" if add else "can no longer edit"
        await ctx.send(
            f"{config.YES} Those people {action} your `{config.BOT_PREFIX}{tag.name}` tag.",
        )

    def content_type(self, tag: converter.Tag):
        cog = self.tag_cog()
        if cog is None:
            return TagContentType.TEXT

        return cog.get_tag_content_type(tag.content)

    async def send_tag_content(
        self,
        ctx: slash_context.InteractionContext,
        tag: converter.Tag,
        *,
        hint: str = None,
    ):
        tag_content_type = self.content_type(tag)
        prefix = f"{hint}\n" if hint else None

        if tag.is_embedded:
            if tag_content_type is TagContentType.IMAGE:
                return await ui.send_static(
                    ctx,
                    title=tag.title,
                    body=hint,
                    media_urls=[tag.content],
                )

            if tag_content_type is TagContentType.VIDEO:
                return await ctx.send(f"{prefix or ''}{tag.clean_content}")

            return await ui.send_static(
                ctx,
                title=tag.title,
                body=f"{prefix or ''}{tag.clean_content}",
            )

        await ctx.send(f"{prefix or ''}{tag.clean_content}")

    @tag.command(name="list", description="List global and local tags.")
    async def list_tags(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag list")
        await ctx.defer()
        entries = []

        global_tags = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE global = true ORDER BY uses desc"
        )
        if global_tags:
            entries.append(
                f"### Global Tags\n-# Tags can only be made global by {self.bot.dciv.name} Moderation and Nation Admins."
            )
            entries.extend(
                f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in global_tags
            )

        if ctx.guild:
            local_tags = await self.bot.db.fetch(
                "SELECT * FROM tag WHERE guild_id = $1 AND global = false ORDER BY uses desc",
                ctx.guild.id,
            )
            if local_tags:
                entries.append("\n### Local Tags")
                entries.extend(
                    f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                    for record in local_tags
                )

        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"All Tags in {ctx.guild.name}" if ctx.guild else "All Global Tags",
            empty_message="There are no tags here.",
            per_page=12,
        )

    @tag.command(name="show", description="Show one tag.")
    async def show(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag show")
        await ctx.defer()
        await self.send_tag_content(ctx, tag)

    @tag.command(name="local", description="List local tags on this server.")
    @app_commands.guild_only()
    async def local(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag local")
        await ctx.defer()
        records = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE guild_id = $1 AND global = false ORDER BY uses desc",
            ctx.guild.id,
        )
        await ui.send_pages(
            ctx,
            entries=[
                f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in records
            ],
            title=f"Local Tags in {ctx.guild.name}",
            empty_message="There are no local tags on this server.",
            per_page=12,
        )

    @tag.command(name="from", description="List tags created by one member.")
    @app_commands.guild_only()
    async def from_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag from")
        await ctx.defer()
        member = member or ctx.author
        records = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE author = $1 AND guild_id = $2 ORDER BY uses desc",
            member.id,
            ctx.guild.id,
        )
        await ui.send_pages(
            ctx,
            entries=[
                f"`{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in records
            ],
            title=f"Tags from {member.display_name}",
            empty_message=f"{member} hasn't made any tags on this server yet.",
            per_page=12,
        )

    @tag.command(name="search", description="Search for a tag.")
    async def search(self, interaction: discord.Interaction, query: str):
        ctx = slash_context.from_interaction(interaction, command_name="tag search")
        await ctx.defer()
        records = await self.bot.db.fetch(
            """SELECT tag.name, tag.title FROM tag
               JOIN tag_lookup l on l.tag_id = tag.id
               WHERE (tag.global = true OR tag.guild_id = $2)
               AND (lower(l.alias) % $1 OR lower(l.alias) LIKE '%' || $1 || '%' OR lower(tag.title) LIKE '%' || $1 || '%' 
                   OR lower(tag.content) LIKE '%' || $1 || '%')
               ORDER BY similarity(l.alias, $1) DESC
               LIMIT 20""",
            query.lower(),
            ctx.guild.id if ctx.guild else 0,
        )
        pretty_names = {}
        for record in records:
            pretty_names[
                f"`{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
            ] = None

        await ui.send_pages(
            ctx,
            entries=list(pretty_names),
            title=f"Tags matching '{query}'",
            empty_message="Nothing found.",
            per_page=12,
        )

    @tag.command(name="random", description="Show a random available tag.")
    async def random(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="tag random")
        await ctx.defer()
        tag_name = await self.bot.db.fetchval(
            "SELECT name FROM tag WHERE tag.global = true OR tag.guild_id = $1 ORDER BY random() limit 1",
            ctx.guild.id if ctx.guild else 0,
        )
        if tag_name is None:
            return await ctx.send(f"{config.NO} There are no tags here.")

        tag = await converter.Tag.convert(ctx, tag_name)
        await self.send_tag_content(
            ctx,
            tag,
            hint=f"{config.HINT} Showing random tag `{config.BOT_PREFIX}{tag_name}`",
        )

    @tag.command(name="info", description="Show metadata about one tag.")
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag info")
        await ctx.defer()
        author = tag.author
        author_value = (
            f"{author.mention} {author}"
            if author is not None
            else "*The author of this tag left this server.*"
        )
        collaborators = (
            "\n".join(
                f"{collaborator.mention} {collaborator}"
                for collaborator in tag.collaborators
            )
            or "-"
        )
        aliases = (
            ", ".join(f"`{config.BOT_PREFIX}{alias}`" for alias in tag.aliases) or "-"
        )

        await ui.send_static(
            ctx,
            title=tag.title,
            sections=[
                ui.LayoutSection("Author", author_value),
                ui.LayoutSection(
                    "Format",
                    f"Global Tag: {'Yes' if tag.is_global else 'No'}\n"
                    f"Tag Format: {'Embed' if tag.is_embedded else 'Plain Text'}\n"
                    f"Uses: {tag.uses}",
                ),
                ui.LayoutSection("Collaborators", collaborators),
                ui.LayoutSection("Aliases", aliases),
            ],
        )

    @tag.command(name="raw", description="Show the raw markdown of one tag.")
    @app_commands.guild_only()
    async def raw(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="tag raw",
            ephemeral=True,
        )
        await ctx.defer(ephemeral=True)
        safe_content = tag.clean_content.replace("```", "'")
        await ctx.send(f"```{safe_content[:1900]}```", ephemeral=True)

    @tag.command(name="stats", description="Show tag statistics.")
    @app_commands.guild_only()
    async def stats(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="tag stats")
        await ctx.defer()

        if member:
            amount = await self.bot.db.fetch(
                "SELECT COUNT(name) FROM tag WHERE author = $1 "
                "UNION ALL "
                "SELECT COUNT(name) FROM tag WHERE author = $1 AND guild_id = $2 "
                "UNION ALL "
                "SELECT COUNT(name) FROM tag WHERE author = $1 AND global = true ",
                member.id,
                ctx.guild.id,
            )
            top_tags = await self.bot.db.fetch(
                "SELECT name, uses FROM tag WHERE author = $1 AND guild_id = $2 ORDER BY uses DESC LIMIT 5",
                member.id,
                ctx.guild.id,
            )
            top_global_tags = await self.bot.db.fetch(
                "SELECT name, uses FROM tag WHERE author = $1 AND global = true ORDER BY uses DESC LIMIT 5",
                member.id,
            )
            return await ui.send_static(
                ctx,
                title=f"Tags from {member.display_name}",
                sections=[
                    ui.LayoutSection(
                        "Counts",
                        f"Any Server: {amount[0]['count']}\n"
                        f"Global: {amount[2]['count']}\n"
                        f"This Server: {amount[1]['count']}",
                    ),
                    ui.LayoutSection(
                        "Top Tags from this Server", self.format_stats(top_tags)
                    ),
                    ui.LayoutSection(
                        "Top Global Tags", self.format_stats(top_global_tags)
                    ),
                ],
            )

        total = await self.bot.db.fetch(
            "SELECT COUNT(name) FROM tag "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE guild_id = $1 "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE global = true",
            ctx.guild.id,
        )
        top_global_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE global = true ORDER BY uses DESC LIMIT 5"
        )
        top_server_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE guild_id = $1 ORDER BY uses DESC LIMIT 5",
            ctx.guild.id,
        )
        top_local_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE global = false AND guild_id = $1 ORDER BY uses DESC LIMIT 5",
            ctx.guild.id,
        )
        await ui.send_static(
            ctx,
            title=f"Tags on {ctx.guild.name}",
            body=(
                f"There are {total[0]['count']} tags in total, of which "
                f"{total[2]['count']} are global. {total[1]['count']} are from this server."
            ),
            sections=[
                ui.LayoutSection("Top Global Tags", self.format_stats(top_global_tags)),
                ui.LayoutSection(
                    "Top Tags from this Server", self.format_stats(top_server_tags)
                ),
                ui.LayoutSection(
                    "Top Local Tags from this Server", self.format_stats(top_local_tags)
                ),
            ],
        )

    @staticmethod
    def format_stats(records):
        if not records:
            return "-"

        return "\n".join(
            f'{index}. `{config.BOT_PREFIX}{record["name"]}` ({record["uses"]} uses)'
            for index, record in enumerate(records, start=1)
        )

    @tag.command(name="create", description="Create a tag.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            TagCreateModal(self, can_make_global=self.can_make_global(interaction))
        )

    @tag.command(name="edit", description="Edit a tag you own or collaborate on.")
    @app_commands.guild_only()
    @slash_checks.tag_check()
    async def edit(self, interaction: discord.Interaction, tag: CollaboratorTagOption):
        await interaction.response.send_modal(
            TagEditModal(
                self,
                tag=tag,
                can_make_global=self.can_make_global(interaction),
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

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("DELETE FROM tag_lookup WHERE tag_id = $1", tag.id)
                await con.execute(
                    "DELETE FROM tag WHERE name = $1 AND guild_id = $2",
                    tag.name,
                    ctx.guild.id,
                )

        await ctx.send(
            f"{config.YES} `{config.BOT_PREFIX}{tag.name}` was removed.",
        )

    @tag.command(name="claim", description="Claim a tag whose owner left this server.")
    @app_commands.guild_only()
    async def claim(self, interaction: discord.Interaction, tag: TagOption):
        ctx = slash_context.from_interaction(interaction, command_name="tag claim")
        await ctx.defer()

        if tag.is_global:
            return await ctx.send(
                f"{config.NO} Global tags cannot be claimed.", ephemeral=True
            )
        if tag.author == ctx.author:
            return await ctx.send(
                f"{config.NO} You already own this tag.", ephemeral=True
            )
        if isinstance(tag.author, discord.Member):
            return await ctx.send(
                f"{config.NO} The owner of this tag is still in this server.",
                ephemeral=True,
            )

        await self.bot.db.execute(
            "UPDATE tag SET author = $1 WHERE id = $2", ctx.author.id, tag.id
        )
        await ctx.send(
            f"{config.YES} You are now the owner `{config.BOT_PREFIX}{tag.name}`.",
        )

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

        if to_person.id == ctx.author.id:
            return await ctx.send(
                f"{config.NO} You cannot transfer your tag to yourself.",
                ephemeral=True,
            )

        await self.bot.db.execute(
            "UPDATE tag SET author = $1 WHERE id = $2",
            to_person.id,
            tag.id,
        )
        await ctx.send(
            f"{config.YES} {to_person} is now the owner of `{config.BOT_PREFIX}{tag.name}`.",
        )

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
        alias = await self.validate_tag_name(ctx, alias)
        await self.bot.db.execute(
            "INSERT INTO tag_lookup (alias, tag_id) VALUES ($1, $2)",
            alias,
            tag.id,
        )
        await ctx.send(
            f"{config.YES} The `{config.BOT_PREFIX}{alias}` alias was added to `{config.BOT_PREFIX}{tag.name}`.",
        )

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

        await self.bot.db.execute(
            "DELETE FROM tag_lookup WHERE alias = $1 AND tag_id = $2",
            alias.invoked_with,
            alias.id,
        )
        await ctx.send(
            f"{config.YES} The alias `{config.BOT_PREFIX}{alias.invoked_with}` was removed.",
        )

    @tag_collaborator.command(name="add", description="Add one collaborator to a tag.")
    @app_commands.guild_only()
    async def collaborator_add(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
        member: discord.Member,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag collaborator add"
        )
        await ctx.defer()
        await self.update_collaborators(ctx, tag=tag, people=[member], add=True)

    @tag_collaborator.command(
        name="remove", description="Remove one collaborator from a tag."
    )
    @app_commands.guild_only()
    async def collaborator_remove(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
        member: discord.Member,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="tag collaborator remove"
        )
        await ctx.defer()
        await self.update_collaborators(ctx, tag=tag, people=[member], add=False)

    @tag_collaborator.command(
        name="bulk-add", description="Add multiple collaborators."
    )
    @app_commands.guild_only()
    async def collaborator_bulk_add(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
    ):
        await interaction.response.send_modal(TagPeopleModal(self, tag=tag, add=True))

    @tag_collaborator.command(
        name="bulk-remove", description="Remove multiple collaborators."
    )
    @app_commands.guild_only()
    async def collaborator_bulk_remove(
        self,
        interaction: discord.Interaction,
        tag: OwnedTagOption,
    ):
        await interaction.response.send_modal(TagPeopleModal(self, tag=tag, add=False))

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

        if not tag.is_global:
            await self.bot.db.execute(
                "UPDATE tag SET global = true WHERE id = $1", tag.id
            )
            return await ctx.send(
                f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is now a global tag.",
            )

        await self.bot.db.execute("UPDATE tag SET global = false WHERE id = $1", tag.id)
        await ctx.send(
            f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is no longer a global tag.",
        )


async def setup(bot):
    await bot.add_cog(TagsSlash(bot))
