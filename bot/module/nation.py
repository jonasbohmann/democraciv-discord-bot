import discord
from discord.ext import commands

from bot.config import config, mk, exceptions
from bot.utils import context, checks, paginator, text, mixin
from bot.utils.converter import CaseInsensitiveMember, CaseInsensitiveRole, CaseInsensitiveCategoryChannel


class Nation(context.CustomCog, mixin.GovernmentMixin):
    """Useful commands for Nation Admins to manage their nation in Multiciv."""

    @commands.group(name="nation", aliases=['civ', 'n'], case_insensitive=True, invoke_without_command=True)
    async def nation(self, ctx):
        """{NATION_NAME}"""

        description = ""
        nation_wiki = self.bot.mk.NATION_NAME.lower()

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
    async def toggle_role(self, ctx, member: CaseInsensitiveMember, *, role: CaseInsensitiveRole):
        """Give someone a role, or remove one from them

        **Example**:
            `{PREFIX}{COMMAND} @DerJonas Rome - Builder` will give DerJonas the 'Rome - Builder' role"""

        if not role.name.lower().startswith(self.bot.mk.NATION_ROLE_PREFIX.lower()):
            return await ctx.send(f"{config.NO} You're not allowed to give someone the `{role.name}` role.")

        if role not in member.roles:
            await member.add_roles(role)
            await ctx.send(f"{config.YES} The `{role.name}` role was given to {member}.")
        else:
            await member.remove_roles(role)
            await ctx.send(f"{config.YES} The `{role.name}` role was removed from {member}.")

    @nationroles.command(name="add", aliases=['create', 'make'])
    @checks.moderation_or_nation_leader()
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

    @nation.group(name="createchannel", aliases=['channel'])
    @checks.moderation_or_nation_leader()
    async def channel(self, ctx, *, category: CaseInsensitiveCategoryChannel = None):
        """Create a new channel in one of your nation's categories"""

        if not category:
            c_name = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} In which category should "
                                     f"the channel be created?")
            category = await CaseInsensitiveCategoryChannel().convert(ctx, c_name)

        if category.id not in self.bot.mk.NATION_CATEGORIES:
            return await ctx.send(f"{config.NO} The `{category.name}` category does not belong to your nation.")

        channel_name = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} What should be the name of the new channel?")

        await category.create_text_channel(name=channel_name)
        await ctx.send(f"{config.YES} Done.")


def setup(bot):
    bot.add_cog(Nation(bot))
