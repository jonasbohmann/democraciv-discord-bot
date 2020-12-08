import collections

import discord
from discord.ext import commands, menus

from bot.config import config, mk
from bot.utils import context, checks, paginator, text, mixin, exceptions
from bot.utils.converter import (
    CaseInsensitiveMember, CaseInsensitiveRole, CaseInsensitiveCategoryChannel,
    CaseInsensitiveTextChannel, DemocracivCaseInsensitiveRole
)


class NationRoleConverter(CaseInsensitiveRole):
    async def convert(self, ctx: context.CustomContext, argument):
        if not ctx.bot.mk.NATION_ROLE_PREFIX:
            raise exceptions.DemocracivBotException(f"{config.NO} You can't use Nation Roles with this bot.")

        arg = argument.lower()
        prefix = ctx.bot.mk.NATION_ROLE_PREFIX.lower()

        if arg.startswith(prefix):
            real_arg = arg

        elif arg.startswith(prefix[:-2]):
            real_arg = arg.replace(prefix[:-2], prefix)

        else:
            real_arg = f"{ctx.bot.mk.NATION_ROLE_PREFIX}{argument}"

        role = await super().convert(ctx, real_arg)

        if not role.name.lower().startswith(ctx.bot.mk.NATION_ROLE_PREFIX.lower()):
            raise commands.BadArgument(f"{config.NO} You're not allowed to give someone the `{role.name}` role.")

        return role


class CIMemberNoBot(CaseInsensitiveMember):
    async def convert(self, ctx, argument):
        member = await super().convert(ctx, argument)

        if member.bot:
            raise commands.BadArgument(f"{config.NO} You cannot give Nation Roles to bots.")

        return member


def nation_role_prefix_not_blank():
    def wrapper(ctx):
        if not ctx.bot.mk.NATION_ROLE_PREFIX:
            raise exceptions.DemocracivBotException(f"{config.NO} You can't use Nation Roles with this bot.")
        else:
            return True

    return commands.check(wrapper)


class PermissionSelectorMenu(menus.Menu):
    def __init__(self, *, role, channel, overwrites):
        self.role = role
        self.channel = channel
        self.overwrites = overwrites
        super().__init__(timeout=120.0, delete_message_after=True)
        self._make_result()

    def _make_result(self):
        self.result = collections.namedtuple("PermissionSelectorResult", ["confirmed", "result"])
        self.result.confirmed = False
        self.result.result = {"read": False, "send": False}
        return self.result

    async def send_initial_message(self, ctx, channel):
        read = "Deny" if self.overwrites.read_messages else "Allow"
        send = "Deny" if self.overwrites.send_messages else "Allow"
        embed = text.SafeEmbed(
            title=f"{config.USER_INTERACTION_REQUIRED}  Which Permissions in #{self.channel.name} do you want "
                  f"to change?",
            description=f"Select as many things as you want, then click the {config.YES} button to continue, "
                        f"or {config.NO} to cancel.\n\n"
                        f":one: {read} Read Messages Permission for `{self.role.name}` in {self.channel.mention}\n"
                        f":two: {send} Send Messages Permission for `{self.role.name}` in {self.channel.mention}"
        )
        return await ctx.send(embed=embed)

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_first_choice(self, payload):
        self.result.result["read"] = not self.result.result["read"]

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_second_choice(self, payload):
        self.result.result["send"] = not self.result.result["send"]

    @menus.button(config.YES)
    async def confirm(self, payload):
        self.result.confirmed = True
        self.stop()

    @menus.button(config.NO)
    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class Nation(context.CustomCog, mixin.GovernmentMixin):
    """Useful commands for Nation Admins to manage their nation in Multiciv."""

    @commands.group(name="nation", aliases=['civ', 'n'], case_insensitive=True, invoke_without_command=True)
    async def nation(self, ctx):
        """{NATION_NAME}"""

        description = ""
        nation_wiki = "ottoman"

        embed = text.SafeEmbed(description=f"{description}\n\n[Constitution]({self.bot.mk.CONSTITUTION})\n"
                                           f"[Wiki](https://reddit.com/r/democraciv/wiki/{nation_wiki})")
        embed.set_author(name=self.bot.mk.NATION_NAME, icon_url=self.bot.mk.safe_flag)

        try:
            legislators = len(self.legislator_role.members)
        except exceptions.RoleNotFoundError:
            legislators = 0

        try:
            citizens = self.bot.get_democraciv_role(mk.DemocracivRole.NATION_CITIZEN)
            embed.add_field(name="Population", value=len(citizens.members))
        except exceptions.RoleNotFoundError:
            pass

        parties = await self.bot.db.fetchval("SELECT COUNT(id) FROM party")
        embed.add_field(name="Political Parties", value=parties)

        if isinstance(self.speaker, discord.Member):
            speaker = f"{self.bot.mk.speaker_term}: {self.speaker.mention}"
        else:
            speaker = f"{self.bot.mk.speaker_term}: -"

        if isinstance(self.prime_minister, discord.Member):
            prime_minister = f"{self.bot.mk.pm_term}: {self.prime_minister.mention}"
        else:
            prime_minister = f"{self.bot.mk.pm_term}: -"

        embed.add_field(name="Government",
                        value=f"{prime_minister}\n"
                              f"{speaker}\n"
                              f"Amount of {self.bot.mk.legislator_term}s: {legislators}",
                        inline=False)

        await ctx.send(embed=embed)

    @nation.command(name="admin")
    async def admin(self, ctx):
        """What is a Nation Admin?"""

        p = config.BOT_PREFIX

        embed = text.SafeEmbed(description=f"Nation Admins are allowed to make roles and "
                                           f"channels on the {self.bot.dciv.name} server that are "
                                           f"specific for their nation (`{p}help Nation`).\n\nAdditionally, they are "
                                           f"allowed to create, edit and delete political parties "
                                           f"(`{p}help Political Parties`).\n\nNation Admins can also pin messages "
                                           f"in every category that belongs to their nation.")

        embed.set_author(name=self.bot.mk.NATION_NAME, icon_url=self.bot.mk.safe_flag)

        role = self.bot.get_democraciv_role(mk.DemocracivRole.NATION_ADMIN)

        if role:
            fmt = [m.mention for m in role.members] or ['-']
            embed.add_field(name="Nation Admins", value="\n".join(fmt))

        await ctx.send(embed=embed)

    @nation.command(name="pin")
    @checks.moderation_or_nation_leader()
    async def pin(self, ctx, *, message: discord.Message):
        """Pin a message

        **Example**
            `{PREFIX}{COMMAND} 784598328666619934` use the message's ID *(only works if you use the command in the same channel as the message you want to pin)*
            `{PREFIX}{COMMAND} https://discord.com/channels/208984105310879744/499669824847478785/784598328666619934` use the message's URL

        """
        if message.channel.category_id not in self.bot.mk.NATION_CATEGORIES:
            raise exceptions.DemocracivBotException(f"{config.NO} You're not allowed to pin messages in this channel.")

        await message.pin()
        await ctx.send(f"{config.YES} Done.")

    @nation.group(name="roles", aliases=['role'], case_insensitive=True, invoke_without_command=True)
    @checks.moderation_or_nation_leader()
    @nation_role_prefix_not_blank()
    async def nationroles(self, ctx):
        """List all nation-specific roles that can be given out with `{PREFIX}nation roles toggle`"""

        predicate = lambda r: r.name.lower().startswith(self.bot.mk.NATION_ROLE_PREFIX.lower())
        found = filter(predicate, ctx.guild.roles)
        fmt = [r.mention for r in found]
        fmt.insert(0, f"These roles can be given out with `{config.BOT_PREFIX}nation roles toggle` by you.\n")

        pages = paginator.SimplePages(entries=fmt, author=f"Nation Roles",
                                      icon=self.bot.mk.safe_flag,
                                      empty_message="There are no roles that you can give out.")
        await pages.start(ctx)

    @nationroles.command(name="toggle")
    @checks.moderation_or_nation_leader()
    @nation_role_prefix_not_blank()
    async def toggle_role(self, ctx, people: commands.Greedy[CIMemberNoBot], *, role: NationRoleConverter):
        """Give someone a role, or remove one from them

        **Example**:
            `{PREFIX}{COMMAND} @DerJonas Builder` will give DerJonas the 'Rome - Builder' role
            `{PREFIX}{COMMAND} @DerJonas @Archwizard @Bird Builder` will give those 3 people the 'Rome - Builder' role"""

        if not people:
            raise commands.BadArgument()

        fmt = []

        for member in people:
            if role not in member.roles:
                await member.add_roles(role)
                fmt.append(f"`{role.name}` was given to {member}")
            else:
                await member.remove_roles(role)
                fmt.append(f"`{role.name}` was removed from {member}")

        fmt = "\n".join(fmt)
        await ctx.send(fmt)

    @nationroles.command(name="add", aliases=['create', 'make'])
    @checks.moderation_or_nation_leader()
    @nation_role_prefix_not_blank()
    async def create_new_nation_role(self, ctx, *, name: str = None):
        """Create a new nation-specific roles that can be given out with `{PREFIX}nation roles toggle`"""

        if not name:
            name = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} What should be the name of the new role?")

        if name.lower().startswith(self.bot.mk.NATION_ROLE_PREFIX.lower()):
            role_name = name
        else:
            role_name = f"{self.bot.mk.NATION_ROLE_PREFIX}{name}"

        role = await ctx.guild.create_role(name=role_name)
        await ctx.send(f"{config.YES} The role was created, you can now give it to people with "
                       f"`{config.BOT_PREFIX}nation roles toggle <person> {role.name}`.")

    @nationroles.command(name="delete", aliases=['remove'])
    @checks.moderation_or_nation_leader()
    @nation_role_prefix_not_blank()
    async def delete_nation_role(self, ctx, *, nation_role: NationRoleConverter):
        """Delete a nation role

        **Example**:
            `{PREFIX}{COMMAND} Rome - Builder` will delete the 'Rome - Builder' role"""

        name = nation_role.name
        await nation_role.delete()
        await ctx.send(f"{config.YES} `{name}` was deleted.")

    @nation.command(name="createchannel", aliases=['channel'])
    @checks.moderation_or_nation_leader()
    async def channel(self, ctx, *, category: CaseInsensitiveCategoryChannel = None):
        """Create a new channel in one of your nation's categories"""

        if not category:
            category = await ctx.converted_input(f"{config.USER_INTERACTION_REQUIRED} In which category should "
                                                 f"the channel be created?", return_input_on_fail=False,
                                                 converter=CaseInsensitiveCategoryChannel)

        if category.id not in self.bot.mk.NATION_CATEGORIES:
            return await ctx.send(f"{config.NO} The `{category.name}` category does not belong to your nation.")

        channel_name = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} What should be the name of the new channel?")

        channel = await category.create_text_channel(name=channel_name)
        await channel.edit(sync_permissions=True)
        await ctx.send(f"{config.YES} Done.")

    @nation.command(name="permissions", aliases=['perms', 'permission', 'perm'])
    @checks.moderation_or_nation_leader()
    async def set_channel_perms(self, ctx, *, channel: CaseInsensitiveTextChannel = None):
        """Toggle Read and/or Send Messages permissions for a role in one of your nation's channels"""

        if not channel:
            channel = await ctx.converted_input(
                f"{config.USER_INTERACTION_REQUIRED} Which channel's permissions should be changed?",
                converter=CaseInsensitiveTextChannel, return_input_on_fail=False)

        if channel.category_id not in self.bot.mk.NATION_CATEGORIES:
            return await ctx.send(f"{config.NO} The `{channel.name}` channel does not belong to your nation.")

        role = await ctx.converted_input(f"{config.USER_INTERACTION_REQUIRED} For which role should the "
                                         f"permissions in {channel.mention} be changed?",
                                         return_input_on_fail=False, converter=DemocracivCaseInsensitiveRole)

        overwrites = channel.overwrites_for(role)

        result = await PermissionSelectorMenu(role=role, channel=channel, overwrites=overwrites).prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on which permission(s) to change.")

        permission_to_change = result.result

        if permission_to_change['read']:
            overwrites.read_messages = not overwrites.read_messages

        if permission_to_change['send']:
            overwrites.send_messages = not overwrites.send_messages

        await channel.set_permissions(target=role, overwrite=overwrites)
        await ctx.send(f"{config.YES} Done.")


def setup(bot):
    bot.add_cog(Nation(bot))
