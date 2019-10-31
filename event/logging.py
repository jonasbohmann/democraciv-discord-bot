import config
import discord
import datetime

from discord.ext import commands
from util.embed import embed_builder


# -- logging.py | event.logging --
#
# Logging module.
#


class Log(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -- Message Events --

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        guild = before.guild

        if before.content == after.content:
            return
        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(before.channel.id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                if not before.clean_content or not after.clean_content:  # Removing this throws a http
                    # 400 bad request exception
                    return
                elif before.clean_content and after.clean_content:
                    channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = embed_builder(title=':pencil2: Message Edited', description="")
                    embed.add_field(name='Author',
                                    value=before.author.mention + ' ' + before.author.name + '#'
                                          + before.author.discriminator,
                                    inline=True)
                    embed.add_field(name='Channel', value=before.channel.mention, inline=True)
                    embed.add_field(name='Before', value=before.clean_content, inline=False)
                    embed.add_field(name='After', value=after.clean_content, inline=False)
                    embed.timestamp = datetime.datetime.utcnow()
                    await channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        guild = message.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(message.channel.id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = embed_builder(title=':wastebasket: Message Deleted', description="")
                embed.add_field(name='Author',
                                value=message.author.mention + ' ' + message.author.name + '#'
                                      + message.author.discriminator,
                                inline=True)
                embed.add_field(name='Channel', value=message.channel.mention, inline=True)

                if not message.embeds:
                    # If the deleted message is an embed, sending this new embed will raise an error as
                    # message.clean_content does not work with embeds
                    embed.add_field(name='Message', value=message.clean_content, inline=False)

                embed.timestamp = datetime.datetime.utcnow()
                await channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = self.bot.get_guild(payload.guild_id)

        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(payload.channel_id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                channel = self.bot.get_channel(payload.channel_id)
                log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = embed_builder(title=':wastebasket: :wastebasket: Bulk of Messages Deleted', description="")
                embed.add_field(name='Amount',
                                value=f'{len(payload.message_ids)}\n', inline=True)
                embed.add_field(name='Channel',
                                value=channel.mention, inline=True)
                embed.timestamp = datetime.datetime.utcnow()
                await log_channel.send(embed=embed)
            else:
                return
        return

    # -- Member Events --

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild

        if config.getGuildConfig(guild.id)['enableWelcomeMessage']:
            information_channel = discord.utils.get(guild.text_channels, name='information')
            help_channel = discord.utils.get(guild.text_channels, name='help')
            welcome_channel = discord.utils.get(guild.text_channels,
                                                name=config.getGuildConfig(guild.id)['welcomeChannel'])

            # General case without mentioning anything in "{}" from the config's welcome_message
            if information_channel is None or help_channel is None:
                welcome_message = config.getStrings(guild.id)['welcomeMessage'].format(member=member.mention)

            # Democraciv-specific case with mentioning {}'s
            else:
                welcome_message = config.getStrings(guild.id)['welcomeMessage'].format(member=member.mention,
                                                                                       guild=guild.name,
                                                                                       information=information_channel.mention,
                                                                                       help=help_channel.mention)
            await welcome_channel.send(welcome_message)

        if config.getGuildConfig(guild.id)['enableLogging']:
            guild = member.guild
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':tada: Member Joined', description="")
            embed.add_field(name='Member', value=member.mention)
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.add_field(name='ID', value=member.id)
            embed.add_field(name='Mobile', value=member.is_on_mobile())
            embed.set_thumbnail(url=member.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await log_channel.send(embed=embed)

        return

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':no_pedestrians: Member Left', description="")
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.set_thumbnail(url=member.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        guild = before.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            if before.display_name != after.display_name:
                log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = embed_builder(title=':arrows_counterclockwise: Nickname Changed', description="")
                embed.add_field(name='Member', value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                inline=False)
                embed.add_field(name='Before', value=before.display_name)
                embed.add_field(name='After', value=after.display_name)
                embed.set_thumbnail(url=before.avatar_url)
                embed.timestamp = datetime.datetime.utcnow()
                await log_channel.send(embed=embed)

            if before.roles != after.roles:

                if len(before.roles) < len(after.roles):
                    for x in after.roles:
                        if x not in before.roles:
                            given_role = x.name
                    guild = before.guild
                    log_channel = discord.utils.get(guild.text_channels,
                                                    name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = embed_builder(title=':sunglasses: Role given to Member', description="")
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=given_role)
                    embed.set_thumbnail(url=before.avatar_url)
                    embed.timestamp = datetime.datetime.utcnow()
                    await log_channel.send(embed=embed)

                if len(before.roles) > len(after.roles):
                    for x in before.roles:
                        if x not in after.roles:
                            removed_role = x.name
                    guild = before.guild
                    log_channel = discord.utils.get(guild.text_channels,
                                                    name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = embed_builder(title=':zipper_mouth: Role removed from Member', description="")
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=removed_role)
                    embed.set_thumbnail(url=before.avatar_url)
                    embed.timestamp = datetime.datetime.utcnow()
                    await log_channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':no_entry: Member Banned', description="")
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':dove: Member Unbanned', description="")
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(embed=embed)
        return

    # -- Guild Events --

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        introduction_channel = guild.text_channels[0]

        # Alert owner of this bot that the bot was invited to some place
        owner_user = self.bot.get_user(int(config.getConfig()['authorID']))
        await owner_user.create_dm()
        owner_dm_channel = owner_user.dm_channel
        await owner_dm_channel.send(f":warning: I was added to {guild.name} ({guild.id}). Here are some invites:")

        # Get invite for new guild to send to owner_dm_channel
        guild_invites = await guild.invites()
        try:
            guild_invite_1 = str(guild_invites[0])
            await owner_dm_channel.send(guild_invite_1)
        except IndexError as e:
            pass

        # Send introduction message to random guild channel
        embed = embed_builder(title=':two_hearts: Hey there!', description="Thanks for inviting me!\n\nYou can check "
                                                                           "`-help` to get some more information "
                                                                           "about me.")

        await introduction_channel.send(embed=embed)

        return

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':new: Role Created', description="")
            embed.add_field(name='Role', value=role.name)
            embed.add_field(name='Colour', value=role.colour)
            embed.add_field(name='ID', value=role.id, inline=False)
            embed.timestamp = datetime.datetime.utcnow()
            await log_channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':exclamation: Role Deleted', description="")
            embed.add_field(name='Role', value=role.name)
            embed.add_field(name='Creation Date',
                            value=datetime.datetime.strftime(role.created_at, "%d.%m.%Y, %H:%M:%S"))
            embed.add_field(name='ID', value=role.id, inline=False)
            embed.timestamp = datetime.datetime.utcnow()
            await log_channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':new: Channel Created', description="")
            embed.add_field(name='Name', value=channel.mention)
            embed.add_field(name='Category', value=channel.category)
            embed.timestamp = datetime.datetime.utcnow()
            await log_channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = embed_builder(title=':exclamation: Channel Deleted', description="")
            embed.add_field(name='Name', value=channel.name)
            embed.add_field(name='Category', value=channel.category)
            embed.timestamp = datetime.datetime.utcnow()
            await log_channel.send(embed=embed)
        return


def setup(bot):
    bot.add_cog(Log(bot))
