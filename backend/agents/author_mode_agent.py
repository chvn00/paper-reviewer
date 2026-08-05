"""
author_mode_agent.py — Modo Autor
----------------------------------
Para cada sección revisada, genera:
  - instruction: qué hacer / cómo redactar (ajustado a la editorial)
  - latex_code:  sugerencia concreta en LaTeX (con formato de la editorial)
"""

import logging
from backend.llm.phi3_client import call_llm, parse_json_response

logger = logging.getLogger(__name__)

AGENT_SECTION_MAP = {
    "TitleAbstractKeywordsReviewer": ["title", "abstract", "keywords"],
    "StructureReviewer":             ["introduction"],
    "MethodologyReviewer":           ["methodology"],
    "StatisticsReviewer":            ["methodology", "results"],
    "FiguresTablesEquationsReviewer":["results"],
    "ResultsReviewer":               ["results"],
    "DiscussionConclusionsReviewer": ["discussion", "conclusions"],
    "WritingReviewer":               ["abstract", "introduction"],
    "ReferencesReviewer":            ["references"],
    "EthicsLimitationsReviewer":     ["conclusions"],
}

SECTION_LABELS = {
    "TitleAbstractKeywordsReviewer": "Title / Abstract / Keywords",
    "StructureReviewer":             "Estructura / Introducción",
    "MethodologyReviewer":           "Metodología",
    "StatisticsReviewer":            "Análisis Estadístico",
    "FiguresTablesEquationsReviewer":"Figuras · Tablas · Ecuaciones",
    "ResultsReviewer":               "Resultados",
    "DiscussionConclusionsReviewer": "Discusión y Conclusiones",
    "WritingReviewer":               "Redacción Científica",
    "ReferencesReviewer":            "Referencias",
    "EthicsLimitationsReviewer":     "Ética y Limitaciones",
}

# Guías de formato y estilo por editorial — se inyectan directamente en el prompt
PUBLISHER_STYLE = {
    "ieee": {
        "name": "IEEE",
        "writing_style": (
            "IEEE style: formal, concise, third-person. "
            "Use active voice sparingly; prefer passive for methods. "
            "Avoid colloquial language. "
            "Contributions must be framed in terms of engineering or technical novelty."
        ),
        "latex_format": (
            "Use \\documentclass[journal]{IEEEtran}. "
            "Abstract must be a single paragraph, 150–250 words, no citations. "
            "Keywords: 4–6 terms using IEEE Taxonomy. "
            "Equations: numbered with \\begin{equation}...\\end{equation}, all variables defined. "
            "Figures: \\begin{figure}[!t]...\\end{figure} with \\caption{} ending in period. "
            "Citations: numeric [1] style using \\cite{}. "
            "Section headers: \\section{I. INTRODUCTION} (Roman numerals, ALL CAPS). "
            "No \\subsection{} deeper than two levels."
        ),
        "reference_format": (
            "IEEE reference format: [1] A. Author, \"Title,\" Journal, vol. X, no. Y, pp. Z–Z, Month Year. "
            "Use \\bibitem in IEEEtran bibliography. DOI mandatory for journal articles."
        ),
    },
    "elsevier": {
        "name": "Elsevier / ScienceDirect",
        "writing_style": (
            "Elsevier style: clear, structured, evidence-based. "
            "Use Highlights (3–5 bullet points, max 85 chars each) before abstract. "
            "Abstract: structured or unstructured depending on journal, 150–300 words. "
            "Emphasize novelty, significance, and practical implications."
        ),
        "latex_format": (
            "Use \\documentclass{elsarticle}. "
            "Abstract inside \\begin{abstract}...\\end{abstract}. "
            "Keywords with \\begin{keyword}...\\sep...\\end{keyword}. "
            "Figures: \\begin{figure}...\\caption{...}\\label{fig:x}\\end{figure}. "
            "Tables: use \\begin{table}...\\begin{tabular}...\\end{tabular}...\\end{table} with \\toprule/\\midrule/\\bottomrule (booktabs). "
            "Equations: \\begin{equation} numbered, or \\begin{align} for multi-line. "
            "Citations: \\cite{key} with natbib; author-year or numeric per journal style."
        ),
        "reference_format": (
            "Elsevier reference format (APA-like): Author, A.A., Author, B.B., Year. Title. Journal Name Vol(Issue), pages. https://doi.org/... "
            "Use \\bibliographystyle{elsarticle-num} or elsarticle-harv."
        ),
    },
    "mdpi": {
        "name": "MDPI",
        "writing_style": (
            "MDPI style: concise, structured, open-access oriented. "
            "Abstract: 200 words max, no references, no abbreviations unless defined. "
            "Keywords: 5–10 terms. "
            "Must include 'Author Contributions' and 'Funding' sections. "
            "Emphasize reproducibility and data availability."
        ),
        "latex_format": (
            "Use MDPI LaTeX template (\\documentclass{Definitions/mdpi}). "
            "Abstract: \\abstract{...} command. "
            "Keywords: \\keyword{word1; word2; ...}. "
            "Sections: \\section{}, \\subsection{}, \\subsubsection{} numbered automatically. "
            "Figures: \\begin{figure}[H] with \\includegraphics and \\caption{}. "
            "Tables: \\begin{table}[H] with \\caption{} above table. Use longtable for multi-page. "
            "Equations: \\begin{equation} or \\begin{linenomath} if line numbers enabled. "
            "Author contributions: \\authorcontributions{Conceptualization, A.A. and B.B.; ...}. "
            "Citations: \\cite{} numeric, references in \\bibliography{}."
        ),
        "reference_format": (
            "MDPI reference format: 1. Author, A.A.; Author, B.B. Title of Article. Journal Abbrev. Year, Vol, page range. "
            "DOI mandatory. Use \\bibliographystyle{mdpi}."
        ),
    },
    "emerald": {
        "name": "Emerald Publishing",
        "writing_style": (
            "Emerald style: management/social-science oriented, structured abstract mandatory. "
            "Structured abstract with: Purpose, Design/methodology/approach, Findings, "
            "Research limitations/implications, Practical implications, Originality/value. "
            "Each heading 40–60 words. Total abstract 250 words max. "
            "Writing should be accessible to practitioners as well as academics."
        ),
        "latex_format": (
            "Emerald uses its own template. "
            "Abstract: structured with \\section*{Purpose}, \\section*{Design/methodology/approach}, etc. "
            "Keywords: 6 maximum, listed after abstract. "
            "Figures and tables: referenced in text, captions below figures, above tables. "
            "Citations: Harvard author-year style — (Smith, 2020) in text, full reference at end. "
            "Headings: use \\section{}, \\subsection{} — no more than 3 levels."
        ),
        "reference_format": (
            "Emerald Harvard format: Smith, J. and Jones, A. (2020), \"Title\", Journal Name, Vol. X No. Y, pp. Z-Z. "
            "Available at: https://doi.org/..."
        ),
    },
    "sage": {
        "name": "SAGE Publications",
        "writing_style": (
            "SAGE style: clear academic prose, social/health sciences focus. "
            "Abstract: 200–250 words, unstructured or structured per journal. "
            "Avoid jargon; define all acronyms at first use. "
            "Limitations section required. Use inclusive language."
        ),
        "latex_format": (
            "Abstract inside \\begin{abstract}...\\end{abstract}. "
            "Keywords: 5–7 terms after abstract. "
            "Figures: \\begin{figure}[htbp] with numbered captions below. "
            "Tables: caption above, \\hline borders, no vertical lines preferred. "
            "Citations: APA (author, year) with \\cite{} and natbib. "
            "Equations: numbered, all symbols defined in surrounding text."
        ),
        "reference_format": (
            "SAGE APA format: Author, A. A., & Author, B. B. (Year). Title of article. "
            "Journal Name, Vol(Issue), pages. https://doi.org/..."
        ),
    },
    "taylor": {
        "name": "Taylor & Francis",
        "writing_style": (
            "Taylor & Francis style: varies by journal family; default to APA style. "
            "Abstract: 100–250 words, key findings highlighted. "
            "Writing: formal, third-person. Interdisciplinary clarity expected. "
            "Acknowledgements and disclosure statements mandatory."
        ),
        "latex_format": (
            "Use \\documentclass[]{interact} (Taylor & Francis template). "
            "Abstract: \\begin{abstract}...\\end{abstract}. "
            "Keywords: \\keywords{word1, word2, ...}. "
            "Figures: \\begin{figure}...\\caption{...}\\end{figure} — EPS or high-res PNG. "
            "Tables: \\begin{table}...\\caption{}...\\begin{tabular}...\\end{tabular}...\\end{table}. "
            "Citations: use \\cite{} with natbib; numeric or author-year per journal. "
            "Equations: numbered with \\begin{equation}."
        ),
        "reference_format": (
            "Taylor & Francis APA: Author AA, Author BB. Title. Journal Name. Year;Vol(Issue):pages. "
            "doi:10.xxxx/xxxxx"
        ),
    },
}

PUBLISHER_STYLE[""] = {
    "name": "General (no editorial específica)",
    "writing_style": (
        "Standard academic writing: formal, clear, third-person. "
        "Structured abstract, clearly defined sections, evidence-based claims."
    ),
    "latex_format": (
        "Standard LaTeX: \\documentclass{article}. "
        "\\begin{abstract}...\\end{abstract}. "
        "\\section{}, \\subsection{} for structure. "
        "\\begin{equation} for numbered equations. "
        "\\begin{figure} and \\begin{table} with captions. "
        "\\cite{} for citations, \\bibliography{} for references."
    ),
    "reference_format": (
        "Standard academic format with author, year, title, journal, volume, pages, DOI."
    ),
}


def _extract_issues(agent_result: dict) -> list[str]:
    """Extrae problemas: weaknesses, major_comments, specific_recommendations.
    Filtra comentarios muy cortos (<20 chars) que no aportan."""
    items = []
    for field in ["weaknesses", "major_comments", "specific_recommendations"]:
        for item in (agent_result.get(field) or []):
            text = _fmt(item)
            # Solo incluir comentarios sustanciales (>20 caracteres)
            if text and len(text) > 20 and text not in items:
                items.append(text)
    return items[:8]  # Aumentar a 8 (era 5) para más contexto


def _fmt(item) -> str:
    if not item:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ["comment", "issue", "recommendation", "text", "description", "weakness", "strength", "finding"]:
            if item.get(key):
                prefix = item.get("criterion") or item.get("section") or ""
                body = _fmt(item[key])
                return f"{prefix}: {body}" if prefix else body
        return "; ".join(f"{k}: {_fmt(v)}" for k, v in item.items() if v)
    if isinstance(item, list):
        return "; ".join(_fmt(i) for i in item if i)
    return str(item).strip()


async def generate_author_suggestion(
    agent_result: dict,
    sections: dict,
    publisher: str = "",
    paper_type: str = "",
) -> dict:
    """
    Genera sugerencia de autor para una sección revisada,
    ajustada al estilo y formato de la editorial seleccionada.
    """
    agent_name    = agent_result.get("agent_name", "")
    section_label = SECTION_LABELS.get(agent_name, agent_name)
    score         = float(agent_result.get("score") or 0)
    skipped       = agent_result.get("skipped", False)

    if skipped:
        return {
            "agent_name":    agent_name,
            "section_label": section_label,
            "score":         score,
            "issues":        [],
            "instruction":   "Esta sección fue omitida en la revisión.",
            "latex_code":    "",
            "publisher":     publisher,
            "skipped":       True,
        }

    issues = _extract_issues(agent_result)

    # Solo retornar sin LaTeX si score es excelente (>=4.5) Y no hay problemas detectados
    if not issues and score >= 4.5:
        return {
            "agent_name":    agent_name,
            "section_label": section_label,
            "score":         score,
            "issues":        [],
            "instruction":   "Excelente — no se detectaron problemas significativos en esta sección.",
            "latex_code":    "",
            "publisher":     publisher,
            "skipped":       False,
        }

    # Si score < 3 pero no hay issues listadas, extraer del texto de la revisión
    if not issues and score < 3.0:
        for field in ["strengths", "weaknesses", "major_comments", "minor_comments"]:
            comments = agent_result.get(field, [])
            if isinstance(comments, list):
                for c in comments[:3]:  # Tomar los primeros 3
                    text = _fmt(c)
                    if text and len(text) > 15:
                        issues.append(text)
                    if len(issues) >= 3:
                        break
            if len(issues) >= 3:
                break

    # Texto de la sección (fallback al texto completo si el parser no separó secciones)
    section_keys = AGENT_SECTION_MAP.get(agent_name, ["abstract"])
    section_parts = []
    for key in section_keys:
        text = (sections.get(key) or "").strip()
        if text:
            section_parts.append(f"[{key.upper()}]\n{text[:4000]}")
    section_text = "\n\n".join(section_parts)
    if not section_text:
        full = (sections.get("_full_text") or "").strip()
        section_text = f"[FULL PAPER EXCERPT]\n{full[:6000]}" if full else "(Texto no disponible)"

    # Estilo editorial
    style = PUBLISHER_STYLE.get(publisher, PUBLISHER_STYLE[""])
    pub_name = style["name"]
    paper_type_str = f" ({paper_type.replace('_', ' ').title()})" if paper_type else ""

    issues_text = "\n".join(f"- {iss}" for iss in issues) if issues else f"(Review score: {score}/5 — reviewers suggested general improvements)"

    prompt = f"""Help an author revise their paper section for submission to {pub_name}{paper_type_str}.

SCORE FROM PEER REVIEW: {score}/5.0
TARGET PUBLISHER STYLE ({pub_name}):
{style["writing_style"]}

CURRENT SECTION:
{section_text}

REVIEWER FINDINGS:
{issues_text}

TASK:
1. "instruction": Give 2-4 specific, actionable suggestions for improving this section to meet {pub_name} standards. Focus on: clarity, completeness, structure, and {pub_name} formatting requirements. Be concrete.
2. "latex_code": Provide an improved version of this section in {pub_name} LaTeX format. Keep it professional and publication-ready. Must be non-empty.

CRITICAL: Always generate both fields with substantial content. Do NOT leave latex_code empty.
Even if the section is well-written, suggest ways to strengthen it further.

Respond ONLY with valid JSON:
{{"instruction": "...", "latex_code": "\\\\section{{...}} ..."}}"""

    system = (
        f"You are an expert academic writing coach specialized in {pub_name} journal submissions. "
        "Generate precise, publisher-specific revision instructions and valid LaTeX code. "
        "Respond only with JSON, no extra text."
    )

    instruction, latex_code = "", ""
    # Hasta 2 intentos: exigimos latex_code no vacío (modelos pequeños a veces lo omiten)
    for attempt in range(2):
        try:
            response = await call_llm(
                prompt,
                system_prompt=system,
                config_override={"max_tokens": 3000, "temperature": 0.3 if attempt == 0 else 0.5},
            )
            parsed = parse_json_response(response, f"AuthorMode:{agent_name}")
            if not parsed.get("parse_error"):
                new_instruction = str(parsed.get("instruction", "")).strip()
                new_latex       = str(parsed.get("latex_code", "")).strip()
                # Conservar el mejor resultado entre intentos
                if new_instruction and (not instruction or new_latex):
                    instruction = new_instruction
                if new_latex:
                    latex_code = new_latex
                if instruction and latex_code:
                    break
        except Exception as e:
            logger.error(f"[AuthorMode] Attempt {attempt+1} failed for {agent_name}: {e}")

    if not instruction and not latex_code:
        instruction = "No se pudo generar la sugerencia para esta sección. Usa ↻ Regenerar para reintentar."

    return {
        "agent_name":    agent_name,
        "section_label": section_label,
        "score":         score,
        "issues":        issues,
        "instruction":   instruction,
        "latex_code":    latex_code,
        "publisher":     publisher,
        "skipped":       False,
    }
