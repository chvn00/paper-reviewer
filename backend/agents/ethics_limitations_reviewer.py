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

CRITICAL RULES:
1. Do NOT require ethical approval unless the paper involves human participants or animal subjects.
   Engineering, design, and computational papers do NOT need ethics approval.
2. AI TOOL DISCLOSURE IS MANDATORY in ALL papers per IEEE/COPE/Elsevier 2024 guidelines.
   Any use of ChatGPT, Copilot, Gemini, Claude, or any generative AI must be declared.
   If no AI was used, authors must still state "No AI tools were used."
   Absence of any AI statement is a compliance gap that must be flagged.

OUTPUT RULES: Respond ONLY with a valid JSON object. Start with { and end with }.
Do not add any text, explanation, or markdown before or after the JSON."""

USER_PROMPT_TEMPLATE = """Evaluate transparency, ethics, and limitations in this manuscript.

CHECK 1 — AI TOOL DISCLOSURE (mandatory for ALL papers, IEEE/COPE/Elsevier 2024):
- Is there an explicit statement about AI tool use? (e.g., "ChatGPT was used to...", "No AI tools were used")
- Look in: acknowledgments, author contributions, footnotes, methodology section
- Signals of undisclosed AI: unusually polished prose, generic phrasing, formulaic structure
- If no AI statement exists → flag as MAJOR comment

CHECK 2 — CONFLICT OF INTEREST:
- Is there a COI declaration? ("The authors declare no conflict of interest" or actual COI disclosed)
- Missing COI declaration is a journal submission requirement

CHECK 3 — FUNDING DISCLOSURE:
- Is funding or grant information disclosed?
- If no external funding: "This research received no external funding" is acceptable

CHECK 4 — LIMITATIONS:
- Are study limitations explicitly stated and specific?
- Vague statements like "future work will improve this" are not sufficient
- Limitations should address: scope, dataset size, generalizability, assumptions

CHECK 5 — ETHICS APPROVAL (only if human/animal subjects involved):
- Does the paper involve human participants, surveys, interviews, or animal experiments?
- If yes: is IRB/ethics committee approval stated with reference number?
- If no: skip this check entirely

CHECK 6 — REPRODUCIBILITY:
- Are code, datasets, or experimental parameters shared or described in enough detail to replicate?

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON. Write at least 3 items in strengths and weaknesses:
{{
  "agent_name": "EthicsLimitationsReviewer",
  "scope": "Research ethics, limitations, and transparency",
  "ai_disclosure_status": "<disclosed|not_disclosed|no_signals_found>",
  "ai_disclosure_statement": "<exact quote from manuscript if found, or 'Not found'>",
  "strengths": [
    "<specific transparency strength found in the manuscript>",
    "<second strength>",
    "<third strength>"
  ],
  "weaknesses": [
    "<specific transparency gap — what is missing and why it matters>",
    "<second weakness>",
    "<third weakness>"
  ],
  "major_comments": [
    "<critical compliance issue: missing AI disclosure, missing COI, or ethics concern>"
  ],
  "minor_comments": [
    "<minor transparency or completeness issue>"
  ],
  "specific_recommendations": [
    "<exact text the authors should add or change>",
    "<second recommendation>",
    "<third recommendation>"
  ],
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
        relevant = ["ethics", "limitation", "discussion", "conclusion",
                    "acknowledgment", "methodology", "method", "declaration"]
        parts = []
        for key, val in sections.items():
            if key.startswith("_"):
                continue
            if any(r in key.lower() for r in relevant):
                parts.append(f"[{key.upper()}]\n{val[:2000]}")
        full = sections.get("_full_text", "")
        if full:
            # Beginning (intro/abstract) and end (acknowledgments/COI) of paper
            parts.append(f"[PAPER START — acknowledgments/COI usually here]\n{full[:2000]}")
            parts.append(f"[PAPER END — acknowledgments/COI usually here]\n{full[-3000:]}")
        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        if result.get("parse_error") or result.get("score", 0) == 0:
            return self._deterministic_result(sections, result.get("raw_output", ""))

        result = self._normalize_result(result)

        # Always inject deterministic AI-disclosure check on top of LLM result
        full_text = sections.get("_full_text", "").lower()
        ai_disclosure = any(term in full_text for term in (
            "chatgpt", "gpt-4", "gpt-3", "copilot", "gemini", "claude", "llm",
            "generative ai", "artificial intelligence tool", "ai-assisted", "ai tool",
            "language model", "large language", "no ai tool", "no generative ai",
            "ia generativa", "herramienta de ia", "sin herramientas de ia",
            "no se utilizaron herramientas", "ai was not used", "did not use ai",
            "midjourney", "dall-e", "stable diffusion", "grammarly"
        ))
        if not ai_disclosure:
            ai_rec = (
                "Add a mandatory AI disclosure statement per IEEE/COPE/Elsevier 2024. "
                "If AI tools were used, name them and describe how. "
                "If not used, state explicitly: 'No generative AI tools were used in this manuscript.'"
            )
            if ai_rec not in result.get("specific_recommendations", []):
                result.setdefault("specific_recommendations", []).insert(0, ai_rec)
            ai_major = "No AI tool disclosure statement found. IEEE/COPE 2024 requires authors to explicitly declare AI tool use or non-use."
            if not any("ai" in c.lower() for c in result.get("major_comments", [])):
                result.setdefault("major_comments", []).insert(0, ai_major)

        # Remove irrelevant ethics-approval complaints for non-human/animal papers
        is_human = any(kw in full_text for kw in (
            "human subject", "patient", "participant", "animal experiment",
            "clinical trial", "informed consent", "irb", "ethics committee"
        ))
        if not is_human:
            for key in ("major_comments", "weaknesses", "specific_recommendations"):
                result[key] = [
                    c for c in result.get(key, [])
                    if not any(kw in c.lower() for kw in (
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
            "chatgpt", "gpt-4", "gpt-3", "copilot", "gemini", "claude", "llm",
            "generative ai", "artificial intelligence tool", "ai-assisted", "ai tool",
            "language model", "large language", "no ai tool", "no generative ai",
            "ia generativa", "herramienta de ia", "herramienta ia", "sin herramientas de ia",
            "no se utilizaron herramientas", "inteligencia artificial generativa",
            "asistido por ia", "asistido por inteligencia artificial",
            "ai was not used", "ai tools were not", "did not use ai",
            "midjourney", "dall-e", "stable diffusion", "grammarly"
        ))
        ai_signals = any(term in text for term in (
            "chatgpt", "gpt-4", "gpt-3", "copilot", "gemini", "claude",
            "generative ai", "ia generativa", "herramienta de ia",
            "language model", "large language model"
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
