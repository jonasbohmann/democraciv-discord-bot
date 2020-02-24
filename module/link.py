from util import mk
from config import links, config
from discord.ext import commands


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
            return await ctx.send(embed=embed)

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

    @commands.command(name='gamesessions', aliases=['gs'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def gamesessions(self, ctx):
        """Game Sessions on YouTube"""
        embed = self.bot.embeds.embed_builder(title=f'Game Sessions with {mk.NATION_NAME}', description="")
        embed.add_field(name="List of Game Sessions on the Wiki", value=links.gswiki, inline=False)
        embed.add_field(name="YouTube Playlist", value=links.gameSessions, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='invite')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def invite(self, ctx):
        """Get an active invite link to this guild"""
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)


def setup(bot):
    bot.add_cog(Link(bot))
