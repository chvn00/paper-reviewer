"""
meta_reviewer.py
-----------------
MetaReviewerAgent: Integrates all agent results into a final editorial decision.
Does NOT call the LLM with paper text — works from structured agent outputs.
Rubric: Combines all Q1 criteria into weighted editorial recommendation.
"""

import logging
import json
from pathlib import Path
from backend.agents.base_agent import BaseReviewerAgent
from backend.llm.phi3_client import call_llm, parse_json_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a chief editor for a Q1 scientific journal (Elsevier/IEEE/Emerald standard).
You have received structured peer review reports from multiple specialist reviewers.
Your task is to synthesize these reports into a final editorial decision.
Respond ONLY with valid JSON. Base your decision ONLY on the provided review data."""

# Score weights for final editorial decision (must sum to 1.0)
SCORE_WEIGHTS = {
    "TitleAbstractKeywordsReviewer": 0.08,
    "StructureReviewer":             0.08,
    "MethodologyReviewer":           0.20,
    "StatisticsReviewer":            0.12,
    "FiguresTablesEquationsReviewer": 0.08,
    "ResultsReviewer":               0.15,
    "DiscussionConclusionsReviewer": 0.10,
    "WritingReviewer":               0.08,
    "ReferencesReviewer":            0.07,
    "EthicsLimitationsReviewer":     0.04,
}

# Thresholds for editorial decisions
DECISION_THRESHOLDS = {
    "Accept":         4.5,
    "Minor Revision": 3.5,
    "Major Revision": 2.5,
    "Reject":         0.0,
}

RUBRICS_PATH = Path(__file__).resolve().parents[2] / "rubrics.json"


def load_rubrics() -> dict:
    try:
        with RUBRICS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "weights": data.get("weights", SCORE_WEIGHTS),
            "decision_thresholds": data.get("decision_thresholds", DECISION_THRESHOLDS),
            "criteria": data.get("criteria", {}),
        }
    except Exception as e:
        logger.warning(f"[MetaReviewer] Could not load rubrics.json: {e}. Using defaults.")
        return {
            "weights": SCORE_WEIGHTS,
            "decision_thresholds": DECISION_THRESHOLDS,
            "criteria": {},
        }


class MetaReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "MetaReviewer"

    @property
    def scope(self) -> str:
        return "Overall manuscript assessment and editorial decision"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return ""  # Not used — uses custom prompt

    async def run(self, sections: dict, mode: str = "fast") -> dict:
        """MetaReviewer does not analyze sections directly."""
        return self._empty_result("MetaReviewer requires agent results — call synthesize() instead.")

    async def synthesize(self, agent_results: list, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        """
        Main method: synthesize all agent results into final report.
        agent_results: list of dicts from each reviewer agent
        """
        logger.info(f"[MetaReviewer] Synthesizing {len(agent_results)} agent results")
        rubrics = load_rubrics()
        weights = rubrics["weights"]
        thresholds = rubrics["decision_thresholds"]

        # ── Compute weighted score ─────────────────────────────────────────
        weighted_sum = 0.0
        weight_used = 0.0
        scores_by_agent = {}

        for result in agent_results:
            name = result.get("agent_name", "")
            score = float(result.get("score", 0))
            skipped = result.get("skipped", False)

            scores_by_agent[name] = {
                "score": score,
                "skipped": skipped,
                "confidence": result.get("confidence", 0),
            }

            if not skipped and score > 0 and name in weights:
                w = float(weights[name])
                weighted_sum += score * w
                weight_used += w

        # Normalize if some agents were skipped
        final_score = (weighted_sum / weight_used) if weight_used > 0 else 0.0
        final_score = round(final_score, 2)

        # ── Editorial decision ─────────────────────────────────────────────
        editorial_decision = "Reject"
        for decision, threshold in thresholds.items():
            if final_score >= threshold:
                editorial_decision = decision
                break

        # ── Collect all comments ───────────────────────────────────────────
        all_major = []
        all_minor = []
        all_strengths = []
        all_recommendations = []
        all_weaknesses = []

        for result in agent_results:
            result = self._normalize_result(result)
            if not result.get("skipped"):
                all_major.extend(result.get("major_comments", []))
                all_minor.extend(result.get("minor_comments", []))
                all_strengths.extend(result.get("strengths", []))
                all_recommendations.extend(result.get("specific_recommendations", []))
                all_weaknesses.extend(result.get("weaknesses", []))

        # ── LLM synthesis for deep mode ────────────────────────────────────
        llm_summary = {}
        if mode == "deep":
            llm_summary = await self._llm_synthesis(
                agent_results, final_score, editorial_decision, sections,
                publisher=publisher, paper_type=paper_type
            )

        # ── Score table (as Elsevier/IEEE rubric dimensions) ──────────────
        score_table = self._build_score_table(agent_results, scores_by_agent)

        # ── Average confidence ─────────────────────────────────────────────
        confidences = [r.get("confidence", 0) for r in agent_results if not r.get("skipped") and r.get("confidence", 0) > 0]
        avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

        return {
            "agent_name": "MetaReviewer",
            "scope": "Overall manuscript assessment and editorial decision",
            "final_weighted_score": final_score,
            "editorial_decision": editorial_decision,
            "publisher": publisher or "general",
            "paper_type": paper_type or "full_article",
            "score_table": score_table,
            "rubric_criteria": rubrics.get("criteria", {}),
            "scores_by_agent": scores_by_agent,
            "all_strengths": self._unique_text(all_strengths)[:10],
            "all_weaknesses": self._unique_text(all_weaknesses)[:10],
            "major_comments": self._unique_text(all_major)[:12],
            "minor_comments": self._unique_text(all_minor)[:12],
            "specific_recommendations": self._unique_text(all_recommendations)[:12],
            "overall_confidence": avg_confidence,
            "llm_synthesis": llm_summary,
            "skipped": False,
            "score": final_score,
            "confidence": avg_confidence,
        }

    async def _llm_synthesis(self, agent_results: list, score: float,
                              decision: str, sections: dict,
                              publisher: str = "", paper_type: str = "") -> dict:
        """Deep mode: LLM generates narrative summary."""
        summary_data = {r.get("agent_name"): {
            "score": r.get("score", 0),
            "major": r.get("major_comments", [])[:2],
            "strengths": r.get("strengths", [])[:2],
        } for r in agent_results}

        prompt = f"""As chief editor, write a synthesis of this peer review.
Final score: {score}/5.0
Editorial decision: {decision}

Agent summaries:
{summary_data}

Respond with JSON:
{{
  "executive_summary": "<2-3 sentences summarizing the manuscript>",
  "main_contribution": "<what the paper contributes to science>",
  "critical_issues": ["<top 3 issues that must be addressed>"],
  "positive_aspects": ["<top 3 strengths>"],
  "decision_rationale": "<why this editorial decision>"
}}"""

        try:
            from backend.agents.base_agent import build_rubric_context
            rubric_ctx = build_rubric_context(publisher, paper_type)
            system = SYSTEM_PROMPT + ("\n\n" + rubric_ctx if rubric_ctx else "")
            response = await call_llm(prompt, system_prompt=system)
            return parse_json_response(response, "MetaReviewer")
        except Exception as e:
            logger.warning(f"[MetaReviewer] LLM synthesis failed: {e}")
            return {}

    def _build_score_table(self, agent_results: list, scores_by_agent: dict) -> dict:
        """Build the final score table with Q1 rubric dimensions."""
        def get_score(name):
            return scores_by_agent.get(name, {}).get("score", 0)

        return {
            "Originality & Novelty":     get_score("TitleAbstractKeywordsReviewer"),
            "Manuscript Structure":       get_score("StructureReviewer"),
            "Methodology & Equations":    get_score("MethodologyReviewer"),
            "Statistical Analysis":       get_score("StatisticsReviewer"),
            "Results & Evidence":         get_score("ResultsReviewer"),
            "Discussion & Conclusions":   get_score("DiscussionConclusionsReviewer"),
            "Figures & Tables":           get_score("FiguresTablesEquationsReviewer"),
            "Scientific Writing":         get_score("WritingReviewer"),
            "References & Citations":     get_score("ReferencesReviewer"),
            "Ethics & Transparency":      get_score("EthicsLimitationsReviewer"),
        }

    def _unique_text(self, values: list) -> list:
        seen = set()
        unique = []
        for value in values:
            text = self._stringify_item(value)
            if text and text not in seen:
                seen.add(text)
                unique.append(text)
        return unique
