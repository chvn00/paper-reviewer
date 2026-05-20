"""
statistics_reviewer.py — CHVN Paper Reviewer v3
-------------------------------------------------
CONDITIONAL: Only activates if paper contains actual comparative statistical analysis.
Engineering design papers (thermodynamics, prototypes, circuits) that report
performance metrics (COP, efficiency) but do NOT run statistical comparisons
are scored neutrally (N/A context) — NOT penalized.
"""

from backend.agents.base_agent import BaseReviewerAgent

SYSTEM_PROMPT = """You are a biostatistician and senior peer reviewer for Q1 scientific journals.
Your first task is to determine whether this manuscript REQUIRES inferential statistical analysis.

IMPORTANT DISTINCTION:
- Engineering DESIGN papers (prototypes, thermodynamic analysis, system design, circuit design)
  that report performance metrics (COP, efficiency, power) do NOT need statistical hypothesis tests.
  For these, evaluate whether uncertainty/variability is adequately reported.
- Experimental comparison papers (algorithm benchmarks, clinical trials, user studies)
  DO need statistical tests (ANOVA, Kruskal-Wallis, t-test, etc.).

Respond ONLY with valid JSON. Never invent statistical results.
If a test is not reported, state "Not reported in the manuscript".
Be specific: name the tests found, the p-values reported, the metrics used."""

USER_PROMPT_TEMPLATE = """Critically evaluate the statistical reporting in this manuscript.

STEP 1 — CLASSIFY THE PAPER:
First determine: Is this paper:
A) An engineering design/prototype paper? (thermodynamics, system design, device fabrication, COP analysis)
B) A comparative experiment paper? (algorithm benchmarks, A/B tests, clinical comparisons, user studies)

STEP 2 — EVALUATE ACCORDINGLY:

FOR TYPE A (engineering design/prototype):
- Statistical hypothesis tests (ANOVA, Kruskal-Wallis) are NOT expected — do not penalize their absence
- Check: Are performance metrics (COP, efficiency, power) clearly calculated and justified?
- Check: Is measurement uncertainty or experimental error discussed?
- Check: Are results reproducible (materials, conditions, instruments described)?
- Score 3.5–4.5 if metrics are clearly reported even without formal stats
- Only flag if quantitative comparisons are made without any uncertainty bounds

FOR TYPE B (comparative/experimental):
Apply full statistical rubric (score 0–5):
1. Appropriate statistical tests for data type
2. Effect sizes reported (not just p-values)
3. Confidence intervals reported
4. Sample size justified / power analysis
5. Multiple comparison corrections (Bonferroni, Holm)
6. Test assumptions verified (normality, independence)
7. Bootstrap or nonparametric methods justified
8. Results reproducible (seeds, runs, variance)

IMPORTANT: If the paper is Type A and you see no inferential statistics, that is CORRECT —
do not add comments asking for ANOVA or Kruskal-Wallis tests.

---
MANUSCRIPT TEXT:
{text}
---

Respond ONLY with this JSON:
{{
  "agent_name": "StatisticsReviewer",
  "scope": "Statistical methods, tests, and reporting quality",
  "paper_type_classified": "design|comparative|mixed",
  "statistical_tests_found": [],
  "metrics_found": [],
  "effect_sizes_reported": true,
  "confidence_intervals_reported": true,
  "sample_size_justified": true,
  "multiple_comparisons_corrected": true,
  "assumptions_verified": true,
  "practical_vs_statistical_significance": true,
  "reproducibility_reported": true,
  "statistical_concerns": [],
  "strengths": [],
  "weaknesses": [],
  "major_comments": [],
  "minor_comments": [],
  "specific_recommendations": [],
  "score": 0.0,
  "confidence": 0.0
}}"""


class StatisticsReviewerAgent(BaseReviewerAgent):

    @property
    def agent_name(self) -> str:
        return "StatisticsReviewer"

    @property
    def scope(self) -> str:
        return "Statistical methods, tests, and reporting quality"

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_user_prompt(self, text: str) -> str:
        return USER_PROMPT_TEMPLATE.format(text=text)

    def get_relevant_sections(self, sections: dict) -> str:
        priority = ["results", "experiments", "methodology", "discussion"]
        parts = []
        full = sections.get("_full_text", "")
        facts = self._stats_facts(full)
        if facts:
            parts.append("[DETECTED STATISTICAL SIGNALS]\n" + facts)
        for key in priority:
            if key in sections:
                parts.append(f"[{key.upper()}]\n{sections[key][:8000]}")
        if full and len(parts) < 2:
            parts.append(f"[FULL TEXT]\n{full}")
        return "\n\n".join(parts)

    async def run(self, sections: dict, mode: str = "fast", publisher: str = "", paper_type: str = "") -> dict:
        """Only activate if actual inferential statistical content detected."""
        text = sections.get("_full_text", "") or self.get_relevant_sections(sections)

        # Distinguish engineering metrics from actual statistical tests
        has_real_stats = self._detect_inferential_stats(text)
        has_only_metrics = self._detect_engineering_metrics_only(text)

        if not has_real_stats and has_only_metrics:
            # Engineering design paper — evaluate metric reporting, don't penalize missing stats
            return self._engineering_paper_result(sections, text)

        if not has_real_stats and not has_only_metrics:
            return self._empty_result(
                "No statistical content detected. Agent skipped — does not penalize score."
            )

        # Paper has actual stats — run full LLM evaluation
        result = await super().run(sections, mode, publisher=publisher, paper_type=paper_type)

        # Post-process: remove ANOVA recommendations if not a comparative paper
        classified = result.get("paper_type_classified", "")
        if classified == "design":
            result["major_comments"] = [
                c for c in result.get("major_comments", [])
                if not any(kw in c.lower() for kw in ("anova", "kruskal", "wilcoxon", "t-test", "hypothesis test"))
            ]
            result["specific_recommendations"] = [
                r for r in result.get("specific_recommendations", [])
                if not any(kw in r.lower() for kw in ("anova", "kruskal", "wilcoxon", "t-test", "hypothesis test"))
            ]
            if result.get("score", 0) < 3.0:
                result["score"] = 3.0

        facts = self._stats_facts(text)
        strong_reporting = sum(1 for line in facts.splitlines() if line.strip()) >= 5
        if strong_reporting and result.get("score", 0) < 3.0:
            result["score"] = 3.5
            result["confidence"] = max(result.get("confidence", 0), 0.6)
            result.setdefault("strengths", []).append(
                "The manuscript reports multiple statistical validation elements, including independent runs, "
                "nonparametric tests, correction procedures, confidence intervals, and performance metrics."
            )
        return self._normalize_result(result)

    def _detect_inferential_stats(self, text: str) -> bool:
        """Detects actual statistical hypothesis testing (not just engineering metrics)."""
        import re
        low = text.lower()
        INFERENTIAL_TERMS = [
            "anova", "t-test", "t test", "wilcoxon", "kruskal",
            "mann-whitney", "chi-square", "pearson correlation", "spearman",
            "hypothesis test", "null hypothesis", "p-value", "p value",
            "p = 0", "p < 0", "p > 0", "p=0", "p<0", "p>0",
            "statistical significance", "statistically significant",
            "confidence interval", "bootstrap", "bonferroni", "holm correction",
            "independent runs", "30 runs", "multiple comparison",
        ]
        return any(term in low for term in INFERENTIAL_TERMS)

    def _detect_engineering_metrics_only(self, text: str) -> bool:
        """Detects engineering performance metrics (COP, efficiency, power, etc.)."""
        low = text.lower()
        ENGINEERING_METRICS = [
            "coefficient of performance", "cop", "efficiency",
            "power consumption", "heat transfer", "thermal", "thermodynamic",
            "voltage", "current", "frequency", "torque", "pressure",
            "rmse", "mae", "accuracy", "recall", "precision", "f1",
        ]
        return any(term in low for term in ENGINEERING_METRICS)

    def _engineering_paper_result(self, sections: dict, text: str) -> dict:
        """Score an engineering design paper on metric reporting quality, not inferential stats."""
        low = text.lower()

        has_uncertainty = any(t in low for t in ("error", "uncertainty", "tolerance", "±", "variation", "deviation"))
        has_conditions = any(t in low for t in ("temperature", "pressure", "ambient", "condition", "operating"))
        has_instruments = any(t in low for t in ("sensor", "instrument", "measured", "measurement", "calibr", "datasheet"))
        has_comparison = any(t in low for t in ("compared to", "versus", "higher than", "lower than", "similar to", "better than"))

        score = 3.0
        strengths = ["Engineering design paper: inferential statistical tests are not required for this paper type."]
        weaknesses = []
        recommendations = []

        if has_uncertainty:
            score += 0.4
            strengths.append("Measurement uncertainty or variability is acknowledged in the manuscript.")
        else:
            weaknesses.append("Measurement uncertainty or experimental error is not explicitly discussed for the reported metrics.")
            recommendations.append("Report measurement uncertainty or error bounds for key metrics (e.g., COP ± X%).")

        if has_conditions:
            score += 0.3
            strengths.append("Operating conditions are described for the reported performance metrics.")

        if has_instruments:
            score += 0.3
            strengths.append("Measurement instruments or data collection methods are mentioned.")
        else:
            weaknesses.append("The instruments or methods used to obtain measurements are not clearly described.")
            recommendations.append("Describe the instruments, sensors, or methods used for each reported measurement.")

        if has_comparison and not self._detect_inferential_stats(text):
            weaknesses.append("Qualitative comparisons with other systems are made without quantitative uncertainty bounds.")
            recommendations.append("When comparing COP or efficiency with other systems, report the operating conditions and uncertainty for a fair comparison.")

        score = min(4.5, round(score, 2))

        return self._normalize_result({
            "agent_name": self.agent_name,
            "scope": self.scope,
            "paper_type_classified": "design",
            "statistical_tests_found": [],
            "metrics_found": ["performance metrics (COP, efficiency, power)"],
            "effect_sizes_reported": False,
            "confidence_intervals_reported": has_uncertainty,
            "sample_size_justified": True,
            "multiple_comparisons_corrected": True,
            "assumptions_verified": True,
            "practical_vs_statistical_significance": True,
            "reproducibility_reported": has_conditions and has_instruments,
            "statistical_concerns": [],
            "strengths": strengths,
            "weaknesses": weaknesses,
            "major_comments": weaknesses[:2],
            "minor_comments": [],
            "specific_recommendations": recommendations,
            "score": score,
            "confidence": 0.75,
        })

    def _stats_facts(self, text: str) -> str:
        low = text.lower()
        signals = []
        checks = [
            ("30 independent runs", "30 independent" in low or "30 runs" in low),
            ("Kruskal-Wallis", "kruskal" in low),
            ("Wilcoxon/rank-sum post-hoc", "wilcoxon" in low or "rank-sum" in low),
            ("Holm correction", "holm" in low),
            ("bootstrap confidence intervals", "bootstrap" in low and "confidence" in low),
            ("coefficient of variation", "coefficient of variation" in low),
            ("RMSE/MSE metrics", "rmse" in low or "mse" in low),
            ("Pareto/hypervolume indicators", "pareto" in low or "hypervolume" in low),
        ]
        for label, ok in checks:
            if ok:
                signals.append(f"- {label} detected")
        return "\n".join(signals)
