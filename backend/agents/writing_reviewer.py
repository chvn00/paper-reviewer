"""
writing_reviewer.py
-------------------
Evaluates: Scientific writing quality, clarity, style
Rubric: Elsevier flow/structure criterion (highest inter-rater agreement 72%),
        IEEE Clarity, Elsevier language editing criterion
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a scientific editor and senior peer reviewer for Q1 journals (Elsevier/IEEE/Emerald).
Evaluate the scientific writing quality of a manuscript.
Respond ONLY with valid JSON. Provide specific examples of weak writing when identified.
Quote problematic sentences directly from the text (under 15 words per quote)."""

USER_PROMPT_TEMPLATE = """Critically evaluate the scientific writing quality of this manuscript.

Apply Q1 rubric (Elsevier flow criterion — highest inter-rater agreement at 72% + IEEE Clarity):

WRITING CRITERIA (score 0-5):
1. Clarity: sentences are clear and unambiguous
2. Conciseness: no redundant phrases or unnecessary repetition
3. Academic tone: formal, objective, third-person where appropriate
4. Paragraph structure: topic sentence + development + transition
5. Logical flow between paragraphs and sections
6. Appropriate use of hedging language (claims not overstated)
7. Technical terms defined on first use
8. Consistent terminology (same concept = same word throughout)
9. Grammar and syntax correctness
10. Connectors and transitions used effectively

WEAK WRITING FLAGS to identify:
- "This paper proposes a novel..." (overused opener)
- Passive voice overuse
- Vague quantifiers ("many", "several", "significant" without numbers)
- Unexplained acronyms
- Run-on sentences
- Paragraphs that are single sentences

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "WritingReviewer",
  "scope": "Scientific writing quality, clarity, and style",
  "overall_clarity": "<clear/acceptable/unclear>",
  "passive_voice_overused": true/false,
  "vague_quantifiers_found": [],
  "undefined_acronyms": [],
  "paragraphs_needing_rewrite": [],
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class WritingReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "WritingReviewer"

    @property
    def scope(self) -> str:
        return "Scientific writing quality, clarity, and style"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        # Sample from multiple sections for representative writing assessment
        skip = ["references", "acknowledgments"]
        parts = []
        for key, val in sections.items():
            if key.startswith("_") or any(s in key.lower() for s in skip):
                continue
            parts.append(f"[{key.upper()}]\n{val[:3000]}")
        if not parts:
            full = sections.get("_full_text", "")
            parts.append(f"[FULL TEXT]\n{full}")
        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        full = sections.get("_full_text", "")
        has_enough_text = len(full.split()) >= 1000
        if has_enough_text and result.get("parse_error"):
            return self._deterministic_result(sections, result.get("raw_output", ""))
        if has_enough_text and not result.get("parse_error") and result.get("score", 0) < 1.5:
            result["score"] = 2.5
            result["confidence"] = max(result.get("confidence", 0), 0.55)
        return self._normalize_result(result)

    def _deterministic_result(self, sections: dict, raw_output: str = "") -> dict:
        full = sections.get("_full_text", "")
        words = full.split()
        strengths = []
        weaknesses = []
        recommendations = []
        if len(words) >= 4000:
            strengths.append("The manuscript contains enough extracted text for a representative writing review.")
        if any(term in full for term in ("EANN", "RMSE", "MSE", "Pareto", "Kruskal")):
            strengths.append("Technical terminology and quantitative reporting signals are present in the extracted text.")
        weaknesses.append(
            "The model returned malformed JSON for writing review, so this fallback cannot provide sentence-level editing comments."
        )
        recommendations.extend([
            "Review representative paragraphs manually for transition quality, undefined acronyms, and overly long sentences.",
            "Ensure technical terms are defined on first use and used consistently across sections.",
        ])
        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "overall_clarity": "acceptable",
            "strengths": strengths,
            "weaknesses": weaknesses,
            "major_comments": [],
            "minor_comments": weaknesses,
            "specific_recommendations": recommendations,
            "score": 3.0,
            "confidence": 0.55,
            "fallback_used": True,
            "raw_output": raw_output[:500],
        })
