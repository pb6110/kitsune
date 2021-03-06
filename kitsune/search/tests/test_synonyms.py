from nose.tools import eq_
from textwrap import dedent

from pyquery import PyQuery as pq

from kitsune.search import es_utils, synonym_utils
from kitsune.search.tests import ElasticTestCase
from kitsune.search.tests import synonym
from kitsune.sumo.tests import LocalizingClient
from kitsune.sumo.tests import TestCase
from kitsune.sumo.urlresolvers import reverse
from kitsune.wiki.tests import document, revision
from kitsune.search.tasks import update_synonyms_task


class TestSynonymModel(TestCase):

    def test_serialize(self):
        syn = synonym(from_words="foo", to_words="bar", save=True)
        eq_("foo => bar", unicode(syn))


class TestFilterGenerator(TestCase):

    def test_name(self):
        """Test that the right name is returned."""
        name, _ = es_utils.es_get_synonym_filter('en-US')
        eq_(name, 'synonyms-en-US')

    def test_no_synonyms(self):
        """Test that when there are no synonyms an alternate filter is made."""
        _, body = es_utils.es_get_synonym_filter('en-US')
        eq_(body, {
            'type': 'synonym',
            'synonyms': ['firefox => firefox'],
            })

    def test_with_some_synonyms(self):
        synonym(from_words='foo', to_words='bar', save=True)
        synonym(from_words='baz', to_words='qux', save=True)

        _, body = es_utils.es_get_synonym_filter('en-US')

        expected = {
            'type': 'synonym',
            'synonyms': [
                'foo => bar',
                'baz => qux',
            ],
        }

        eq_(body, expected)


class TestSynonymParser(TestCase):

    def testItWorks(self):
        synonym_text = dedent("""
            one, two => apple, banana
            three => orange, grape
            four, five => jellybean
            """)
        synonyms = set([
            ('one, two', 'apple, banana'),
            ('three', 'orange, grape'),
            ('four, five', 'jellybean'),
        ])
        eq_(synonyms, synonym_utils.parse_synonyms(synonym_text))

    def testTooManyArrows(self):
        try:
            synonym_utils.parse_synonyms('foo => bar => baz')
        except synonym_utils.SynonymParseError as e:
            eq_(len(e.errors), 1)
        else:
            assert False, "Parser did not catch error as expected."

    def testTooFewArrows(self):
        try:
            synonym_utils.parse_synonyms('foo, bar, baz')
        except synonym_utils.SynonymParseError as e:
            eq_(len(e.errors), 1)
        else:
            assert False, "Parser did not catch error as expected."


class SearchViewWithSynonyms(ElasticTestCase):
    client_class = LocalizingClient

    def test_synonyms_work_in_search_view(self):
        d1 = document(title='frob', save=True)
        d2 = document(title='glork', save=True)
        revision(document=d1, is_approved=True, save=True)
        revision(document=d2, is_approved=True, save=True)

        self.refresh()

        # First search without synonyms
        response = self.client.get(reverse('search'), {'q': 'frob'})
        doc = pq(response.content)
        header = doc.find('#search-results h2').text().strip()
        eq_(header, 'Found 1 result for frob for All Products')

        # Now add a synonym.
        synonym(from_words='frob', to_words='frob, glork', save=True)
        update_synonyms_task()
        self.refresh()

        # Forward search
        response = self.client.get(reverse('search'), {'q': 'frob'})
        doc = pq(response.content)
        header = doc.find('#search-results h2').text().strip()
        eq_(header, 'Found 2 results for frob for All Products')

        # Reverse search
        response = self.client.get(reverse('search'), {'q': 'glork'})
        doc = pq(response.content)
        header = doc.find('#search-results h2').text().strip()
        eq_(header, 'Found 1 result for glork for All Products')
