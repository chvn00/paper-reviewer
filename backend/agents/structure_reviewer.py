"""
structure_reviewer.py
---------------------
Evaluates: Overall manuscript structure and coherence
Rubric: Elsevier IMRaD flow, IEEE Validity, Emerald scope coherence
"""

from backend.agents.base_agent import BaseReviewerAgent
import re

SYSTEM_PROMPT = """You are a senior peer reviewer for a Q1 scientific journal (Elsevier/IEEE/Emerald standard).
Evaluate the overall structure and logical coherence of a scientific manuscript.
Respond ONLY with valid JSON. Do not add text before or after.
Do not invent content. If something is absent, write "Not reported in the manuscript"."""

USER_PROMPT_TEMPLATE = """Evaluate the structure and logical organization of this manuscript.

Apply Q1 journal rubric criteria (Elsevier/IEEE/Emerald):

STRUCTURE CRITERIA (score each 0-5):
1. Logical flow: Introduction → Literature → Methods → Results → Discussion → Conclusions
2. Research problem clearly stated in Introduction
3. Research question or hypothesis explicitly declared
4. Objectives stated and later addressed in conclusions
5. Transitions and coherence between sections
6. Section balance (no section disproportionately long or absent)
7. Consistency: objectives match methods match results match conclusions

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "StructureReviewer",
  "scope": "Manuscript structure and logical coherence",
  "sections_detected": [],
  "missing_sections": [],
  "structure_flow_score": 0.0,
  "hypothesis_declared": true/false,
  "objectives_match_conclusions": true/false,
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class StructureReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "StructureReviewer"

    @property
    def scope(self) -> str:
        return "Manuscript structure and logical coherence"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        visible = [k for k in sections if not k.startswith("_")]
        structure_map = "[SECTION MAP]\n" + "\n".join(f"- {k}" for k in visible)
        excerpts = "\n\n".join(
            f"[{k.upper()}]\n{v[:280]}"
            for k, v in sections.items()
            if not k.startswith("_")
        )
        all_text = f"{structure_map}\n\n{excerpts}"
        if not excerpts.strip():
            all_text = f"[FULL TEXT]\n{sections.get('_full_text', '')[:3000]}"
        return all_text[:2600]

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        visible = [k for k in sections if not k.startswith("_")]
        if visible and (result.get("parse_error") or result.get("score", 0) == 0):
            return self._deterministic_result(sections, result.get("raw_output", ""))
        return result

    def _deterministic_result(self, sections: dict, raw_output: str = "") -> dict:
        visible = [k for k in sections if not k.startswith("_")]
        expected = ["introduction", "methodology", "results", "discussion", "conclusions"]
        equivalents = {
            "methodology": ["methodology", "experiments"],
            "results": ["results", "experiments"],
            "discussion": ["discussion", "section_vi"],
            "conclusions": ["conclusions", "section_vii"],
        }

        def has_section(name: str) -> bool:
            options = equivalents.get(name, [name])
            return any(option in sections and sections.get(option, "").strip() for option in options)

        present = [name for name in expected if has_section(name)]
        missing = [name for name in expected if name not in present]
        has_front_matter = any(k in sections for k in ("title", "abstract", "keywords"))
        section_positions = {name: i for i, name in enumerate(visible)}

        intro = sections.get("introduction", "")
        method = sections.get("methodology", "") or sections.get("experiments", "")
        results = sections.get("results", "") or sections.get("experiments", "")
        discussion = sections.get("discussion", "") or sections.get("section_vi", "")
        conclusions = sections.get("conclusions", "") or sections.get("section_vii", "")

        flow_sequence = [name for name in ("introduction", "methodology", "experiments", "results", "discussion", "conclusions") if name in sections]
        has_ordered_core = self._is_ordered(section_positions, ["introduction", "methodology", "experiments", "discussion", "conclusions"])
        intro_has_problem = self._has_any(intro, ["problem", "challenge", "objective", "aim", "identify", "identification", "propose"])
        method_has_design = self._has_any(method, ["framework", "model", "formulation", "algorithm", "method", "optimization", "experimental"])
        validation_has_evidence = self._has_any(results, ["validation", "results", "compared", "baseline", "experiment", "performance"])
        discussion_links_results = self._has_any(discussion, ["results", "section v", "establish", "demonstrate", "evidence"])
        conclusions_present_claims = len(conclusions.split()) >= 80

        score = 1.0 + (len(present) / len(expected)) * 3.2
        if has_front_matter:
            score += 0.4
        if "introduction" in present and ("discussion" in present or "conclusions" in present):
            score += 0.4
        if has_ordered_core:
            score += 0.3
        score = round(min(4.2, score), 2)

        strengths = []
        weaknesses = []
        recommendations = []
        if flow_sequence:
            strengths.append(f"The manuscript follows a detectable progression: {' -> '.join(flow_sequence)}.")
        if intro_has_problem:
            strengths.append("The introduction appears to establish the problem/objective before the technical sections.")
        else:
            weaknesses.append("The introduction excerpt does not clearly expose the research problem/objective in parser-visible text.")
            recommendations.append("Make the research objective explicit near the end of the introduction.")
        if method_has_design:
            strengths.append("The technical middle sections contain method/framework/model signals, supporting a methodological reading.")
        else:
            weaknesses.append("The method/framework is not clearly signposted in the detected structural excerpts.")
            recommendations.append("Use a clearer heading or transition for the proposed framework/method.")
        if validation_has_evidence:
            strengths.append("Validation/results signals are present after the methodological material.")
        else:
            weaknesses.append("The validation/results stage is not strongly signposted in the detected excerpts.")
            recommendations.append("Separate validation/results from method description so the evidence chain is easier to follow.")
        if discussion_links_results:
            strengths.append("The discussion appears to refer back to results, which supports structural coherence.")
        else:
            weaknesses.append("The discussion excerpt does not clearly connect interpretation back to the results.")
            recommendations.append("Begin the discussion by explicitly tying the main results to the study objective.")
        if conclusions_present_claims:
            strengths.append("A substantive conclusion section was detected.")
        else:
            weaknesses.append("The conclusion section appears short or weakly detected.")
            recommendations.append("Use the conclusion to answer the objective and summarize the main validated contribution.")
        if missing:
            weaknesses.append(f"Some canonical structural elements were not clearly detected: {', '.join(missing)}.")
        if raw_output:
            weaknesses.append("The language model response was not valid JSON, so this structure review was generated from parser-visible section evidence.")

        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "sections_detected": visible,
            "missing_sections": missing,
            "structure_flow_score": score,
            "hypothesis_declared": intro_has_problem,
            "objectives_match_conclusions": "introduction" in present and "conclusions" in present,
            "strengths": strengths[:6],
            "weaknesses": weaknesses,
            "major_comments": [],
            "minor_comments": weaknesses[:3],
            "specific_recommendations": recommendations[:5],
            "score": score,
            "confidence": 0.65,
            "fallback_used": True,
            "raw_output": raw_output[:500],
        })

    def _has_any(self, text: str, terms: list) -> bool:
        lower = text.lower()
        return any(term in lower for term in terms)

    def _is_ordered(self, positions: dict, sequence: list) -> bool:
        found = [positions[name] for name in sequence if name in positions]
        return found == sorted(found) and len(found) >= 4
