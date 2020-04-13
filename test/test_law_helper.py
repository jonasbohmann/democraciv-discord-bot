import asyncio
import unittest

from util.law_helper import LawUtils


def async_test(coro):
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro(*args, **kwargs))

    return wrapper


class MockBot:
    def __init__(self, session):
        self.session = session


class TestLawHelper(unittest.TestCase):

    def setUp(self):
        self.bot = None
        self.laws = LawUtils(self.bot)

    def test_sort_dict_by_value(self):
        to_be_sorted = {'b': 3, 'd': 0, 'a': 5, 'c': 1}
        sorted_dict = {'a': 5, 'b': 3, 'c': 1, 'd': 0}
        self.assertDictEqual(self.laws.sort_dict_by_value(to_be_sorted), sorted_dict,
                             'Element order in sorted dicts don\'t match!')

    def test_is_google_docs_link_success(self):
        test_strings = ('https://docs.google.com/document/d/1deWktyhCDWlmC88C2eP7vjpH6sP6NuJ7KfrXX8kcO-s/edit',
                        'https://goo.gl/forms/b4aVtsGCs7ZFvSAx2', 'https://forms.gle/ETyFrr6qucr95MMA9')

        for link in test_strings:
            self.assertTrue(self.laws.is_google_doc_link(link), "Valid URL failed Google Docs Link test")

    def test_is_google_docs_link_fail(self):
        test_strings = ('google.com', 'http://docs.google.com/aaaaaaaaaaaaaaaaaaaaaaaaa',
                        'https://wikipedia.com/wiki/Help')

        for link in test_strings:
            self.assertFalse(self.laws.is_google_doc_link(link), "Invalid URL got through Google Docs Link test")

    def test_generate_law_tags(self):
        description1 = "elections are a mystery to the people of arabia"
        description2 = "bill title - this is a noun and another noun yet again"
        tags = ['elections', 'mystery', 'people', 'arabia', 'noun']

        self.assertCountEqual(self.laws.generate_law_tags(description1, description2), tags)

