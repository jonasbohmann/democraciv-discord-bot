import copy
import nltk
import typing
import discord
import asyncpg
import datetime
import collections

from discord.ext import tasks
from bs4 import BeautifulSoup, SoupStrainer

from bot.utils import exceptions
from bot.config import mk
from bot.utils.converter import Session, Bill, Law


class MockContext:
    def __init__(self, bot):
        self.bot = bot


class AnnouncementQueue:
    def __init__(self, bot, channel):
        self.bot = bot
        self._channel: mk.DemocracivChannel = channel
        self._objects: typing.List[typing.Union[Bill, Law, Session]] = []
        self._last_addition = None
        self._task = None

    def __del__(self):
        if self._task is not None:
            self._task.cancel()

    @property
    def channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.get_democraciv_channel(self._channel)

    def get_message(self) -> str:
        raise NotImplementedError()

    def split_message(self, message: str) -> typing.List[str]:
        lines = message.splitlines(keepends=True)
        split_into_2000 = dict()
        index = 0

        for paragraph in lines:
            try:
                split_into_2000[index]
            except KeyError:
                split_into_2000[index] = ""

            split_into_2000[index] = split_into_2000[index] + ''.join(paragraph)

            if (len(''.join(split_into_2000[index]))) > 1900:
                index += 1

        return list(split_into_2000.values())

    def add(self, obj: typing.Union[Bill, Law, Session]):
        if len(self._objects) == 0:
            self._task = copy.copy(self._wait)
            self._task.start()

        self._objects.append(obj)
        self._last_addition = datetime.datetime.utcnow()

    async def send_messages(self):
        message = self.get_message()

        if len(message) > 2000:
            split_messages = self.split_message(message)
            for msg in split_messages:
                await self.channel.send(msg)
        else:
            await self.channel.send(message)
        self._objects.clear()
        self._task.cancel()

    @tasks.loop(seconds=30)
    async def _wait(self):
        if self._last_addition is not None and \
                datetime.datetime.utcnow() - self._last_addition > datetime.timedelta(minutes=10):
            self._last_addition = None
            await self.send_messages()


class LawUtils:
    """Several helper functions to query the database for session, bill & law info. """

    def __init__(self, bot):
        self.bot = bot
        self.illegal_tags = ('act', 'the', 'author', 'authors', 'date',
                             'name', 'bill', 'law', 'and', 'd/m/y', 'type', 'description')

        # The natural language processor module nltk used for legislature_tags needs extra data to work
        nltk.download('punkt')
        nltk.download('averaged_perceptron_tagger')

    @staticmethod
    def is_google_doc_link(link: str) -> bool:
        """Checks whether a link is a valid Google Docs or Google Forms link"""

        valid_google_docs_url_strings = ('https://docs.google.com/', 'https://drive.google.com/',
                                         'https://forms.gle/', 'https://goo.gl/forms')

        if len(link) < 15 or not link.startswith(valid_google_docs_url_strings):
            return False
        else:
            return True

    async def get_active_leg_session(self) -> typing.Optional[Session]:
        law_id = await self.bot.db.fetchval("SELECT id FROM legislature_sessions WHERE is_active = true")

        if law_id is not None:
            return await Session.convert(MockContext(self.bot), law_id)

        return None

    async def get_last_leg_session(self) -> typing.Optional[Session]:
        law_id = await self.bot.db.fetchval("SELECT MAX(id) FROM legislature_sessions")

        if law_id is not None:
            return await Session.convert(MockContext(self.bot), law_id)

        return None

    def scrape_google_docs_html(self, text: str):
        strainer = SoupStrainer(property=["og:title", "og:description"])
        soup = BeautifulSoup(text, "lxml", parse_only=strainer)  # Use lxml parser to speed things up

        if soup is None:
            return None

        meta_tags = soup.find_all("meta")

        if not meta_tags:
            return None

        try:
            title = meta_tags[0]['content']
            description = meta_tags[1]['content']
        except (IndexError, KeyError):
            return None

        if title.endswith(' - Google Docs'):
            title = title[:-14]

        if description.endswith('...'):
            description = description[:-3]

        soup.decompose()  # Garbage collection
        return {'title': title, 'description': description}

    async def get_google_docs_meta_data(self, link: str) -> typing.Optional[typing.Dict[str, str]]:
        """Gets title of a Google Docs document"""

        async with self.bot.session.get(link) as response:
            if response.status == 200:
                text = await response.read()

        if not text:
            return None

        return await self.bot.loop.run_in_executor(None, self.scrape_google_docs_html, text)

    def generate_law_tags(self, google_docs_description: str, author_description: str) -> typing.List[str]:
        """Generates tags from all nouns of submitter-provided description and the Google Docs description"""

        # Function to check if token is noun
        is_noun = lambda pos: pos[:2] == 'NN'

        # Tokenize both descriptions
        tokenized_docs_description = nltk.word_tokenize(google_docs_description)
        tokenized_author_description = nltk.word_tokenize(author_description)

        # Add all nouns to list
        tags = [word for (word, pos) in nltk.pos_tag(tokenized_docs_description) +
                nltk.pos_tag(tokenized_author_description) if is_noun(pos) and
                len(word) >= 3 and
                word.lower() not in self.illegal_tags]

        # Eliminate duplicate tags
        tags = list(set(tags))

        return tags

    @staticmethod
    def sort_dict_by_value(to_be_sorted: dict) -> dict:
        """Sorts a dict by values in reverse order (i.e.: bigger number -> top of the dict)"""

        to_be_sorted = {k: v for k, v in sorted(to_be_sorted.items(),
                                                key=lambda item: item[1], reverse=True)}

        return to_be_sorted

    @staticmethod
    def count_rows_from_db_record(record: asyncpg.Record, record_key: str) -> dict:
        """Converts a database asyncp.Record into a dict with Record keys as keys and their
         amount of occurrence as value"""

        record_as_list = []

        for r in record:
            record_as_list.append(r[record_key])

        counter = collections.Counter(record_as_list)
        return dict(counter)

    def get_pretty_stats(self, to_be_pretty: dict, stats_name: str) -> str:
        """Prettifies the dicts used in generate_leg_statistics() to strings"""

        pretty = f""
        i = 1

        for key, value in to_be_pretty.items():
            if self.bot.get_user(key) is not None:
                if i > 5:
                    break

                if value == 1:
                    # Singular stats_name
                    pretty += f"{i}. {self.bot.get_user(key).mention} with {value} {stats_name[:-1]}\n"
                else:
                    # Plural stats_name
                    pretty += f"{i}. {self.bot.get_user(key).mention} with {value} {stats_name}\n"

                i += 1

            else:
                continue

        return pretty

    async def generate_leg_statistics(self) -> list:
        """Generates statistics for the -legislature stats command"""

        # General total amount of things
        amount_of_sessions = await self.bot.db.fetchval("SELECT COUNT(id) FROM legislature_sessions")
        amount_of_bills = await self.bot.db.fetchval("SELECT COUNT(id) FROM legislature_bills")
        amount_of_laws = await self.bot.db.fetchval("SELECT COUNT(law_id) FROM legislature_laws")
        amount_of_motions = await self.bot.db.fetchval("SELECT COUNT(id) FROM legislature_motions")

        # Sorted statistics by Discord Member
        amount_of_bills_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT submitter FROM "
                                                                                              "legislature_bills"),
                                                                      'submitter')
        amount_of_sessions_by_speaker = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT speaker FROM "
                                                                                               "legislature_sessions"),
                                                                       'speaker')
        query = """SELECT submitter FROM legislature_bills AS b WHERE exists (SELECT 1 FROM legislature_laws l
                   WHERE l.bill_id = b.id)"""
        amount_of_laws_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch(query), 'submitter')

        # Prettified sorted statistics by discord.Member
        pretty_top_submitter = self.get_pretty_stats(self.sort_dict_by_value(amount_of_bills_by_submitter), 'bills')

        pretty_top_speaker = self.get_pretty_stats(self.sort_dict_by_value(amount_of_sessions_by_speaker), 'sessions')

        pretty_top_lawmaker = self.get_pretty_stats(self.sort_dict_by_value(amount_of_laws_by_submitter), 'laws')

        return [amount_of_sessions, amount_of_bills, amount_of_laws, amount_of_motions,
                pretty_top_submitter, pretty_top_speaker, pretty_top_lawmaker]



    async def update_pg_trgm_similarity_threshold(self, threshold: float = 0.3, connection=None):
        # I couldn't figure out how to make the setting persist in all sessions from the connection pool, so
        # we just set it every time per connection

        con = connection or self.bot.db
        await con.execute(f"SET pg_trgm.similarity_threshold = {threshold}")

    async def search_law_by_name(self, name: str, connection=None) -> typing.Dict[str, None]:
        """Search for laws by their name, returns list with prettified strings of found laws"""

        con = connection or self.bot.db

        query = """SELECT law_id FROM legislature_laws AS l
                   JOIN legislature_bills lb ON l.bill_id = lb.id
                   WHERE lower(lb.bill_name) LIKE '%' || $1 || '%' 
                   ORDER BY similarity(lower(lb.bill_name), $1) DESC
                   LIMIT 10;"""

        laws = await con.fetch(query, name.lower())

        found = dict()

        for law_id in laws:
            law = await Law.convert(MockContext(self.bot), law_id['law_id'])
            found[f"Law #{law.id} - [{law.bill.name}]({law.bill.link})"] = None

        return found

    async def search_law_by_tag(self, tag: str, connection=None) -> typing.Dict[str, None]:
        """Search for laws by their tag(s), returns list with prettified strings of found laws"""

        # Once a bill is passed into law, the bot automatically generates tags for it to allow for easier and faster
        # searching.

        # The bot takes the submitter-provided description (from the -legislature submit command) *and* the description
        # from Google Docs (og:description property in HTML, usually the title of the Google Doc and the first
        # few sentences of content.) and tokenizes those with nltk. Then, every noun from both descriptions is saved
        # into the legislature_tags table with the corresponding law_id.

        con = connection or self.bot.db

        found_laws = await con.fetch("SELECT id FROM legislature_tags WHERE tag % $1 ORDER BY tag <-> $1",
                                     tag.lower())

        # Abuse dict as ordered set
        pretty_laws = dict()

        for law_id in found_laws:
            law = await Law.convert(MockContext(self.bot), law_id['id'])
            pretty_laws[f"Law #{law.id} - [{law.bill.name}]({law.bill.link})"] = None

        return pretty_laws
