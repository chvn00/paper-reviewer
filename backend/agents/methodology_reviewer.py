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
IMPORTANT: You must evaluate the methodology HOLISTICALLY — even if there is no chapter explicitly
called "Methodology". Look at how the paper is structured: what is presented first, what comes after,
whether the sequence is logical (problem → model → method → experiment → results → conclusion).
Infer what the authors actually did from the full manuscript, including sections named Framework,
Approach, Proposed Method, Model, Formulation, System Model, Experiments, Evaluation, or Results.
Respond ONLY with valid JSON. Never invent content not present in the text.
If something is absent, state exactly: "Not reported in the manuscript"."""

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

Respond ONLY with this JSON:
{{
  "agent_name": "MethodologyReviewer",
  "scope": "Methodology, experimental design, equations, reproducibility — holistic review",
  "design_type": "<experimental/computational/theoretical/mixed/unclear>",
  "inferred_method_summary": "<1-2 sentence summary of what the authors did>",
  "presentation_sequence": [],
  "logical_flow_assessment": "<good/acceptable/weak/broken>",
  "sequence_issues": [],
  "reproducibility_score": 0.0,
  "equations_present": true,
  "equations_numbered": true,
  "equations_defined": true,
  "equations_issues": [],
  "dataset_described": true,
  "baseline_comparison_fair": true,
  "bias_addressed": true,
  "physical_constraints_incorporated": true,
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
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
        # Build a holistic map of the article, not a dependency on a Methodology header.
        outline = []
        for key, val in sections.items():
            if key.startswith("_"):
                continue
            first_line = next((line.strip() for line in val.splitlines() if line.strip()), "")
            outline.append(f"{key}: {first_line[:160]}")

        priority = [
            "title", "abstract", "introduction", "literature", "methodology",
            "experiments", "results", "discussion", "conclusions",
        ]
        parts = []
        if outline:
            parts.append("[ARTICLE MAP]\n" + "\n".join(outline[:20]))

        for key in priority:
            if key in sections and sections[key]:
                parts.append(f"[{key.upper()}]\n{sections[key][:6000]}")

        for key, val in sections.items():
            if key.startswith("_") or key in priority:
                continue
            if key.startswith("section_"):
                parts.append(f"[{key.upper()}]\n{val[:4000]}")

        # Always add full text portion for holistic flow analysis
        full = sections.get("_full_text", "")
        if full:
            parts.append(f"[FULL PAPER START - for holistic flow analysis]\n{full[:12000]}")
            if len(full) > 24000:
                middle = len(full) // 2
                parts.append(f"[FULL PAPER MIDDLE]\n{full[middle:middle+8000]}")
        if not parts and full:
            parts.append(f"[FULL TEXT]\n{full}")

        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        has_method_evidence = any(
            sections.get(k, "").strip()
            for k in ("methodology", "experiments", "results", "discussion", "conclusions")
        )
        if has_method_evidence and result.get("score", 0) < 2.0:
            result["score"] = 2.5
            result["confidence"] = max(result.get("confidence", 0), 0.55)
        return self._normalize_result(result)
