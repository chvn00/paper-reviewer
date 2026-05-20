"""
results_reviewer.py
-------------------
Evaluates: Results section quality and empirical support
Rubric: Elsevier criterion #4 (results supported by data — 53% inter-rater, most disputed),
        IEEE Data validity, Emerald accuracy of findings
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for Q1 scientific journals.
Evaluate the Results section of a scientific manuscript for clarity, completeness, and validity.
Respond ONLY with valid JSON. Never invent results or metrics.
If results are not clearly presented, state what is missing specifically."""

USER_PROMPT_TEMPLATE = """Critically evaluate the Results section of this manuscript.

Apply Q1 rubric (Elsevier criterion: results supported by data — most contested criterion at 53%):

RESULTS CRITERIA (score 0-5):
1. Results clearly answer the stated research objectives
2. All results are supported by actual data (no unsupported claims)
3. Results presented before interpretation (facts separate from opinion)
4. Quantitative results include appropriate precision and units
5. Negative results reported honestly (not hidden or minimized)
6. Comparison with baseline or state-of-the-art included
7. Results consistent across text, figures, and tables
8. Limitations of results acknowledged

IMPORTANT:
- If detected facts list MSE, RMSE, CV, Pareto, hypervolume, or baseline comparisons, do not say quantitative results are absent.
- You may still criticize whether those results are sufficiently detailed, consistently reported, or tied to figures/tables.

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "ResultsReviewer",
  "scope": "Results validity and empirical support",
  "results_answer_objectives": true/false,
  "quantitative_results_present": true/false,
  "baseline_comparison_present": true/false,
  "negative_results_reported": true/false,
  "unsupported_claims": [],
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class ResultsReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "ResultsReviewer"

    @property
    def scope(self) -> str:
        return "Results validity and empirical support"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        relevant = ["results", "findings", "experiments", "performance", "evaluation"]
        parts = []
        full = sections.get("_full_text", "")
        facts = self._result_facts(full)
        if facts:
            parts.append("[DETECTED RESULT SIGNALS]\n" + facts)
        if sections.get("abstract"):
            parts.append(f"[ABSTRACT]\n{sections['abstract'][:5000]}")
        for key, val in sections.items():
            if any(r in key.lower() for r in relevant):
                parts.append(f"[{key.upper()}]\n{val[:12000]}")
        if not parts:
            parts.append(f"[FULL TEXT]\n{full[1000:]}")
        return "\n\n".join(parts)

    def _result_facts(self, text: str) -> str:
        low = text.lower()
        signals = []
        checks = [
            ("MSE reported", "mse" in low or "mean square error" in low),
            ("RMSE reported", "rmse" in low or "root mean square error" in low),
            ("CV/dispersion reported", "coefficient of variation" in low or "cv" in low),
            ("GA baseline comparison", "genetic algorithm" in low or " ga " in low),
            ("PSO baseline comparison", "particle swarm" in low or "pso" in low),
            ("Pareto analysis", "pareto" in low),
            ("Hypervolume/spread indicators", "hypervolume" in low or "spread" in low),
            ("30 independent runs", "30 independent" in low or "30 runs" in low),
        ]
        for label, ok in checks:
            if ok:
                signals.append(f"- {label}")
        return "\n".join(signals)
