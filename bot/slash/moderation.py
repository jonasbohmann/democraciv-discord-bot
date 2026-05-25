import discord

from discord import app_commands
from discord.ext import commands

from bot.config import config, mk, token
from bot.slash import ui, checks as slash_checks, context as slash_context
from bot.utils import exceptions


class ModerationSlash(commands.Cog):
    moderation = app_commands.Group(
        name="moderation",
        description="Moderation links and tools.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    async def send_mod_link(
        self,
        ctx: slash_context.InteractionContext,
        *,
        title: str,
        url: str,
    ):

        url = url or "https://laws.democraciv.com/404"

        unsafe = True

        if isinstance(ctx.channel, discord.TextChannel):
            unsafe_members = [
                member
                for member in ctx.channel.members
                if not member.bot and not member.guild_permissions.administrator
            ]
            unsafe = len(ctx.channel.members) >= 20 or bool(unsafe_members)

        await ctx.send(
            view=ui.RichLayout(
                title=title,
                links=[ui.LayoutLink("Open", url, "\U0001f517")],
                author_id=ctx.author.id,
            ),
            ephemeral=unsafe,
        )

    @moderation.command(name="hub", description="Link to the Moderation Hub.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def hub(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="moderation hub")
        await self.send_mod_link(ctx, title="Moderation Hub", url=token.MOD_HUB)

    @moderation.command(name="registry", description="Link to the Democraciv Registry.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def registry(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="moderation registry"
        )
        await self.send_mod_link(ctx, title="Democraciv Registry", url=token.REGISTRY)

    @moderation.command(
        name="drive", description="Link to the Moderation Google Drive."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def drive(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="moderation drive"
        )
        await self.send_mod_link(
            ctx, title="Moderation Google Drive", url=token.MOD_DRIVE
        )

    @moderation.command(name="pin", description="Link to DerJonas' Election Tool.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def pin(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="moderation pin")
        await self.send_mod_link(
            ctx, title="DerJonas' Election Tool", url=token.PIN_TOOL
        )

    @moderation.command(
        name="guidelines",
        description="Link to DerJonas' Democraciv Moderation Guidelines & Procedures",
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def guidelines(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation guidelines",
        )
        await self.send_mod_link(
            ctx,
            title="DerJonas' Democraciv Moderation Guidelines & Procedures",
            url=token.MOD_GUIDELINES,
        )

    async def archive_channel_impl(
        self,
        ctx: slash_context.InteractionContext,
        *,
        channel: discord.TextChannel,
        archive_category: discord.CategoryChannel,
    ):
        archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")

        if archives_role is None:
            return await ctx.send(
                f"{config.NO} There is no role named `Archives` for me to use.",
                ephemeral=True,
            )

        everyone_perms = discord.PermissionOverwrite(
            read_message_history=False,
            send_messages=False,
            read_messages=False,
            add_reactions=False,
        )
        archive_perms = discord.PermissionOverwrite(
            read_message_history=True,
            send_messages=False,
            read_messages=True,
            add_reactions=False,
        )

        await channel.edit(
            name=(
                f"mk{self.bot.mk.MARK}-{channel.name}"
                if not channel.name.startswith(f"mk{self.bot.mk.MARK}-")
                else channel.name
            ),
            overwrites={
                self.bot.dciv.default_role: everyone_perms,
                archives_role: archive_perms,
            },
            category=archive_category,
        )
        await self.bot.db.execute(
            "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
            channel.guild.id,
            channel.id,
        )

    @moderation.command(
        name="archive-channel", description="Archive a MK-specific channel."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archive_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        archive_category: discord.CategoryChannel,
    ):

        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation archive-channel",
        )

        await ctx.defer()
        await self.archive_channel_impl(
            ctx,
            channel=channel,
            archive_category=archive_category,
        )

        await ctx.send(f"{config.YES} Channel was archived.")

    @moderation.command(
        name="archive-category",
        description="Archive every text channel in a MK-specific category.",
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archive_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        archive_category: discord.CategoryChannel,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation archive-category",
        )

        await ctx.defer()

        confirmed = await ui.confirm(
            ctx,
            title=f"Archive {category.name}",
            body=f"Archive every channel in `{category}`?",
            confirm_label="Archive",
        )

        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        for channel in category.text_channels:
            await channel.send(
                f":tada: Thanks for playing Democraciv MK{self.bot.mk.MARK}!"
            )
            await self.archive_channel_impl(
                ctx,
                channel=channel,
                archive_category=archive_category,
            )

        await ctx.send(f"{config.YES} Done.")


async def setup(bot):
    await bot.add_cog(ModerationSlash(bot))
