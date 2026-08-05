from __future__ import annotations

import unittest
from datetime import date

from manzanares_agent.scoring import commercial_score


class ScoringTest(unittest.TestCase):
    def test_prospect_placeholder_does_not_inflate_urgency(self) -> None:
        prospect = {
            "status": "prospect",
            "monthly_value": 2_000_000,
            "interest_score": 70,
            "purchase_frequency": 0,
            "days_since_purchase": 999,
            "phone": "300",
            "segment": "retail",
            "assigned_advisor": "Ana",
            "weighted_pipeline": 0,
            "next_action_date": None,
        }
        score = commercial_score(prospect, today=date(2026, 6, 25))
        self.assertEqual(score.urgency, 8)
        self.assertLessEqual(score.total, 70)

    def test_overdue_action_increases_urgency(self) -> None:
        row = {
            "status": "active",
            "monthly_value": 4_000_000,
            "interest_score": 80,
            "purchase_frequency": 3,
            "days_since_purchase": 10,
            "phone": "300",
            "segment": "hotel",
            "assigned_advisor": "Ana",
            "weighted_pipeline": 3_000_000,
            "next_action_date": "2026-06-24",
        }
        score = commercial_score(row, today=date(2026, 6, 25))
        self.assertEqual(score.urgency, 15)
        self.assertIn("siguiente accion vencida o para hoy", score.reasons)


if __name__ == "__main__":
    unittest.main()
