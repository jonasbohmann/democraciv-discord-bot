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
        per_page = None

        if model is models.Bill:
            all_objects = await self.bot.db.fetch("SELECT id FROM bill ORDER BY id;")
        elif model is models.Law:
            all_objects = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE status = $1 ORDER BY id;",
                models.BillIsLaw.flag.value,
            )
        elif model is models.Motion:
            per_page = 12
            all_objects = await self.bot.db.fetch("SELECT id FROM motion ORDER BY id;")

        formatted = []

        for record in all_objects:
            obj = await model.convert(ctx, record["id"])
            formatted.append(obj.formatted)

        if model is models.Law:
            title = f"All Laws in {self.bot.mk.NATION_NAME}"
            empty_message = f"There are no laws yet."
        else:
            title = f"All Submitted {model.__name__}s"
            empty_message = f"No one has submitted any {model.__name__.lower()}s yet."

        pages = paginator.SimplePages(
            entries=formatted,
            icon=self.bot.mk.NATION_ICON_URL,
            author=title,
            empty_message=empty_message,
            per_page=per_page,
        )
        await pages.start(ctx)

    async def _detail_view(
        self,
        ctx: context.CustomContext,
        *,
        obj: typing.Union[models.Bill, models.Motion],
    ):
        embed = text.SafeEmbed(
            title=f"{obj.name} (#{obj.id})", description=obj.description, url=obj.link
        )

        if obj.submitter is not None:
            embed.set_author(
                name=f"Submitted by {obj.submitter.name}",
                icon_url=obj.submitter.avatar_url_as(static_format="png"),
            )
            submitted_by_value = f"{obj.submitter.mention} {obj.submitter}"
        else:
            submitted_by_value = f"*Unknown Person*"

        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)

        if isinstance(obj, models.Bill):
            # is_vetoable = "Yes" if obj.is_vetoable else "No"

            # embed.add_field(name="Veto-able", value=is_vetoable, inline=True)
            embed.add_field(
                name="Status",
                value=obj.status.emojified_status(verbose=True),
                inline=False,
            )

            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    [f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors]
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

            history = [
                f"{entry.date.strftime('%d %B %Y')} - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:5]
            ]

            if history:
                embed.add_field(name="History", value="\n".join(history))

            if obj.status.is_law:
                # todo remove session when mk8 ends
                embed.set_footer(
                    text=f"All dates are in UTC. This is an active law. Session #{obj.session.id}"
                )
            else:
                embed.set_footer(
                    text=f"All dates are in UTC. Session #{obj.session.id}"
                )

            view = await ctx.send(embed=embed)

            if await ctx.ask_to_continue(message=view, emoji="\U0001f4c3"):
                await self._show_bill_text(ctx, obj)

            return

        await ctx.send(embed=embed)

    async def _show_bill_text(self, ctx, bill: models.Bill):
        entries = bill.content.splitlines()
        entries.insert(
            0,
            f"[Link to the Google Docs document of this Bill]({bill.link})\n"
            f"*Am I showing you outdated or wrong text? Tell the {self.bot.mk.speaker_term} to "
            f"synchronize this text with the Google Docs text of this bill with "
            f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} bill synchronize {bill.id}`.*\n\n",
        )
        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"{bill.name} (#{bill.id})",
        )

        await pages.start(ctx)

    async def _search_model(self, ctx, *, model, query: str, return_model=False):
        if len(query) < 3:
            raise exceptions.DemocracivBotException(
                f"{config.NO} The query to search for has to be at least 3 characters long."
            )

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
                if return_model:
                    formatted.append(obj)
                else:
                    formatted.append(obj.formatted)
        else:
            is_law = model is models.Law
            # First, search by name similarity
            async with self.bot.db.acquire() as con:
                results = await self._search_bill_by_name(
                    query, connection=con, search_laws=is_law, return_model=return_model
                )

                # Set word similarity threshold for search by tag
                await self._update_pg_trgm_similarity_threshold(0.4, connection=con)

                # Then, search by tag similarity
                # for word in query.split():
                #    if len(word) < 3 or word in (
                #        "the",
                #        "author",
                #        "authors",
                #        "date",
                #        "name",
                #        "and",
                #        "d/m/y",
                #        "type",
                #        "description",
                #        "by",
                #        "generated",
                #    ):
                #        continue

                result = await self._search_bill_by_tag(
                    query, connection=con, search_laws=is_law, return_model=return_model
                )
                if result:
                    results.update(result)

            formatted = list(results)

        return formatted

    async def _from_person_model(self, ctx, *, member_or_party, model, paginate=True):
        member = member_or_party or ctx.author
        submit_term = "written" if model is models.Law else "submitted"
        per_page = None

        if isinstance(member, converter.PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
            empty = (
                f"No member of {name} has {submit_term} a {model.__name__.lower()} yet."
            )
            title = f"{model.__name__}s from members of {name}"
            icon = await member.get_logo() or self.bot.mk.NATION_ICON_URL or EmptyEmbed
        else:
            name = member.display_name
            members = [member.id]
            empty = f"{name} hasn't {submit_term} any {model.__name__.lower()}s yet."
            title = f"{model.__name__}s from {name}"
            icon = member.avatar_url_as(static_format="png")

        if model is models.Bill:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )

        elif model is models.Law:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) AND status = $2 ORDER BY id;",
                members,
                models.BillIsLaw.flag.value,
            )
        else:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM motion WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )
            per_page = 12

        formatted = []

        for record in objs_from_thing:
            obj = await model.convert(ctx, record["id"])
            formatted.append(obj.formatted)

        if not paginate:
            return formatted

        pages = paginator.SimplePages(
            entries=formatted,
            author=title,
            icon=icon,
            per_page=per_page,
            empty_message=empty,
        )
        await pages.start(ctx)

    async def _search_bill_by_name(
        self, name: str, connection=None, search_laws: bool = False, return_model=False
    ) -> typing.Dict[typing.Union[models.Bill, models.Law, str], None]:
        """Search for bills by their name, returns list with prettified strings of found bills"""

        con = connection or self.bot.db

        model = models.Bill if not search_laws else models.Law

        if search_laws:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE (lower(name) LIKE '%' || $1 || '%' OR lower(name) % $1) AND status = $2"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
                models.BillIsLaw.flag.value,
            )
        else:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE (lower(name) LIKE '%' || $1 || '%' OR lower(name) % $1)"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
            )

        found = {}

        for record in objs:
            obj = await model.convert(context.MockContext(self.bot), record["id"])
            if return_model:
                found[obj] = None
            else:
                found[obj.formatted] = None

        return found

    async def _search_bill_by_tag(
        self,
        tag: str,
        connection=None,
        search_laws: bool = False,
        *,
        return_model=False,
    ) -> typing.Dict[typing.Union[models.Bill, models.Law, str], None]:
        """Search for bills by their tag(s), returns list with prettified strings of found laws"""

        con = connection or self.bot.db

        model = models.Bill if not search_laws else models.Law

        if search_laws:
            found_bills = await con.fetch(
                "SELECT bill_lookup_tag.bill_id FROM bill_lookup_tag "
                "JOIN bill on bill_lookup_tag.bill_id=bill.id "
                "WHERE (bill_lookup_tag.tag % $1 OR bill_lookup_tag.tag LIKE '%' || $1 || '%') AND bill.status = $2 ORDER BY bill_lookup_tag.tag <-> $1",
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
            obj = await model.convert(context.MockContext(self.bot), record["bill_id"])
            if return_model:
                formatted[obj] = None
            else:
                formatted[obj.formatted] = None

        return formatted

    async def _update_pg_trgm_similarity_threshold(
        self, threshold: float = 0.3, connection=None
    ):
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

        return len(link) >= 15 and link.startswith(valid_google_docs_url_strings)

    async def get_active_leg_session(self) -> typing.Optional[models.Session]:
        session_id = await self.bot.db.fetchval(
            "SELECT id FROM legislature_session WHERE status != 'Closed'"
        )

        if session_id is not None:
            return await models.Session.convert(
                context.MockContext(self.bot), session_id
            )

    async def get_last_leg_session(self) -> typing.Optional[models.Session]:
        session_id = await self.bot.db.fetchval(
            "SELECT MAX(id) FROM legislature_session"
        )

        if session_id is not None:
            return await models.Session.convert(
                context.MockContext(self.bot), session_id
            )

    class MockChannel:
        id = 0
        name = mention = "deleted channel"

        async def send(self, *args, **kwargs):
            pass

    @property
    def gov_announcements_channel(
        self,
    ) -> typing.Union[discord.TextChannel, MockChannel]:
        try:
            return self.bot.get_democraciv_channel(
                mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL
            )
        except exceptions.ChannelNotFoundError:
            return self.MockChannel()

    speaker = _make_property(mk.DemocracivRole.SPEAKER)
    vice_speaker = _make_property(mk.DemocracivRole.VICE_SPEAKER)
    chief_justice = _make_property(mk.DemocracivRole.CHIEF_JUSTICE)
    prime_minister = _make_property(mk.DemocracivRole.PRIME_MINISTER)
    lt_prime_minister = _make_property(mk.DemocracivRole.LT_PRIME_MINISTER)

    @property
    def speaker_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER)
        except exceptions.RoleNotFoundError:
            return None

    @property
    def vice_speaker_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.VICE_SPEAKER)
        except exceptions.RoleNotFoundError:
            return None

    @property
    def legislator_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)
        except exceptions.RoleNotFoundError:
            return None

    async def dm_legislators(self, *, message: str, reason: str):
        if not self.legislator_role:
            return

        for legislator in self.legislator_role.members:
            await self.bot.safe_send_dm(
                target=legislator, reason=reason, message=message
            )

    def is_cabinet(self, member: discord.Member) -> bool:
        return (
            self.speaker_role in member.roles or self.vice_speaker_role in member.roles
        )

    @property
    def justice_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUSTICE)

    @property
    def judge_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUDGE)
