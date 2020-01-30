from config import links, config
from util import mk, utils
from discord.ext import commands


# -- link.py | module.links --
#
# Collection of link commands.
#


class Link(commands.Cog):
    """Collection of links to all aspects of Democraciv"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='links', aliases=['l'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def links(self, ctx):
        """Get a list of important links"""

        important_links_list = f"[Wiki]({links.wiki})\n\n" \
                               f"[Subreddit]({links.subreddit})\n\n" \
                               f"[Constitution]({links.constitution})\n\n" \
                               f"[Legal Code]({links.laws})\n\n" \
                               f"[Political Parties]({links.parties})\n\n" \
                               f"[Election Schedule]({links.schedule})\n\n" \
                               f"[Game Sessions]({links.gswiki})\n\n" \
                               f"[Docket of the {mk.NATION_ADJECTIVE} Legislature]({links.legislativedocket})\n\n" \
                               f"[Worksheet of the {mk.NATION_ADJECTIVE} Ministry]({links.executiveworksheet})\n\n" \
                               f"[File a Case to the Supreme Court]({links.sue})\n\n" \
                               f"[All Supreme Court Cases]({links.sccases})\n\n"

        embed = self.bot.embeds.embed_builder(title='Important Links', description=important_links_list)
        await ctx.send(embed=embed)

    @commands.command(name='constitution', aliases=['c', 'const'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def constitution(self, ctx):
        """Get a link to our constitution"""
        embed = self.bot.embeds.embed_builder(title=f'The Constitution of {mk.NATION_NAME}',
                                              description=links.constitution)
        await ctx.send(embed=embed)

    @commands.command(name='government', aliases=['gov', 'g'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def government(self, ctx, number: int = None):
        """Get a link to the wiki page of our government"""
        if not number:
            embed = self.bot.embeds.embed_builder(title=f'The Government of {mk.NATION_NAME}',
                                                  description=links.government)
            await ctx.send(embed=embed)
            return

        if number == 1:
            ordinal = "First"
        elif number == 2:
            ordinal = "Second"
        elif number == 3:
            ordinal = "Third"
        else:
            ordinal = f"{str(number)}th"

        embed = self.bot.embeds.embed_builder(title=f'{ordinal} Government of {mk.NATION_NAME}',
                                              description=f'{links.government}/{str(number)}')
        await ctx.send(embed=embed)
        return

    @commands.command(name='parties', aliases=['p'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def parties(self, ctx):
        """Get a link to our Political Parties"""
        embed = self.bot.embeds.embed_builder(title=f'Political Parties in {mk.NATION_NAME}', description=links.parties)
        await ctx.send(embed=embed)

    @commands.command(name='legalcode', aliases=['lc'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legalcode(self, ctx):
        """Get a link to the Code of Law"""
        embed = self.bot.embeds.embed_builder(title=f'Legal Code of {mk.NATION_NAME}', description=links.laws)
        await ctx.send(embed=embed)

    @commands.command(name='wiki', aliases=['w', 'info'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def wiki(self, ctx):
        """Check out the official Wiki"""
        embed = self.bot.embeds.embed_builder(title='Official Wiki', description=links.wiki)
        await ctx.send(embed=embed)

    @commands.command(name='beginnersguide', aliases=['b'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def beginnersGuide(self, ctx):
        """Getting Started in Democraciv"""
        embed = self.bot.embeds.embed_builder(title="Beginner's Guide", description=links.beginnersGuide)
        await ctx.send(embed=embed)

    @commands.command(name='discord')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def discord(self, ctx):
        """Get an active invite link to the Democraciv Discord guild"""
        await ctx.send(links.discord)

    @commands.command(name='archive')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def archive(self, ctx):
        """Discover the Archives of r/Democraciv"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive', description=links.archive)
        await ctx.send(embed=embed)

    @commands.command(name='mk5')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def mk5(self, ctx):
        """Archives of Democraciv MK5"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK5', description=links.mk5)
        await ctx.send(embed=embed)

    @commands.command(name='mk4')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def mk4(self, ctx):
        """Archives of Democraciv MK4"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK4', description=links.mk4)
        await ctx.send(embed=embed)

    @commands.command(name='mk3')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def mk3(self, ctx):
        """Archives of Democraciv MK3"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK3', description=links.mk3)
        await ctx.send(embed=embed)

    @commands.command(name='mk2')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def mk2(self, ctx):
        """Archives of Democraciv MK2"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK2', description=links.mk2)
        await ctx.send(embed=embed)

    @commands.command(name='mk1')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def mk1(self, ctx):
        """Archives of Democraciv MK1"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK1', description=links.mk1)
        await ctx.send(embed=embed)

    @commands.command(name='gamesessions', aliases=['gs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def gamesessions(self, ctx):
        """Game Sessions on YouTube"""
        embed = self.bot.embeds.embed_builder(title=f'Game Sessions with {mk.NATION_NAME}', description="")
        embed.add_field(name="List of Game Sessions on the Wiki", value=links.gswiki, inline=False)
        embed.add_field(name="YouTube Playlist", value=links.gameSessions, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='schedule')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def schedule(self, ctx):
        """Schedule for the next elections"""
        embed = self.bot.embeds.embed_builder(title='Schedule', description=links.schedule)
        await ctx.send(embed=embed)

    # @commands.command(name='move')
    # @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    # async def move(self, ctx):
    #    """Change your city of residence"""
    #    embed = self.bot.embeds.embed_builder(title='Change your City of Residency',
    #                                          description=links.residencyForm'])
    #    await ctx.send(embed=embed)

    # @commands.command(name='residency')
    # @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    # async def residency(self, ctx):
    #    """See the current population of every city"""
    #    embed = self.bot.embeds.embed_builder(title='Residency Spreadsheet',
    #                                          description=links.residencyList'])
    #    await ctx.send(embed=embed)

    @commands.command(name='sue')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def sue(self, ctx):
        """Submit a Case to the Supreme Court"""
        embed = self.bot.embeds.embed_builder(title=f'Submit a Case to the Supreme Court of {mk.NATION_NAME}',
                                              description=links.sue)
        await ctx.send(embed=embed)

    @commands.command(name='register')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def register(self, ctx):
        """Register to Vote"""
        embed = self.bot.embeds.embed_builder(title='Register to Vote', description=links.register)
        await ctx.send(embed=embed)

    @commands.command(name='states')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def states(self, ctx):
        """Overview of our States"""
        embed = self.bot.embeds.embed_builder(title=f'The States of {mk.NATION_NAME}', description=links.states)
        await ctx.send(embed=embed)

    @commands.command(name='turnout')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def turnout(self, ctx):
        """Live turnout of the latest election"""
        embed = self.bot.embeds.embed_builder(title='Live Election Turnout', description=links.turnout)
        await ctx.send(embed=embed)

    @commands.command(name='docket', aliases=['d'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def docket(self, ctx):
        """Docket for the Legislature"""
        embed = self.bot.embeds.embed_builder(title=f'Docket for the {mk.NATION_ADJECTIVE} Legislature',
                                              description=links.legislativedocket)
        await ctx.send(embed=embed)

    @commands.command(name='worksheet')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def ministry(self, ctx):
        """The Ministry's worksheet"""
        embed = self.bot.embeds.embed_builder(title=f'Worksheet of the {mk.NATION_ADJECTIVE} Ministry',
                                              description=links.executiveworksheet)
        await ctx.send(embed=embed)

    @commands.command(name='dgwiki', aliases=['rbwiki'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def dgwiki(self, ctx):
        """Get a link to the (unofficial) dgwiki.tk"""
        embed = self.bot.embeds.embed_builder(title='Unofficial Demogames Wiki',
                                              description=links.dgwikitk)
        await ctx.send(embed=embed)

    @commands.command(name='cases')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def cases(self, ctx):
        """See all Supreme Court cases"""
        embed = self.bot.embeds.embed_builder(title=f'Cases of the Supreme Court of {mk.NATION_NAME}',
                                              description=links.sccases)
        await ctx.send(embed=embed)

    @commands.command(name='procedures', aliases=['procedure'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def legislativeprocedures(self, ctx):
        """The Legislative Procedures"""
        embed = self.bot.embeds.embed_builder(title=f'Procedures for the {mk.NATION_ADJECTIVE} Legislature',
                                              description=links.legislativeprocedures)
        await ctx.send(embed=embed)

    @commands.command(name='stvcalculator')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def stvcalculator(self, ctx):
        """Source Code of our STV calculator"""
        embed = self.bot.embeds.embed_builder(title='Source Code of our STV calculator',
                                              description=links.stvcalcsource)
        await ctx.send(embed=embed)

    @commands.command(name='map')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def map(self, ctx):
        """Interactive Democraciv Map"""
        embed = self.bot.embeds.embed_builder(title='Interactive Map of our Continent',
                                              description=links.dcivmap)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Link(bot))
