import dataclasses
import typing

import asyncpg
import discord

from bot.config import config
from bot.services.context import CommandContextProtocol
from bot.services.results import OperationResult
from bot.utils import converter, exceptions


@dataclasses.dataclass
class SelfroleRoleResolution:
    role: discord.Role
    created: bool


class SelfroleService:
    def __init__(self, bot):
        self.bot = bot

    async def list_roles(
        self, ctx: CommandContextProtocol
    ) -> typing.List[discord.Role]:
        role_list = await self.bot.db.fetch(
            "SELECT role_id FROM selfrole WHERE guild_id = $1", ctx.guild.id
        )
        roles = []

        for record in role_list:
            role = ctx.guild.get_role(record["role_id"])
            if role is not None:
                roles.append(role)

        return roles

    async def toggle_role(
        self,
        ctx: CommandContextProtocol,
        *,
        selfrole: converter.Selfrole,
    ) -> OperationResult:
        if not isinstance(ctx.author, discord.Member):
            raise exceptions.DemocracivBotException(
                f"{config.NO} This command can only be used in a server."
            )

        if selfrole.role not in ctx.author.roles:
            try:
                await ctx.author.add_roles(selfrole.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.ADD_ROLE, selfrole.role.name
                )

            return OperationResult(message=f"{config.YES} {selfrole.join_message}")

        try:
            await ctx.author.remove_roles(selfrole.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.REMOVE_ROLE, selfrole.role.name
            )

        return OperationResult(
            message=f"{config.YES} The `{selfrole.role.name}` role was removed from you."
        )

    async def resolve_role(
        self,
        ctx: CommandContextProtocol,
        *,
        role: typing.Union[str, discord.Role],
    ) -> SelfroleRoleResolution:
        if isinstance(role, discord.Role):
            return SelfroleRoleResolution(role=role, created=False)

        role_name = (role or "").strip()
        discord_role = discord.utils.find(
            lambda candidate: candidate.name.lower() == role_name.lower(),
            ctx.guild.roles,
        )

        if discord_role is not None:
            return SelfroleRoleResolution(role=discord_role, created=False)

        if not role_name:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Provide an existing or new role name."
            )

        try:
            discord_role = await ctx.guild.create_role(name=role_name)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.CREATE_ROLE, role_name
            )

        return SelfroleRoleResolution(role=discord_role, created=True)

    async def upsert_role(
        self,
        ctx: CommandContextProtocol,
        *,
        role: discord.Role,
        join_message: str,
    ) -> OperationResult:
        try:
            await self.bot.db.execute(
                "INSERT INTO selfrole (guild_id, role_id, join_message) VALUES ($1, $2, $3) "
                "ON CONFLICT (guild_id, role_id) DO UPDATE SET join_message = $3",
                ctx.guild.id,
                role.id,
                join_message,
            )
        except asyncpg.UniqueViolationError:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} `{role.name}` is already a selfrole on this server."
            )

        return OperationResult(
            message=f"{config.YES} `{role.name}` was added as a selfrole."
        )

    async def create_role(
        self,
        ctx: CommandContextProtocol,
        *,
        role_name: str,
        join_message: str,
    ) -> OperationResult:
        resolution = await self.resolve_role(ctx, role=role_name)
        return await self.upsert_role(
            ctx, role=resolution.role, join_message=join_message
        )

    async def edit_role(
        self,
        ctx: CommandContextProtocol,
        *,
        selfrole: converter.Selfrole,
        join_message: str,
    ) -> OperationResult:
        await self.bot.db.execute(
            "UPDATE selfrole SET join_message = $1 WHERE guild_id = $2 AND role_id = $3",
            join_message,
            ctx.guild.id,
            selfrole.role.id,
        )
        return OperationResult(
            message=(
                f"{config.YES} The join message for `{selfrole.role.name}` was updated."
            )
        )

    async def delete_role(
        self,
        ctx: CommandContextProtocol,
        *,
        selfrole: converter.Selfrole,
        hard_delete: bool,
        display_name: str = None,
    ) -> OperationResult:
        role_name = display_name or selfrole.role.name

        await self.bot.db.execute(
            "DELETE FROM selfrole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            selfrole.role.id,
        )

        if hard_delete:
            try:
                await selfrole.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.DELETE_ROLE, detail=selfrole.role.name
                )

            return OperationResult(
                message=(
                    f"{config.YES} The `{role_name}` selfrole and its Discord role "
                    "were deleted."
                )
            )

        return OperationResult(
            message=(
                f"{config.YES} The `{role_name}` selfrole was removed from the "
                f"`{config.BOT_PREFIX}roles` list but I did not delete its Discord role."
            )
        )
