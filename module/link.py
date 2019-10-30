import config

from util.embed import embed_builder
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
        embed = embed_builder(title='Important Links', description=config.getLinks()['importantLinks'])
        await ctx.send(embed=embed)

    @commands.command(name='constitution', aliases=['c', 'const'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def constitution(self, ctx):
        """Get a link to our constitution"""
        embed = embed_builder(title='The Constitution of Arabia', description=config.getLinks()['constitution'])
        await ctx.send(embed=embed)

    @commands.command(name='government', aliases=['gov', 'g'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def government(self, ctx, number: str = None):
        """Get a link to the wiki page of our government"""
        if not number:
            embed = embed_builder(title='The Government of Arabia', description=config.getLinks()['government'])
            await ctx.send(embed=embed)
            return

        if number == "1":
            ordinal = "First"
        if number == "2":
            ordinal = "Second"
        if number == "3":
            ordinal = "Third"
        if int(number) in range(4, 10):
            ordinal = number + "th"

        link = 'government-' + number
        if link in config.getLinks():
            embed = embed_builder(title=ordinal + ' Government of Arabia', description=config.getLinks()[link])
            await ctx.send(embed=embed)
            return

        if link not in config.getLinks():
            await ctx.send(f':x: Sorry, I could not find the {ordinal.lower()} government.')
            return

    @commands.command(name='parties', aliases=['p'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def parties(self, ctx):
        """Get a link to our Political Parties"""
        embed = embed_builder(title='Political Parties', description=config.getLinks()['parties'])
        await ctx.send(embed=embed)

    @commands.command(name='laws')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def laws(self, ctx):
        """Get a link to the Code of Law"""
        embed = embed_builder(title='Legal Code of Arabia', description=config.getLinks()['laws'])
        await ctx.send(embed=embed)

    @commands.command(name='wiki', aliases=['w', 'info'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wiki(self, ctx):
        """Check out the official Wiki"""
        embed = embed_builder(title='Official Wiki', description=config.getLinks()['wiki'])
        await ctx.send(embed=embed)

    @commands.command(name='beginnersguide', aliases=['b'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def beginnersguide(self, ctx):
        """Getting Started in Democraciv"""
        embed = embed_builder(title="Beginner's Guide", description=config.getLinks()['beginnersGuide'])
        await ctx.send(embed=embed)

    @commands.command(name='invite')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this server"""
        await ctx.send(config.getLinks()['discord'])

    @commands.command(name='archive')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def archive(self, ctx):
        """Discover the Archives of r/Democraciv"""
        embed = embed_builder(title='Democraciv Archive', description=config.getLinks()['archive'])
        await ctx.send(embed=embed)

    @commands.command(name='mk5')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk5(self, ctx):
        """MK5-Archives"""
        embed = embed_builder(title='Democraciv Archive - MK5', description=config.getLinks()['mk5'])
        await ctx.send(embed=embed)

    @commands.command(name='mk4')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk4(self, ctx):
        """MK4-Archives"""
        embed = embed_builder(title='Democraciv Archive - MK4', description=config.getLinks()['mk4'])
        await ctx.send(embed=embed)

    @commands.command(name='mk3')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk3(self, ctx):
        """MK3-Archives"""
        embed = embed_builder(title='Democraciv Archive - MK3', description=config.getLinks()['mk3'])
        await ctx.send(embed=embed)

    @commands.command(name='mk2')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk2(self, ctx):
        """MK2-Archives"""
        embed = embed_builder(title='Democraciv Archive - MK2', description=config.getLinks()['mk2'])
        await ctx.send(embed=embed)

    @commands.command(name='mk1')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk1(self, ctx):
        """MK1-Archives"""
        embed = embed_builder(title='Democraciv Archive - MK1', description=config.getLinks()['mk1'])
        await ctx.send(embed=embed)

    @commands.command(name='gamesessions', aliases=['gs'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def gamesessions(self, ctx):
        """Game Sessions on YouTube"""
        embed = embed_builder(title='Game Sessions', description=config.getLinks()['gameSessions'])
        await ctx.send(embed=embed)

    @commands.command(name='schedule')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def schedule(self, ctx):
        """Schedule for the next elections"""
        embed = embed_builder(title='Schedule', description=config.getLinks()['schedule'])
        await ctx.send(embed=embed)

    @commands.command(name='move')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def move(self, ctx):
        """Change your city of residence"""
        embed = embed_builder(title='Change your City of Residency', description=config.getLinks()['residencyForm'])
        await ctx.send(embed=embed)

    @commands.command(name='residency')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def residency(self, ctx):
        """See the current population of every city"""
        embed = embed_builder(title='Residency Spreadsheet', description=config.getLinks()['residencyList'])
        await ctx.send(embed=embed)

    @commands.command(name='sue')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def sue(self, ctx):
        """Submit a Case to the Supreme Court"""
        embed = embed_builder(title='Submit a Case to the Supreme Court of Arabia',
                              description=config.getLinks()['supremeCourtCaseSubmitter'])
        await ctx.send(embed=embed)

    @commands.command(name='register')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def register(self, ctx):
        """Register to Vote"""
        embed = embed_builder(title='Register to Vote', description=config.getLinks()['register'])
        await ctx.send(embed=embed)

    @commands.command(name='states')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def states(self, ctx):
        """Overview of our States"""
        embed = embed_builder(title='The States of Arabia', description=config.getLinks()['states'])
        await ctx.send(embed=embed)

    @commands.command(name='turnout')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def turnout(self, ctx):
        """Live turnout of the latest election"""
        embed = embed_builder(title='Live Election Turnout', description=config.getLinks()['turnout'])
        await ctx.send(embed=embed)

    @commands.command(name='quire')
    @commands.has_permissions(administrator=True)
    async def quire(self, ctx):
        """Quire Project Management"""
        embed = embed_builder(title='Quire',
                              description=config.getLinks()['quire'])
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Link(bot))
