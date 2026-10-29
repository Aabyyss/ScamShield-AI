"""Tests for the offline entity scanner and the shareable report."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scamshield import engine
from scamshield.entities import assess, domains_in
from scamshield.report import build_report
from scamshield.samples import SAMPLE_BY_KEY


class EntityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = os.environ.get("SCAMSHIELD_DB")
        os.environ["SCAMSHIELD_DB"] = str(Path(self._tmp.name) / "test.db")

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("SCAMSHIELD_DB", None)
        else:
            os.environ["SCAMSHIELD_DB"] = self._old_db
        self._tmp.cleanup()

    def test_free_mailbox_is_high_risk(self) -> None:
        found = assess("Send your CV to dubai.hr.services786@gmail.com")
        email = next(e for e in found if e.kind == "email")
        self.assertEqual(email.risk, "high")
        self.assertIn("Free mailbox", email.reasons[0])

    def test_shortener_is_high_risk(self) -> None:
        found = assess("Apply here: https://bit.ly/visa-offer")
        url = next(e for e in found if e.kind == "url")
        self.assertEqual(url.risk, "high")
        self.assertIn("shortener", url.reasons[0].lower())

    def test_lookalike_brand_domain_is_high_risk(self) -> None:
        found = assess("careers-systemsltd.com is our portal")
        domain = next(e for e in found if e.kind == "domain")
        self.assertEqual(domain.risk, "high")
        self.assertIn("Systems Limited", domain.reasons[0])

    def test_official_domain_is_not_flagged(self) -> None:
        found = assess("careers.systemsltd.com")
        domain = next(e for e in found if e.kind == "domain")
        self.assertEqual(domain.risk, "low")

    def test_masked_phone_is_flagged(self) -> None:
        found = assess("Send the fee on JazzCash 0300-XXXXXXX")
        phone = next(e for e in found if e.kind == "phone")
        self.assertEqual(phone.risk, "medium")

    def test_id_number_is_masked_in_output(self) -> None:
        found = assess("My CNIC is 35202-1234567-1, please verify")
        personal = next(e for e in found if e.kind == "personal")
        self.assertNotIn("1234567", personal.value)
        self.assertIn("•", personal.value)

    def test_domains_in_finds_emails_and_links(self) -> None:
        text = "mail hr@example.com or visit https://jobs.example.pk/apply and example.xyz"
        found = domains_in(text)
        self.assertIn("example.com", found)
        self.assertIn("jobs.example.pk", found)
        self.assertIn("example.xyz", found)

    def test_no_entities_in_clean_text(self) -> None:
        self.assertEqual(assess("Please confirm the interview time."), [])

    def test_report_contains_verdict_quote_and_disclaimer(self) -> None:
        message = SAMPLE_BY_KEY["dubai_hotel"].text
        result = engine.analyze(message, use_ai=False)
        report = build_report(result, message)
        self.assertIn("HIGH RISK", report)
        self.assertIn("JazzCash", report)
        self.assertIn("not a legal accusation", report)
        # The pasted message is kept locally in the report for the user's own records.
        self.assertIn("Message as pasted", report)


if __name__ == "__main__":
    unittest.main()
