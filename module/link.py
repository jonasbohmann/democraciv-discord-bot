import config

from discord.ext import commands


# -- link.py | module.links --
#
# Collection of link commands.
#


class Link(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='links', aliases=['l'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def links(self, ctx):
        """Get a list of important links"""

        important_links_list = f"[Wiki]({config.getLinks()['wiki']})\n\n" \
                               f"[Subreddit]({config.getLinks()['subreddit']})\n\n" \
                               f"[Constitution]({config.getLinks()['constitution']})\n\n" \
                               f"[Legal Code]({config.getLinks()['laws']})\n\n" \
                               f"[Political Parties]({config.getLinks()['parties']})\n\n" \
                               f"[Election Schedule]({config.getLinks()['schedule']})\n\n" \
                               f"[Game Sessions]({config.getLinks()['gs-wiki']})\n\n" \
                               f"[Docket of the Arabian Legislature]({config.getLinks()['legislative-docket']})\n\n" \
                               f"[Worksheet of the Arabian Ministry]({config.getLinks()['executive-worksheet']})\n\n" \
                               f"[File a Case to the Supreme Court]({config.getLinks()['sue']})\n\n" \
                               f"[All Supreme Court Cases]({config.getLinks()['sc-cases']})\n\n"

        embed = self.bot.embeds.embed_builder(title='Important Links', description=important_links_list)
        await ctx.send(embed=embed)

    @commands.command(name='constitution', aliases=['c', 'const'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def constitution(self, ctx):
        """Get a link to our constitution"""
        embed = self.bot.embeds.embed_builder(title='The Constitution of Arabia',
                                              description=config.getLinks()['constitution'])
        await ctx.send(embed=embed)

    @commands.command(name='government', aliases=['gov', 'g'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def government(self, ctx, number: str = None):
        """Get a link to the wiki page of our government"""
        if not number:
            embed = self.bot.embeds.embed_builder(title='The Government of Arabia',
                                                  description=config.getLinks()['government'])
            await ctx.send(embed=embed)
            return

        number = int(number)

        if number == 1:
            ordinal = "First"
        elif number == 2:
            ordinal = "Second"
        elif number == 3:
            ordinal = "Third"
        else:
            ordinal = f"{str(number)}th"

        link = 'government-' + str(number)
        if link in config.getLinks():
            embed = self.bot.embeds.embed_builder(title=ordinal + ' Government of Arabia',
                                                  description=config.getLinks()[link])
            await ctx.send(embed=embed)
            return

        if link not in config.getLinks():
            await ctx.send(f':x: Sorry, I could not find the {ordinal.lower()} government.')
            return

    @commands.command(name='parties', aliases=['p'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def parties(self, ctx):
        """Get a link to our Political Parties"""
        embed = self.bot.embeds.embed_builder(title='Political Parties', description=config.getLinks()['parties'])
        await ctx.send(embed=embed)

    @commands.command(name='laws')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def laws(self, ctx):
        """Get a link to the Code of Law"""
        embed = self.bot.embeds.embed_builder(title='Legal Code of Arabia', description=config.getLinks()['laws'])
        await ctx.send(embed=embed)

    @commands.command(name='wiki', aliases=['w', 'info'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wiki(self, ctx):
        """Check out the official Wiki"""
        embed = self.bot.embeds.embed_builder(title='Official Wiki', description=config.getLinks()['wiki'])
        await ctx.send(embed=embed)

    @commands.command(name='beginnersguide', aliases=['b'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def beginnersGuide(self, ctx):
        """Getting Started in Democraciv"""
        embed = self.bot.embeds.embed_builder(title="Beginner's Guide", description=config.getLinks()['beginnersGuide'])
        await ctx.send(embed=embed)

    @commands.command(name='discord')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def discord(self, ctx):
        """Get an active invite link to the Democraciv Discord guild"""
        await ctx.send(config.getLinks()['discord'])

    @commands.command(name='archive')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def archive(self, ctx):
        """Discover the Archives of r/Democraciv"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive', description=config.getLinks()['archive'])
        await ctx.send(embed=embed)

    @commands.command(name='mk5')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk5(self, ctx):
        """Archives of Democraciv MK5"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK5', description=config.getLinks()['mk5'])
        await ctx.send(embed=embed)

    @commands.command(name='mk4')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk4(self, ctx):
        """Archives of Democraciv MK4"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK4', description=config.getLinks()['mk4'])
        await ctx.send(embed=embed)

    @commands.command(name='mk3')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk3(self, ctx):
        """Archives of Democraciv MK3"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK3', description=config.getLinks()['mk3'])
        await ctx.send(embed=embed)

    @commands.command(name='mk2')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk2(self, ctx):
        """Archives of Democraciv MK2"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK2', description=config.getLinks()['mk2'])
        await ctx.send(embed=embed)

    @commands.command(name='mk1')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk1(self, ctx):
        """Archives of Democraciv MK1"""
        embed = self.bot.embeds.embed_builder(title='Democraciv Archive - MK1', description=config.getLinks()['mk1'])
        await ctx.send(embed=embed)

    @commands.command(name='gamesessions', aliases=['gs'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def gamesessions(self, ctx):
        """Game Sessions on YouTube"""
        embed = self.bot.embeds.embed_builder(title='Game Sessions', description="")
        embed.add_field(name="List of Game Sessions on the Wiki", value=config.getLinks()['gs-wiki'], inline=False)
        embed.add_field(name="YouTube Playlist", value=config.getLinks()['gameSessions'], inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='schedule')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def schedule(self, ctx):
        """Schedule for the next elections"""
        embed = self.bot.embeds.embed_builder(title='Schedule', description=config.getLinks()['schedule'])
        await ctx.send(embed=embed)

    # @commands.command(name='move')
    # @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    # async def move(self, ctx):
    #    """Change your city of residence"""
    #    embed = self.bot.embeds.embed_builder(title='Change your City of Residency',
    #                                          description=config.getLinks()['residencyForm'])
    #    await ctx.send(embed=embed)

    # @commands.command(name='residency')
    # @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    # async def residency(self, ctx):
    #    """See the current population of every city"""
    #    embed = self.bot.embeds.embed_builder(title='Residency Spreadsheet',
    #                                          description=config.getLinks()['residencyList'])
    #    await ctx.send(embed=embed)

    @commands.command(name='sue')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def sue(self, ctx):
        """Submit a Case to the Supreme Court"""
        embed = self.bot.embeds.embed_builder(title='Submit a Case to the Supreme Court of Arabia',
                                              description=config.getLinks()['sue'])
        await ctx.send(embed=embed)

    @commands.command(name='register')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def register(self, ctx):
        """Register to Vote"""
        embed = self.bot.embeds.embed_builder(title='Register to Vote', description=config.getLinks()['register'])
        await ctx.send(embed=embed)

    @commands.command(name='states')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def states(self, ctx):
        """Overview of our States"""
        embed = self.bot.embeds.embed_builder(title='The States of Arabia', description=config.getLinks()['states'])
        await ctx.send(embed=embed)

    @commands.command(name='turnout')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def turnout(self, ctx):
        """Live turnout of the latest election"""
        embed = self.bot.embeds.embed_builder(title='Live Election Turnout', description=config.getLinks()['turnout'])
        await ctx.send(embed=embed)

    @commands.command(name='quire', aliases=['q'])
    @commands.has_permissions(administrator=True)
    async def quire(self, ctx):
        """Quire Project Management"""
        embed = self.bot.embeds.embed_builder(title='Quire',
                                              description=config.getLinks()['quire'])
        await ctx.send(embed=embed)

    @commands.command(name='docket', aliases=['d'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def docket(self, ctx):
        """Docket for the Arabian Legislature"""
        embed = self.bot.embeds.embed_builder(title='Docket for the Arabian Legislature',
                                              description=config.getLinks()['legislative-docket'])
        await ctx.send(embed=embed)

    @commands.command(name='ministry', aliases=['m'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def ministry(self, ctx):
        """The Ministry's worksheet"""
        embed = self.bot.embeds.embed_builder(title='Worksheet of the Arabian Ministry',
                                              description=config.getLinks()['executive-worksheet'])
        await ctx.send(embed=embed)

    @commands.command(name='dgwiki', aliases=['rbwiki'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def dgwiki(self, ctx):
        """Get a link to the (unofficial) dgwiki.tk"""
        embed = self.bot.embeds.embed_builder(title='Unofficial Demogames Wiki',
                                              description=config.getLinks()["dgwiki-tk"])
        await ctx.send(embed=embed)

    @commands.command(name='cases')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def cases(self, ctx):
        """See all Supreme Court cases"""
        embed = self.bot.embeds.embed_builder(title='Cases of the Supreme Court of Arabia',
                                              description=config.getLinks()["sc-cases"])
        await ctx.send(embed=embed)

    @commands.command(name='procedures', aliases=['procedure'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def legislativeprocedures(self, ctx):
        """The Legislative Procedures"""
        embed = self.bot.embeds.embed_builder(title='Procedures for the Arabian Legislature',
                                              description=config.getLinks()["legislative-procedures"])
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Link(bot))
