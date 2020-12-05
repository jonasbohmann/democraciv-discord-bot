import typing
import discord

from discord.embeds import EmptyEmbed

from bot.config import mk, config
from bot.utils import exceptions, context, models, paginator, text, converter


def _make_property(role: mk.DemocracivRole):
    return property(lambda self: self._safe_get_member(role))


class GovernmentMixin:
    def __init__(self, b):
        self.bot = b

    def _safe_get_member(self, role) -> typing.Optional[discord.Member]:
        try:
            return self.bot.get_democraciv_role(role).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    async def _paginate_all_(self, ctx, *, model):
        if model is models.Bill:
            all_objects = await self.bot.db.fetch(f"SELECT id FROM bill ORDER BY id;")
        elif model is models.Law:
            all_objects = await self.bot.db.fetch(
                f"SELECT id FROM bill WHERE status = $1 ORDER BY id;",
                models.BillIsLaw.flag.value,
            )
        elif model is models.Motion:
            all_objects = await self.bot.db.fetch(f"SELECT id FROM motion ORDER BY id;")

        formatted = []

        for record in all_objects:
            obj = await model.convert(ctx, record["id"])
            formatted.append(obj.formatted)

        if model is models.Law:
            title = f"{self.bot.mk.NATION_EMOJI}  All Laws in {self.bot.mk.NATION_NAME}"
            empty_message = f"There are now laws yet."
        else:
            title = f"{self.bot.mk.NATION_EMOJI}  All Submitted {model.__name__}s"
            empty_message = f"No one has submitted any {model.__name__.lower()}s yet."

        pages = paginator.SimplePages(entries=formatted, title=title, empty_message=empty_message)
        await pages.start(ctx)

    async def _detail_view(self, ctx, *, obj: typing.Union[models.Bill, models.Motion]):
        embed = text.SafeEmbed(title=f"{obj.name} (#{obj.id})",
                               description=obj.description,
                               url=obj.link)

        if obj.submitter is not None:
            embed.set_author(
                name=f"Submitted by {obj.submitter.name}",
                icon_url=obj.submitter.avatar_url_as(static_format="png"),
            )
            submitted_by_value = f"{obj.submitter.mention} (during Session #{obj.session.id})"
        else:
            submitted_by_value = f"*Person left {self.bot.dciv.name}* (during Session #{obj.session.id})"

        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)

        if isinstance(obj, models.Bill):
            is_vetoable = "Yes" if obj.is_vetoable else "No"

            embed.add_field(name="Veto-able", value=is_vetoable, inline=True)
            embed.add_field(
                name="Status",
                value=obj.status.emojified_status(verbose=True),
                inline=False,
            )

            history = [f"{entry.date.strftime('%d %b %y')} - {entry.after}" for entry in obj.history[:3]]

            if history:
                embed.add_field(name="History", value="\n".join(history))

            if obj.status.is_law:
                embed.set_footer(text="All dates are in UTC. This is an active law.")
            else:
                embed.set_footer(text="All dates are in UTC.")

        await ctx.send(embed=embed)

    async def _search_model(self, ctx, *, model, query: str):
        if len(query) < 3:
            return await ctx.send(f"{config.NO} The query to search for has to be at least 3 characters long.")

        if model is models.Motion:
            found = await self.bot.db.fetch(
                "SELECT id from motion WHERE (lower(title) LIKE '%' || $1 || '%') OR"
                " (lower(description) LIKE '%' || $1 || '%') "
                "ORDER BY similarity(lower(title), $1) DESC LIMIT 20",
                query.lower(),
            )
            formatted = []

            for record in found:
                obj = await model.convert(ctx, record["id"])
                formatted.append(obj.formatted)
        else:
            is_law = model is models.Law
            # First, search by name similarity
            async with self.bot.db.acquire() as con:
                results = await self._search_bill_by_name(query, connection=con, search_laws=is_law)

                # Set word similarity threshold for search by tag
                await self._update_pg_trgm_similarity_threshold(0.4, connection=con)

                # Then, search by tag similarity
                for word in query.split():
                    if len(word) < 3 or word in (
                        "act",
                        "the",
                        "author",
                        "authors",
                        "date",
                        "name",
                        "bill",
                        "law",
                        "and",
                        "d/m/y",
                        "type",
                        "description",
                    ):
                        continue

                    result = await self._search_bill_by_tag(word, connection=con, search_laws=is_law)
                    if result:
                        results.update(result)

            formatted = list(results)

        pages = paginator.SimplePages(
            entries=formatted,
            title=f"{self.bot.mk.NATION_EMOJI}  {model.__name__}s matching '{query}'",
            empty_message="Nothing found.",
        )
        await pages.start(ctx)

    async def _from_person_model(self, ctx, *, member_or_party, model):
        member = member_or_party or ctx.author

        if isinstance(member, converter.PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
            empty = f"No member of {name} has submitted a {model.__name__.lower()} yet."
            title = f"{model.__name__}s from members of {name}"
            icon = await member.get_logo() or EmptyEmbed
        else:
            name = member.display_name
            members = [member.id]
            empty = f"{name} hasn't submitted any {model.__name__.lower()}s yet."
            title = f"{model.__name__}s from {name}"
            icon = member.avatar_url_as(static_format="png")

        if model in (models.Bill, models.Law):
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM bill " "WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )
        else:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM motion " "WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )

        formatted = []

        for record in objs_from_thing:
            obj = await model.convert(ctx, record["id"])
            formatted.append(obj.formatted)

        pages = paginator.SimplePages(entries=formatted, author=title, icon=icon, empty_message=empty)
        await pages.start(ctx)

    async def _search_bill_by_name(
        self, name: str, connection=None, search_laws: bool = False
    ) -> typing.Dict[str, None]:
        """Search for bills by their name, returns list with prettified strings of found bills"""

        con = connection or self.bot.db

        if search_laws:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE lower(name) LIKE '%' || $1 || '%' AND status = $2"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
                models.BillIsLaw.flag.value,
            )
        else:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE lower(name) LIKE '%' || $1 || '%'"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
            )

        found = {}

        for record in objs:
            model = models.Bill if not search_laws else models.Law
            obj = await model.convert(context.MockContext(self.bot), record["id"])
            found[obj.formatted] = None

        return found

    async def _search_bill_by_tag(self, tag: str, connection=None, search_laws: bool = False) -> typing.Dict[str, None]:
        """Search for bills by their tag(s), returns list with prettified strings of found laws"""

        # Once a bill is passed into law, the bot automatically generates tags for it to allow for easier and faster
        # searching.

        # The bot takes the submitter-provided description (from the -legislature submit command) *and* the description
        # from Google Docs (og:description property in HTML, usually the title of the Google Doc and the first
        # few sentences of content.) and tokenizes those with nltk. Then, every noun from both descriptions is saved
        # into the legislature_tags table with the corresponding law_id.

        con = connection or self.bot.db

        if search_laws:
            found_bills = await con.fetch(
                "SELECT bill_lookup_tag.bill_id FROM bill_lookup_tag "
                "JOIN bill on bill_lookup_tag.bill_id=bill.id "
                "WHERE (bill_lookup_tag.tag % $1 OR tag LIKE '%' || $1 || '%') AND bill.status = $2 ORDER BY tag <-> $1",
                tag.lower(),
                models.BillIsLaw.flag.value,
            )
        else:
            found_bills = await con.fetch(
                "SELECT bill_id FROM bill_lookup_tag WHERE tag % $1 OR tag LIKE '%' || $1 || '%' ORDER BY tag <-> $1",
                tag.lower(),
            )

        # Abuse dict as ordered set
        formatted = {}

        for record in found_bills:
            model = models.Bill if not search_laws else models.Law
            obj = await model.convert(context.MockContext(self.bot), record["bill_id"])
            formatted[obj.formatted] = None

        return formatted

    async def _update_pg_trgm_similarity_threshold(self, threshold: float = 0.3, connection=None):
        # I couldn't figure out how to make the setting persist in all sessions from the connection pool, so
        # we just set it every time per connection

        con = connection or self.bot.db
        await con.execute(f"SET pg_trgm.similarity_threshold = {threshold}")

    @staticmethod
    def is_google_doc_link(link: str) -> bool:
        """Checks whether a link is a valid Google Docs or Google Forms link"""

        valid_google_docs_url_strings = (
            "https://docs.google.com/",
            "https://drive.google.com/",
            "https://forms.gle/",
            "https://goo.gl/forms",
        )

        if len(link) < 15 or not link.startswith(valid_google_docs_url_strings):
            return False
        else:
            return True

    async def get_active_leg_session(self) -> typing.Optional[models.Session]:
        session_id = await self.bot.db.fetchval("SELECT id FROM legislature_session WHERE is_active = true")

        if session_id is not None:
            return await models.Session.convert(context.MockContext(self.bot), session_id)

    async def get_last_leg_session(self) -> typing.Optional[models.Session]:
        session_id = await self.bot.db.fetchval("SELECT MAX(id) FROM legislature_session")

        if session_id is not None:
            return await models.Session.convert(context.MockContext(self.bot), session_id)

    @property
    def gov_announcements_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.get_democraciv_channel(mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

    speaker = _make_property(mk.DemocracivRole.SPEAKER)
    vice_speaker = _make_property(mk.DemocracivRole.VICE_SPEAKER)
    chief_justice = _make_property(mk.DemocracivRole.CHIEF_JUSTICE)
    prime_minister = _make_property(mk.DemocracivRole.PRIME_MINISTER)
    lt_prime_minister = _make_property(mk.DemocracivRole.LT_PRIME_MINISTER)

    @property
    def speaker_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER)

    @property
    def vice_speaker_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.VICE_SPEAKER)

    @property
    def legislator_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)

    async def dm_legislators(self, *, message: str, reason: str):
        for legislator in self.legislator_role.members:
            await self.bot.safe_send_dm(target=legislator, reason=reason, message=message)

    def is_cabinet(self, member: discord.Member) -> bool:
        if self.speaker_role in member.roles or self.vice_speaker_role in member.roles:
            return True
        return False

    @property
    def justice_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUSTICE)

    @property
    def judge_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUDGE)
