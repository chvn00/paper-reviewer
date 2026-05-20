"""
base_agent.py — CHVN Paper Reviewer v3
----------------------------------------
Fixes:
- Sequential execution in fast/balanced mode to avoid timeouts
- Shorter, tighter prompts for Phi-3 Mini
- Reduced max_chars to fit within context
- Faster JSON response format
- Stop/save support
"""

import asyncio
import logging
import json
from abc import ABC, abstractmethod
from backend.llm.phi3_client import call_llm, parse_json_response
from backend.agents.parser_agent import ParserAgent

logger = logging.getLogger(__name__)

MODE_CONFIG = {
    "fast": {
        "max_chars": 20000,
        "max_tokens_override": 2500,
        "system_suffix": (
            "REVIEW DEPTH: Fast screening mode. "
            "Evaluate all criteria but be concise — maximum 3 items per category. "
            "Focus on issues that would require author revision."
        ),
        "prompt_suffix": (
            "\nFast screening mode: cover all criteria concisely. "
            "Prioritize issues that require author action over minor observations."
        ),
    },
    "balanced": {
        "max_chars": 40000,
        "max_tokens_override": 4000,
        "system_suffix": (
            "REVIEW DEPTH: Standard peer-review mode. "
            "Evaluate all criteria thoroughly. Provide 4–6 items per category. "
            "This is the depth expected for a first round at a Q1 journal. "
            "Verify that title, abstract, keywords, and references are coherent with the body."
        ),
        "prompt_suffix": (
            "\nBalanced review mode: full criteria evaluation. "
            "Cover strengths and weaknesses in equal depth. "
            "Verify consistency between title, abstract, keywords, body sections, and references."
        ),
    },
    "deep": {
        "max_chars": 48000,
        "max_tokens_override": 4096,
        "system_suffix": (
            "REVIEW DEPTH: Exhaustive Q1 journal review — maximum rigor. "
            "You must analyze the ENTIRE manuscript as a chief editor would before final acceptance. "
            "Check: (1) internal consistency across ALL sections including title, abstract, keywords, "
            "introduction, methodology, results, discussion, conclusions, and references; "
            "(2) every quantitative claim backed by data; "
            "(3) every figure/table title matches its content and is self-contained; "
            "(4) every equation is numbered, defined, and dimensionally consistent; "
            "(5) reproducibility — could an independent researcher replicate this work exactly?; "
            "(6) statistical validity — correct tests, reported effect sizes, confidence intervals; "
            "(7) reference recency, relevance, and self-citation bias; "
            "(8) ethical compliance and conflict-of-interest declaration; "
            "(9) alignment between stated objectives and actual conclusions. "
            "Flag EVERY issue — major and minor. Leave nothing unchecked."
        ),
        "prompt_suffix": (
            "\nDeep review mode — exhaustive analysis: "
            "Read the FULL provided text before evaluating. "
            "Verify cross-section consistency: do the abstract claims match the results? "
            "Do the conclusions follow from the data? Are keywords aligned with content? "
            "Scrutinize figure/table captions for completeness. "
            "Check that every method step is reproducible as written. "
            "Identify any gap between what was promised in the introduction and what was delivered. "
            "Provide specific, evidence-based feedback for every weakness — cite section or line when possible."
        ),
    },
}


PUBLISHER_RUBRIC = {
    "ieee": {
        "name": "IEEE",
        "emphasis": (
            "IEEE review standards: prioritize technical rigor, mathematical correctness, "
            "and experimental validation against state-of-the-art baselines. "
            "Equations must be numbered and defined. Reproducibility is critical — "
            "algorithms must be described with sufficient precision for independent implementation. "
            "Novelty must be clearly differentiated from prior IEEE publications."
        ),
        "criteria_weights": "heavily weight: technical contribution, experimental validation, mathematical rigor, reproducibility.",
    },
    "elsevier": {
        "name": "Elsevier",
        "emphasis": (
            "Elsevier review standards: evaluate originality, significance of contribution, "
            "methodological soundness, and clarity of presentation. "
            "References must be current and comprehensive. "
            "Data availability and ethical declarations are required. "
            "Statistical methods must be appropriate and fully reported."
        ),
        "criteria_weights": "heavily weight: originality, methodology, clarity, reference quality, ethical compliance.",
    },
    "mdpi": {
        "name": "MDPI",
        "emphasis": (
            "MDPI review standards: focus on scientific soundness and methodological validity. "
            "Novelty bar is moderate — correctness and reproducibility are paramount. "
            "Open data and open code are strongly valued. "
            "Figures must have complete captions. "
            "Replication studies are welcome if methodology is sound."
        ),
        "criteria_weights": "heavily weight: scientific soundness, data transparency, reproducibility, figure/table quality.",
    },
    "emerald": {
        "name": "Emerald",
        "emphasis": (
            "Emerald review standards (management, business, social sciences): "
            "the paper must have BOTH theoretical AND practical implications — both are mandatory. "
            "Conceptual rigor matters as much as empirical validation. "
            "Qualitative methods are fully accepted. "
            "Equations and mathematical formalism are secondary to conceptual clarity. "
            "Research design must align with the stated epistemological stance."
        ),
        "criteria_weights": "heavily weight: practical implications, theoretical contribution, research design rigor, conceptual clarity.",
    },
    "sage": {
        "name": "SAGE",
        "emphasis": (
            "SAGE review standards: covers social sciences, humanities, and STEM. "
            "Qualitative, quantitative, and mixed methods are equally valid. "
            "Evaluate methodological coherence within the chosen paradigm. "
            "Interpretive rigor matters for qualitative work. "
            "Relevance to the field's audience is a key criterion."
        ),
        "criteria_weights": "heavily weight: methodological coherence, field relevance, interpretive rigor, originality.",
    },
    "taylor": {
        "name": "Taylor & Francis",
        "emphasis": (
            "Taylor & Francis review standards: broad scope across disciplines. "
            "Evaluate originality, significance, and clarity of argument. "
            "For STEM journals: experimental rigor and data quality are primary. "
            "For humanities/social science journals: argumentation quality and literature coverage are primary. "
            "Ensure the paper scope matches the journal's aims."
        ),
        "criteria_weights": "heavily weight: originality, scope fit, argument clarity, literature coverage.",
    },
}

PAPER_TYPE_RUBRIC = {
    "short_communication": {
        "name": "Short Communication",
        "emphasis": (
            "SHORT COMMUNICATION format: this is a brief focused report (typically 2000–4000 words). "
            "Do NOT penalize for limited literature review depth — brevity is by design. "
            "Evaluate whether the core finding is significant enough to warrant standalone publication. "
            "Introduction and discussion can be concise. Methods must still be reproducible. "
            "One clear, well-supported finding is sufficient."
        ),
    },
    "letter": {
        "name": "Letter",
        "emphasis": (
            "LETTER format: very concise communication (typically 1000–2500 words, 1–2 figures/tables). "
            "Do NOT require extensive literature review or full methodology section. "
            "Evaluate: is the finding novel and significant enough for rapid communication? "
            "Is the evidence sufficient despite the short format? "
            "Focus on impact and clarity, not exhaustiveness."
        ),
    },
    "review": {
        "name": "Review Article",
        "emphasis": (
            "REVIEW ARTICLE format: no original experiments required. "
            "Evaluate: comprehensiveness of literature coverage, quality of synthesis, "
            "identification of research gaps, and clarity of the narrative. "
            "The authors must contribute an analytical framework or novel synthesis — "
            "a mere list of papers is not acceptable. "
            "Recency and breadth of references are critical."
        ),
    },
    "conference": {
        "name": "Conference Paper",
        "emphasis": (
            "CONFERENCE PAPER format: typically 6–12 pages, focused contribution. "
            "Evaluate novelty and technical soundness within the scope of a conference contribution. "
            "Full reproducibility and exhaustive baselines are not always expected. "
            "Preliminary results are acceptable if the direction is promising and clearly stated."
        ),
    },
    "case_study": {
        "name": "Case Study",
        "emphasis": (
            "CASE STUDY format: in-depth analysis of a specific instance or context. "
            "Do NOT require generalizable statistical results. "
            "Evaluate: richness of context description, analytical rigor, "
            "transferability of insights, and reflexivity of the researcher. "
            "Theoretical framework must guide the analysis."
        ),
    },
    "conceptual": {
        "name": "Conceptual Paper",
        "emphasis": (
            "CONCEPTUAL PAPER format: no empirical data required. "
            "Evaluate: logical consistency of the argument, novelty of the conceptual framework, "
            "grounding in existing literature, and practical or theoretical implications. "
            "The contribution must be a new theoretical lens, model, or framework — "
            "not a simple restatement of existing theory."
        ),
    },
    "technical_note": {
        "name": "Technical Note",
        "emphasis": (
            "TECHNICAL NOTE format: brief technical contribution, method improvement, or dataset description. "
            "Evaluate: technical correctness, reproducibility, and practical utility. "
            "Novelty bar is lower than a full article — incremental improvements are acceptable. "
            "Implementation details must be precise."
        ),
    },
}


def build_rubric_context(publisher: str, paper_type: str) -> str:
    parts = []
    if publisher and publisher in PUBLISHER_RUBRIC:
        r = PUBLISHER_RUBRIC[publisher]
        parts.append(f"TARGET PUBLISHER — {r['name']}: {r['emphasis']} Scoring: {r['criteria_weights']}")
    if paper_type and paper_type in PAPER_TYPE_RUBRIC:
        r = PAPER_TYPE_RUBRIC[paper_type]
        parts.append(f"PAPER TYPE — {r['name']}: {r['emphasis']}")
    return "\n\n".join(parts)


class BaseReviewerAgent(ABC):

    @property
    @abstractmethod
    def agent_name(self) -> str:
        pass

    @property
    @abstractmethod
    def scope(self) -> str:
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def get_user_prompt(self, text: str) -> str:
        pass

    def get_relevant_sections(self, sections: dict) -> str:
        # Return full text — truncation is handled per-mode in _run_single
        return sections.get("_full_text", "")

    async def run(self, sections: dict, mode: str = "fast",
                  publisher: str = "", paper_type: str = "") -> dict:
        logger.info(f"[{self.agent_name}] Starting (mode={mode} publisher={publisher or '-'} type={paper_type or '-'})")
        cfg = MODE_CONFIG.get(mode, MODE_CONFIG["fast"])
        rubric_ctx = build_rubric_context(publisher, paper_type)

        try:
            text = self.get_relevant_sections(sections)
            if not text or len(text.strip()) < 50:
                text = sections.get("_full_text", "")
                if not text or len(text.strip()) < 50:
                    return self._empty_result("Insufficient text for analysis.")

            result = await self._run_single(text, cfg, rubric_ctx)
            result["agent_name"] = self.agent_name
            result["scope"]      = self.scope
            result["mode"]       = mode
            result = self._normalize_result(result)
            logger.info(f"[{self.agent_name}] Done. Score={result.get('score', 0)}")
            return result

        except asyncio.CancelledError:
            return self._empty_result("Stopped by user.")
        except Exception as e:
            logger.error(f"[{self.agent_name}] Error: {e}")
            return self._error_result(str(e))

    async def _run_single(self, text: str, cfg: dict, rubric_ctx: str = "") -> dict:
        truncated = text[:cfg["max_chars"]]
        prompt    = self.get_user_prompt(truncated) + cfg.get("prompt_suffix", "")
        system    = self.get_system_prompt() + "\n" + cfg.get("system_suffix", "")
        if rubric_ctx:
            system += "\n\n" + rubric_ctx
        response  = await call_llm(
            prompt, system_prompt=system,
            config_override={"max_tokens": cfg["max_tokens_override"]}
        )
        return parse_json_response(response, self.agent_name)

    def _normalize_result(self, r: dict) -> dict:
        defaults = {
            "agent_name": self.agent_name, "scope": self.scope,
            "strengths": [], "weaknesses": [], "major_comments": [],
            "minor_comments": [], "specific_recommendations": [],
            "score": 0, "confidence": 0,
            "skipped": False, "skip_reason": "", "parse_error": False,
        }
        for k, v in defaults.items():
            if k not in r:
                r[k] = v
        for key in ("strengths", "weaknesses", "major_comments", "minor_comments", "specific_recommendations"):
            r[key] = self._normalize_text_list(r.get(key, []))
        try:
            r["score"]      = max(0, min(5, float(r.get("score", 0))))
            r["confidence"] = max(0, min(1, float(r.get("confidence", 0))))
        except (ValueError, TypeError):
            r["score"]      = 0
            r["confidence"] = 0
        return r

    def _normalize_text_list(self, value) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        items = []
        for item in value:
            text = self._stringify_item(item)
            if text and not self._is_low_value_comment(text):
                items.append(text)
        return items

    def _stringify_item(self, item) -> str:
        if item is None:
            return ""
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, (int, float, bool)):
            return str(item)
        if isinstance(item, dict):
            if set(item.keys()).issubset({"type", "score"}) or (
                str(item.get("type", "")).upper().endswith("CRITERIA") and "score" in item
            ):
                return ""
            preferred = (
                "comment", "issue", "recommendation", "text", "description",
                "finding", "weakness", "strength", "major_comment", "minor_comment",
            )
            for key in preferred:
                if key in item and item[key]:
                    prefix = str(item.get("criterion") or item.get("section") or "").strip()
                    body = self._stringify_item(item[key])
                    return f"{prefix}: {body}".strip(": ") if body else prefix
            pairs = []
            for key, val in item.items():
                body = self._stringify_item(val)
                if body:
                    pairs.append(f"{key}: {body}")
            return "; ".join(pairs)
        if isinstance(item, list):
            return "; ".join(self._stringify_item(x) for x in item if self._stringify_item(x))
        try:
            return json.dumps(item, ensure_ascii=False)
        except TypeError:
            return str(item).strip()

    def _is_low_value_comment(self, text: str) -> bool:
        low = text.lower().strip()
        if not low:
            return True
        blocked = (
            "score was floored",
            "pending human review",
            "deterministic fallback was used",
            "model response was not valid json",
            "language model response was not valid json",
            "type: writing criteria",
        )
        return any(term in low for term in blocked)

    def _empty_result(self, reason: str) -> dict:
        return self._normalize_result({
            "agent_name": self.agent_name, "scope": self.scope,
            "skipped": True, "skip_reason": reason,
            "strengths": [], "weaknesses": [], "major_comments": [],
            "minor_comments": [], "specific_recommendations": [],
            "score": 0, "confidence": 0,
        })

    def _error_result(self, error: str) -> dict:
        return self._normalize_result({
            "agent_name": self.agent_name, "scope": self.scope,
            "skipped": True, "skip_reason": f"Error: {error}",
            "strengths": [], "weaknesses": [f"Agent failed: {error}"],
            "major_comments": [], "minor_comments": [],
            "specific_recommendations": ["Re-run review or check Ollama."],
            "score": 0, "confidence": 0,
        })
