"""
parser_agent.py — CHVN Paper Reviewer v3
-----------------------------------------
Fixes:
- LaTeX PDF support: cleans ligatures, math artifacts, special chars
- Detects abstract inline IEEE style: "Abstract—" or "abstract" at paragraph start
- Detects references/bibliography with [1] pattern
- Robust section detection for IEEE, Elsevier, LaTeX-generated PDFs
- Always injects _full_text for holistic agent review
"""

import re
import logging

logger = logging.getLogger(__name__)

# ─── Section keyword → canonical ─────────────────────────────────────────────
SECTION_KEYWORD_MAP = {
    # ── English ──────────────────────────────────────────────────────────────
    "abstract":           "abstract",
    "index terms":        "keywords",
    "keywords":           "keywords",
    "key words":          "keywords",
    "introduction":       "introduction",
    "background":         "introduction",
    "motivation":         "introduction",
    "related work":       "literature",
    "literature":         "literature",
    "state of the art":   "literature",
    "prior work":         "literature",
    "methodology":        "methodology",
    "methods":            "methodology",
    "proposed":           "methodology",
    "framework":          "methodology",
    "approach":           "methodology",
    "formulation":        "methodology",
    "system model":       "methodology",
    "platform":           "methodology",
    "identification":     "methodology",
    "algorithm":          "methodology",
    "architecture":       "methodology",
    "physics":            "methodology",
    "neural":             "methodology",
    "optimization":       "methodology",
    "eann":               "methodology",
    "multi-objective":    "methodology",
    "parameter":          "methodology",
    "feature":            "methodology",
    "mapping":            "methodology",
    "evolutionary":       "methodology",
    "two-phase":          "methodology",
    "baseline":           "methodology",
    "complexity":         "methodology",
    "deployment":         "methodology",
    "experiment":         "experiments",
    "experimental":       "experiments",
    "simulation":         "experiments",
    "setup":              "experiments",
    "preprocessing":      "experiments",
    "results":            "results",
    "findings":           "results",
    "performance":        "results",
    "evaluation":         "results",
    "validation":         "results",
    "statistical":        "results",
    "accuracy":           "results",
    "robustness":         "results",
    "visual evidence":    "results",
    "computational":      "results",
    "discussion":         "discussion",
    "analysis":           "discussion",
    "implications":       "discussion",
    "conclusion":         "conclusions",
    "summary":            "conclusions",
    "future":             "conclusions",
    "references":         "references",
    "bibliography":       "references",
    "acknowledgment":     "acknowledgments",
    "acknowledgement":    "acknowledgments",
    "biography":          "biography",
    "appendix":           "appendix",
    # ── Spanish ──────────────────────────────────────────────────────────────
    "resumen":            "abstract",
    "palabras clave":     "keywords",
    "palabras-clave":     "keywords",
    "introducción":       "introduction",
    "introduccion":       "introduction",
    "antecedentes":       "introduction",
    "trabajos relacionados": "literature",
    "revisión de literatura": "literature",
    "revision de literatura": "literature",
    "estado del arte":    "literature",
    "marco teórico":      "literature",
    "marco teorico":      "literature",
    "metodología":        "methodology",
    "metodologia":        "methodology",
    "materiales y métodos": "methodology",
    "materiales y metodos": "methodology",
    "diseño":             "methodology",
    "diseño experimental": "experiments",
    "experimentos":       "experiments",
    "experimentación":    "experiments",
    "pruebas":            "experiments",
    "resultados":         "results",
    "hallazgos":          "results",
    "rendimiento":        "results",
    "evaluación":         "results",
    "validación":         "results",
    "discusión":          "discussion",
    "discusion":          "discussion",
    "análisis":           "discussion",
    "analisis":           "discussion",
    "conclusiones":       "conclusions",
    "conclusión":         "conclusions",
    "conclusion":         "conclusions",
    "trabajos futuros":   "conclusions",
    "referencias":        "references",
    "bibliografía":       "references",
    "bibliografia":       "references",
    "agradecimientos":    "acknowledgments",
    "agradecimiento":     "acknowledgments",
    "apéndice":           "appendix",
    "apendice":           "appendix",
    "anexo":              "appendix",
}

STATS_KEYWORDS = [
    "statistical", "anova", "t-test", "wilcoxon", "kruskal", "bootstrap",
    "p-value", "confidence interval", "significance",
    "p-value", "p value", "p=", "p <", "p >", "p<0", "p>0",
    "anova", "t-test", "wilcoxon", "kruskal", "kruskal-wallis",
    "mann-whitney", "chi-square", "pearson", "spearman",
    "confidence interval", "bootstrap", "standard deviation",
    "nonparametric", "post-hoc", "holm", "bonferroni",
    "interquartile", "iqr", "median", "variance",
    "rmse", "mse", "mae", "r2", "r²", "coefficient of variation",
    "hypervolume", "pareto dominance", "statistical", "significant",
    "independent runs", "stochastic runs", "bootstrap confidence",
    "rank-sum", "effect size", "95%", "mean ±", "std",
]

ROMAN_SECTION_MAP = {
    "I": "introduction",
    "II": "literature",
    "III": "methodology",
    "V": "discussion",
    "VI": "discussion",
    "VII": "conclusions",
}

EQUATION_KEYWORDS = [
    "equation", "eq.", "formula", "theorem", "lemma",
    "∑", "∫", "∂", "∇", "≈", "≤", "≥", "∈",
    "argmax", "argmin", "minimize", "subject to",
    "tanh", "matrix", "eigenvalue", "state-space",
]

# LaTeX ligatures and artifacts to clean
LATEX_LIGATURES = {
    "ﬁ": "fi", "ﬀ": "ff", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "ft", "ﬆ": "st", "\x00": "", "\uf0b7": "•",
    "\u2212": "-", "\u2013": "-", "\u2014": "—",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
}


class ParserAgent:

    def __init__(self):
        self.name = "ParserAgent"

    def run(self, pdf_path: str) -> dict:
        logger.info(f"[ParserAgent v3] Processing: {pdf_path}")
        warnings = []

        raw_text, method = self._extract_text(pdf_path, warnings)

        if not raw_text or len(raw_text.strip()) < 100:
            return {
                "success": False,
                "error": "Could not extract readable text. PDF may be scanned/image-based.",
                "warnings": warnings, "sections": {}, "metadata": {},
            }

        # Clean including LaTeX artifacts
        cleaned = self._clean_text(raw_text)

        # Detect sections
        sections = self._detect_sections(cleaned)
        self._infer_title(cleaned, sections)
        self._extract_inline_keywords(cleaned, sections)

        # Always inject full text
        sections["_full_text"] = cleaned

        # Feature detection
        has_stats  = self._detect_statistics(cleaned)
        eq_count   = self._count_sequential_equations(cleaned)
        has_eq     = eq_count > 0
        fig_count  = self._count_figures(cleaned)
        tab_count  = self._count_tables(cleaned)
        has_figs   = fig_count > 0
        has_tables = tab_count > 0
        fmt        = self._detect_format(cleaned)

        visible = [k for k in sections if not k.startswith("_")]
        words   = cleaned.split()

        metadata = {
            "word_count":        len(words),
            "char_count":        len(cleaned),
            "sections_found":    visible,
            "extraction_method": method,
            "has_statistics":    has_stats,
            "has_equations":     has_eq,
            "has_figures":       has_figs,
            "has_tables":        has_tables,
            "figure_count":      fig_count,
            "table_count":       tab_count,
            "equation_count":    eq_count,
            "format_detected":   fmt,
        }

        if not sections.get("abstract"):
            warnings.append("Abstract not detected as separate section — content included in full text.")
        if not sections.get("references"):
            warnings.append("References not detected as separate section — content included in full text.")

        logger.info(
            f"[ParserAgent v3] Format={fmt} | Sections={visible} | "
            f"Words={len(words)} | Stats={has_stats} | "
            f"Figs={fig_count} | Tables={tab_count} | Eqs={eq_count}"
        )

        return {
            "success": True, "raw_text": cleaned,
            "sections": sections, "metadata": metadata, "warnings": warnings,
        }

    # ─── Extraction ───────────────────────────────────────────────────────────

    def _extract_text(self, pdf_path: str, warnings: list) -> tuple:
        # PyMuPDF blocks mode — best for two-column LaTeX
        try:
            import fitz
            doc = fitz.open(pdf_path)
            pages = []
            for page in doc:
                blocks = page.get_text("blocks")
                blocks.sort(key=lambda b: (round(b[1] / 20) * 20, b[0]))
                pages.append("\n".join(b[4].strip() for b in blocks if b[4].strip()))
            doc.close()
            text = "\n\n".join(pages)
            if len(text.strip()) > 200:
                return text, "PyMuPDF-blocks"
        except Exception as e:
            warnings.append(f"PyMuPDF blocks: {e}")

        # PyMuPDF text mode fallback
        try:
            import fitz
            doc = fitz.open(pdf_path)
            text = "\n".join(p.get_text("text") for p in doc)
            doc.close()
            if len(text.strip()) > 200:
                return text, "PyMuPDF-text"
        except Exception as e:
            warnings.append(f"PyMuPDF text: {e}")

        # pdfplumber last resort
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            if len(text.strip()) > 200:
                return text, "pdfplumber"
        except Exception as e:
            warnings.append(f"pdfplumber: {e}")

        return "", "failed"

    # ─── Cleaning ─────────────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        # Fix LaTeX ligatures first
        for bad, good in LATEX_LIGATURES.items():
            text = text.replace(bad, good)

        # Remove LaTeX math artifacts
        text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", text)  # \command{arg}
        text = re.sub(r"\$[^$]+\$", " [eq] ", text)         # inline math $...$

        lines = text.split("\n")
        cleaned = []
        prev_empty = False

        for line in lines:
            line = line.strip()
            if not line:
                if not prev_empty:
                    cleaned.append("")
                prev_empty = True
                continue
            prev_empty = False

            # Skip standalone page numbers
            if re.match(r"^\d{1,4}$", line):
                continue
            # Skip pure URLs
            if re.match(r"^https?://\S+$", line):
                continue
            # Skip very short noise
            if len(line) < 3:
                continue
            # Skip IEEE running headers
            if re.match(r"^IEEE\s+TRANSACTIONS", line, re.IGNORECASE):
                continue

            cleaned.append(line)

        text = "\n".join(cleaned)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        # Fix hyphenated line breaks (LaTeX common)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        return text.strip()

    # ─── Section detection ────────────────────────────────────────────────────

    def _detect_sections(self, text: str) -> dict:
        # Try IEEE Roman numerals
        ieee = self._detect_ieee(text)
        if len(ieee) >= 3:
            # Also try to extract abstract inline
            self._extract_inline_abstract(text, ieee)
            self._extract_references_block(text, ieee)
            logger.info(f"[Parser] IEEE: {list(ieee.keys())}")
            return ieee

        # Standard keywords
        std = self._detect_standard(text)
        if len(std) >= 2:
            self._extract_inline_abstract(text, std)
            self._extract_references_block(text, std)
            logger.info(f"[Parser] Standard: {list(std.keys())}")
            return std

        # Fallback
        logger.info("[Parser] Fallback: body only")
        result = {"body": text}
        self._extract_inline_abstract(text, result)
        self._extract_references_block(text, result)
        return result

    def _detect_ieee(self, text: str) -> dict:
        """Match Roman numeral headers and map them to canonical sections."""
        sections = {}
        lines = text.split("\n")
        current_key = "preamble"
        current_alias = None
        current_content = []
        roman_count = 0

        for line in lines:
            s = line.strip()
            m = re.match(
                r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\.?\s+(.+)$",
                s, re.IGNORECASE
            )
            if m and len(s.split()) <= 12:
                content = "\n".join(current_content).strip()
                if content and current_key:
                    sections[current_key] = sections.get(current_key, "") + "\n" + content
                    if current_alias:
                        sections[current_alias] = content
                roman = m.group(1).upper()
                title = m.group(2).strip().lower()
                canonical = self._map_roman_section(roman, title) or self._map_canonical(title)
                current_key = canonical or f"section_{roman_count}"
                current_alias = f"section_{roman.lower()}" if roman in ("VI", "VII") else None
                current_content = []
                roman_count += 1
            else:
                current_content.append(line)

        if current_content:
            content = "\n".join(current_content).strip()
            if content and current_key:
                sections[current_key] = sections.get(current_key, "") + "\n" + content
                if current_alias:
                    sections[current_alias] = content

        return {k: v.strip() for k, v in sections.items() if v.strip()} if roman_count >= 3 else {}

    def _detect_standard(self, text: str) -> dict:
        sections = {}
        lines = text.split("\n")
        current_key = "preamble"
        current_content = []

        for line in lines:
            s = line.strip()
            if not s:
                current_content.append(line)
                continue

            # ── Strict numbered section: "1. Title" on one line ──────────────
            num_match = re.match(r"^(\d+(?:\.\d+)?)\.\s+(.+)$", s)
            if num_match:
                section_title = num_match.group(2).strip()
                words = section_title.split()
                # Must be short title, no trailing sentence punctuation
                if len(words) <= 8 and not section_title.endswith((".", "!", "?", ",")):
                    canonical = self._map_canonical(section_title.lower())
                    if canonical and canonical != current_key:
                        content = "\n".join(current_content).strip()
                        if content:
                            sections[current_key] = sections.get(current_key, "") + "\n" + content
                        current_key = canonical
                        current_content = []
                        continue

            # ── Standalone section header (no inline content) ─────────────────
            words = s.split()
            word_count = len(words)

            # Must be short (≤ 6 words)
            if word_count > 6:
                current_content.append(line)
                continue

            # Must NOT end with sentence punctuation
            if s.endswith((".", "!", "?", ",")):
                current_content.append(line)
                continue

            # Must NOT be an inline section (header—content on same line)
            # e.g. "Abstract—This paper..." or "Keywords—neural, network"
            if re.search(r"[—–\-:]\s*\w", s):
                current_content.append(line)
                continue

            # Must NOT look like a sentence fragment (verb-object, preposition, etc.)
            # Simple heuristic: contains digits mixed with text mid-word = likely content
            if re.search(r"\d", s) and not re.match(r"^\d", s):
                current_content.append(line)
                continue

            canonical = self._map_canonical(s.lower())
            if canonical and canonical != current_key:
                content = "\n".join(current_content).strip()
                if content:
                    sections[current_key] = sections.get(current_key, "") + "\n" + content
                current_key = canonical
                current_content = []
            else:
                current_content.append(line)

        if current_content:
            content = "\n".join(current_content).strip()
            if content:
                sections[current_key] = sections.get(current_key, "") + "\n" + content

        return {k: v.strip() for k, v in sections.items() if v.strip()}

    def _extract_inline_abstract(self, text: str, sections: dict):
        """
        Detect IEEE-style inline abstract:
        'Abstract—This paper...' or 'abstract This paper...'
        Also handles Spanish 'Resumen—' style.
        Works regardless of case, italic markers, or em-dash style.
        """
        if "abstract" in sections:
            return

        # More lenient stop markers — only hard section headers (not keywords inline)
        _STOP = (
            r"(?:"
            r"(?:\n\s*)?(?:Index\s+Terms|Keywords?|Key\s+words|Palabras\s+clave)\s*[—–\-:]"
            r"|\n\s*(?:I\.?\s+|1\.?\s+)(?:INTRODUCTION|Introducci[oó]n)"
            r"|\n\s*[A-Z]+\s*(?:\n|$)"  # All-caps header on own line
            r")"
        )

        patterns = [
            # IEEE dash style: Abstract— or Resumen— (very greedy, max 5000)
            rf"(?:Abstract|Resumen)\s*[—–\-:]\s*(.{{50,5000}}?){_STOP}",
            # Abstract followed by newline then body text
            rf"[Aa]bstract\s*[—–\-\.]?\s*(.{{50,4000}}?){_STOP}",
            # ABSTRACT all caps
            rf"ABSTRACT\s*[—–\-\.]?\s*(.{{50,4000}}?){_STOP}",
            # RESUMEN all caps (Spanish)
            rf"RESUMEN\s*[—–\-\.]?\s*(.{{50,4000}}?){_STOP}",
        ]

        for pat in patterns:
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if m:
                abstract_text = m.group(1).strip()
                # Remove trailing author/submission metadata
                abstract_text = re.sub(
                    r'\s*(?:--\s*Manuscript|Manuscript\s+Number|Number:).*$',
                    '', abstract_text, flags=re.IGNORECASE | re.DOTALL
                )
                if abstract_text and len(abstract_text) > 50:
                    sections["abstract"] = abstract_text
                    logger.info("[Parser] Inline abstract detected")
                    return

        # Fallback: first large paragraph before Introduction (EN or ES, Roman or numbered)
        intro_match = re.search(
            r"\b(?:I\.?\s+INTRODUCTION|1\.?\s+Introducci[oó]n|1\.?\s+INTRODUCTION)\b",
            text, re.IGNORECASE
        )
        if intro_match:
            before = text[:intro_match.start()]
            paragraphs = [p.strip() for p in before.split("\n\n") if len(p.strip()) > 150]
            if paragraphs:
                sections["abstract"] = paragraphs[-1]
                logger.info("[Parser] Abstract inferred from pre-introduction content")

    def _infer_title(self, text: str, sections: dict):
        """Infer title from the first substantial lines when absent."""
        if sections.get("title"):
            return
        lines = []
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                continue
            # Stop at structural markers
            if re.match(r"^(abstract|index terms|keywords|resumen|palabras clave)\b", s, re.IGNORECASE):
                break
            if re.match(r"^(I|II|III|IV|V|VI|VII)\.?\s+", s, re.IGNORECASE):
                break
            # Skip metadata lines (Manuscript Number, DOI, etc.)
            if re.match(r"^(?:Manuscript|Number:|DOI|doi|authors?|author|received|revised)", s, re.IGNORECASE):
                continue
            if len(s) < 10:  # Skip very short lines
                continue
            # Allow titles up to 60 words (increased from 25)
            if len(s.split()) <= 60:
                lines.append(s)
            # Allow up to 5 lines for very long titles (increased from 3)
            if len(lines) == 5:
                break
        if lines:
            title = " ".join(lines).strip()
            # Remove trailing metadata like "-- Manuscript Draft"
            title = re.sub(r'\s*--\s*Manuscript.*$', '', title, flags=re.IGNORECASE)
            sections["title"] = title

    def _extract_inline_keywords(self, text: str, sections: dict):
        """
        Detect inline keywords: 'Keywords—word1; word2' or 'Palabras clave—...'
        Picks up BOTH Spanish and English keyword lines; deduplicates.
        """
        _STOP = (
            r"(?:\n\n"
            r"|\bManuscript\s+received\b"
            r"|\n\s*I\.?\s+INTRODUCTION"
            r"|\n\s*\d+\.\s+[A-ZÁÉÍÓÚÑ]"
            r"|\n[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\n"   # standalone capitalized word = section
            r")"
        )
        found_kw_sets = []

        patterns = [
            # Increased max from 600 to 1000 for longer keyword lists
            r"\b(?:Index\s+Terms|Keywords?|Key\s+words)\s*[—–\-:]\s*(.{10,1000}?)" + _STOP,
            r"\bPalabras\s+clave\s*[—–\-:]\s*(.{10,1000}?)" + _STOP,
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                kw_text = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
                found_kw_sets.append(kw_text)

        if found_kw_sets:
            # Use English keywords if available, else Spanish, else both
            en = next((k for k in found_kw_sets if re.search(r"[a-zA-Z]{4}", k)), None)
            es = next((k for k in found_kw_sets if re.search(r"[áéíóúñÁÉÍÓÚÑ]", k)), None)
            sections["keywords"] = en or es or found_kw_sets[0]
            logger.info("[Parser] Inline keywords detected")

    def _extract_references_block(self, text: str, sections: dict):
        """
        Detect references block by [1] pattern or REFERENCES header.
        Handles both IEEE numbered refs and bibliography styles.
        """
        if "references" in sections:
            return

        # Look for REFERENCES header (all caps, IEEE style)
        ref_match = re.search(
            r"\bREFERENCES\b|\bBIBLIOGRAPHY\b|\bREFERENCIAS\b",
            text, re.IGNORECASE
        )
        if ref_match:
            sections["references"] = text[ref_match.start():ref_match.start() + 3000].strip()
            logger.info("[Parser] References block detected by header")
            return

        # Look for [1] pattern — numbered reference list
        ref_block = re.search(r"(\[1\].{20,200}\n(?:\[\d+\].{10,200}\n?){3,})", text)
        if ref_block:
            sections["references"] = ref_block.group(1).strip()
            logger.info("[Parser] References detected by [1] numbering pattern")

    def _map_canonical(self, text_lower: str) -> str:
        # Strip leading numbers like "1. " or "2.1 " before matching
        clean = re.sub(r"^\d+(?:\.\d+)?\s*\.?\s*", "", text_lower).strip()
        for kw, canonical in SECTION_KEYWORD_MAP.items():
            # Keyword must be at the START of the heading text (not a substring mid-sentence)
            if clean.startswith(kw):
                return canonical
        return None

    def _map_roman_section(self, roman: str, title_lower: str) -> str:
        title_based = self._map_canonical(title_lower)
        if title_based in ("methodology", "results", "experiments", "discussion", "conclusions", "literature"):
            return title_based
        if roman == "IV":
            if any(k in title_lower for k in ("result", "finding", "performance", "evaluation")):
                return "results"
            return "experiments"
        if roman in ROMAN_SECTION_MAP:
            return ROMAN_SECTION_MAP[roman]
        return None

    def _detect_format(self, text: str) -> str:
        if re.search(r"^(I|II|III|IV|V|VI|VII)\.?\s+[A-Z]", text, re.MULTILINE):
            return "IEEE"
        if "elsevier" in text.lower() or "sciencedirect" in text.lower():
            return "Elsevier"
        if "springer" in text.lower():
            return "Springer"
        if "\\documentclass" in text.lower() or "\\begin{" in text.lower():
            return "LaTeX"
        return "Generic"

    def _detect_statistics(self, text: str) -> bool:
        tl = text.lower()
        return any(kw.lower() in tl for kw in STATS_KEYWORDS)

    def _detect_equations(self, text: str) -> bool:
        return self._count_sequential_equations(text) > 0

    def _count_sequential_equations(self, text: str) -> int:
        main_text = re.split(r"\bREFERENCES\b|\bBIBLIOGRAPHY\b|\bBIOGRAPHY\b", text, flags=re.IGNORECASE)[0]
        numbers = [
            int(n)
            for n in re.findall(r"\(\s*(\d{1,3})\s*\)", main_text)
            if 1 <= int(n) <= 100
        ]
        if not numbers:
            return 0

        present = set(numbers)
        if 1 not in present:
            return 0

        count = 0
        for n in range(1, 101):
            if n in present:
                count = n
            else:
                break

        return count if count >= 3 else 0

    def _count_figures(self, text: str) -> int:
        # Match: Fig. N, Figure N, Figura N (English and Spanish, abbreviated and full)
        nums = set()
        for pat in [
            r"\bFig(?:ure|ura|\.)\s*([1-9]\d*)\b",
            r"\bFigure\s+([1-9]\d*)\b",
        ]:
            nums.update(re.findall(pat, text, re.IGNORECASE))
        return len(nums)

    def _count_tables(self, text: str) -> int:
        # Match: Table I/1, Tabla N, Cuadro N (Roman or Arabic numerals)
        nums = set()
        for pat in [
            r"\bTable\s+([IVX]+|[1-9]\d*)\b",
            r"\bTabla?\s+([1-9]\d*)\b",
            r"\bCuadro\s+([1-9]\d*)\b",
        ]:
            nums.update(re.findall(pat, text, re.IGNORECASE))
        return len(nums)

    @staticmethod
    def chunk_text(text: str, max_chars: int = 3000) -> list:
        if len(text) <= max_chars:
            return [text]
        chunks = []
        current = ""
        for para in text.split("\n\n"):
            if len(current) + len(para) + 2 <= max_chars:
                current += para + "\n\n"
            else:
                if current:
                    chunks.append(current.strip())
                current = para + "\n\n"
        if current:
            chunks.append(current.strip())
        return chunks if chunks else [text[:max_chars]]
