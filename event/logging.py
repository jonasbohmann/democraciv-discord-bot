import config
import discord
import datetime


# -- logging.py | event.logging --
#
# Logging module.
#


class Log:
    def __init__(self, bot):
        self.bot = bot

    # -- Message Events --

    async def on_message_edit(self, before, after):
        if before.content == after.content:
            return
        if config.getConfig()['enableLogging']:
            if str(before.channel.id) not in config.getConfig()['excludedChannelsFromLogging']:
                if not before.clean_content or not after.clean_content:  # Removing this throws a http 400 bad request exception
                    return
                elif before.clean_content and after.clean_content:
                    guild = before.guild
                    channel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                    embed = discord.Embed(title=':pencil2: Message Edited', colour=0x7f0000)
                    embed.add_field(name='Author',
                                    value=before.author.mention + ' ' + before.author.name + '#' + before.author.discriminator,
                                    inline=True)
                    embed.add_field(name='Channel', value=before.channel.mention, inline=True)
                    embed.add_field(name='Before', value=before.clean_content, inline=False)
                    embed.add_field(name='After', value=after.clean_content, inline=False)
                    embed.timestamp = datetime.datetime.utcnow()
                    embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                    await channel.send(embed=embed)
            else:
                return
        return

    async def on_message_delete(self, message):
        if config.getConfig()['enableLogging']:
            if str(message.channel.id) not in config.getConfig()['excludedChannelsFromLogging']:
                guild = message.guild
                channel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                embed = discord.Embed(title=':wastebasket: Message Deleted', colour=0x7f0000)
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.add_field(name='Author',
                                value=message.author.mention + ' ' + message.author.name + '#' + message.author.discriminator,
                                inline=True)
                embed.add_field(name='Channel', value=message.channel.mention, inline=True)
                embed.add_field(name='Message', value=message.clean_content, inline=False)
                embed.timestamp = datetime.datetime.utcnow()
                await channel.send(content=None, embed=embed)
            else:
                return
        return

    async def on_raw_bulk_message_delete(self, payload):
        if config.getConfig()['enableLogging']:
            if str(payload.channel_id) not in config.getConfig()['excludedChannelsFromLogging']:
                guild = self.bot.get_guild(payload.guild_id)
                channel = self.bot.get_channel(payload.channel_id)
                logchannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                embed = discord.Embed(title=':wastebasket: :wastebasket: Bulk of Messages Deleted', colour=0x7f0000)
                embed.add_field(name='Amount',
                                value=f'{len(payload.message_ids)}\n', inline=True)
                embed.add_field(name='Channel',
                                value=channel.mention, inline=True)
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                await logchannel.send(content=None, embed=embed)
            else:
                return
        return

    # -- Member Events --

    async def on_member_join(self, member):
        if config.getConfig()['enableWelcomeMessage']:
            guild = member.guild
            welcomeChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['welcomeChannel'])
            welcomeMessage = config.getStrings()['welcomeMessage'].format(member=member.mention, guild=guild.name)
            await welcomeChannel.send(welcomeMessage)
        if config.getConfig()['enableLogging']:
            guild = member.guild
            logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':tada: Member Joined', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Member', value=member.mention)
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.add_field(name='ID', value=member.id)
            embed.add_field(name='Mobile', value=member.is_on_mobile())
            embed.set_thumbnail(url=member.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await logChannel.send(content=None, embed=embed)
        return

    async def on_member_remove(self, member):
        if config.getConfig()['enableLogging']:
            guild = member.guild
            channel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':no_pedestrians: Member Left', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.set_thumbnail(url=member.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
        return

    async def on_member_update(self, before, after):
        if config.getConfig()['enableLogging']:
            if before.display_name != after.display_name:
                guild = before.guild
                logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                embed = discord.Embed(title=':arrows_counterclockwise: Nickname Changed', colour=0x7f0000)
                embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                embed.add_field(name='Member', value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                inline=False)
                embed.add_field(name='Before', value=before.display_name)
                embed.add_field(name='After', value=after.display_name)
                embed.set_thumbnail(url=before.avatar_url)
                embed.timestamp = datetime.datetime.utcnow()
                await logChannel.send(content=None, embed=embed)

            if before.roles != after.roles:

                if len(before.roles) < len(after.roles):
                    for x in after.roles:
                        if x not in before.roles:
                            givenRole = x.name
                    guild = before.guild
                    logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                    embed = discord.Embed(title=':sunglasses: Role given to Member', colour=0x7f0000)
                    embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=givenRole)
                    embed.set_thumbnail(url=before.avatar_url)
                    embed.timestamp = datetime.datetime.utcnow()
                    await logChannel.send(content=None, embed=embed)

                if len(before.roles) > len(after.roles):
                    for x in before.roles:
                        if x not in after.roles:
                            removedRole = x.name
                    guild = before.guild
                    logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
                    embed = discord.Embed(title=':zipper_mouth: Role removed from Member', colour=0x7f0000)
                    embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=removedRole)
                    embed.set_thumbnail(url=before.avatar_url)
                    embed.timestamp = datetime.datetime.utcnow()
                    await logChannel.send(content=None, embed=embed)
            else:
                return
        return

    async def on_member_ban(self, guild, user):
        if config.getConfig()['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':no_entry: Member Banned', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
        return

    async def on_member_unban(self, guild, user):
        if config.getConfig()['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':dove: Member Unbanned', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            embed.timestamp = datetime.datetime.utcnow()
            await channel.send(content=None, embed=embed)
        return

    # -- Guild Events --

    async def on_guild_role_create(self, role):
        if config.getConfig()['enableLogging']:
            guild = role.guild
            logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':new: Role Created', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Role', value=role.name)
            embed.add_field(name='Colour', value=role.colour)
            embed.add_field(name='ID', value=role.id, inline=False)
            embed.timestamp = datetime.datetime.utcnow()
            await logChannel.send(content=None, embed=embed)
        return

    async def on_guild_role_delete(self, role):
        if config.getConfig()['enableLogging']:
            guild = role.guild
            logChannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':exclamation: Role Deleted', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Role', value=role.name)
            embed.add_field(name='Creation Date',
                            value=datetime.datetime.strftime(role.created_at, "%d.%m.%Y, %H:%M:%S"))
            embed.add_field(name='ID', value=role.id, inline=False)
            embed.timestamp = datetime.datetime.utcnow()
            await logChannel.send(content=None, embed=embed)
        return

    async def on_guild_channel_create(self, channel):
        if config.getConfig()['enableLogging']:
            guild = channel.guild
            logchannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':new: Channel Created', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Name', value=channel.mention)
            embed.add_field(name='Category', value=channel.category)
            embed.timestamp = datetime.datetime.utcnow()
            await logchannel.send(content=None, embed=embed)
        return

    async def on_guild_channel_delete(self, channel):
        if config.getConfig()['enableLogging']:
            guild = channel.guild
            logchannel = discord.utils.get(guild.text_channels, name=config.getConfig()['logChannel'])
            embed = discord.Embed(title=':exclamation: Channel Deleted', colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            embed.add_field(name='Name', value=channel.name)
            embed.add_field(name='Category', value=channel.category)
            embed.timestamp = datetime.datetime.utcnow()
            await logchannel.send(content=None, embed=embed)
        return


def setup(bot):
    bot.add_cog(Log(bot))
