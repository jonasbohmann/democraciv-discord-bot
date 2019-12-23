import collections
import asyncpg
import nltk

from bs4 import BeautifulSoup, SoupStrainer

"""
   Several helper functions to query the database for date relevant for legislative sessions.
   
"""


class LawUtils:

    def __init__(self, bot):
        self.bot = bot
        nltk.download('punkt')
        nltk.download('averaged_perceptron_tagger')

    def is_google_doc_link(self, link: str):
        valid_google_docs_url_strings = ['https://docs.google.com/', 'https://drive.google.com/',
                                         'https://forms.gle/', 'https://goo.gl/forms']

        if len(link) < 15 or not link.startswith(tuple(valid_google_docs_url_strings)):
            return False
        else:
            return True

    async def get_active_leg_session(self):
        active_leg_session_id = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE is_active = true")

        if active_leg_session_id is None:
            return None
        else:
            return active_leg_session_id['id']

    async def get_status_of_active_leg_session(self):
        active_leg_session_status = await self.bot.db.fetchrow("SELECT status FROM legislature_sessions WHERE"
                                                               " is_active = true")

        if active_leg_session_status is None:
            return None
        else:
            return active_leg_session_status['status']

    async def get_last_leg_session(self):
        last_session = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE id = "
                                                  "(SELECT MAX(id) FROM legislature_sessions)")

        if last_session is not None:
            return last_session['id']
        else:
            return None

    async def get_highest_bill_id(self):
        last_bill = await self.bot.db.fetchrow("SELECT id FROM legislature_bills WHERE id = "
                                               "(SELECT MAX(id) FROM legislature_bills)")

        if last_bill is not None:
            return last_bill['id']
        else:
            return None

    async def generate_new_bill_id(self):
        last_id = await self.get_highest_bill_id()

        if last_id is None:
            last_id = 0

        return last_id + 1

    async def get_highest_law_id(self):
        last_law = await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE law_id = "
                                              "(SELECT MAX(law_id) FROM legislature_laws)")

        if last_law is not None:
            return last_law['law_id']
        else:
            return None

    async def generate_new_law_id(self):
        last_law = await self.get_highest_law_id()

        if last_law is None:
            last_law = 0

        return last_law + 1

    async def get_highest_motion_id(self):
        last_motion = await self.bot.db.fetchrow("SELECT id FROM legislature_motions WHERE id = "
                                                 "(SELECT MAX(id) FROM legislature_motions)")

        if last_motion is not None:
            return last_motion['id']
        else:
            return None

    async def generate_new_motion_id(self):
        last_id = await self.get_highest_motion_id()

        if last_id is None:
            last_id = 0

        return last_id + 1

    async def get_google_docs_title(self, link: str):
        try:
            async with self.bot.session.get(link) as response:
                text = await response.read()

            strainer = SoupStrainer(property="og:title")  # Only parse the title property to save time
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)  # Use lxml parser to speed things up

            bill_title = soup.find("meta")['content']  # Get title of Google Docs website

            if bill_title.endswith(' - Google Docs'):
                bill_title = bill_title[:-14]

            soup.decompose()  # Garbage collection

            return bill_title

        except Exception:
            return None

    async def get_google_docs_description(self, link: str):
        try:
            async with self.bot.session.get(link) as response:
                text = await response.read()

            strainer = SoupStrainer(property="og:description")
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)

            bill_description = soup.find("meta")['content']

            if bill_description.endswith('...'):
                bill_description = bill_description[:-3]

            soup.decompose()  # Garbage collection

            return bill_description

        except Exception:
            return None

    @staticmethod
    def generate_law_tags(google_docs_description: str, author_description: str):

        is_noun = lambda pos: pos[:2] == 'NN'

        tokenized_docs_description = nltk.word_tokenize(google_docs_description)

        tokenized_author_description = nltk.word_tokenize(author_description)

        tags = [word for (word, pos) in nltk.pos_tag(tokenized_docs_description) +
                nltk.pos_tag(tokenized_author_description) if is_noun(pos)]

        tags = list(set(tags))

        return tags

    async def pass_into_law(self, ctx, bill_id: int, bill_details: asyncpg.Record) -> bool:

        await self.bot.db.execute("UPDATE legislature_bills SET voted_on_by_ministry = true, has_passed_ministry = "
                                  "true WHERE id = $1", bill_id)

        _law_id = await self.bot.laws.generate_new_law_id()

        try:
            await self.bot.db.execute("INSERT INTO legislature_laws (bill_id, law_id, description) VALUES"
                                      "($1, $2, $3)", bill_id, _law_id, bill_details['description'])
        except asyncpg.UniqueViolationError:
            await ctx.send(f":x: This bill is already law!")
            return False

        _google_docs_description = await self.bot.laws.get_google_docs_description(bill_details['link'])
        _tags = await self.bot.loop.run_in_executor(None, self.bot.laws.generate_law_tags, _google_docs_description,
                                                    bill_details['description'])

        for tag in _tags:
            await self.bot.db.execute("INSERT INTO legislature_tags (id, tag) VALUES ($1, $2)", _law_id,
                                      tag.lower())

        return True

    @staticmethod
    def sort_dict_by_value(to_be_sorted: dict) -> dict:

        to_be_sorted = {k: v for k, v in sorted(to_be_sorted.items(),
                                                key=lambda item: item[1], reverse=True)}

        return to_be_sorted

    @staticmethod
    def count_rows_from_db_record(record: asyncpg.Record, record_key: str) -> dict:
        record_as_list = []
        for r in record:
            record_as_list.append(r[record_key])
        counter = collections.Counter(record_as_list)
        return dict(counter)

    async def generate_leg_statistics(self) -> list:
        amount_of_sessions = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_sessions"))['count']
        amount_of_bills = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_bills"))['count']
        amount_of_laws = (await self.bot.db.fetchrow("SELECT COUNT(law_id) FROM legislature_laws"))['count']
        amount_of_motions = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_motions"))['count']

        amount_of_bills_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT submitter FROM "
                                                                                              "legislature_bills"),
                                                                      'submitter')
        amount_of_sessions_by_speaker = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT speaker FROM "
                                                                                               "legislature_sessions"),
                                                                       'speaker')
        amount_of_laws_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT submitter FROM "
                                                                                             "legislature_bills WHERE"
                                                                                             " has_passed_leg = true "
                                                                                             "AND has_passed_ministry "
                                                                                             "= true"), 'submitter')

        pretty_top3_submitter = f""
        i = 1
        for key, value in self.sort_dict_by_value(amount_of_bills_by_submitter).items():
            pretty_top3_submitter += f"{i}. {self.bot.get_user(key).mention} with {value} bills\n"
            i += 1

        pretty_top_speaker = f""
        i = 1
        for key, value in self.sort_dict_by_value(amount_of_sessions_by_speaker).items():
            pretty_top_speaker += f"{i}. {self.bot.get_user(key).mention} with {value} sessions\n"
            i += 1

        pretty_top_lawmaker = f""
        i = 1
        for key, value in self.sort_dict_by_value(amount_of_laws_by_submitter).items():
            pretty_top_lawmaker += f"{i}. {self.bot.get_user(key).mention} with {value} laws\n"
            i += 1

        return [amount_of_sessions, amount_of_bills, amount_of_laws, amount_of_motions,
                pretty_top3_submitter, pretty_top_speaker, pretty_top_lawmaker]
