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
        if role.guild.id != ctx.guild.id:
            role_name = role.name
            description = f":warning: This role is from the {self.bot.dciv.name} server, not from this server."
        else:
            role_name = f"{role.name} {role.mention}"
            description = None

        if role != role.guild.default_role:
            members = (
                "\n".join(f"{member.mention} {member}" for member in role.members)
                or "-"
            )
        else:
            members = "*Too long to display.*"

        await ctx.send(
            view=ui.RichLayout(
                title="Role Information",
                body=description,
                sections=[
                    ui.LayoutSection("Role", role_name),
                    ui.LayoutSection("ID", str(role.id)),
                    ui.LayoutSection(
                        "Created on", role.created_at.strftime("%B %d, %Y")
                    ),
                    ui.LayoutSection("Colour", str(role.colour)),
                    ui.LayoutSection(f"Members ({len(role.members)})", members),
                ],
                accent_colour=role.colour.value if role.colour.value else None,
                author_id=ctx.author.id,
            )
        )

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

        roles = [role.mention for role in member.roles[::-1] if not role.is_default()]
        join_pos, max_members = await self.get_member_join_position(
            member,
            ctx.guild.members,
        )
        join_pos = join_pos or "Unknown"
        join_date = await self.get_member_join_date(member)

        await ui.send_static(
            ctx,
            title=str(member),
            sections=[
                ui.LayoutSection("Person", f"{member.mention} {member}"),
                ui.LayoutSection("ID", str(member.id)),
                ui.LayoutSection(
                    "Discord Registration",
                    member.created_at.strftime("%B %d, %Y"),
                ),
                ui.LayoutSection(
                    "Joined",
                    join_date.strftime("%B %d, %Y") if join_date else "Unknown",
                ),
                ui.LayoutSection("Join Position", f"{join_pos}/{max_members}"),
                ui.LayoutSection(
                    f"Roles ({len(member.roles) - 1})", ", ".join(roles) or "-"
                ),
            ],
            links=[
                ui.LayoutLink(
                    "Avatar",
                    member.display_avatar.with_size(4096).url,
                    "\U0001f5bc",
                )
            ],
        )

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

        if ctx.guild.id == self.bot.dciv.id:
            if self.cached_sorted_veterans_on_democraciv:
                veterans = self.cached_sorted_veterans_on_democraciv
            else:
                records = await self.bot.db.fetch(
                    "SELECT member FROM original_join_date ORDER BY join_date LIMIT 15"
                )
                veterans = self.cached_sorted_veterans_on_democraciv = [
                    self.bot.get_user(record["member"]) for record in records
                ]
        else:
            veterans = [member for member in ctx.guild.members if not member.bot]
            veterans.sort(key=lambda member: member.joined_at)
            veterans = veterans[:15]

        entries = [
            (
                f"{position}. {veteran.mention} {veteran}"
                if veteran
                else f"{position}. *Unknown User*"
            )
            for position, veteran in enumerate(veterans, start=1)
        ]
        await ui.send_static(
            ctx,
            title=f"Veterans of {ctx.guild.name}",
            body="These are the first 15 people who joined this server. Bot accounts are not counted.",
            sections=[ui.LayoutSection("Members", "\n".join(entries) or "-")],
        )

    @app_commands.command(
        name="whohas", description="Show detailed information about a role."
    )
    @app_commands.guild_only()
    async def whohas(self, interaction: discord.Interaction, role: discord.Role):
        ctx = slash_context.from_interaction(interaction, command_name="whohas")
        await ctx.defer()
        await self.send_role_info(ctx, role)

    @app_commands.command(
        name="role-info", description="Show detailed information about a role."
    )
    @app_commands.guild_only()
    async def role_info_command(
        self, interaction: discord.Interaction, role: discord.Role
    ):
        ctx = slash_context.from_interaction(interaction, command_name="role-info")
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
        passed = random.randrange(1, stop=100) >= 65
        images = (
            [
                "https://preview.redd.it/i-will-give-your-ocs-a-vibe-check-v0-0y5skb0tx9sb1.jpeg?width=750&format=pjpg&auto=webp&s=b1d8598547a600f7c589a069ee92be6a08bb1589",
                "https://i.kym-cdn.com/photos/images/original/001/599/028/bf3.jpg",
            ]
            if passed
            else [
                "https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg",
                "https://i.imgflip.com/3ebtvt.jpg",
            ]
        )
        pretty = "passed" if passed else "not passed"
        await ui.send_static(
            ctx,
            title=f"{user} has {pretty} the vibe check",
            media_urls=[random.choice(images)],
        )

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

        await ui.send_static(ctx, title="Random Dog", media_urls=[url])

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
