"""
methodology_reviewer.py — CHVN Paper Reviewer v2
--------------------------------------------------
Holistic methodological review — does NOT require a chapter called "Methodology".
Evaluates the logical flow and scientific rigor across the entire paper:
What is presented first? Does the sequence make sense?
Is there coherence between problem → model → experiment → validation → conclusion?
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for a Q1 scientific journal (Elsevier/IEEE/Emerald).
You specialize in evaluating research methodology, experimental design, and mathematical formulations.
Evaluate the methodology HOLISTICALLY — even if there is no section explicitly called "Methodology".
Look at sections named Framework, Approach, Proposed Method, Model, Experiments, Evaluation, or Results.
OUTPUT RULES: Respond ONLY with a valid JSON object. Start your response with { and end with }.
Do not add any text, explanation, or markdown before or after the JSON. Never invent content."""

USER_PROMPT_TEMPLATE = """Perform a holistic methodological review of this scientific manuscript.

You do NOT need a chapter called "Methodology" — evaluate the logical flow and scientific rigor
of the entire paper. Ask yourself:
- What problem is defined and how?
- What model or theoretical framework is proposed?
- Is the sequence logical: problem → model → method → experiment → results → conclusion?
- Are there gaps in the scientific chain?
- What did the authors actually do, in sequence?
- Is the method understandable from the way it is presented, even without a "Methodology" header?

Apply Q1 journal rubric (IEEE Validity + Elsevier reproducibility + Emerald research design):

CRITERIA (score 0-5 each):
1. Research design appropriateness for stated objectives
2. Logical sequence: is each section well-motivated by the previous one?
3. Reproducibility: could an independent researcher replicate this work?
4. Dataset/experimental setup: size, source, preprocessing, justification
5. Variables clearly defined (independent, dependent, control)
6. Algorithms/protocols described with sufficient precision
7. Equations: numbered, defined, dimensionally consistent, properly introduced
8. Physical/domain constraints properly incorporated
9. Potential biases identified and addressed
10. Comparison with baselines: is it fair and rigorous?

HOLISTIC QUESTIONS:
- Is what is presented first the right thing to present first?
- Does each section flow naturally from the previous?
- Are there logical gaps between the proposed method and the experiments?
- Does the validation directly test what the method claims to solve?

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON. Write at least 3 items in each list:
{{
  "agent_name": "MethodologyReviewer",
  "scope": "Methodology, experimental design, equations, reproducibility — holistic review",
  "inferred_method_summary": "<1-2 sentence summary of what the authors actually did>",
  "logical_flow_assessment": "<good/acceptable/weak/broken>",
  "strengths": [
    "<specific methodological strength with evidence from the text>",
    "<second strength>",
    "<third strength>"
  ],
  "weaknesses": [
    "<specific methodological weakness — what is missing, unclear, or not reproducible>",
    "<second weakness>",
    "<third weakness>"
  ],
  "major_comments": [
    "<critical issue that must be fixed before acceptance>"
  ],
  "minor_comments": [
    "<minor clarification or completeness issue>"
  ],
  "specific_recommendations": [
    "<concrete action: what to add, clarify, or fix>",
    "<second action>",
    "<third action>"
  ],
  "score": 0.0,
  "confidence": 0.0
}}"""


class MethodologyReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "MethodologyReviewer"

    @property
    def scope(self) -> str:
        return "Methodology, experimental design, equations — holistic review"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        # Send only the most relevant sections — llama3.2 fails with too much context
        priority = [
            "methodology", "experiments", "results",
            "introduction", "abstract", "conclusions", "discussion",
        ]
        parts = []

        # Outline: just section names so model knows paper structure
        outline = [k for k in sections if not k.startswith("_")]
        if outline:
            parts.append("[PAPER SECTIONS DETECTED]\n" + ", ".join(outline[:15]))

        for key in priority:
            if key in sections and sections[key].strip():
                parts.append(f"[{key.upper()}]\n{sections[key][:3000]}")

        # Fallback: use beginning of full text if no named sections found
        if len(parts) <= 1:
            full = sections.get("_full_text", "")
            parts.append(f"[FULL TEXT]\n{full[:8000]}")

        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)

        if result.get("parse_error") or result.get("score", 0) == 0:
            return self._deterministic_result(sections, result.get("raw_output", ""))

        has_method_evidence = any(
            sections.get(k, "").strip()
            for k in ("methodology", "experiments", "results", "discussion", "conclusions")
        )
        if has_method_evidence and result.get("score", 0) < 2.0:
            result["score"] = 2.5
            result["confidence"] = max(result.get("confidence", 0), 0.55)
        return self._normalize_result(result)

    def _deterministic_result(self, sections: dict, raw_output: str = "") -> dict:
        """Fallback when LLM fails to produce valid JSON."""
        text = " ".join(
            sections.get(k, "") for k in
            ("methodology", "experiments", "results", "discussion", "conclusions", "_full_text")
        ).lower()

        has_equations = any(t in text for t in ("eq.", "equation", "formula", "(1)", "(2)", "ecuation"))
        has_dataset = any(t in text for t in ("dataset", "data set", "database", "corpus", "sample", "n =", "n="))
        has_baseline = any(t in text for t in ("baseline", "compared to", "benchmark", "state-of-the-art", "vs."))
        has_repro = any(t in text for t in ("algorithm", "parameter", "hyperparameter", "configuration", "setting", "code"))
        has_validation = any(t in text for t in ("validation", "test", "evaluation", "accuracy", "rmse", "mae", "f1", "precision", "recall"))

        strengths, weaknesses, recommendations = [], [], []

        if has_equations:
            strengths.append("Mathematical formulations or equations are present, supporting the theoretical foundation.")
        if has_dataset:
            strengths.append("Dataset or experimental data is referenced, indicating empirical validation.")
        if has_baseline:
            strengths.append("Baseline or benchmark comparisons are present.")
        if has_validation:
            strengths.append("Quantitative validation metrics are referenced in the results.")
        if has_repro:
            strengths.append("Implementation parameters or algorithmic details are described.")

        if not has_dataset:
            weaknesses.append("No clear dataset description was detected — sample size, source, and preprocessing should be stated explicitly.")
            recommendations.append("Describe the dataset: source, size, preprocessing steps, and how it supports the research objective.")
        if not has_baseline:
            weaknesses.append("No baseline comparison was detected — results cannot be contextualised without reference methods.")
            recommendations.append("Include comparison against at least one established baseline or state-of-the-art method.")
        if not has_repro:
            weaknesses.append("Reproducibility details appear limited — key parameters and configurations should be explicitly reported.")
            recommendations.append("Report all hyperparameters, software versions, and configuration settings needed to reproduce results.")
        if not has_equations:
            weaknesses.append("No mathematical formulations detected — key model components should be described formally.")

        if not strengths:
            strengths.append("Methodological content is present in the manuscript.")
        if not weaknesses:
            weaknesses.append("Methodology could not be fully evaluated from extracted text — verify completeness of the methodology section.")

        score = 2.0
        score += 0.4 * sum([has_equations, has_dataset, has_baseline, has_repro, has_validation])
        score = min(4.2, round(score, 1))

        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "inferred_method_summary": "Assessed via deterministic signal detection (LLM parse failed).",
            "logical_flow_assessment": "acceptable",
            "strengths": strengths,
            "weaknesses": weaknesses,
            "major_comments": weaknesses[:1],
            "minor_comments": weaknesses[1:3],
            "specific_recommendations": recommendations,
            "score": score,
            "confidence": 0.55,
            "fallback_used": True,
            "raw_output": raw_output[:300],
        })
