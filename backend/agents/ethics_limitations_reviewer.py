"""
ethics_limitations_reviewer.py — CHVN Paper Reviewer v3
---------------------------------------------------------
Evaluates: Transparency, limitations, and responsible reporting.
Key rule: Ethical approval for human/animal subjects is only required
when the paper involves human participants or animal experiments.
Engineering prototypes, computational systems, and design papers
do NOT require ethical approval — this should NOT penalize the score.

MANDATORY check (per IEEE/COPE 2024): AI tool disclosure.
Any use of generative AI (ChatGPT, Copilot, etc.) in writing or analysis must be declared.
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a research ethics specialist and senior peer reviewer for Q1 journals.
Evaluate transparency, limitations, and responsible reporting in a scientific manuscript.

CRITICAL RULE: Do NOT require or penalize absence of ethical approval unless the paper
explicitly involves human participants or animal subjects. For engineering, computer science,
and prototype/design papers, ethical approval is NOT applicable.

MANDATORY IN ALL PAPERS (per IEEE/COPE 2024):
- Disclosure of generative AI tool use (ChatGPT, Copilot, Gemini, etc.) in writing or analysis.
  If AI tools were used, they must be declared. Silence = potential concern.

Respond ONLY with valid JSON. Apply proportional, context-aware ethics assessment."""

USER_PROMPT_TEMPLATE = """Evaluate the transparency, limitations, and responsible reporting in this manuscript.

STEP 1 — PAPER TYPE:
Determine if this paper involves:
A) Human subjects (surveys, clinical trials, user studies, interviews) → ethics approval REQUIRED
B) Animal experiments → ethics approval REQUIRED
C) Engineering/design/prototype/computational → ethics approval NOT applicable

STEP 2 — EVALUATE BASED ON TYPE:

FOR ALL PAPER TYPES (required):
1. Conflict of interest declaration (mandatory for all journals)
2. Funding / grant disclosure (mandatory)
3. AI tool disclosure: Was ChatGPT, Copilot, or any generative AI used in writing, analysis, or figures?
   This MUST be declared per IEEE, Elsevier, MDPI, and COPE 2024 guidelines.
4. Limitations section: explicitly stated, specific, and honest (not vague disclaimers)
5. Generalizability of findings appropriately qualified
6. Reproducibility: materials, parameters, conditions described for replication

FOR HUMAN/ANIMAL STUDIES ONLY:
7. Ethical approval from IRB/ethics committee stated
8. Informed consent described
9. Data anonymization / privacy protection addressed

SCORING GUIDE:
- Type C paper (engineering/design): do not deduct points for missing ethics approval
- Strong score (4.0–5.0): limitations explicit + COI declared + funding disclosed + AI disclosure clear
- Acceptable (3.0–3.9): some transparency elements present, limitations partially addressed
- Weak (2.0–2.9): no limitations section, missing COI/funding, unclear AI use
- Very weak (1.0–1.9): multiple transparency omissions that undermine scientific credibility

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "EthicsLimitationsReviewer",
  "scope": "Research ethics, limitations, and transparency",
  "paper_involves_human_subjects": false,
  "paper_involves_animal_subjects": false,
  "ethical_approval_applicable": false,
  "ethical_approval_mentioned": false,
  "ai_tool_use_disclosed": false,
  "ai_tool_use_detected_signals": false,
  "data_availability_stated": false,
  "conflict_of_interest_declared": false,
  "funding_disclosed": false,
  "limitations_explicitly_stated": false,
  "limitations_are_specific": false,
  "reproducibility_addressed": false,
  "ethics_concerns": [],
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class EthicsLimitationsReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "EthicsLimitationsReviewer"

    @property
    def scope(self) -> str:
        return "Research ethics, limitations, and transparency"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        relevant = ["ethics", "limitations", "discussion", "conclusions",
                    "acknowledgments", "methodology", "methods"]
        parts = []
        for key, val in sections.items():
            if any(r in key.lower() for r in relevant):
                parts.append(f"[{key.upper()}]\n{val[:800]}")
        if not parts:
            full = sections.get("_full_text", "")
            # Check beginning and end of paper (where ethics/COI usually appear)
            parts.append(f"[FULL TEXT — START]\n{full[:2000]}")
            parts.append(f"[FULL TEXT — END]\n{full[-2000:]}")
        return "\n\n".join(parts)[:5000]

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        if result.get("parse_error") or result.get("score", 0) == 0:
            return self._deterministic_result(sections, result.get("raw_output", ""))
        result = self._normalize_result(result)
        # Post-process: remove ethics approval complaints if paper doesn't involve humans/animals
        if not result.get("paper_involves_human_subjects") and not result.get("paper_involves_animal_subjects"):
            result["major_comments"] = [
                c for c in result.get("major_comments", [])
                if not any(kw in c.lower() for kw in (
                    "ethical approval", "irb", "ethics committee",
                    "informed consent", "human subject", "animal subject"
                ))
            ]
            result["weaknesses"] = [
                w for w in result.get("weaknesses", [])
                if not any(kw in w.lower() for kw in (
                    "ethical approval", "irb", "ethics committee", "informed consent"
                ))
            ]
            result["specific_recommendations"] = [
                r for r in result.get("specific_recommendations", [])
                if not any(kw in r.lower() for kw in (
                    "ethical approval", "irb", "ethics committee", "informed consent"
                ))
            ]
        return result

    def _deterministic_result(self, sections: dict, raw_output: str = "") -> dict:
        text = " ".join(
            sections.get(k, "")
            for k in ("methodology", "discussion", "conclusions", "acknowledgments", "references", "_full_text")
        ).lower()

        human_or_animal = any(term in text for term in (
            "human subject", "patient", "participant", "animal experiment",
            "clinical trial", "informed consent", "irb", "ethics committee"
        ))
        ai_disclosure = any(term in text for term in (
            "chatgpt", "gpt", "copilot", "gemini", "claude", "llm",
            "generative ai", "artificial intelligence tool", "ai-assisted",
            "language model", "ia generativa", "herramienta ia"
        ))
        ai_signals = any(term in text for term in (
            "chatgpt", "gpt-", "copilot", "gemini", "claude", "generative ai",
            "ia generativa", "herramienta de ia"
        ))
        data_available = any(term in text for term in (
            "data availability", "available at", "repository", "github", "zenodo", "dataset"
        ))
        funding = any(term in text for term in (
            "funding", "grant", "supported by", "financi", "acknowledg", "agradec"
        ))
        conflict = any(term in text for term in (
            "conflict of interest", "competing interest", "no conflict",
            "conflicto de interés", "conflicto de interes"
        ))
        limitations = any(term in text for term in (
            "limitation", "future work", "constraint", "threat", "limitación",
            "limitacion", "trabajo futuro", "restricción"
        ))
        reproducibility = any(term in text for term in (
            "code", "dataset", "repository", "parameters", "specification",
            "reproducib", "replicab", "código", "parámetros"
        ))

        # Score: ethics approval NOT counted for non-human/animal papers
        score = 1.5
        if not human_or_animal:
            score += 0.3  # Bonus: no human/animal subjects = ethics not applicable
        if funding:
            score += 0.4
        if conflict:
            score += 0.4
        if limitations:
            score += 0.6
        if reproducibility:
            score += 0.4
        if ai_disclosure:
            score += 0.3
        elif ai_signals:
            score -= 0.3  # Signals detected but not declared

        score = min(4.5, round(score, 2))

        strengths = []
        weaknesses = []
        recommendations = []

        if not human_or_animal:
            strengths.append("Engineering/design paper: ethical approval for human/animal subjects is not applicable.")
        if funding:
            strengths.append("Funding or acknowledgment information is present.")
        if limitations:
            strengths.append("Limitations or future work are acknowledged.")
        if ai_disclosure:
            strengths.append("AI tool use is disclosed in the manuscript.")
        elif ai_signals:
            weaknesses.append("Signals of AI tool use detected but no explicit AI disclosure found. IEEE/COPE 2024 requires authors to declare any use of generative AI in writing or analysis.")
            recommendations.append(
                "Add a clear statement declaring whether generative AI tools (e.g., ChatGPT, Copilot) were used in drafting, editing, or analyzing content in this manuscript. This is mandatory per IEEE/COPE 2024 guidelines."
            )
        else:
            recommendations.append(
                "Add a statement clarifying whether generative AI tools were used in any part of this manuscript (writing, figures, analysis). Even a 'no AI tools were used' statement satisfies IEEE/COPE 2024 requirements."
            )

        if not conflict:
            weaknesses.append("Conflict-of-interest declaration was not detected.")
            recommendations.append("Include a conflict-of-interest declaration (e.g., 'The authors declare no conflict of interest.').")
        if not limitations:
            weaknesses.append("No explicit limitations section was detected.")
            recommendations.append("Add a limitations paragraph addressing scope constraints, assumptions, and potential generalizability issues of the proposed system.")
        if not funding:
            weaknesses.append("Funding disclosure was not detected.")
            recommendations.append("Disclose funding sources or state that no external funding was received.")

        if human_or_animal:
            weaknesses.append("Human or animal subject signals detected. Verify ethical approval and informed consent are explicitly stated.")
            recommendations.append("If human participants or animal subjects were involved, state the ethical approval body and reference number.")

        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "paper_involves_human_subjects": human_or_animal,
            "paper_involves_animal_subjects": False,
            "ethical_approval_applicable": human_or_animal,
            "ethical_approval_mentioned": human_or_animal,
            "ai_tool_use_disclosed": ai_disclosure,
            "ai_tool_use_detected_signals": ai_signals,
            "data_availability_stated": data_available,
            "conflict_of_interest_declared": conflict,
            "funding_disclosed": funding,
            "limitations_explicitly_stated": limitations,
            "limitations_are_specific": limitations,
            "reproducibility_addressed": reproducibility,
            "ethics_concerns": [],
            "strengths": strengths,
            "weaknesses": weaknesses,
            "major_comments": weaknesses[:2],
            "minor_comments": weaknesses[2:4],
            "specific_recommendations": recommendations,
            "score": score,
            "confidence": 0.65,
            "fallback_used": True,
            "raw_output": raw_output[:500],
        })
