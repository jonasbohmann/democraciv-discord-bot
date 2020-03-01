import typing
import discord
import asyncpg

from util.flow import Flow
from discord.ext import commands
from config import config, links
from util import utils, exceptions, mk
from util.converter import PoliticalParty
from util.exceptions import ForbiddenTask


class Party(commands.Cog, name='Political Parties'):
    """Interact with the political parties of Democraciv"""

    # TODO - Move all party commands into -party group. Don't allow non-party roles in -members <role>, move that
    #  functionality into -whois <role>

    def __init__(self, bot):
        self.bot = bot

    async def collect_parties_and_members(self) -> typing.List[typing.Tuple[str, int]]:
        """Returns all parties with a role on the Democraciv guild and their amount of members for -members."""
        parties_and_members = []

        parties = await self.bot.db.fetch("SELECT id FROM parties")
        parties = [record['id'] for record in parties]

        error_string = "[DATABASE] The following ids were added as a party but have no role on the Democraciv guild: "

        for party in parties:
            role = self.bot.democraciv_guild_object.get_role(party)

            if role is None:
                error_string += f'{str(party)}, '
                continue

            parties_and_members.append((role.name, len(role.members)))

        if len(error_string) > 95:
            print(error_string)

        return parties_and_members

    @commands.command(name='join')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def join(self, ctx, *, party: PoliticalParty):
        """Join a political party"""

        if party.role not in ctx.message.author.roles:

            if party.is_private:
                if party.leader is None:
                    msg = f':x: {party.role.name} is invite-only. Ask the party leader for an invitation.'
                else:
                    msg = f':x: {party.role.name} is invite-only. Ask {party.leader.mention} for an invitation.'

                return await ctx.send(msg)

            try:
                await ctx.message.author.add_roles(party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

            if party.role.name == 'Independent':
                await ctx.send(f':white_check_mark: You are now an {party.role.name}!')

            else:
                await ctx.send(
                    f':white_check_mark: You\'ve joined {party.role.name}! Now head to their Discord Server and '
                    f'introduce yourself: {party.discord_invite}')

        else:
            return await ctx.send(f':x: You are already part of {party.role.name}!')

    @commands.command(name='form')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def form(self, ctx):
        """Form a political party"""
        await ctx.send(f"You can fill out this form with all the details to form a political party:\n{links.formparty}")

    @commands.command(name='leave')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def leave(self, ctx, *, party: PoliticalParty):
        """Leave a political party"""

        if party.role in ctx.message.author.roles:
            try:
                await ctx.message.author.remove_roles(party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.REMOVE_ROLE, detail=party.role.name)

            if party.role.name == 'Independent':
                msg = f':white_check_mark: You are no longer an {party.role.name}!'
            else:
                msg = f':white_check_mark: You left {party.role.name}!'
            await ctx.send(msg)

        else:
            return await ctx.send(f':x: You are not part of {party.role.name}!')

    @commands.command(name='members')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def members(self, ctx, *, party: str = None):
        """Get the current political party ranking or a list of all party members on the Democraciv guild"""

        # Show Ranking
        if party is None:
            party_list_embed_content = []

            sorted_parties_and_members = sorted(await self.collect_parties_and_members(), key=lambda x: x[1],
                                                reverse=True)

            for party in sorted_parties_and_members:
                if party[0] == 'Independent':
                    continue
                if party[1] == 1:
                    party_list_embed_content.append(f'**{party[0]}**\n{party[1]} member')
                else:
                    party_list_embed_content.append(f'**{party[0]}**\n{party[1]} members')

            # Append Independents to message
            independent_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name='Independent')

            if independent_role is not None:
                if len(independent_role.members) == 1:
                    party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                    f'{len(independent_role.members)} citizen')
                else:
                    party_list_embed_content.append(f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n**Independent**\n'
                                                    f'{len(independent_role.members)} citizens')
            if len(party_list_embed_content) == 0:
                party_list_embed_content = ['There are no political parties yet.']

            embed = self.bot.embeds.embed_builder(title=f'Ranking of Political Parties in {mk.NATION_NAME}',
                                                  description='\n\n'.join(party_list_embed_content), colour=0x7f0000)

            return await ctx.send(embed=embed)

        # Show member names of single party
        elif party:
            try:
                political_party = await PoliticalParty.convert(ctx, party)
                role = political_party.role
            except exceptions.PartyNotFoundError:
                # '-members <role>' is often used for non-party roles so we allow this by catching PartyNotFoundError
                role = discord.utils.get(self.bot.democraciv_guild_object.roles, name=party)

            if role is None:
                if ctx.guild.id != self.bot.democraciv_guild_object.id:
                    return await ctx.send(":x: This command uses the roles and members from the Democraciv guild,"
                                          " not the ones from this guild!")
                raise exceptions.RoleNotFoundError(party)

            list_of_members = [member.name for member in role.members]

            if len(list_of_members) == 0:
                list_of_members = ['No members.']

            title = 'Independent Citizens' if party == 'Independent' else f'Members of {role.name}'

            embed = self.bot.embeds.embed_builder(title=title, description='\n'.join(list_of_members), colour=0x7f0000)
            return await ctx.send(embed=embed)

    async def create_new_party(self, ctx) -> typing.Optional[PoliticalParty]:
        await ctx.send(":information_source: Reply with the name of the new party you want to create.")

        flow = Flow(self.bot, ctx)
        role_name = await flow.get_new_role(240)

        if isinstance(role_name, str):
            await ctx.send(
                f":white_check_mark: I will **create a new role** on this guild named `{role_name}`"
                f" for the new party.")
            try:
                discord_role = await ctx.guild.create_role(name=role_name)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, role_name)

        else:
            discord_role = role_name

            await ctx.send(
                f":white_check_mark: I'll use the **pre-existing role** named "
                f"'{discord_role.name}' for the new party.")

        await ctx.send(":information_source: Reply with the invite link to the party's Discord guild.")

        party_invite = await flow.get_text_input(300)

        if not party_invite:
            return None

        is_private = False
        private_question = await ctx.send(
            "Should this new party be private? React with :white_check_mark: if yes, or with :x: if not.")

        reaction = await flow.get_yes_no_reaction_confirm(private_question, 240)

        if reaction is None:
            return None

        if reaction:
            is_private = True

            await ctx.send(":information_source: Reply with the name of the party's leader.")

            leader = await flow.get_text_input(240)

            if leader:
                try:
                    leader_role = await commands.MemberConverter().convert(ctx, leader)
                except commands.BadArgument:
                    raise exceptions.MemberNotFoundError(leader)

        elif not reaction:
            is_private = False

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                if is_private:
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO parties (id, discord_invite, is_private, leader) VALUES ($1, $2, $3, $4)",
                            discord_role.id, party_invite, True, leader_role.id)
                    except asyncpg.UniqueViolationError:
                        await ctx.send(f":x: A party named `{discord_role.name}` already exists!")
                        return None
                else:
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO parties (id, discord_invite, is_private) VALUES ($1, $2, $3)",
                            discord_role.id, party_invite, False)
                    except asyncpg.UniqueViolationError:
                        await ctx.send(f":x: A party named `{discord_role.name}` already exists!")
                        return None

                status = await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                   discord_role.name.lower(), discord_role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: `{discord_role.name}` was added as a new party.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

        return await PoliticalParty.convert(ctx, discord_role.id)

    @commands.command(name='addparty')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addparty(self, ctx):
        """Add a new political party"""
        await self.create_new_party(ctx)

    @commands.command(name='deleteparty')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def deleteparty(self, ctx, hard: bool, *, party: PoliticalParty):
        """Remove a political party

                Usage:
                 `-deleteparty true <party>` will remove the party **and** delete its Discord role
                 `-deleteparty false <party>` will remove the party but not delete its Discord role

        """

        if hard:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(ForbiddenTask.DELETE_ROLE, detail=party.role.name)

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await self.bot.db.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                await self.bot.db.execute("DELETE FROM parties WHERE id = $1", party.role.id)

        await ctx.send(f':white_check_mark: `{party.role.name}` and all its aliases were deleted.')

    @commands.command(name='addalias')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def addalias(self, ctx):
        """Add a new alias to a political party"""

        await ctx.send(":information_source: Reply with the name of the party that the new alias should belong to:")

        flow = Flow(self.bot, ctx)

        party_name = await flow.get_text_input(240)

        if not party_name:
            return

        # Check if party role already exists
        try:
            party = await PoliticalParty.convert(ctx, party_name)
        except exceptions.PartyNotFoundError:
            raise exceptions.RoleNotFoundError(party_name)

        await ctx.send(f":information_source: Reply with the alias for `{party.role.name}`:")

        alias = await flow.get_text_input(240)

        if not alias:
            return

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                status = await self.bot.db.execute("INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                                                   alias.lower(), party.role.id)

        if status == "INSERT 0 1":
            await ctx.send(f':white_check_mark: Alias `{alias}` for party '
                           f'`{party.role.name}` was added.')
        else:
            await ctx.send(":x: Unexpected database error occurred.")

    @commands.command(name='deletealias', aliases=['removealias'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def deletealias(self, ctx, *, alias: str):
        """Delete a party's alias"""
        try:
            await PoliticalParty.convert(ctx, alias)
        except exceptions.PartyNotFoundError:
            return await ctx.send(f":x: {alias} is not an alias of any party.")

        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias.lower())
        await ctx.send(f':white_check_mark: Alias `{alias}` was deleted.')

    @commands.command(name='listaliases')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def listaliases(self, ctx, *, party: PoliticalParty):
        """List all aliases of a given party"""

        if not party.aliases:
            return await ctx.send(f":x: There are no aliases for `{party.role.name}`.")

        embed = self.bot.embeds.embed_builder(title=f'Aliases of {party.role.name}',
                                              description='\n'.join(party.aliases))
        await ctx.send(embed=embed)

    @commands.command(name='mergeparty', aliases=['mergeparties'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.has_democraciv_role(mk.DemocracivRole.MODERATION_ROLE)
    async def mergeparties(self, ctx, amount_of_parties: int):
        """Merge one or multiple parties into a single, new party"""

        flow = Flow(self.bot, ctx)

        to_be_merged = []

        for i in range(1, amount_of_parties + 1):
            await ctx.send(f":information_source: What's the name or alias political party #{i}?")

            name = await flow.get_text_input(120)

            if not name:
                return

            try:
                party = await PoliticalParty.convert(ctx, name)
            except exceptions.PartyNotFoundError:
                return await ctx.send(f":x: There is no party that matches `{name}`. Aborted.")

            to_be_merged.append(party)

        members_to_merge = list(set([member for party in to_be_merged for member in party.role.members]))
        pretty_parties = [f"`{party.role.name}`" for party in to_be_merged]

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to merge"
                                      f" {', '.join(pretty_parties)} into one, new party?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 120)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        try:
            new_party = await self.create_new_party(ctx)
        except exceptions.DemocracivBotException as e:
            return await ctx.send(f"{e.message}\n:x: Party creation failed, old parties were not deleted.")

        if new_party is None:
            return await ctx.send(":x: Party creation failed, old parties were not deleted.")

        for member in members_to_merge:
            await member.add_roles(new_party.role)

        for party in to_be_merged:
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await self.bot.db.execute("DELETE FROM party_alias WHERE party_id = $1", party.role.id)
                    await self.bot.db.execute("DELETE FROM parties WHERE id = $1", party.role.id)

            await party.role.delete()

        await ctx.send(":white_check_mark: The old parties were deleted and"
                       " all their members have now the role of the new party.")


def setup(bot):
    bot.add_cog(Party(bot))
