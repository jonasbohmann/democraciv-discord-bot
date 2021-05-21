import discord
import datetime

from discord.ext import commands

from bot.utils import context, text


class _Log(context.CustomCog):
    hidden = True

    async def log_event(
        self,
        guild: discord.Guild,
        title: str,
        fields: dict,
        thumbnail: str = None,
        to_owner: bool = False,
        reason: str = None,
    ):

        if guild is None:
            return

        if not await self.bot.get_guild_setting(guild.id, "logging_enabled"):
            return

        if reason:
            if not await self.bot.get_guild_setting(guild.id, reason):
                return

        embed = text.SafeEmbed(title=title)

        for field in fields:
            embed.add_field(name=field, value=fields[field][0], inline=fields[field][1])

        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)

        # Send event embed to log channel
        log_channel = await self.bot.get_logging_channel(guild)

        if log_channel is not None:
            await log_channel.send(embed=embed)

        if to_owner:
            embed.add_field(
                name="Guild", value=f"{guild.name} ({guild.id})", inline=False
            )
            await self.bot.owner.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild is None:
            return

        if await self.bot.is_channel_excluded(before.guild.id, before.channel.id):
            return

        if not before.content or not after.content or before.content == after.content:
            return

        embed_fields = {
            "Author": [f"{before.author.mention} {before.author}", False],
            "Channel": [before.channel.mention, True],
            "Jump": [f"[Link]({before.jump_url})", True],
            "Before": [before.content, False],
            "After": [after.content, False],
        }

        await self.log_event(
            before.guild,
            ":pencil2:  Message Edited",
            embed_fields,
            reason="logging_message_edit",
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild is None:
            return

        if await self.bot.is_channel_excluded(message.guild.id, message.channel.id):
            return

        embed_fields = {
            "Author": [f"{message.author.mention} {message.author}", True],
            "Channel": [message.channel.mention, False],
        }

        if message.content:
            embed_fields["Message"] = [message.content, False]

        await self.log_event(
            message.guild,
            ":wastebasket:  Message Deleted",
            embed_fields,
            reason="logging_message_delete",
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = self.bot.get_guild(payload.guild_id)

        if await self.bot.is_channel_excluded(guild.id, payload.channel_id):
            return

        channel = self.bot.get_channel(payload.channel_id)

        embed_fields = {
            "Amount": [len(payload.message_ids), True],
            "Channel": [channel.mention, True],
        }

        await self.log_event(
            guild,
            ":wastebasket: :wastebasket:  Bulk of Messages Deleted",
            embed_fields,
            reason="logging_message_delete",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed_fields = {
            "Person": [f"{member.mention} {member}", False],
            "ID": [member.id, False],
        }

        await self.log_event(
            member.guild,
            ":tada:  Person Joined",
            embed_fields,
            thumbnail=member.avatar_url_as(static_format="png"),
            reason="logging_member_join_leave",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed_fields = {"Person": [member, False], "ID": [member.id, False]}

        await self.log_event(
            member.guild,
            ":no_pedestrians:  Person Left",
            embed_fields,
            thumbnail=member.avatar_url_as(static_format="png"),
            reason="logging_member_join_leave",
        )

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.display_name != after.display_name:
            embed_fields = {
                "Person": [f"{before.mention} {before}", False],
                "Before": [before.display_name, False],
                "After": [after.display_name, False],
            }

            await self.log_event(
                before.guild,
                ":arrows_counterclockwise:  Nickname Changed",
                embed_fields,
                thumbnail=before.avatar_url_as(static_format="png"),
                reason="logging_member_nickname_change",
            )

        elif before.roles != after.roles:
            if len(before.roles) < len(after.roles):
                given_role = "*invalid role*"

                for x in after.roles:
                    if x not in before.roles:
                        given_role = x.name
                        break

                embed_fields = {
                    "Person": [f"{before.mention} {before}", False],
                    "Role": [given_role, False],
                }

                await self.log_event(
                    before.guild,
                    ":sunglasses:  Role given to Person",
                    embed_fields,
                    thumbnail=before.avatar_url_as(static_format="png"),
                    reason="logging_member_role_change",
                )

            elif len(before.roles) > len(after.roles):
                removed_role = "*invalid role*"

                for x in before.roles:
                    if x not in after.roles:
                        removed_role = x.name
                        break

                embed_fields = {
                    "Person": [f"{before.mention} {before}", False],
                    "Role": [removed_role, False],
                }

                await self.log_event(
                    before.guild,
                    ":zipper_mouth:  Role removed from Person",
                    embed_fields,
                    thumbnail=before.avatar_url_as(static_format="png"),
                    reason="logging_member_role_change",
                )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        embed_fields = {"Name": [user, True]}

        await self.log_event(
            guild,
            ":no_entry:  Person Banned",
            embed_fields,
            thumbnail=user.avatar_url_as(static_format="png"),
            to_owner=True,
            reason="logging_ban_unban",
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        embed_fields = {"Name": [user, True]}

        await self.log_event(
            guild,
            ":dove:  Person Unbanned",
            embed_fields,
            thumbnail=user.avatar_url_as(static_format="png"),
            to_owner=True,
            reason="logging_ban_unban",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        # Handle exception if bot was just added to new guild
        try:
            embed_fields = {
                "Role": [role.name, True],
                "Colour": [role.colour, True],
                "ID": [role.id, False],
            }

            await self.log_event(
                role.guild,
                ":new:  Role Created",
                embed_fields,
                reason="logging_role_create_delete",
            )

        except TypeError:
            return

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        embed_fields = {
            "Role": [role.name, True],
            "Created On": [
                datetime.datetime.strftime(role.created_at, "%B %d, %Y"),
                True,
            ],
            "ID": [role.id, False],
        }

        await self.log_event(
            role.guild,
            ":exclamation:  Role Deleted",
            embed_fields,
            reason="logging_role_create_delete",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed_fields = {
            "Name": [channel.mention, True],
            "Category": [channel.category, True],
        }

        await self.log_event(
            channel.guild,
            ":new:  Channel Created",
            embed_fields,
            reason="logging_guild_channel_create_delete",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed_fields = {
            "Name": [channel.name, True],
            "Category": [channel.category, True],
        }

        await self.log_event(
            channel.guild,
            ":exclamation:  Channel Deleted",
            embed_fields,
            reason="logging_guild_channel_create_delete",
        )

    async def on_guild_remove(self, guild):
        await self.bot.owner.send(
            f":warning:  I was removed from {guild.name} ({guild.id})."
        )


def setup(bot):
    bot.add_cog(_Log(bot))
