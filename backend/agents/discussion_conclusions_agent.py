"""
discussion_conclusions_agent.py
--------------------------------
Evaluates: Discussion depth and conclusions validity
Rubric: Elsevier IMRaD framework, IEEE Advancement, Emerald contribution assessment
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for Q1 scientific journals.
Evaluate the Discussion and Conclusions sections of a scientific manuscript.
Respond ONLY with valid JSON. Do not invent interpretations.
If content is absent, state "Not reported in the manuscript"."""

USER_PROMPT_TEMPLATE = """Critically evaluate the Discussion and Conclusions sections of this manuscript.

Apply Q1 rubric (Elsevier IMRaD + IEEE Advancement + Emerald contribution):

DISCUSSION CRITERIA (score 0-5):
1. Results interpreted in context of existing literature
2. Unexpected findings addressed and explained
3. Limitations of the study clearly stated
4. Comparison with prior work (not just citation, but actual comparison)
5. Theoretical and practical implications discussed
6. Avoids over-generalizing beyond the data

CONCLUSIONS CRITERIA (score 0-5):
1. Directly derived from results (no new claims not supported by data)
2. Answers the original research question/hypothesis
3. Specific and quantified (not vague statements like "good results")
4. Future work directions are concrete and justified
5. Does not simply repeat the abstract
6. Contribution to the field clearly stated

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "DiscussionConclusionsReviewer",
  "scope": "Discussion depth and conclusions validity",
  "limitations_declared": true/false,
  "literature_comparison_in_discussion": true/false,
  "conclusions_derived_from_results": true/false,
  "conclusions_answer_hypothesis": true/false,
  "over_generalization_detected": true/false,
  "future_work_specified": true/false,
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class DiscussionConclusionsReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "DiscussionConclusionsReviewer"

    @property
    def scope(self) -> str:
        return "Discussion depth and conclusions validity"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        relevant = ["discussion", "conclusions", "conclusion", "summary", "section_vi", "section_vii"]
        parts = []
        for key in ("section_vi", "section_vii", "discussion", "conclusions"):
            if key in sections and sections[key]:
                parts.append(f"[{key.upper()}]\n{sections[key][:1500]}")
        for key, val in sections.items():
            if key in ("section_vi", "section_vii", "discussion", "conclusions"):
                continue
            if any(r in key.lower() for r in relevant):
                parts.append(f"[{key.upper()}]\n{val[:1500]}")
        if not parts:
            full = sections.get("_full_text", "")
            parts.append(f"[FULL TEXT END]\n{full[-3000:]}")
        return "\n\n".join(parts)[:3000]
