"""
references_reviewer.py — CHVN Paper Reviewer v3
-------------------------------------------------
Evaluates: References quality, format, sequence, recency, relevance
Rubric: IEEE citation format, Emerald originality, Elsevier reproducibility

Checks:
- IEEE [1],[2],... numbering format and sequential order
- Reference format completeness (author, year, title, journal/conf, volume, pages, DOI)
- Grey literature vs. indexed journal/conference papers
- URL-only references (not acceptable in IEEE)
- "Cuadros" vs. "Tables" nomenclature for IEEE papers
"""

import re
from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for Q1 scientific journals.
Evaluate the references section and citation practices of a scientific manuscript.
Respond ONLY with valid JSON. Do not invent references.
Only comment on references actually visible in the manuscript text.

IMPORTANT — IEEE FORMAT RULES:
1. References must use numbered style [1], [2], [3] in sequential order
2. Each reference must include: authors, title, journal/conference, volume, pages, year, DOI (preferred)
3. URL-only references are NOT acceptable in IEEE journals (must accompany a proper citation)
4. Self-references to government websites, NGO reports, or news articles need special justification
5. All references must be cited in the text in sequential order — no gaps in numbering
6. "Cuadro" terminology: In IEEE papers written in Spanish, tables must be called "Tabla" or "Table", NOT "Cuadro"."""

USER_PROMPT_TEMPLATE = """Critically evaluate the references and citation practices in this manuscript.

Apply Q1 rubric: IEEE format + Emerald originality + Elsevier reproducibility

STEP 1 — FORMAT CHECK (IEEE [1],[2],... style):
- Are references numbered sequentially with no gaps? (e.g., [1],[2],[3],... not [1],[3],[5])
- Does each reference include: author(s), title, journal/venue, volume/pages/year?
- Are DOIs present? (preferred for IEEE)
- Are any references URL-only? (flag as major issue — URLs change and lack permanence)
- Are government websites, reports, or grey literature cited? (acceptable if minimal and relevant)

STEP 2 — QUALITY AND INDEXING:
- Are references from reputable indexed journals or IEEE/ACM/Springer/Elsevier conferences?
- Are there obvious predatory or low-quality journals?
- Do references appear legitimate (plausible authors, titles, journals)?
- Is the DOI format correct? (doi.org/10.XXXX/...)
- Self-citation ratio: >30% is a red flag

STEP 3 — RELEVANCE AND RECENCY:
- Do references directly support the claims made?
- Are there recent references (last 5 years)?
- Are foundational/seminal works for the domain present?
- Are obvious gaps visible (e.g., no references to thermodynamics standards, IoT protocols, etc.)?

STEP 4 — IEEE TERMINOLOGY (for papers with Spanish content):
- Tables must be called "Table" or "Tabla" in IEEE papers — NOT "Cuadro"
- Figures must be called "Figure" or "Figura" — NOT "Gráfico" or "Esquema" for main figures
- Flag if "Cuadro" is used instead of "Tabla/Table" as a minor comment

---
MANUSCRIPT TEXT (References + Introduction for citation context):
{text}
---

Respond ONLY with this JSON. Write at least 3 items in each list:
{{
  "agent_name": "ReferencesReviewer",
  "scope": "References quality, recency, and relevance",
  "strengths": [
    "<specific strength about the references>",
    "<second strength>",
    "<third strength>"
  ],
  "weaknesses": [
    "<specific weakness: missing recency, gaps, URL-only, etc.>",
    "<second weakness>",
    "<third weakness>"
  ],
  "major_comments": [
    "<critical reference issue that must be fixed>"
  ],
  "minor_comments": [
    "<minor formatting or style issue>"
  ],
  "specific_recommendations": [
    "<concrete action: add, remove, or fix specific references>",
    "<second action>",
    "<third action>"
  ],
  "score": 0.0,
  "confidence": 0.0
}}"""


class ReferencesReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "ReferencesReviewer"

    @property
    def scope(self) -> str:
        return "References quality, recency, and relevance"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        parts = []
        full_text = sections.get("_full_text", "")
        references = sections.get("references", "")

        # Deterministic pre-analysis facts for the LLM
        facts = self._reference_facts(references or full_text)
        if facts:
            parts.append("[DETECTED REFERENCE FACTS]\n" + facts)

        if references:
            parts.append(f"[REFERENCES]\n{references[:5000]}")

        # Include intro for citation context
        intro = sections.get("introduction", "") or sections.get("preamble", "")
        if intro:
            parts.append(f"[INTRODUCTION — citation context]\n{intro[:1200]}")

        if not parts:
            parts.append(f"[FULL TEXT]\n{full_text[:3000]}")

        return "\n\n".join(parts)[:7000]

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)

        # Deterministic post-processing
        full_text = sections.get("_full_text", "")
        references = sections.get("references", "")
        ref_count = self._count_references(references)
        gaps = self._detect_numbering_gaps(references or full_text)
        url_only = self._detect_url_only_refs(references or full_text)
        cuadro_used = self._detect_cuadro(full_text)
        has_doi = "doi" in (references or full_text).lower()

        # Floor score if refs detected but LLM was too harsh
        if ref_count >= 8 and result.get("score", 0) < 2.5:
            result["score"] = 2.5
            result["confidence"] = max(result.get("confidence", 0), 0.55)

        # Inject deterministic findings
        if gaps:
            result.setdefault("major_comments", []).append(
                f"Reference numbering is not sequential. Gaps detected at positions: {gaps}. "
                "IEEE requires continuous numbering [1],[2],[3],... in order of first citation."
            )
            result["score"] = max(1.5, result.get("score", 2.5) - 0.5)

        if url_only:
            result.setdefault("major_comments", []).append(
                f"URL-only references detected ({len(url_only)} entries). "
                "IEEE does not accept URL-only citations — each must include author, title, source, and date."
            )
            result.setdefault("specific_recommendations", []).append(
                "Replace URL-only references with properly formatted citations including author, "
                "title, organization/journal, year, and URL+access date."
            )
            result["score"] = max(1.5, result.get("score", 2.5) - 0.3 * len(url_only))

        if cuadro_used:
            result.setdefault("minor_comments", []).append(
                "The manuscript uses 'Cuadro' to label tables. In IEEE publications (including Spanish-language ones), "
                "tables must be labeled 'Tabla' or 'Table', not 'Cuadro'."
            )
            result.setdefault("specific_recommendations", []).append(
                "Replace all instances of 'Cuadro' with 'Tabla' (or 'Table') to comply with IEEE style guidelines."
            )

        if has_doi:
            result.setdefault("strengths", []).append(
                "DOI identifiers are present in the references, improving long-term link stability."
            )

        result["cuadro_instead_of_tabla"] = cuadro_used
        result["numbering_gaps_detected"] = gaps
        result["url_only_references"] = url_only

        return self._normalize_result(result)

    # ── Deterministic helpers ─────────────────────────────────────────────────

    def _reference_facts(self, text: str) -> str:
        count = self._count_references(text)
        current_year = 2026
        years = [int(y) for y in re.findall(r"\b(19\d{2}|20[012]\d)\b", text)
                 if int(y) <= current_year]
        recent = [y for y in years if y >= 2021]
        gaps = self._detect_numbering_gaps(text)
        url_count = len(self._detect_url_only_refs(text))
        cuadro = self._detect_cuadro(text)
        has_doi = "doi" in text.lower()

        facts = []
        if count:
            facts.append(f"- ~{count} numbered references detected")
        if years:
            facts.append(f"- Year range: {min(years)}–{max(years)}")
        if recent:
            facts.append(f"- References since 2021: {len(recent)}")
        if gaps:
            facts.append(f"- Numbering gaps at: {gaps}")
        if url_count:
            facts.append(f"- URL-only references detected: {url_count}")
        if has_doi:
            facts.append("- DOI identifiers found")
        if cuadro:
            facts.append("- 'Cuadro' used instead of 'Tabla/Table' (IEEE non-compliant)")
        return "\n".join(facts)

    def _count_references(self, text: str) -> int:
        numbered = set(int(n) for n in re.findall(r"\[(\d{1,3})\]", text))
        if numbered:
            return max(numbered)
        lines = [l for l in text.splitlines() if re.search(r"\b(19\d{2}|20\d{2})\b", l)]
        return len(lines)

    def _detect_numbering_gaps(self, text: str) -> list:
        """Find missing numbers in [1],[2],... sequence."""
        nums = sorted(set(int(n) for n in re.findall(r"\[(\d{1,3})\]", text)))
        if len(nums) < 3:
            return []
        gaps = []
        for i in range(len(nums) - 1):
            if nums[i + 1] - nums[i] > 1:
                gaps.extend(range(nums[i] + 1, nums[i + 1]))
        return gaps[:10]  # cap to avoid noise

    def _detect_url_only_refs(self, text: str) -> list:
        """Detect reference entries that are ONLY a URL with no author/title."""
        lines = text.splitlines()
        url_only = []
        for line in lines:
            stripped = line.strip()
            # Line that starts with [N] and contains a URL but has very few other words
            if re.match(r"^\[\d+\]", stripped):
                urls = re.findall(r"https?://\S+", stripped)
                if urls:
                    # Remove URL from line, check what's left
                    remaining = re.sub(r"https?://\S+", "", stripped).strip()
                    remaining = re.sub(r"\[\d+\]", "", remaining).strip()
                    # If less than 5 words remain, it's URL-only
                    if len(remaining.split()) < 5:
                        url_only.append(stripped[:80])
        return url_only

    def _detect_cuadro(self, text: str) -> bool:
        """Detect use of 'Cuadro' as table label (IEEE non-compliant)."""
        return bool(re.search(r"\bCuadro\s+\d+", text, re.IGNORECASE))
