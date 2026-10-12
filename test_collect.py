import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collect

class CollectorTests(unittest.TestCase):
    def test_event_schema_with_explicit_dates(self):
        page='<script type="application/ld+json">{"@type":"ExhibitionEvent","name":"Immersive Lights","startDate":"2026-10-12","endDate":"2026-10-20","url":"https://example.org/light","image":"https://example.org/image.jpg"}</script>'
        results=collect.parse_jsonld(page,"Gallery","2026-10-12","2026-10-19")
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]["image_url"],"https://example.org/image.jpg")
        self.assertFalse(results[0]["verified_time"])

    def test_undated_news_never_becomes_an_event(self):
        page='<script type="application/ld+json">{"@type":"NewsArticle","name":"London show announced","datePublished":"2026-10-12"}</script>'
        self.assertEqual(collect.parse_jsonld(page,"News","2026-10-12","2026-10-19"),[])

    def test_rss_pubdate_not_used_as_event_date(self):
        feed=b'<rss><channel><item><title>London theatre production</title><link>https://example.org/article</link><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        leads=collect.extract_rss_leads(feed,"news")
        self.assertEqual(len(leads),1)
        self.assertEqual(len(leads[0]),4)

    def test_date_specific_calendar_marks_only_that_day(self):
        html = """<html><head><title>London exhibitions open on Tuesday 13th October 2026</title></head><body>
        <h1>London exhibitions open on Tuesday 13th October 2026</h1>
        <div class="exhibition"><h3><a href="/exhibitions/test-show">Anish Kapoor</a></h3>
        <p>A contemporary sculpture exhibition at the Hayward Gallery.</p>
        <p>Exhibition ends on Sunday 18th Oct</p>
        <p>Hayward Gallery, Southwark</p></div></body></html>"""
        results = collect.parse_date_calendar(html, "2026-10-13", "https://www.ianvisits.co.uk/calendar/date/2026/10/13/exhibitions")
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]["title"],"Anish Kapoor")
        self.assertEqual(results[0]["calendar_dates"],["2026-10-13"])
        self.assertFalse(results[0]["verified_time"])
        self.assertFalse(results[0]["schedule_uncertain"])

    def test_structured_json_explicit_datetime(self):
        payload={"events":[{"title":"London Theatre","datetime":"2026-10-13T19:30:00","venue":"London Theatre","city":"London","link":"https://example.org/theatre","description":"Modern performance"}]}
        e=collect.parse_structured_feed(payload,"Tickts London","2026-10-12","2026-10-19")
        self.assertEqual(len(e),1)
        self.assertTrue(e[0]["verified_time"])

    def test_aggregated_news_requires_actual_event_dates(self):
        payload=b'<rss><channel><item><title>London gallery news</title><link>https://example.org/a</link><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        def mock_fetch(url):
            if url.endswith("features.rss"): return payload
            return b'<html>No event-specific dates</html>'
        with patch.object(collect,"VENUE_PAGES",[]),patch.object(collect,"STRUCTURED_FEEDS",[]),patch.object(collect,"NEWS_RSS",["https://example.org/features.rss"]):
            with self.assertRaises(RuntimeError):
                collect.run(today="2026-10-12",http_fetch=mock_fetch,prior={"events":[]})

    def test_keeps_prior_events_when_new_events_found(self):
        data={"events":[{"title":"An Older Exhibition","venue":"Tate","start_date":"2026-09-01","end_date":"2026-10-30","url":"https://tate.org.uk/a","score":60}]}
        def mock_fetch(url):
            return json.dumps({"events":[{"title":"Contemporary Art Night","datetime":"2026-10-15T19:00","venue":"London Art Club","city":"London","link":"https://example.org/event","description":"Contemporary art exhibition"}]}).encode()
        with patch.object(collect,"VENUE_PAGES",[]),patch.object(collect,"NEWS_RSS",[]),patch.object(collect,"STRUCTURED_FEEDS",[("Tickts London","https://example.org/feed")]):
            res=collect.run(today="2026-10-12",http_fetch=mock_fetch,prior=data)
        self.assertEqual(res["fresh_events"],1)
        self.assertEqual(len(res["events"]),2)
        self.assertTrue(next(e for e in res["events"] if e["title"]=="An Older Exhibition")["schedule_uncertain"])

if __name__=="__main__":
    unittest.main()
