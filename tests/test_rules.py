"""Regression tests for the deterministic layer.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scamshield import engine  # noqa: E402
from scamshield.engine import _level_for  # noqa: E402
from scamshield.rules import prescan, rule_score  # noqa: E402
from scamshield.samples import SAMPLES, SAMPLE_BY_KEY  # noqa: E402


def level_for(text: str) -> tuple[str, int, list[str]]:
    hits = prescan(text)
    score = rule_score(hits)
    return _level_for(score), score, [h.key for h in hits]


class TestDemoCorpus(unittest.TestCase):
    """Every demo sample must land in its advertised band, or the stage demo lies."""

    def test_expected_levels(self) -> None:
        for sample in SAMPLES:
            with self.subTest(sample=sample.key):
                level, score, keys = level_for(sample.text)
                self.assertEqual(
                    level, sample.expected, f"{sample.key} scored {score} with {keys}"
                )

    def test_scam_samples_are_high(self) -> None:
        for key in ("dubai_hotel", "saudi_visa", "task_scam"):
            with self.subTest(sample=key):
                level, _, _ = level_for(SAMPLE_BY_KEY[key].text)
                self.assertEqual(level, "HIGH")

    def test_legitimate_offer_is_clean(self) -> None:
        level, score, keys = level_for(SAMPLE_BY_KEY["legit_offer"].text)
        self.assertEqual(level, "LOW")
        self.assertEqual(keys, [], "a real offer letter must not trigger any fraud rule")
        self.assertEqual(score, 0)


class TestNoFalsePositives(unittest.TestCase):
    """Rules must require intent, not just vocabulary."""

    def test_bringing_cnic_to_interview_is_not_harvesting(self) -> None:
        text = "Please bring your CNIC copy to our office in Gulberg for the interview record."
        self.assertNotIn("identity_harvesting", [h.key for h in prescan(text)])

    def test_sending_cnic_is_harvesting(self) -> None:
        text = "Kindly send your CNIC copy and passport scan on WhatsApp to confirm the seat."
        self.assertIn("identity_harvesting", [h.key for h in prescan(text)])

    def test_company_states_no_fee(self) -> None:
        text = (
            "No payment or fee of any kind is required at any stage of our hiring process. "
            "Reply to this email or call our HR desk on +92 42 111 797 836."
        )
        keys = [h.key for h in prescan(text)]
        self.assertNotIn("upfront_payment", keys)

    def test_visa_fee_still_caught(self) -> None:
        text = "Visa processing fee Rs 35,000 only, send on JazzCash and share the screenshot."
        keys = [h.key for h in prescan(text)]
        self.assertIn("upfront_payment", keys)
        self.assertIn("personal_payment_channel", keys)


class TestScoring(unittest.TestCase):
    def test_clean_text_scores_zero(self) -> None:
        self.assertEqual(rule_score(prescan("Hello, is this position still open?")), 0)

    def test_single_critical_signal_floors_score(self) -> None:
        text = "Please pay the visa fee of Rs 20,000 to confirm your seat."
        self.assertGreaterEqual(rule_score(prescan(text)), 82)

    def test_score_never_exceeds_100(self) -> None:
        self.assertLessEqual(rule_score(prescan(SAMPLE_BY_KEY["saudi_visa"].text)), 100)

    def test_levels_map_correctly(self) -> None:
        self.assertEqual(_level_for(0), "LOW")
        self.assertEqual(_level_for(29), "LOW")
        self.assertEqual(_level_for(30), "MEDIUM")
        self.assertEqual(_level_for(64), "MEDIUM")
        self.assertEqual(_level_for(65), "HIGH")


class TestModelGuardrails(unittest.TestCase):
    """The model must never be able to invent a verdict the text does not support."""

    def run_with_payload(self, sample_key: str, payload: dict):
        original = engine.call_model
        engine.call_model = lambda *a, **k: payload  # type: ignore[assignment]
        try:
            return engine.analyze(SAMPLE_BY_KEY[sample_key].text, model="test-model")
        finally:
            engine.call_model = original  # type: ignore[assignment]

    def test_invented_payment_flag_is_discarded(self) -> None:
        payload = {
            "headline": "This is a scam.",
            "summary": "The sender demands a fee.",
            "red_flags": [
                {
                    "code": "upfront_payment",
                    "title": "Requests payment before contract",
                    "evidence": "send Rs 50,000 today to confirm your seat",
                    "why_it_matters": "Fees are never charged.",
                    "severity": "critical",
                }
            ],
        }
        result = self.run_with_payload("legit_offer", payload)
        self.assertEqual(result.risk_level, "LOW")
        self.assertEqual(result.red_flags, [])
        self.assertEqual(result.discarded_claims, 1)

    def test_no_fee_sentence_is_not_a_payment_demand(self) -> None:
        payload = {
            "headline": "Payment requested",
            "summary": "A fee is mentioned.",
            "red_flags": [
                {
                    "code": "upfront_payment",
                    "title": "Mentions payment",
                    "evidence": "No payment or fee of any kind is required at any stage",
                    "why_it_matters": "Fees are a scam signal.",
                    "severity": "critical",
                }
            ],
        }
        result = self.run_with_payload("legit_offer", payload)
        self.assertEqual(result.discarded_claims, 1)
        self.assertEqual(result.risk_level, "LOW")

    def test_uncorroborated_high_is_downgraded(self) -> None:
        payload = {
            "headline": "Unrealistic salary",
            "summary": "Pay looks high.",
            "red_flags": [
                {
                    "code": "unrealistic_pay",
                    "title": "Unrealistic salary",
                    "evidence": "Annual salary: PKR 1,800,000",
                    "why_it_matters": "Too high for the role.",
                    "severity": "critical",
                }
            ],
        }
        result = self.run_with_payload("legit_offer", payload)
        self.assertEqual(result.red_flags[0].severity, "medium")
        self.assertEqual(result.risk_level, "LOW")
        self.assertLessEqual(result.risk_score, 15)

    def test_model_flags_never_lower_a_rule_verdict(self) -> None:
        payload = {
            "verdict": "likely_legitimate",
            "risk_level": "LOW",
            "risk_score": 5,
            "headline": "Looks fine.",
            "summary": "Nothing concerning.",
            "red_flags": [],
        }
        result = self.run_with_payload("dubai_hotel", payload)
        self.assertEqual(result.risk_level, "HIGH")
        self.assertEqual(result.risk_score, 100)

    def test_quote_without_ellipsis_still_verifies(self) -> None:
        text = "Visa processing fee: Rs 35,000 only"
        self.assertTrue(
            engine._quote_verified("Visa processing fee: Rs 35,000", engine._normalise(text), engine._tokens(text))
        )
        self.assertFalse(
            engine._quote_verified("a completely invented sentence", engine._normalise(text), engine._tokens(text))
        )


if __name__ == "__main__":
    unittest.main()
