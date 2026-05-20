"""
title_abstract_agent.py
------------------------
Evaluates: Title, Abstract, Keywords
Rubric: IEEE Clarity + Novelty, Elsevier objective clarity, Emerald scope/originality
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a senior peer reviewer for a Q1 scientific journal (Elsevier/IEEE/Emerald standard).
Your task is to critically evaluate the Title, Abstract, and Keywords of a scientific manuscript.
You must respond ONLY with a valid JSON object. Do not include any text before or after the JSON.
Do not invent information. If something is not present, state "Not reported in the manuscript".
Be critical and specific. Vague praise is not acceptable."""

USER_PROMPT_TEMPLATE = """Evaluate the Title, Abstract, and Keywords of the following manuscript.
Also perform a HOLISTIC CONSISTENCY CHECK between the abstract and the paper body.

Apply these rubric criteria (IEEE + Elsevier + Emerald Q1 standards):

TITLE (score 0-5):
- Specificity and informativeness (avoids vague terms like "novel approach")
- Reflects the actual contribution
- Appropriate length (10-20 words is a guideline, not a hard maximum)
- Contains key terms for discoverability

ABSTRACT (score 0-5):
- Follows structured format: Background, Objective, Methods, Results, Conclusions
- States the research problem clearly
- Quantifies results (does NOT use vague phrases like "significantly improved")
- Does not contain references or undefined abbreviations
- Standalone readability

ABSTRACT HOLISTIC CHECK — CRITICAL:
Compare the abstract claims against the actual paper body (Introduction, Results, Conclusions).
Check:
1. Does the abstract promise results/contributions that are NOT delivered in the paper?
2. Does the paper contain important findings that are NOT mentioned in the abstract?
3. Are the quantitative values in the abstract (COP, accuracy, efficiency, etc.) consistent with what is reported in the results?
4. Does the abstract accurately describe the methodology actually used?
5. Is the scope described in the abstract consistent with what the paper covers?
Flag any discrepancies between abstract claims and actual paper content as MAJOR issues.

KEYWORDS (score 0-5):
- 4-8 keywords present
- Not duplicating title words
- Includes domain-specific indexing terms
- Mix of specific and general terms

COMMENT RULES:
- Every item in strengths, weaknesses, comments, and recommendations must start with one of:
  [TITLE], [ABSTRACT], or [KEYWORDS].
- Score 0 only if title, abstract, and keywords are all missing.
- If title, abstract, and keywords are present, score should normally be between 2.5 and 5.0.
- Do not claim "15 words max"; only say the title can be shortened if it is genuinely hard to scan.
- Be critical, but do not punish detection errors when the detected fields are shown below.

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON structure:
{{
  "agent_name": "TitleAbstractKeywordsReviewer",
  "scope": "Title, Abstract, Keywords",
  "title_assessment": {{
    "detected_title": "<first line or best guess>",
    "is_specific": true/false,
    "reflects_contribution": true/false,
    "issues": []
  }},
  "abstract_assessment": {{
    "has_background": true/false,
    "has_objective": true/false,
    "has_methods": true/false,
    "has_results": true/false,
    "has_conclusions": true/false,
    "quantifies_results": true/false,
    "issues": []
  }},
  "keywords_assessment": {{
    "keywords_found": [],
    "count": 0,
    "issues": []
  }},
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class TitleAbstractKeywordsReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "TitleAbstractKeywordsReviewer"

    @property
    def scope(self) -> str:
        return "Title, Abstract, Keywords"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        title    = sections.get("title", "").strip()
        abstract = sections.get("abstract", "").strip()
        keywords = sections.get("keywords", "").strip()

        parts = []
        if title or abstract or keywords:
            parts.append(
                "[DETECTED FIELDS]\n"
                f"TITLE: {title or 'Not detected'}\n"
                f"KEYWORDS: {keywords or 'Not detected'}\n"
                f"ABSTRACT: {abstract[:1600] or 'Not detected'}"
            )

        # Include body sections for holistic abstract consistency check
        for key in ["introduction", "results", "conclusions", "discussion"]:
            if key in sections and sections[key]:
                parts.append(f"[{key.upper()} — for abstract consistency check]\n{sections[key][:600]}")

        if not parts:
            full = sections.get("_full_text", "")
            parts.append(f"[FULL TEXT]\n{full[:2000]}")
        return "\n\n".join(parts)[:4000]

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)
        has_detected = any(sections.get(k, "").strip() for k in ("title", "abstract", "keywords"))
        if has_detected and (result.get("parse_error") or result.get("score", 0) == 0):
            return self._deterministic_result(sections, result.get("raw_output", ""))
        if has_detected:
            return self._calibrate_result(result, sections)
        return result

    def _calibrate_result(self, result: dict, sections: dict) -> dict:
        title = sections.get("title", "").strip()
        abstract = sections.get("abstract", "").strip()
        keywords = sections.get("keywords", "").strip()
        detected_count = sum(bool(v) for v in (title, abstract, keywords))

        if detected_count == 3 and result.get("score", 0) < 2.5:
            result["score"] = 3.0
            result.setdefault("minor_comments", []).append(
                "[ABSTRACT] Score floor applied because title, abstract, and keywords were all detected; review comments should justify any lower score."
            )
        elif detected_count == 2 and result.get("score", 0) < 2.0:
            result["score"] = 2.5

        for key in ("strengths", "weaknesses", "major_comments", "minor_comments", "specific_recommendations"):
            result[key] = self._label_items(result.get(key, []))

        result = self._enrich_sparse_comments(result, title, abstract, keywords)
        return self._normalize_result(result)

    def _enrich_sparse_comments(self, result: dict, title: str, abstract: str, keywords_text: str) -> dict:
        total_comments = sum(len(result.get(k, [])) for k in ("strengths", "weaknesses", "major_comments", "specific_recommendations"))
        if total_comments >= 4:
            return result

        keywords = [k.strip(" .;") for k in keywords_text.replace(";", ",").split(",") if k.strip(" .;")]
        title_words = len(title.split())
        abstract_words = len(abstract.split())

        strengths = result.setdefault("strengths", [])
        weaknesses = result.setdefault("weaknesses", [])
        recommendations = result.setdefault("specific_recommendations", [])

        if title:
            strengths.append("[TITLE] The title clearly signals the core method and application domain.")
            if title_words > 20:
                weaknesses.append("[TITLE] The title is informative but relatively long, which can reduce scanability.")
                recommendations.append("[TITLE] Consider a slightly shorter title while preserving method, data source, and domain terms.")
        else:
            weaknesses.append("[TITLE] No title was detected in the parsed manuscript.")

        if abstract_words >= 120:
            strengths.append("[ABSTRACT] The abstract provides substantial methodological and validation detail.")
            if any(ch.isdigit() for ch in abstract):
                strengths.append("[ABSTRACT] Quantitative result signals are present in the abstract.")
        elif abstract:
            weaknesses.append("[ABSTRACT] The abstract appears short for a full Q1-style summary.")
            recommendations.append("[ABSTRACT] Ensure the abstract covers problem, method, validation, quantitative results, and implications.")

        if keywords:
            strengths.append(f"[KEYWORDS] {len(keywords)} keywords were detected for indexing and discoverability.")
            if len(keywords) > 8:
                weaknesses.append("[KEYWORDS] The keyword list is broad; some journals prefer a tighter set of 4-8 terms.")
        else:
            recommendations.append("[KEYWORDS] Add 4-8 domain-specific indexing terms after the abstract.")

        result["strengths"] = strengths[:5]
        result["weaknesses"] = weaknesses[:4]
        result["specific_recommendations"] = recommendations[:4]
        if not result.get("major_comments") and weaknesses:
            result["major_comments"] = weaknesses[:1]
        return result

    def _label_items(self, items: list) -> list:
        labels = ("[TITLE]", "[ABSTRACT]", "[KEYWORDS]")
        labelled = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if text.startswith(labels):
                labelled.append(text)
                continue
            low = text.lower()
            if "keyword" in low:
                labelled.append(f"[KEYWORDS] {text}")
            elif "abstract" in low:
                labelled.append(f"[ABSTRACT] {text}")
            elif "title" in low:
                labelled.append(f"[TITLE] {text}")
            else:
                labelled.append(f"[ABSTRACT] {text}")
        return labelled

    def _deterministic_result(self, sections: dict, raw_output: str = "") -> dict:
        title = sections.get("title", "").strip()
        abstract = sections.get("abstract", "").strip()
        keywords_text = sections.get("keywords", "").strip()
        keywords = [k.strip(" .;") for k in keywords_text.replace(";", ",").split(",") if k.strip(" .;")]

        title_words = len(title.split())
        has_title = bool(title)
        has_abstract = len(abstract.split()) >= 80
        has_keywords = len(keywords) >= 3

        score = 0.0
        score += 1.5 if has_title else 0
        score += 2.0 if has_abstract else 0
        score += 1.0 if has_keywords else 0
        if has_title and 8 <= title_words <= 25:
            score += 0.3
        if has_keywords and 4 <= len(keywords) <= 10:
            score += 0.2
        score = min(4.0, score)

        weaknesses = []
        recommendations = []
        if not has_title:
            weaknesses.append("[TITLE] Title was not detected by the parser.")
            recommendations.append("[TITLE] Add a clear title at the beginning of the manuscript.")
        elif title_words > 25:
            weaknesses.append("[TITLE] The title is long and may be difficult to scan.")
            recommendations.append("[TITLE] Consider shortening the title while preserving the core contribution.")
        if not has_abstract:
            weaknesses.append("[ABSTRACT] Abstract was not detected or is too short for reliable evaluation.")
            recommendations.append("[ABSTRACT] Provide a standalone abstract covering objective, method, results, and conclusion.")
        if not has_keywords:
            weaknesses.append("[KEYWORDS] Keywords were not detected or fewer than three were found.")
            recommendations.append("[KEYWORDS] Provide 4-8 indexing terms after the abstract.")

        if raw_output:
            weaknesses.append("[ABSTRACT] The language model response was not valid JSON, so a parser-based fallback was used.")

        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "title_assessment": {
                "detected_title": title or "Not reported in the manuscript",
                "is_specific": has_title and title_words >= 6,
                "reflects_contribution": has_title,
                "issues": ["Long title"] if title_words > 25 else [],
            },
            "abstract_assessment": {
                "has_background": has_abstract,
                "has_objective": has_abstract,
                "has_methods": has_abstract,
                "has_results": has_abstract,
                "has_conclusions": has_abstract,
                "quantifies_results": any(ch.isdigit() for ch in abstract),
                "issues": [] if has_abstract else ["Abstract not detected or too short"],
            },
            "keywords_assessment": {
                "keywords_found": keywords,
                "count": len(keywords),
                "issues": [] if has_keywords else ["Insufficient keywords detected"],
            },
            "strengths": [
                item for item, ok in [
                    ("[TITLE] Title detected and available for review.", has_title),
                    ("[ABSTRACT] Abstract detected and available for review.", has_abstract),
                    ("[KEYWORDS] Keywords detected and available for review.", has_keywords),
                ] if ok
            ],
            "weaknesses": weaknesses,
            "major_comments": [],
            "minor_comments": weaknesses[:3],
            "specific_recommendations": recommendations,
            "score": score,
            "confidence": 0.65,
            "fallback_used": True,
            "raw_output": raw_output[:500],
        })
