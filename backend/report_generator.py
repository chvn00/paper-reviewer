"""
report_generator.py
--------------------
Generates a structured PDF report from multi-agent review results.
Uses ReportLab for PDF generation — no external services.
"""

import os
import logging
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

logger = logging.getLogger(__name__)

# ─── Color palette (academic/professional) ────────────────────────────────────
DARK_NAVY   = colors.HexColor("#1a2744")
ACCENT_BLUE = colors.HexColor("#2563eb")
LIGHT_GRAY  = colors.HexColor("#f1f5f9")
MED_GRAY    = colors.HexColor("#94a3b8")
SUCCESS     = colors.HexColor("#16a34a")
WARNING     = colors.HexColor("#d97706")
DANGER      = colors.HexColor("#dc2626")
WHITE       = colors.white

DECISION_COLORS = {
    "Accept":         SUCCESS,
    "Minor Revision": colors.HexColor("#2563eb"),
    "Major Revision": WARNING,
    "Reject":         DANGER,
}


class ReportGenerator:

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.styles = self._build_styles()
        self.story = []

    def _build_styles(self):
        base = getSampleStyleSheet()
        custom = {
            "Title": ParagraphStyle("Title", fontName="Helvetica-Bold",
                                     fontSize=20, textColor=DARK_NAVY,
                                     leading=26, spaceAfter=8, alignment=TA_CENTER),
            "Subtitle": ParagraphStyle("Subtitle", fontName="Helvetica",
                                        fontSize=11, textColor=MED_GRAY,
                                        leading=16, spaceAfter=20, alignment=TA_CENTER),
            "H1": ParagraphStyle("H1", fontName="Helvetica-Bold",
                                  fontSize=14, textColor=DARK_NAVY,
                                  spaceBefore=16, spaceAfter=6),
            "H2": ParagraphStyle("H2", fontName="Helvetica-Bold",
                                  fontSize=11, textColor=ACCENT_BLUE,
                                  spaceBefore=10, spaceAfter=4),
            "Body": ParagraphStyle("Body", fontName="Helvetica",
                                    fontSize=9.5, textColor=colors.HexColor("#1e293b"),
                                    spaceAfter=6, leading=14, alignment=TA_JUSTIFY),
            "Bullet": ParagraphStyle("Bullet", fontName="Helvetica",
                                      fontSize=9, textColor=colors.HexColor("#334155"),
                                      leftIndent=14, spaceAfter=3, leading=13),
            "Badge": ParagraphStyle("Badge", fontName="Helvetica-Bold",
                                     fontSize=13, textColor=WHITE,
                                     alignment=TA_CENTER),
            "Small": ParagraphStyle("Small", fontName="Helvetica",
                                     fontSize=8, textColor=MED_GRAY,
                                     spaceAfter=4, alignment=TA_CENTER),
            "Warning": ParagraphStyle("Warning", fontName="Helvetica-Oblique",
                                       fontSize=8.5, textColor=WARNING,
                                       spaceAfter=6),
        }
        return custom

    def generate(self, review_data: dict, filename_original: str) -> str:
        """Generate PDF report. Returns path to generated file."""
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        self._add_header(filename_original, review_data)
        self._add_ai_warning()
        self._add_metadata_section(review_data)
        self._add_decision_banner(review_data)
        self._add_score_table(review_data)
        self._add_agent_reviews(review_data)
        self._add_major_comments(review_data)
        self._add_minor_comments(review_data)
        self._add_recommendations(review_data)
        self._add_footer_disclaimer()

        doc.build(self.story)
        logger.info(f"[ReportGenerator] PDF saved: {self.output_path}")
        return self.output_path

    # ─── Sections ─────────────────────────────────────────────────────────────

    def _add_header(self, filename: str, data: dict):
        self.story.append(Spacer(1, 0.5*cm))
        self.story.append(Paragraph("🧠 CHVN Paper Reviewer", ParagraphStyle(
            "AppName", fontName="Helvetica-Bold", fontSize=11,
            textColor=ACCENT_BLUE, alignment=TA_CENTER, spaceAfter=4,
        )))
        self.story.append(Paragraph("Multi-Agent Scientific Paper Review", self.styles["Title"]))
        model_used = data.get("model_used") or "local model"
        self.story.append(Paragraph(
            f"{model_used} · {datetime.now().strftime('%B %d, %Y %H:%M')}",
            self.styles["Subtitle"]
        ))
        self.story.append(HRFlowable(width="100%", thickness=2, color=ACCENT_BLUE))
        self.story.append(Spacer(1, 0.3*cm))

        meta = data.get("metadata", {})
        meta_review = data.get("meta_review", {})
        publisher  = meta_review.get("publisher", "")
        paper_type = meta_review.get("paper_type", "")
        cell_style = ParagraphStyle(
            "InfoCell", fontName="Helvetica", fontSize=9,
            textColor=colors.HexColor("#1e293b"), leading=13,
            wordWrap="CJK",
        )
        label_style = ParagraphStyle(
            "InfoLabel", fontName="Helvetica-Bold", fontSize=9,
            textColor=DARK_NAVY, leading=13,
        )
        sections_text = ", ".join(meta.get("sections_found", [])) or "N/A"
        info_data = [
            [Paragraph("File", label_style),              Paragraph(filename, cell_style)],
            [Paragraph("Words", label_style),             Paragraph(f"{meta.get('word_count', 'N/A'):,}", cell_style)],
            [Paragraph("Sections Detected", label_style), Paragraph(sections_text, cell_style)],
            [Paragraph("Review Mode", label_style),       Paragraph(data.get("mode", "fast").upper(), cell_style)],
            [Paragraph("Model", label_style),             Paragraph(model_used, cell_style)],
        ]
        if publisher and publisher != "general":
            info_data.append([Paragraph("Target Publisher", label_style), Paragraph(publisher.upper(), cell_style)])
        if paper_type and paper_type != "full_article":
            info_data.append([Paragraph("Paper Type", label_style), Paragraph(paper_type.replace("_", " ").title(), cell_style)])
        t = Table(info_data, colWidths=[4*cm, 13*cm])
        t.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [LIGHT_GRAY, WHITE]),
            ("GRID",      (0,0), (-1,-1), 0.5, MED_GRAY),
            ("PADDING",   (0,0), (-1,-1), 5),
            ("VALIGN",    (0,0), (-1,-1), "TOP"),
        ]))
        self.story.append(t)
        self.story.append(Spacer(1, 0.5*cm))

    def _add_ai_warning(self):
        warning_text = (
            "⚠ AI-ASSISTED REVIEW NOTICE: This report was generated by CHVN Paper Reviewer, "
            "an AI-powered multi-agent system running locally. "
            "It is intended as a supplementary tool to assist human peer reviewers. "
            "All findings must be validated by a qualified domain expert before "
            "editorial decisions are made. The AI may miss context-specific nuances and should not be "
            "used as the sole basis for acceptance or rejection."
        )
        self.story.append(Paragraph(warning_text, self.styles["Warning"]))
        self.story.append(HRFlowable(width="100%", thickness=0.5, color=MED_GRAY))
        self.story.append(Spacer(1, 0.3*cm))

    def _add_metadata_section(self, data: dict):
        meta = data.get("metadata", {})
        warnings = data.get("warnings", [])
        if warnings:
            self.story.append(Paragraph("Parser Warnings", self.styles["H2"]))
            for w in warnings:
                self.story.append(Paragraph(f"• {w}", self.styles["Bullet"]))
            self.story.append(Spacer(1, 0.2*cm))

    def _add_decision_banner(self, data: dict):
        meta_result = data.get("meta_review", {})
        decision = meta_result.get("editorial_decision", "N/A")
        score = meta_result.get("final_weighted_score", 0)
        confidence = meta_result.get("overall_confidence", 0)
        color = DECISION_COLORS.get(decision, MED_GRAY)

        self.story.append(Paragraph("Editorial Decision", self.styles["H1"]))

        banner_data = [[
            Paragraph(f"<b>{decision.upper()}</b>", ParagraphStyle(
                "D", fontName="Helvetica-Bold", fontSize=18,
                textColor=WHITE, alignment=TA_CENTER
            )),
            Paragraph(
                f"<b>Weighted Score: {score:.1f} / 5.0</b><br/>Confidence: {confidence:.0%}",
                ParagraphStyle("S", fontName="Helvetica", fontSize=11,
                               textColor=WHITE, alignment=TA_CENTER)
            )
        ]]
        t = Table(banner_data, colWidths=[8.5*cm, 8.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), color),
            ("PADDING",    (0,0), (-1,-1), 14),
            ("ALIGN",      (0,0), (-1,-1), "CENTER"),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ROUNDEDCORNERS", [6]),
        ]))
        self.story.append(t)
        self.story.append(Spacer(1, 0.5*cm))

        # LLM synthesis if available
        synthesis = meta_result.get("llm_synthesis", {})
        if synthesis.get("executive_summary"):
            self.story.append(Paragraph("Executive Summary", self.styles["H2"]))
            self.story.append(Paragraph(synthesis["executive_summary"], self.styles["Body"]))
        if synthesis.get("decision_rationale"):
            self.story.append(Paragraph("Decision Rationale", self.styles["H2"]))
            self.story.append(Paragraph(synthesis["decision_rationale"], self.styles["Body"]))
        self.story.append(Spacer(1, 0.3*cm))

    def _add_score_table(self, data: dict):
        meta_result = data.get("meta_review", {})
        score_table = meta_result.get("score_table", {})
        if not score_table:
            return

        self.story.append(Paragraph("Evaluation Score Table", self.styles["H1"]))
        self.story.append(Paragraph(
            "Scale: 0 = Not evaluable | 1 = Very weak | 2 = Weak | 3 = Acceptable | 4 = Good | 5 = Excellent",
            self.styles["Small"]
        ))
        self.story.append(Spacer(1, 0.2*cm))

        header = [
            Paragraph("<b>Criterion</b>", ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE)),
            Paragraph("<b>Score</b>",     ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, alignment=TA_CENTER)),
            Paragraph("<b>Rating</b>",    ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, alignment=TA_CENTER)),
            Paragraph("<b>Visual</b>",    ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE, alignment=TA_CENTER)),
        ]

        def score_to_label(s):
            if s == 0:   return "N/A"
            if s < 2:    return "Very Weak"
            if s < 3:    return "Weak"
            if s < 3.5:  return "Acceptable"
            if s < 4.5:  return "Good"
            return "Excellent"

        def score_to_bar(s):
            filled = round(s)
            return "■" * filled + "□" * (5 - filled)

        rows = [header]
        row_colors = []
        for i, (criterion, score) in enumerate(score_table.items()):
            s = float(score)
            skipped = s == 0
            label = "Skipped" if skipped else score_to_label(s)
            bar   = "—" if skipped else score_to_bar(s)
            display = "—" if skipped else f"{s:.1f}"
            row_colors.append(LIGHT_GRAY if i % 2 == 0 else WHITE)
            rows.append([
                Paragraph(criterion, ParagraphStyle("TC", fontName="Helvetica", fontSize=9)),
                Paragraph(display,   ParagraphStyle("TC", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER)),
                Paragraph(label,     ParagraphStyle("TC", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
                Paragraph(bar,       ParagraphStyle("TC", fontName="Courier", fontSize=9, alignment=TA_CENTER)),
            ])

        t = Table(rows, colWidths=[8*cm, 2*cm, 3*cm, 4*cm])
        style = [
            ("BACKGROUND", (0,0), (-1,0), DARK_NAVY),
            ("GRID",       (0,0), (-1,-1), 0.5, MED_GRAY),
            ("PADDING",    (0,0), (-1,-1), 6),
        ]
        for i, bg in enumerate(row_colors, start=1):
            style.append(("BACKGROUND", (0,i), (-1,i), bg))
        t.setStyle(TableStyle(style))
        self.story.append(t)
        self.story.append(Spacer(1, 0.5*cm))

    def _add_agent_reviews(self, data: dict):
        agent_results = data.get("agent_results", [])
        if not agent_results:
            return

        self.story.append(PageBreak())
        self.story.append(Paragraph("Detailed Agent Reviews", self.styles["H1"]))

        for result in agent_results:
            if result.get("agent_name") == "MetaReviewer":
                continue

            name = result.get("agent_name", "Unknown")
            scope = result.get("scope", "")
            score = float(result.get("score", 0))
            skipped = result.get("skipped", False)

            block = []
            block.append(HRFlowable(width="100%", thickness=1, color=LIGHT_GRAY))
            block.append(Paragraph(f"{name}", self.styles["H2"]))
            block.append(Paragraph(f"<i>{scope}</i>", ParagraphStyle(
                "SI", fontName="Helvetica-Oblique", fontSize=8.5, textColor=MED_GRAY, spaceAfter=4
            )))

            if skipped:
                block.append(Paragraph(
                    f"⊘ Skipped: {result.get('skip_reason', '')}",
                    ParagraphStyle("SK", fontName="Helvetica-Oblique", fontSize=9, textColor=MED_GRAY)
                ))
            else:
                block.append(Paragraph(f"Score: <b>{score:.1f} / 5.0</b> | Confidence: {result.get('confidence', 0):.0%}",
                    ParagraphStyle("SC", fontName="Helvetica", fontSize=9, textColor=ACCENT_BLUE, spaceAfter=4)
                ))

                for section, items in [
                    ("Strengths", result.get("strengths", [])),
                    ("Weaknesses", result.get("weaknesses", [])),
                    ("Major Comments", result.get("major_comments", [])),
                    ("Minor Comments", result.get("minor_comments", [])),
                    ("Recommendations", result.get("specific_recommendations", [])),
                ]:
                    if items:
                        block.append(Paragraph(f"<b>{section}:</b>", ParagraphStyle(
                            "SL", fontName="Helvetica-Bold", fontSize=9, textColor=DARK_NAVY, spaceAfter=2
                        )))
                        for item in items:
                            block.append(Paragraph(f"• {item}", self.styles["Bullet"]))

            block.append(Spacer(1, 0.3*cm))
            self.story.extend(block)

    def _add_major_comments(self, data: dict):
        meta = data.get("meta_review", {})
        comments = meta.get("major_comments", [])
        if not comments:
            return
        self.story.append(PageBreak())
        self.story.append(Paragraph("Consolidated Major Comments", self.styles["H1"]))
        self.story.append(Paragraph(
            "These issues must be addressed before the manuscript can be accepted.",
            self.styles["Body"]
        ))
        for i, c in enumerate(comments, 1):
            self.story.append(Paragraph(f"<b>[{i}]</b> {c}", self.styles["Bullet"]))
        self.story.append(Spacer(1, 0.3*cm))

    def _add_minor_comments(self, data: dict):
        meta = data.get("meta_review", {})
        comments = meta.get("minor_comments", [])
        if not comments:
            return
        self.story.append(Paragraph("Consolidated Minor Comments", self.styles["H1"]))
        self.story.append(Paragraph(
            "These are suggestions that would improve the manuscript quality.",
            self.styles["Body"]
        ))
        for i, c in enumerate(comments, 1):
            self.story.append(Paragraph(f"<b>[{i}]</b> {c}", self.styles["Bullet"]))
        self.story.append(Spacer(1, 0.3*cm))

    def _add_recommendations(self, data: dict):
        meta = data.get("meta_review", {})
        recs = meta.get("specific_recommendations", [])
        if not recs:
            return
        self.story.append(Paragraph("Specific Improvement Recommendations", self.styles["H1"]))
        for i, r in enumerate(recs, 1):
            self.story.append(Paragraph(f"{i}. {r}", self.styles["Bullet"]))
        self.story.append(Spacer(1, 0.3*cm))

    def _add_footer_disclaimer(self):
        self.story.append(Spacer(1, 1*cm))
        self.story.append(HRFlowable(width="100%", thickness=0.5, color=MED_GRAY))
        self.story.append(Spacer(1, 0.2*cm))
        self.story.append(Paragraph(
            "Generated by CHVN Paper Reviewer · Multi-Agent AI Review System · "
            "All processing runs locally via Ollama — no manuscript content is transmitted to external servers. "
            "Rubrics based on Elsevier, IEEE, Emerald, SAGE, MDPI, and Taylor &amp; Francis Q1 peer review standards. "
            "This document does not constitute an official editorial decision.",
            self.styles["Small"]
        ))
