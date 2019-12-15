import discord
import datetime

import util.utils as utils
import util.exceptions as exceptions

from config import config
from discord.ext import commands
from bs4 import BeautifulSoup, SoupStrainer


class Legislature(commands.Cog):
    """Useful commands for Legislators"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='submit')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @utils.is_democraciv_guild()
    async def submit(self, ctx, google_docs_url: str):
        """Submit a new bill directly to the current Speaker of the Legislature"""

        speaker_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name="Speaker of the Legislature")
        vice_speaker_role = discord.utils.get(self.bot.democraciv_guild_object.roles, name="Vice-Speaker "
                                                                                           "of the Legislature")
        valid_google_docs_url_strings = ['https://docs.google.com/', 'https://drive.google.com/']

        if len(google_docs_url) < 15 or not google_docs_url:
            await ctx.send(":x: You have to give me a valid Google Docs URL of the bill you want to submit!")
            return

        if not any(string in google_docs_url for string in valid_google_docs_url_strings):
            await ctx.send(":x: That doesn't look like a Google Docs URL.")
            return

        if speaker_role is None:
            raise exceptions.RoleNotFoundError("Speaker of the Legislature")

        if vice_speaker_role is None:
            raise exceptions.RoleNotFoundError("Vice-Speaker of the Legislature")

        if len(speaker_role.members) == 0:
            raise exceptions.NoOneHasRoleError("Speaker of the Legislature")

        if len(vice_speaker_role.members) == 0:
            raise exceptions.NoOneHasRoleError("Vice-Speaker of the Legislature")

        speaker_person = speaker_role.members[0]  # Assuming there's only 1 speaker ever
        vice_speaker_person = vice_speaker_role.members[0]  # Assuming there's only 1 vice-speaker ever

        try:
            async with ctx.typing():
                async with self.bot.session.get(google_docs_url) as response:
                    text = await response.read()

                strainer = SoupStrainer(property="og:title")  # Only parse the title property HTMl to save time
                soup = BeautifulSoup(text, "lxml", parse_only=strainer)  # Use lxml parser to speed things up

                bill_title = soup.find("meta")['content']  # Get title of Google Docs website

                if bill_title.endswith(' - Google Docs'):
                    bill_title = bill_title[:-14]

                soup.decompose()  # Garbage collection

        except Exception:
            await ctx.send(":x: Could not connect to Google Docs.")
            return

        embed = self.bot.embeds.embed_builder(title="New Bill Submitted", description="", time_stamp=True)
        embed.add_field(name="Title", value=bill_title, inline=False)
        embed.add_field(name="Author", value=ctx.message.author.name)
        embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow())
        embed.add_field(name="URL", value=google_docs_url, inline=False)

        try:
            await speaker_person.send(embed=embed)
            await vice_speaker_person.send(embed=embed)

            await ctx.send(
                f":white_check_mark: Successfully submitted '{bill_title}' to the Legislative Cabinet!")
        except Exception:
            await ctx.send(":x: Unexpected error occurred during DMing the Speaker or Vice-Speaker!"
                           " Your bill was not submitted, please try again!")
            return

    @submit.error
    async def submiterror(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole) or isinstance(error, commands.MissingRole):
            await ctx.send(":x: Only Legislators are allowed to use this command!")

        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'google_docs_url':
                await ctx.send(":x: You have to give me a valid Google Docs URL of the bill you want to submit!")


def setup(bot):
    bot.add_cog(Legislature(bot))
