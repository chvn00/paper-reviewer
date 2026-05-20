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
You specialize in evaluating the quality, coherence, and scientific correctness of figures, tables, and equations.
Your key question: Do the figures, tables, and equations MAKE SENSE in context?
Do they support the claims made in the text? Are they self-explanatory?
Respond ONLY with valid JSON. Do not invent figure or table content.
Base your evaluation ONLY on what is described or referenced in the text."""

USER_PROMPT_TEMPLATE = """Evaluate the figures, tables, and equations in this manuscript.

Apply Q1 journal rubric (IEEE Clarity + Elsevier data reporting + Emerald presentation):

FIGURES CRITERIA (score 0-5):
1. Each figure has a descriptive, self-explanatory caption
2. Figures are referenced in text BEFORE they appear
3. Axes labeled with units where applicable
4. Figure content is coherent with what the text claims it shows
5. The figure is necessary — not redundant with tables or text
6. Error bars or uncertainty shown where applicable
7. Comparison figures include all relevant baselines
8. The figure makes sense: could a reader understand it without reading the full paper?

TABLES CRITERIA (score 0-5):
1. Descriptive title and column headers present
2. Units specified in headers
3. Statistical significance indicated (*, **, p-values)
4. Data in table is consistent with claims made in text
5. No redundancy between tables and figures
6. Values are precise and consistent across the paper
7. The table makes sense: are the comparisons meaningful?

EQUATIONS CRITERIA (score 0-5):
1. Equations are numbered sequentially
2. All variables defined before or immediately after use
3. Equations are dimensionally consistent
4. Equations are properly introduced with context
5. Mathematical notation is standard for the field
6. Equations are referenced in text when used
7. The equations make sense: do they correctly represent what the text describes?

COHERENCE CHECK — CRITICAL:
- Does the text make claims that figures/tables don't support?
- Do figures show something different from what the text describes?
- Are there numerical inconsistencies between tables and text?
- Do equations match the described algorithms/methods?

IMPORTANT:
- If figures, tables, or equations are detected in the supplied manuscript facts, do not say they are absent.
- Do not claim "No numerical values or data are presented in tables" unless the table excerpts are actually empty.
- If only captions/references are visible, say "the extracted text does not expose table bodies" instead of assuming the tables lack data.

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "FiguresTablesEquationsReviewer",
  "scope": "Figures, tables, equations — quality and coherence with text",
  "figures_count_detected": 0,
  "tables_count_detected": 0,
  "equations_count_detected": 0,
  "figures_self_explanatory": true,
  "figures_referenced_before_appearance": true,
  "figures_coherent_with_text": true,
  "figures_issues": [],
  "tables_headers_complete": true,
  "tables_data_consistent_with_text": true,
  "tables_issues": [],
  "equations_numbered": true,
  "equations_variables_defined": true,
  "equations_coherent_with_methods": true,
  "equations_issues": [],
  "text_figure_inconsistencies": [],
  "text_table_inconsistencies": [],
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
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
