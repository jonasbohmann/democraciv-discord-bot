import discord
from discord.ext import commands

from config import config
from util import utils, mk


class ANewDawn(commands.Cog, name="A New Dawn"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='smite')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.COUNCIL_OF_SAGES, mk.DemocracivRole.SUPREME_LEADER,
                                   mk.DemocracivRole.WES_ROLE, mk.DemocracivRole.QI_ROLE)
    async def smite(self, ctx):
        """Unleash the power of the One on High"""
        messages = await ctx.channel.history(limit=5).flatten()
        messages.pop(0)

        for message in messages:
            await message.add_reaction("\U0001f329")

    @commands.command(name='excommunicate')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @utils.has_any_democraciv_role(mk.DemocracivRole.COUNCIL_OF_SAGES, mk.DemocracivRole.SUPREME_LEADER,
                                   mk.DemocracivRole.WES_ROLE, mk.DemocracivRole.QI_ROLE)
    async def excommunicate(self, ctx, *, person: discord.Member):
        """Heretic!"""
        believer = ctx.guild.get_role(694958914030141441)
        role = ctx.guild.get_role(694972373824307341)
        channel = ctx.guild.get_channel(694974887424426115)
        await ctx.send(f"\U0001f329 {person.display_name} is a heretic, get him!")
        await person.add_roles(role)
        await person.remove_roles(believer)
        await channel.send(f"{person.display_name} has been banished to the dungeon.")

    @commands.command(name='backtonormal', hidden=True)
    @commands.is_owner()
    async def back_to_normal(self, ctx):
        # Archive April Fools Channel
        government_category: discord.CategoryChannel = discord.utils.get(self.bot.democraciv_guild_object.categories,
                                                                         name="Government")

        everyone_perms = discord.PermissionOverwrite(read_message_history=False, send_messages=False,
                                                     read_messages=False)
        everyone_role = self.bot.democraciv_guild_object.default_role
        archive_perms = discord.PermissionOverwrite(read_message_history=True, send_messages=False, read_messages=True)
        archives_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name="Archives")

        for channel in government_category.text_channels:
            await channel.send(f":tada: Happy April Fools' Day!")
            await channel.edit(name=f"mk{mk.MARK}-april-fools-{channel.name}",
                               overwrites={everyone_role: everyone_perms, archives_role: archive_perms})

        # Delete April Fools Roles
        believer_role = ctx.guild.get_role(694958914030141441)
        await believer_role.delete()
        heretic_role = ctx.guild.get_role(694972373824307341)
        await heretic_role.delete()

        a = mk.get_democraciv_role(self.bot, mk.DemocracivRole.QI_ROLE)
        await a.delete()
        b = mk.get_democraciv_role(self.bot, mk.DemocracivRole.WES_ROLE)
        await b.delete()
        c = mk.get_democraciv_role(self.bot, mk.DemocracivRole.COUNCIL_OF_SAGES)
        await c.delete()
        d = mk.get_democraciv_role(self.bot, mk.DemocracivRole.SUPREME_LEADER)
        await d.delete()

        mk6_archives = ctx.guild.get_channel(637016439940972549)
        for channel in mk6_archives.text_channels:
            await channel.edit(name=f"{channel.name[4:]}", category=government_category)

        # Give government roles back
        async def give_role(person, role):
            member = await commands.MemberConverter().convert(ctx, person)
            _role = await commands.RoleConverter().convert(ctx, role)
            if member is None or _role is None:
                return await ctx.send(f":x: Failed with {person} -> {role}.")
            await member.add_roles(_role)

        arab_gov = ["Carlitos",
                    "Charisarian",
                    "Quaerendo_Invenietis",
                    "Shain",
                    "Peppeghetti Sparoni",
                    "WereRobot",
                    "John the Jellyfish",
                    "MadMadelyn",
                    "jgallarday001",
                    "UltimateDude101",
                    "AngusAbercrombie",
                    "MouseKing__",
                    "Bird",
                    "solace005",
                    "WesGutt",
                    "Taylor",
                    "SK-CU-47",
                    "DerJonas",
                    "Piper",
                    "Joe McCarthy",
                    "Montezuma",
                    "141135",
                    "ArchWizard101"]

        for person in arab_gov:
            try:
                await give_role(person, "Arabian Government")
            except Exception:
                continue

        legislator = ["MadMadelyn",
                      "UltimateDude101",
                      "AngusAbercrombie",
                      "Taylor",
                      "SK-CU-47",
                      "Joe McCarthy]"]

        for person in legislator:
            try:
                await give_role(person, "Legislator")
            except Exception:
                continue

        minister = ["Shain",
                    "jgallarday001",
                    "MouseKing__",
                    "WesGutt",
                    "Montezuma"]

        for person in minister:
            try:
                await give_role(person, "Minister")
            except Exception:
                continue

        comms = ["Quaerendo_Invenietis",
                 "Peppeghetti Sparoni",
                 "Bird",
                 "141135"]

        for person in comms:
            try:
                await give_role(person, "Department of Communications")
            except Exception:
                continue

        war = ["WesGutt",
               "Taylor",
               "Joe McCarthy"]

        for person in war:
            try:
                await give_role(person, "Arabian Committee on War and Security")
            except Exception:
                continue

        await ctx.send(":tada: Happy April Fools' Day everyone!")


def setup(bot):
    bot.add_cog(ANewDawn(bot))
