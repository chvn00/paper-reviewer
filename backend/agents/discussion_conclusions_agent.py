"""
discussion_conclusions_agent.py
--------------------------------
Evaluates: Discussion depth and conclusions validity
Rubric: Elsevier IMRaD framework, IEEE Advancement, Emerald contribution assessment
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for Q1 scientific journals.
Evaluate the Discussion and Conclusions sections of a scientific manuscript.
OUTPUT RULES: Respond ONLY with a valid JSON object. Start your response with { and end with }.
Do not add any text, explanation, or markdown before or after the JSON.
Write at least 3 detailed, specific comments per category. One-liners are not acceptable."""

USER_PROMPT_TEMPLATE = """Critically evaluate the Discussion and Conclusions sections of this manuscript.

DISCUSSION — check each point and comment on it:
1. Are results interpreted in context of existing literature, or just restated?
2. Are unexpected or negative findings addressed and explained?
3. Are the study limitations clearly stated?
4. Is there real comparison with prior work (numbers, not just "previous studies showed...")?
5. Are theoretical and practical implications discussed?
6. Does the discussion over-generalize beyond what the data supports?

CONCLUSIONS — check each point and comment on it:
1. Are conclusions directly traceable to the results (no new unsupported claims)?
2. Do conclusions answer the original research question?
3. Are conclusions specific and quantified, or vague ("results were good")?
4. Is future work concrete and justified?
5. Does the conclusion merely repeat the abstract?
6. Is the contribution to the field clearly stated?

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON. Write at least 3 items in each list:
{{
  "agent_name": "DiscussionConclusionsReviewer",
  "scope": "Discussion depth and conclusions validity",
  "strengths": [
    "<specific strength of the discussion or conclusions with evidence from text>",
    "<second strength>",
    "<third strength>"
  ],
  "weaknesses": [
    "<specific weakness with reference to what is missing or wrong>",
    "<second weakness>",
    "<third weakness>"
  ],
  "major_comments": [
    "<most critical issue that must be addressed before acceptance>"
  ],
  "minor_comments": [
    "<minor wording, style, or completeness issue>"
  ],
  "specific_recommendations": [
    "<concrete action: what the authors should add, remove, or revise>",
    "<second action>",
    "<third action>"
  ],
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
                parts.append(f"[{key.upper()}]\n{sections[key][:3000]}")
        for key, val in sections.items():
            if key in ("section_vi", "section_vii", "discussion", "conclusions"):
                continue
            if any(r in key.lower() for r in relevant):
                parts.append(f"[{key.upper()}]\n{val[:3000]}")
        # Also include results for traceability check
        if "results" in sections:
            parts.append(f"[RESULTS — for traceability check]\n{sections['results'][:2000]}")
        if not parts:
            full = sections.get("_full_text", "")
            parts.append(f"[FULL TEXT END]\n{full[-5000:]}")
        return "\n\n".join(parts)
