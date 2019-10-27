import config
import discord

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
        embed = discord.Embed(title='Important Links', description=config.getLinks()['importantLinks'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='constitution', aliases=['c', 'const'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def constitution(self, ctx):
        """Get a link to our constitution"""
        embed = discord.Embed(title='The Constitution of Arabia', description=config.getLinks()['constitution'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='government', aliases=['gov', 'g'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def government(self, ctx, number: str = None):
        """Get a link to the wiki page of our government"""
        if not number:
            embed = discord.Embed(title='The Government of Arabia', description=config.getLinks()['government'],
                                  colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
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
            embed = discord.Embed(title=ordinal + ' Government of Arabia', description=config.getLinks()[link],
                                  colour=0x7f0000)
            embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
            await ctx.send(content=None, embed=embed)
            return

        if link not in config.getLinks():
            await ctx.send(f':x: Sorry, I could not find the {ordinal.lower()} government.')
            return

    @commands.command(name='parties', aliases=['p'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def parties(self, ctx):
        """Get a link to our Political Parties"""
        embed = discord.Embed(title='Political Parties', description=config.getLinks()['parties'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='laws')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def laws(self, ctx):
        """Get a link to the Code of Law"""
        embed = discord.Embed(title='Code of Law', description=config.getLinks()['laws'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='wiki', aliases=['w', 'info'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def wiki(self, ctx):
        """Check out the official Wiki"""
        embed = discord.Embed(title='Official Wiki', description=config.getLinks()['wiki'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='beginnersguide', aliases=['b'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def beginnersguide(self, ctx):
        """Getting Started in r/Democraciv"""
        embed = discord.Embed(title="Beginner's Guide", description=config.getLinks()['beginnersGuide'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='invite')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this server"""
        await ctx.send(config.getLinks()['discord'])

    @commands.command(name='archive')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def archive(self, ctx):
        """Discover the Archives of r/Democraciv"""
        embed = discord.Embed(title='Democraciv Archive', description=config.getLinks()['archive'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='mk5')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk5(self, ctx):
        """MK5-Archives"""
        embed = discord.Embed(title='Democraciv Archive - MK5', description=config.getLinks()['mk5'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='mk4')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk4(self, ctx):
        """MK4-Archives"""
        embed = discord.Embed(title='Democraciv Archive - MK4', description=config.getLinks()['mk4'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='mk3')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk3(self, ctx):
        """MK3-Archives"""
        embed = discord.Embed(title='Democraciv Archive - MK3', description=config.getLinks()['mk3'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='mk2')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk2(self, ctx):
        """MK2-Archives"""
        embed = discord.Embed(title='Democraciv Archive - MK2', description=config.getLinks()['mk2'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='mk1')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def mk1(self, ctx):
        """MK1-Archives"""
        embed = discord.Embed(title='Democraciv Archive - MK1', description=config.getLinks()['mk1'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='gamesessions', aliases=['gs'])
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def gamesessions(self, ctx):
        """Game Sessions on YouTube"""
        embed = discord.Embed(title='Game Sessions', description=config.getLinks()['gameSessions'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='schedule')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def schedule(self, ctx):
        """Schedule for the next elections"""
        embed = discord.Embed(title='Schedule', description=config.getLinks()['schedule'], colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='move')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def move(self, ctx):
        """Change your city of residence"""
        embed = discord.Embed(title='Change your City of Residency', description=config.getLinks()['residencyForm'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='residency')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def residency(self, ctx):
        """See the current population of every city"""
        embed = discord.Embed(title='Residency Spreadsheet', description=config.getLinks()['residencyList'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='sue')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def sue(self, ctx):
        """Submit a Case to the Supreme Court"""
        embed = discord.Embed(title='Submit a Case to the Supreme Court of Arabia',
                              description=config.getLinks()['supremeCourtCaseSubmitter'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='register')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def register(self, ctx):
        """Register to Vote"""
        embed = discord.Embed(title='Register to Vote',
                              description=config.getLinks()['register'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)#

    @commands.command(name='states')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def states(self, ctx):
        """Overview of our States"""
        embed = discord.Embed(title='The States of Arabia',
                              description=config.getLinks()['states'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)

    @commands.command(name='turnout')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def turnout(self, ctx):
        """Live turnout of the latest election"""
        embed = discord.Embed(title='Live Election Turnout',
                              description=config.getLinks()['turnout'],
                              colour=0x7f0000)
        embed.set_footer(text=config.getConfig()['botName'], icon_url=config.getConfig()['botIconURL'])
        await ctx.send(content=None, embed=embed)


def setup(bot):
    bot.add_cog(Link(bot))
