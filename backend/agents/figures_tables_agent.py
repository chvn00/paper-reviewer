"""
figures_tables_agent.py — CHVN Paper Reviewer v2
--------------------------------------------------
Evaluates figures, tables, and equations for:
- Technical correctness and completeness
- Coherence with the text (does the figure/table support what the text claims?)
- Whether equations make sense in context
- Whether tables present data consistently
- Whether figures would be interpretable to a reader
CONDITIONAL: Activates only if figures/tables/equations detected.
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer and scientific editor for Q1 journals (IEEE/Elsevier/Emerald).
Evaluate the quality and coherence of figures, tables, and equations.
Your key question: Do figures, tables, and equations support the claims made in the text?
OUTPUT RULES: Respond ONLY with a valid JSON object. Start your response with { and end with }.
Do not add any text, explanation, or markdown before or after the JSON.
Base your evaluation ONLY on what is described or referenced in the text."""

USER_PROMPT_TEMPLATE = """Evaluate the figures, tables, and equations in this manuscript.
Write specific, evidence-based comments — minimum 3 per category.

FIGURES — evaluate and comment:
- Do captions fully describe what the figure shows (self-explanatory)?
- Are axes labeled with units?
- Are figures referenced in the text before they appear?
- Is the content coherent with what the text claims?
- Are error bars or uncertainty ranges shown where expected?

TABLES — evaluate and comment:
- Do tables have descriptive titles and complete column headers with units?
- Is the data consistent with claims made in the text?
- Are values precise and consistent across the paper?

EQUATIONS — evaluate and comment:
- Are equations numbered sequentially?
- Are all variables defined before or immediately after use?
- Are equations dimensionally consistent?
- Are equations referenced in the text when used?

COHERENCE CHECK:
- Does the text make claims that figures/tables do not support?
- Are there numerical inconsistencies between tables and text?
- Do equations match the described methods?

NOTE: Do not say figures/tables are absent if they are listed in the detected facts above.

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON. Write at least 3 items in each list:
{{
  "agent_name": "FiguresTablesEquationsReviewer",
  "scope": "Figures, tables, equations — quality and coherence with text",
  "strengths": [
    "<specific strength about figures, tables or equations>",
    "<second strength>",
    "<third strength>"
  ],
  "weaknesses": [
    "<specific weakness with evidence from text>",
    "<second weakness>",
    "<third weakness>"
  ],
  "major_comments": [
    "<critical issue that must be fixed>"
  ],
  "minor_comments": [
    "<minor presentation or formatting issue>"
  ],
  "specific_recommendations": [
    "<concrete action for figures>",
    "<concrete action for tables>",
    "<concrete action for equations>"
  ],
  "score": 0.0,
  "confidence": 0.0
}}"""


class FiguresTablesReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "FiguresTablesEquationsReviewer"

    @property
    def scope(self) -> str:
        return "Figures, tables, equations — quality and coherence with text"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        priority = ["results", "methodology", "experiments", "discussion"]
        parts = []
        full = sections.get("_full_text", "")
        facts = self._presentation_facts(full)
        if facts:
            parts.append("[DETECTED PRESENTATION SIGNALS]\n" + facts)
        for key in priority:
            if key in sections:
                parts.append(f"[{key.upper()}]\n{sections[key][:6000]}")
        if full and len(parts) < 2:
            parts.append(f"[FULL TEXT]\n{full}")
        if not parts and full:
            parts.append(f"[FULL TEXT]\n{full}")
        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        """Conditional: only run if figures, tables, or equations detected."""
        text = sections.get("_full_text", "") or self.get_relevant_sections(sections)
        from backend.agents.parser_agent import ParserAgent
        p = ParserAgent()
        has_figs  = p._count_figures(text) > 0
        has_tabs  = p._count_tables(text) > 0
        has_eqs   = p._count_sequential_equations(text) > 0
        if not (has_figs or has_tabs or has_eqs):
            return self._empty_result(
                "No figures, tables, or equations detected. Agent skipped."
            )
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        if result.get("parse_error") or result.get("score", 0) == 0:
            return self._deterministic_result(text)
        return self._normalize_result(result)

    def _presentation_facts(self, text: str) -> str:
        from backend.agents.parser_agent import ParserAgent
        p = ParserAgent()
        fig_count = p._count_figures(text)
        table_count = p._count_tables(text)
        eq_count = p._count_sequential_equations(text)
        facts = []
        if fig_count:
            facts.append(f"- {fig_count} figure references detected")
        if table_count:
            facts.append(f"- {table_count} table references detected")
        if eq_count:
            facts.append(f"- {eq_count} sequential numbered equations detected")
        return "\n".join(facts)

    def _deterministic_result(self, text: str) -> dict:
        from backend.agents.parser_agent import ParserAgent
        p = ParserAgent()
        fig_count = p._count_figures(text)
        table_count = p._count_tables(text)
        eq_count = p._count_sequential_equations(text)
        strengths = []
        weaknesses = []
        recommendations = []
        if fig_count:
            strengths.append(f"{fig_count} figure references were detected in the manuscript.")
        if table_count:
            strengths.append(f"{table_count} table references were detected in the manuscript.")
        if eq_count:
            strengths.append(f"{eq_count} sequentially numbered equations were detected, suggesting a substantial mathematical formulation.")
        weaknesses.append(
            "The model response could not be used reliably, so this fallback verifies presence and numbering but cannot judge visual quality or table body completeness."
        )
        recommendations.append(
            "Manually inspect captions, axes, units, table headers, and variable definitions in the final PDF."
        )
        score = 3.5
        if fig_count and table_count and eq_count >= 3:
            score = 4.0
        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "figures_count_detected": fig_count,
            "tables_count_detected": table_count,
            "equations_count_detected": eq_count,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "major_comments": [],
            "minor_comments": weaknesses,
            "specific_recommendations": recommendations,
            "score": score,
            "confidence": 0.62,
            "fallback_used": True,
        })
