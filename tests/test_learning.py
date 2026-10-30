"""Tests for the local learning store: bounded weights, phrases, trust, reset.

The important properties are negative ones — a single click must not change anything, repeated
feedback must not stack, and feedback must never be able to whitewash a critical scam signal.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scamshield import engine, learning
from scamshield.samples import SAMPLE_BY_KEY


class LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = os.environ.get("SCAMSHIELD_DB")
        os.environ["SCAMSHIELD_DB"] = str(Path(self._tmp.name) / "learning.db")
        # The app only writes after the user opts in; the tests do the same thing.
        learning.set_consent(True)

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("SCAMSHIELD_DB", None)
        else:
            os.environ["SCAMSHIELD_DB"] = self._old_db
        self._tmp.cleanup()

    def _label(self, key: str, level: str) -> None:
        text = SAMPLE_BY_KEY[key].text
        result = engine.analyze(text, use_ai=False)
        verdict_id = learning.record_verdict(text, result)
        learning.record_feedback(
            verdict_id, result.risk_level, level, [hit.key for hit in result.rule_hits]
        )

    def test_nothing_is_stored_without_consent(self) -> None:
        learning.set_consent(False)
        text = SAMPLE_BY_KEY["dubai_hotel"].text
        result = engine.analyze(text, use_ai=False)
        self.assertIsNone(learning.record_verdict(text, result))
        self.assertEqual(learning.verdict_count(), 0)

    def test_unasked_install_does_not_record(self) -> None:
        learning.set_consent(True)
        learning.clear_history()
        with learning._session() as conn:  # simulate a brand-new install
            conn.execute("DELETE FROM settings")
        result = engine.analyze(SAMPLE_BY_KEY["dubai_hotel"].text, use_ai=False)
        self.assertIsNone(learning.record_verdict(SAMPLE_BY_KEY["dubai_hotel"].text, result))
        self.assertIsNone(learning.consent_choice())
        self.assertFalse(learning.learning_enabled())

    def test_store_health_reports_a_writable_path(self) -> None:
        health = learning.store_health()
        self.assertTrue(health["ok"])
        self.assertIn("learning.db", health["path"])

    def test_one_correction_does_not_move_weights(self) -> None:
        self._label("borderline", "LOW")
        self.assertEqual(learning.rule_multipliers().get("unofficial_channel"), 1.0)

    def test_three_labels_move_weight_down(self) -> None:
        for _ in range(3):
            self._label("borderline", "LOW")
        multiplier = learning.rule_multipliers()["unofficial_channel"]
        self.assertLess(multiplier, 1.0)
        self.assertGreaterEqual(multiplier, learning.MIN_MULT)

    def test_three_confirmed_scams_move_weight_up(self) -> None:
        for _ in range(3):
            self._label("dubai_hotel", "HIGH")
        self.assertGreater(learning.rule_multipliers()["unofficial_channel"], 1.0)

    def test_repeated_feedback_replaces_instead_of_stacking(self) -> None:
        text = SAMPLE_BY_KEY["borderline"].text
        result = engine.analyze(text, use_ai=False)
        verdict_id = learning.record_verdict(text, result)
        keys = [hit.key for hit in result.rule_hits]
        for _ in range(5):
            learning.record_feedback(verdict_id, "MEDIUM", "LOW", keys)
        stats = learning.rule_stat("unofficial_channel")
        self.assertAlmostEqual(stats["legit"], 1.0)
        self.assertEqual(stats["labels"], 1.0)

    def test_feedback_cannot_whitewash_a_critical_fee_demand(self) -> None:
        for _ in range(3):
            self._label("dubai_hotel", "LOW")
        result = engine.analyze(SAMPLE_BY_KEY["dubai_hotel"].text, use_ai=False)
        self.assertEqual(result.risk_level, "HIGH")
        self.assertGreaterEqual(result.risk_score, 82)

    def test_taught_phrase_is_rejected_when_too_generic(self) -> None:
        ok, message = learning.add_phrase("visa")
        self.assertFalse(ok)
        self.assertIn("two words", message)

    def test_taught_phrase_adds_a_labelled_flag(self) -> None:
        ok, _ = learning.add_phrase("ghar baithe kamai")
        self.assertTrue(ok)
        result = engine.analyze(
            "Assalam o alaikum, ghar baithe kamai offer for students. Send CV.",
            use_ai=False,
        )
        learned = [hit for hit in result.rule_hits if hit.key == "learned_phrase"]
        self.assertEqual(len(learned), 1)
        self.assertIn("ghar baithe kamai", " ".join(learned[0].evidence).lower())

    def test_trusted_domain_dampens_free_mailbox_signal(self) -> None:
        text = SAMPLE_BY_KEY["dubai_hotel"].text
        before = engine.analyze(text, use_ai=False)
        before_hit = next(h for h in before.rule_hits if h.key == "unofficial_channel")

        ok, _ = learning.add_trusted_domain("gmail.com")
        self.assertTrue(ok)
        after = engine.analyze(text, use_ai=False)
        after_hit = next(h for h in after.rule_hits if h.key == "unofficial_channel")

        self.assertLess(after_hit.weight, before_hit.weight)
        self.assertEqual(after_hit.severity, "low")
        self.assertIn("trusted", after_hit.learned_note)

    def test_trust_requires_a_real_domain(self) -> None:
        ok, _ = learning.add_trusted_domain("not a domain")
        self.assertFalse(ok)

    def test_reset_restores_designed_weights(self) -> None:
        for _ in range(3):
            self._label("borderline", "LOW")
        learning.add_phrase("kamaal ka offer hai")
        learning.add_trusted_domain("example.com")
        learning.reset_learning()
        self.assertEqual(learning.rule_multipliers(), {})
        self.assertEqual(learning.phrases(), [])
        self.assertEqual(learning.trusted_domains(), [])

    def test_similar_cases_find_near_duplicates(self) -> None:
        text = SAMPLE_BY_KEY["dubai_hotel"].text
        result = engine.analyze(text, use_ai=False)
        learning.record_verdict(text, result)
        similar = learning.similar_cases(text.replace("Imran", "Usman"))
        self.assertTrue(similar)
        self.assertGreaterEqual(similar[0].similarity, 85)

    def test_different_messages_are_not_similar(self) -> None:
        legit = SAMPLE_BY_KEY["legit_offer"].text
        result = engine.analyze(legit, use_ai=False)
        learning.record_verdict(legit, result)
        self.assertEqual(learning.similar_cases(SAMPLE_BY_KEY["task_scam"].text), [])

    def test_learning_does_not_store_message_text(self) -> None:
        text = SAMPLE_BY_KEY["dubai_hotel"].text
        learning.record_verdict(text, engine.analyze(text, use_ai=False))
        raw = learning.db_path().read_bytes()
        self.assertNotIn(b"JazzCash", raw)
        self.assertNotIn(b"dubai.hr.services786", raw)


if __name__ == "__main__":
    unittest.main()
