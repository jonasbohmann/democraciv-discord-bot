import io
import operator
import random
import typing

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import context as slash_context
from bot.slash import ui
from bot.utils import text


class UtilitySlash(commands.Cog):
    random_group = app_commands.Group(
        name="random",
        description="Random generators.",
    )

    def __init__(self, bot):
        self.bot = bot
        self.cached_sorted_veterans_on_democraciv = []

    async def get_member_join_date(self, member: discord.Member):
        if member.guild.id == self.bot.dciv.id:
            original_date = await self.bot.db.fetchval(
                "SELECT join_date FROM original_join_date WHERE member = $1",
                member.id,
            )
            if original_date is not None:
                return original_date

        return member.joined_at

    async def get_member_join_position(
        self,
        member: discord.Member,
        members: typing.List[discord.Member],
    ):
        if member.guild.id == self.bot.dciv.id:
            sql = """SELECT position.row_number FROM 
                       (SELECT member, ROW_NUMBER () OVER (ORDER BY join_date) AS row_number
                             FROM original_join_date
                       ) AS position
                      WHERE member = $1"""
            join_position = await self.bot.db.fetchval(sql, member.id)
            all_members = await self.bot.db.fetchval(
                "SELECT COUNT(member) FROM original_join_date"
            )
            if join_position:
                return join_position, all_members

        all_members = len(members)
        joins = tuple(sorted(members, key=operator.attrgetter("joined_at")))
        if None in joins:
            return None, all_members

        try:
            return joins.index(member) + 1, all_members
        except ValueError:
            return None, all_members

    async def send_role_info(
        self,
        ctx: slash_context.InteractionContext,
        role: discord.Role,
    ):
        if role is None:
            return await ctx.send(
                f"{config.NO} `role` is neither a role on this server, nor on the Democraciv server."
            )

        if role.guild.id != ctx.guild.id:
            description = f":warning:  This role is from the {self.bot.dciv.name} server, not from this server!"
            role_name = role.name
        else:
            description = ""
            role_name = f"{role.name} {role.mention}"

        if role != role.guild.default_role:
            role_members = (
                "\n".join([f"{member.mention} {member}" for member in role.members])
                or "-"
            )
        else:
            role_members = "*Too long to display.*"

        embed = text.SafeEmbed(
            title="Role Information", description=description, colour=role.colour
        )

        embed.add_field(name="Role", value=role_name, inline=False)
        embed.add_field(name="ID", value=role.id, inline=False)
        embed.add_field(
            name="Created on", value=role.created_at.strftime("%B %d, %Y"), inline=True
        )
        embed.add_field(name="Colour", value=role.colour, inline=True)
        embed.add_field(
            name=f"Members ({len(role.members)})", value=role_members, inline=False
        )
        await ctx.send(embed=embed)

    @app_commands.command(
        name="delete-press-post",
        description="Delete one Reddit press post created by the bot.",
    )
    async def delete_press_post(self, interaction: discord.Interaction, url: str):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="delete-press-post",
        )
        await ctx.defer()
        if (
            f"reddit.com/r/{config.DEMOCRACIV_SUBREDDIT.lower()}" not in url.lower()
            and "comments" not in url.lower()
        ):
            return await ctx.send(
                f"{config.NO} Make sure the link to your Reddit press post is in the exact Reddit comments format.",
                ephemeral=True,
            )

        partitioned_url = url.partition("reddit.com/r/")
        if not partitioned_url[2]:
            return await ctx.send(
                f"{config.NO} Make sure the link to your Reddit press post is in the exact Reddit comments format.",
                ephemeral=True,
            )

        url = f"https://oauth.reddit.com/r/{partitioned_url[2]}"
        error_msg = f"{config.NO} Something went wrong. Are you sure that you gave me a real link to a press Reddit post?"
        js = await self.bot.api_request("POST", "reddit/post/get", json={"url": url})

        try:
            post = js[0]["data"]["children"][0]["data"]
            if post["author"].lower() == "[deleted]":
                return await ctx.send(f"{config.HINT} This post was already removed.")

            if (
                post["subreddit"].lower() != config.DEMOCRACIV_SUBREDDIT.lower()
                or post["author"].lower() != config.STARBOARD_REDDIT_USERNAME.lower()
            ):
                return await ctx.send(error_msg, ephemeral=True)

            content = "".join(post["selftext"].split())
            post_id = post["name"]
        except (TypeError, KeyError, IndexError):
            return await ctx.send(error_msg, ephemeral=True)

        if f"!A_ID:{ctx.author.id}" not in content:
            return await ctx.send(
                f"{config.NO} You are not the author of that press article.",
                ephemeral=True,
            )

        resp = await self.bot.api_request(
            "POST",
            "reddit/post/delete",
            json={"id": post_id},
        )
        if "error" in resp:
            return await ctx.send(error_msg, ephemeral=True)

        await ctx.send(f"{config.YES} Your press article was removed from Reddit.")

    @app_commands.command(
        name="whois", description="Show detailed information about a member."
    )
    @app_commands.guild_only()
    async def whois(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="whois")
        await ctx.defer()
        member = member or ctx.author

        embed = text.SafeEmbed()

        if isinstance(member, discord.User) and not isinstance(member, discord.Member):
            embed.description = ":warning: This person is not here in this server."

        embed.add_field(name="Person", value=f"{member} {member.mention}", inline=False)
        embed.add_field(name="ID", value=member.id, inline=False)
        embed.add_field(
            name="Discord Registration",
            value=member.created_at.strftime("%B %d, %Y"),
            inline=True,
        )

        if isinstance(member, discord.Member):
            join_pos, max_members = await self.get_member_join_position(
                member, ctx.guild.members
            )

            if not join_pos:
                join_pos = "Unknown"

            join_date = await self.get_member_join_date(member)
            embed.add_field(
                name="Joined",
                value=join_date.strftime("%B %d, %Y") if join_date else "Unknown",
                inline=True,
            )
            embed.add_field(
                name="Join Position", value=f"{join_pos}/{max_members}", inline=True
            )

            roles = [
                role.mention for role in member.roles[::-1] if not role.is_default()
            ]
            embed.add_field(
                name=f"Roles ({len(member.roles) - 1})",
                value=", ".join(roles) or "-",
                inline=False,
            )

        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @app_commands.command(name="avatar", description="View someone's avatar.")
    @app_commands.guild_only()
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        ctx = slash_context.from_interaction(interaction, command_name="avatar")
        await ctx.defer()
        user = user or ctx.author
        avatar_png = user.display_avatar.with_size(4096).url
        await ui.send_static(
            ctx,
            title=str(user),
            media_urls=[avatar_png],
            links=[ui.LayoutLink("Open Avatar", avatar_png, "\U0001f5bc")],
        )

    @app_commands.command(
        name="veterans", description="List the first 15 members who joined this server."
    )
    @app_commands.guild_only()
    async def veterans(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="veterans")
        await ctx.defer()

        sorted_first_15_members = []

        if ctx.guild.id == self.bot.dciv.id:
            if self.cached_sorted_veterans_on_democraciv:
                sorted_first_15_members = self.cached_sorted_veterans_on_democraciv
            else:
                vets = await self.bot.db.fetch(
                    "SELECT member FROM original_join_date ORDER BY join_date LIMIT 15"
                )
                self.cached_sorted_veterans_on_democraciv = sorted_first_15_members = [
                    self.bot.get_user(r["member"]) for r in vets
                ]
        else:
            guild_members_without_bots = [
                member for member in ctx.guild.members if not member.bot
            ]
            guild_members_without_bots.sort(key=lambda m: m.joined_at)
            sorted_first_15_members = guild_members_without_bots[:15]

        message = [
            "These are the first 15 people who joined this server.\nBot accounts are not counted.\n"
        ]

        for position, veteran in enumerate(sorted_first_15_members, start=1):
            fmt = f"{veteran.mention} {veteran}" if veteran else "*Unknown User*"
            message.append(f"{position}. {fmt}")

        embed = text.SafeEmbed(description="\n".join(message))
        embed.set_author(name=f"Veterans of {ctx.guild.name}", icon_url=ctx.guild_icon)
        await ctx.send(embed=embed)

    @app_commands.command(
        name="whohas", description="Show detailed information about a role."
    )
    @app_commands.guild_only()
    async def whohas(self, interaction: discord.Interaction, role: discord.Role):
        ctx = slash_context.from_interaction(interaction, command_name="whohas")
        await ctx.defer()
        await self.send_role_info(ctx, role)

    @random_group.command(name="number", description="Generate a random number.")
    async def random_number(
        self,
        interaction: discord.Interaction,
        start: int = 1,
        end: int = 100,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="random number")
        await ctx.defer()
        try:
            result = random.randint(start, end)
        except ValueError:
            return await ctx.send(
                f"{config.NO} Invalid random number range.", ephemeral=True
            )

        await ctx.send(
            f":arrows_counterclockwise: Random number ({start} - {end}): **{result}**"
        )

    @random_group.command(
        name="choose", description="Choose one option from a comma-separated list."
    )
    async def random_choose(self, interaction: discord.Interaction, choices: str):
        ctx = slash_context.from_interaction(interaction, command_name="random choose")
        await ctx.defer()
        parsed = [
            choice.strip()
            for choice in choices.replace("\n", ",").split(",")
            if choice.strip()
        ]
        if not parsed:
            return await ctx.send(
                f"{config.NO} Give me at least one choice.", ephemeral=True
            )

        await ctx.send(f":tada: The winner is: **{random.choice(parsed)}**")

    @random_group.command(name="coin", description="Flip a coin.")
    async def random_coin(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="random coin")
        await ctx.send(
            f":arrows_counterclockwise: **{random.choice(['Heads', 'Tails'])}**"
        )

    @app_commands.command(name="vibecheck", description="Run a vibe check.")
    @app_commands.guild_only()
    async def vibecheck(
        self, interaction: discord.Interaction, user: discord.User = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="vibecheck")
        await ctx.defer()
        user = user or ctx.author

        not_vibing = [
            "https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg",
            "https://s3.amazonaws.com/media.thecrimson.com/photos/2019/11/18/194724_1341037.png",
            "https://i.kym-cdn.com/photos/images/newsfeed/001/574/493/3ab.jpg",
            "https://i.imgflip.com/3ebtvt.jpg",
            "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT814jrNuqJsaVVHGqWw_0snlcysLN5fLpocEYrx6hzkgXYx7RV5w&s",
            "https://img.buzzfeed.com/buzzfeed-static/static/2019-10/7/15/asset/c5dd65974640/sub-buzz-521-1570462442-1.png?downsize=700:*&output-format=auto&output-quality=auto",
            "https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/12132fe4-1709-4287-9dcc-4ee9fc252a01/ddk55pz-bf72cab3-2b9e-474e-94a8-00e5f53d2baf.jpg?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZTBkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiJcL2ZcLzEyMTMyZmU0LTE3MDktNDI4Ny05ZGNjLTRlZTlmYzI1MmEwMVwvZGRrNTVwei1iZjcyY2FiMy0yYjllLTQ3NGUtOTRhOC0wMGU1ZjUzZDJiYWYuanBnIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.Sb6Axu0O6iZ3YmZJHg5wRe-r41iLnWVqa_ddWrtbQlo",
            "https://pbs.twimg.com/media/EHgYHjOX4AAuv6s.jpg",
            "https://pbs.twimg.com/media/EGTsxzaUwAAuBLG?format=jpg&name=900x900",
            "https://66.media.tumblr.com/c2fc65d9f8614dbd9bb7378983e0598e/tumblr_pxw332rEmZ1yom1s3o1_1280.png",
        ]

        vibing = [
            "https://preview.redd.it/i-will-give-your-ocs-a-vibe-check-v0-0y5skb0tx9sb1.jpeg?width=750&format=pjpg&auto=webp&s=b1d8598547a600f7c589a069ee92be6a08bb1589",
            "https://images.squarespace-cdn.com/content/63c88a61bbbb6e3e419189da/1687420314895-70N8D0I60O36DB4PCRX0/You-Passed-The-Vibe-Check-Cats-y2k-png-design.jpg?format=1500w&content-type=image%2Fjpeg",
            "https://i.kym-cdn.com/photos/images/original/001/599/028/bf3.jpg",
            "https://i.redd.it/p4e6a65i3bw31.jpg",
            "https://media.makeameme.org/created/congratulations-you-have-61e05e0d4b.jpg",
        ]

        passed = random.randrange(1, stop=100) >= 65

        if passed:
            image = random.choice(vibing)
            pretty = "passed"
        else:
            image = random.choice(not_vibing)
            pretty = "not passed"

        embed = text.SafeEmbed(
            title=f"{user} has __{pretty}__ the vibe check",
        )
        embed.set_image(url=image)
        await ctx.send(embed=embed)

    @app_commands.command(name="dog", description="Show a random dog image or video.")
    async def dog(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="dog")
        await ctx.defer()
        async with self.bot.session.get("https://random.dog/woof") as resp:
            if resp.status != 200:
                return await ctx.send(f"{config.NO} No dog found :(")

            filename = await resp.text()
            url = f"https://random.dog/{filename}"

        filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
        if filename.endswith((".mp4", ".webm")):
            async with self.bot.session.get(url) as other:
                if other.status != 200:
                    return await ctx.send(
                        f"{config.NO} Could not download dog video :("
                    )
                if int(other.headers["Content-Length"]) >= filesize:
                    return await ctx.send(
                        f"{config.NO} Video was too big to upload, watch it here instead: {url}"
                    )

                fp = io.BytesIO(await other.read())
                return await ctx.send(file=discord.File(fp, filename=filename))

        embed = text.SafeEmbed(title="Random Dog")
        embed.set_image(url=url)
        embed.set_footer(text="Just for Taylor.")
        await ctx.send(embed=embed)

    @app_commands.command(name="cat", description="Show a random cat.")
    async def cat(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="cat")
        await ctx.defer()
        async with self.bot.session.get(
            "https://api.thecatapi.com/v1/images/search"
        ) as response:
            if response.status != 200:
                return await ctx.send(f"{config.NO} No cat found :(")

            data = await response.json()

        await ui.send_static(ctx, title="Random Cat", media_urls=[data[0]["url"]])

    @app_commands.command(
        name="server-invite", description="Create a permanent invite for this server."
    )
    @app_commands.guild_only()
    async def server_invite(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="server-invite")
        await ctx.defer()
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)


async def setup(bot):
    await bot.add_cog(UtilitySlash(bot))
