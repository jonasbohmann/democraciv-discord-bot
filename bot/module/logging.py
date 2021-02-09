import discord
import datetime

from discord.ext import commands

from bot.utils import context, text


class Log(context.CustomCog):
    hidden = True

    async def log_event(
        self,
        guild: discord.Guild,
        title: str,
        fields: dict,
        thumbnail: str = None,
        to_owner: bool = False,
    ):

        if guild is None:
            return

        if not await self.bot.get_guild_setting(guild.id, "logging_enabled"):
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
            embed.add_field(name="Guild", value=f"{guild.name} ({guild.id})", inline=False)
            await self.bot.owner.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild is None:
            return

        if not await self.bot.is_channel_excluded(before.guild.id, before.channel.id):
            if not before.clean_content or not after.clean_content:
                return

            if before.content == after.content:
                return

            if before.embeds or after.embeds:
                return

            embed_fields = {
                "Author": [f"{before.author.mention} {before.author}", False],
                "Channel": [before.channel.mention, True],
                "Jump": [f"[Link]({before.jump_url})", True],
                "Before": [before.content, False],
                "After": [after.content, False],
            }

            await self.log_event(before.guild, ":pencil2:  Message Edited", embed_fields)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild is None:
            return

        if not await self.bot.is_channel_excluded(message.guild.id, message.channel.id):
            embed_fields = {
                "Author": [f"{message.author.mention} {message.author}", True],
                "Channel": [message.channel.mention, False],
            }

            if message.content:
                embed_fields["Message"] = [message.content, False]

            await self.log_event(message.guild, ":wastebasket:  Message Deleted", embed_fields)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = self.bot.get_guild(payload.guild_id)

        if not await self.bot.is_channel_excluded(guild.id, payload.channel_id):
            channel = self.bot.get_channel(payload.channel_id)

            embed_fields = {
                "Amount": [len(payload.message_ids), True],
                "Channel": [channel.mention, True],
            }

            await self.log_event(
                guild,
                ":wastebasket: :wastebasket:  Bulk of Messages Deleted",
                embed_fields,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed_fields = {
            "Member": [f"{member.mention} {member}", False],
            "ID": [member.id, False],
        }

        await self.log_event(
            member.guild,
            ":tada:  Member Joined",
            embed_fields,
            thumbnail=member.avatar_url_as(static_format="png"),
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed_fields = {"Name": [member, False], "ID": [member.id, False]}

        await self.log_event(
            member.guild,
            ":no_pedestrians:  Member Left",
            embed_fields,
            thumbnail=member.avatar_url_as(static_format="png"),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.display_name != after.display_name:
            if not await self.bot.get_guild_setting(before.guild.id, "logging_enabled"):
                return

            embed_fields = {
                "Member": [f"{before.mention} {before}", False],
                "Before": [before.display_name, False],
                "After": [after.display_name, False],
            }

            await self.log_event(
                before.guild,
                ":arrows_counterclockwise:  Nickname Changed",
                embed_fields,
                thumbnail=before.avatar_url_as(static_format="png"),
            )

        elif before.roles != after.roles:
            if not await self.bot.get_guild_setting(before.guild.id, "logging_enabled"):
                return

            if len(before.roles) < len(after.roles):
                given_role = "*invalid role*"

                for x in after.roles:
                    if x not in before.roles:
                        given_role = x.name
                        break

                embed_fields = {
                    "Member": [f"{before.mention} {before}", False],
                    "Role": [given_role, False],
                }

                await self.log_event(
                    before.guild,
                    ":sunglasses:  Role given to Member",
                    embed_fields,
                    thumbnail=before.avatar_url_as(static_format="png"),
                )

            elif len(before.roles) > len(after.roles):
                removed_role = "*invalid role*"

                for x in before.roles:
                    if x not in after.roles:
                        removed_role = x.name
                        break

                embed_fields = {
                    "Member": [f"{before.mention} {before}", False],
                    "Role": [removed_role, False],
                }

                await self.log_event(
                    before.guild,
                    ":zipper_mouth:  Role removed from Member",
                    embed_fields,
                    thumbnail=before.avatar_url_as(static_format="png"),
                )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        embed_fields = {"Name": [user, True]}

        await self.log_event(
            guild,
            ":no_entry:  Member Banned",
            embed_fields,
            thumbnail=user.avatar_url_as(static_format="png"),
            to_owner=True,
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        embed_fields = {"Name": [user, True]}

        await self.log_event(
            guild,
            ":dove:  Member Unbanned",
            embed_fields,
            thumbnail=user.avatar_url_as(static_format="png"),
            to_owner=True,
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

            await self.log_event(role.guild, ":new:  Role Created", embed_fields)

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

        await self.log_event(role.guild, ":exclamation:  Role Deleted", embed_fields)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed_fields = {
            "Name": [channel.mention, True],
            "Category": [channel.category, True],
        }

        await self.log_event(channel.guild, ":new:  Channel Created", embed_fields)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed_fields = {
            "Name": [channel.name, True],
            "Category": [channel.category, True],
        }

        await self.log_event(channel.guild, ":exclamation:  Channel Deleted", embed_fields)

    async def on_guild_remove(self, guild):
        await self.bot.owner.send(f":warning:  I was removed from {guild.name} ({guild.id}).")


def setup(bot):
    bot.add_cog(Log(bot))
