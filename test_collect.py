import datetime
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import collect


class CollectorTests(unittest.TestCase):
    def test_extracts_supported_event_from_json_ld(self):
        markup = """<script type="application/ld+json">
        {"@graph":[{"@type":"ExhibitionEvent","name":"Test Exhibition",
        "startDate":"2026-10-12","endDate":"2026-10-20",
        "url":"https://example.org/exhibition"}]}
        </script>"""
        results = collect.extract_html_events(markup, "Test Venue", "2026-10-11", "2026-10-18")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Exhibition")
        self.assertFalse(results[0]["verified_time"])

    def test_rss_only_accepts_allowlisted_venue_urls(self):
        feed = b"""<rss><channel><item><link>https://www.tate.org.uk/whats-on/test</link></item><item><link>https://invalid.example.com/another</link></item></channel></rss>"""
        self.assertEqual(collect.feed_candidates(feed), [("Tate", "https://www.tate.org.uk/whats-on/test")])

    def test_missing_event_dates_are_excluded(self):
        result = collect.parse_event(
            {"@type": "Event", "name": "Undated", "url": "https://example.org/a"},
            "Example", "2026-10-11", "2026-10-18")
        self.assertIsNone(result)

    def test_all_blocked_sources_do_not_replace_published_data(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset = Path(folder) / "events.json"
            prior = '{"updated_at":"previous", "events":[]}'
            dataset.write_text(prior)
            with patch.object(collect, "ROOT", Path(folder)):
                with patch.object(collect, "SOURCES", [("Blocked", "https://example.org")]), patch.object(collect, "DISCOVERY_FEEDS", []):
                    with patch("collect.urllib.request.urlopen", side_effect=OSError("403 blocked")):
                        with self.assertRaises(SystemExit):
                            collect.main()
            self.assertEqual(dataset.read_text(), prior)


if __name__ == "__main__":
    unittest.main()
