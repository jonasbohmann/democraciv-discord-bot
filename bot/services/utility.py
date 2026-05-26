import dataclasses
import datetime
import operator
import typing

import discord

from bot.services.context import CommandContextProtocol


@dataclasses.dataclass
class WhoisResult:
    person: typing.Union[discord.Member, discord.User]
    outside_server: bool
    join_date: typing.Optional[datetime.datetime] = None
    join_position: typing.Optional[int] = None
    max_members: typing.Optional[int] = None
    role_mentions: typing.Optional[str] = None
    role_count: typing.Optional[int] = None


@dataclasses.dataclass
class RoleInfoResult:
    role: discord.Role
    description: str
    role_name: str
    role_members: str


@dataclasses.dataclass
class VeteransResult:
    guild_name: str
    guild_icon: typing.Optional[str]
    veterans: typing.Sequence[
        typing.Optional[typing.Union[discord.Member, discord.User]]
    ]


class UtilityService:
    def __init__(self, bot):
        self.bot = bot
        self.cached_sorted_veterans_on_democraciv = []

    async def get_member_join_date(
        self, member: discord.Member
    ) -> typing.Optional[datetime.datetime]:
        if member.guild.id == self.bot.dciv.id:
            original_date = await self.bot.db.fetchval(
                "SELECT join_date FROM original_join_date WHERE member = $1",
                member.id,
            )
            if original_date is not None:
                return original_date

        return member.joined_at

    async def get_member_join_position(
        self,
        member: discord.Member,
        members: typing.Sequence[discord.Member],
    ) -> typing.Tuple[typing.Optional[int], int]:
        if member.guild.id == self.bot.dciv.id:
            sql = """SELECT position.row_number FROM
                       (SELECT member, ROW_NUMBER () OVER (ORDER BY join_date) AS row_number
                             FROM original_join_date
                       ) AS position
                      WHERE member = $1"""

            join_position = await self.bot.db.fetchval(sql, member.id)
            all_members = await self.bot.db.fetchval(
                "SELECT COUNT(member) FROM original_join_date"
            )

            if join_position:
                return join_position, all_members

        all_members = len(members)
        joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))

        if None in joins:
            return None, all_members

        try:
            return joins.index(member) + 1, all_members
        except ValueError:
            return None, all_members

    async def get_whois(
        self,
        ctx: CommandContextProtocol,
        person: typing.Union[discord.Member, discord.User],
    ) -> WhoisResult:
        result = WhoisResult(
            person=person,
            outside_server=not isinstance(person, discord.Member),
        )

        if not isinstance(person, discord.Member):
            return result

        join_pos, max_members = await self.get_member_join_position(
            person, ctx.guild.members
        )
        roles = [role.mention for role in person.roles[::-1] if not role.is_default()]

        result.join_position = join_pos
        result.max_members = max_members
        result.join_date = await self.get_member_join_date(person)
        result.role_mentions = ", ".join(roles) or "-"
        result.role_count = len(person.roles) - 1
        return result

    def get_role_info(
        self,
        ctx: CommandContextProtocol,
        role: discord.Role,
    ) -> RoleInfoResult:
        if role.guild.id != ctx.guild.id:
            description = (
                f":warning:  This role is from the {self.bot.dciv.name} server, "
                "not from this server!"
            )
            role_name = role.name
        else:
            description = ""
            role_name = f"{role.name} {role.mention}"

        if role != role.guild.default_role:
            role_members = (
                "\n".join([f"{member.mention} {member}" for member in role.members])
                or "-"
            )
        else:
            role_members = "*Too long to display.*"

        return RoleInfoResult(
            role=role,
            description=description,
            role_name=role_name,
            role_members=role_members,
        )

    async def get_veterans(self, ctx: CommandContextProtocol) -> VeteransResult:
        sorted_first_15_members = []

        if ctx.guild.id == self.bot.dciv.id:
            if self.cached_sorted_veterans_on_democraciv:
                sorted_first_15_members = self.cached_sorted_veterans_on_democraciv
            else:
                vets = await self.bot.db.fetch(
                    "SELECT member FROM original_join_date ORDER BY join_date LIMIT 15"
                )
                self.cached_sorted_veterans_on_democraciv = sorted_first_15_members = [
                    self.bot.get_user(record["member"]) for record in vets
                ]
        else:
            guild_members_without_bots = [
                member for member in ctx.guild.members if not member.bot
            ]
            guild_members_without_bots.sort(key=lambda member: member.joined_at)
            sorted_first_15_members = guild_members_without_bots[:15]

        return VeteransResult(
            guild_name=ctx.guild.name,
            guild_icon=ctx.guild_icon,
            veterans=sorted_first_15_members,
        )
