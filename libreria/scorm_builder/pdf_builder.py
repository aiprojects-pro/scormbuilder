"""Generador de PDF descargable a partir de un tema.

Genera un PDF con el contenido del tema como apuntes de consulta:
portada, índice, contenido de cada subapartado y referencias.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER

from scorm_builder.parser import (
    CourseStructure, Topic, Subsection, Block, BlockType,
)
from scorm_builder.themes import Theme


def _block_to_paragraphs(block: Block, styles: dict) -> List:
    """Convierte un Block en uno o varios elementos de reportlab."""
    out = []
    bt = block.type
    if isinstance(bt, str):
        from scorm_builder.parser import BlockType
        bt = BlockType(bt)

    if bt == BlockType.PARAGRAPH:
        out.append(Paragraph(block.text, styles["body"]))
    elif bt == BlockType.HEADING_3:
        out.append(Paragraph(block.text, styles["h3"]))
    elif bt == BlockType.HEADING_4:
        out.append(Paragraph(block.text, styles["h4"]))
    elif bt == BlockType.LIST_BULLET:
        for it in block.items:
            out.append(Paragraph("• " + it, styles["li"]))
    elif bt == BlockType.LIST_NUMBER:
        for i, it in enumerate(block.items, 1):
            out.append(Paragraph(f"{i}. {it}", styles["li"]))
    elif bt in (BlockType.CALLOUT_KEY, BlockType.CALLOUT_ALERT, BlockType.CALLOUT_SUCCESS, BlockType.CALLOUT_WARN):
        prefix = {
            BlockType.CALLOUT_KEY: "★ ",
            BlockType.CALLOUT_ALERT: "⚠ ",
            BlockType.CALLOUT_SUCCESS: "✓ ",
            BlockType.CALLOUT_WARN: "! ",
        }[bt]
        out.append(Paragraph(prefix + "<b>" + block.text + "</b>", styles["callout"]))
    elif bt == BlockType.QUOTE:
        out.append(Paragraph("<i>" + block.text + "</i>", styles["quote"]))
    elif bt == BlockType.TABLE:
        if block.rows:
            t = Table(block.rows, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0A2540")),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#E2E8F0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#F8FAFC"), white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            out.append(t)

    return out


def _make_styles(theme: Theme):
    """Crea el conjunto de estilos del PDF basado en el theme."""
    primary_deep = HexColor(theme.primary_deep)
    primary = HexColor(theme.primary)
    ink = HexColor(theme.ink)
    ink_soft = HexColor(theme.ink_soft)
    paper_warm = HexColor(theme.paper_warm)

    base = getSampleStyleSheet()

    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontSize=22, leading=26, textColor=primary_deep,
            spaceAfter=18, fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=15, leading=18, textColor=primary,
            spaceAfter=10, spaceBefore=18, fontName="Helvetica-Bold",
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"],
            fontSize=12, leading=15, textColor=ink,
            spaceAfter=6, spaceBefore=10, fontName="Helvetica-Bold",
        ),
        "h4": ParagraphStyle(
            "h4", parent=base["Heading4"],
            fontSize=10, leading=13, textColor=primary_deep,
            spaceAfter=4, spaceBefore=8, fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=10.5, leading=15, textColor=ink_soft,
            alignment=TA_JUSTIFY, spaceAfter=8,
        ),
        "lead": ParagraphStyle(
            "lead", parent=base["Normal"],
            fontSize=11, leading=16, textColor=ink,
            alignment=TA_LEFT, leftIndent=10, fontName="Helvetica-Oblique",
            spaceAfter=12,
        ),
        "li": ParagraphStyle(
            "li", parent=base["Normal"],
            fontSize=10.5, leading=14, textColor=ink_soft,
            alignment=TA_JUSTIFY, leftIndent=15, spaceAfter=4,
        ),
        "callout": ParagraphStyle(
            "callout", parent=base["Normal"],
            fontSize=10.5, leading=14, textColor=ink,
            backColor=paper_warm, borderColor=primary, borderWidth=0,
            leftIndent=10, rightIndent=10, borderPadding=8,
            spaceAfter=10, spaceBefore=10,
        ),
        "quote": ParagraphStyle(
            "quote", parent=base["Normal"],
            fontSize=10, leading=14, textColor=ink,
            leftIndent=20, rightIndent=20, fontName="Helvetica-Oblique",
            spaceAfter=10,
        ),
    }


def _make_header_footer(course_title: str, topic_title: str, theme: Theme):
    """Genera la función de header/footer del PDF."""
    primary_deep = HexColor(theme.primary_deep)
    accent = HexColor(theme.accent)
    ink = HexColor(theme.ink)

    def draw(canvas, doc):
        canvas.saveState()
        # Cabecera
        canvas.setFillColor(primary_deep)
        canvas.rect(0, A4[1] - 1.5 * cm, A4[0], 1.5 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2 * cm, A4[1] - 1 * cm, course_title[:60])
        canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1 * cm, topic_title[:50])
        # Pie
        canvas.setFillColor(ink)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, "Apuntes del tema")
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
        canvas.restoreState()

    return draw


def build_pdf(
    topic: Topic,
    course: CourseStructure,
    theme: Theme,
    output_path: Path,
) -> Path:
    """Genera un PDF de apuntes del tema."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _make_styles(theme)

    story = []

    # Portada
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(course.metadata.title, styles["h1"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"<b>Tema {topic.number}:</b> {topic.title}", styles["h2"]))
    story.append(Spacer(1, 1 * cm))
    if topic.intro:
        story.append(Paragraph(topic.intro, styles["lead"]))
    story.append(Spacer(1, 1 * cm))
    if course.metadata.author:
        story.append(Paragraph(f"<b>Autor/entidad:</b> {course.metadata.author}", styles["body"]))
    story.append(Paragraph("Apuntes de consulta del tema. Material formativo complementario al curso e-learning.", styles["body"]))
    story.append(PageBreak())

    # Índice
    story.append(Paragraph("Índice del tema", styles["h1"]))
    for sub in topic.subsections:
        story.append(Paragraph(f"{sub.number} {sub.title}", styles["body"]))
    if topic.quiz:
        story.append(Paragraph(f"{topic.number}.{len(topic.subsections)+1} Evaluación final", styles["body"]))
    story.append(PageBreak())

    # Contenido
    for sub in topic.subsections:
        story.append(Paragraph(f"{sub.number} {sub.title}", styles["h2"]))
        for block in sub.blocks:
            elements = _block_to_paragraphs(block, styles)
            for el in elements:
                story.append(el)
        story.append(Spacer(1, 0.3 * cm))

    # Quiz al final
    if topic.quiz:
        story.append(PageBreak())
        story.append(Paragraph("Evaluación final", styles["h2"]))
        story.append(Paragraph(
            f"Total de preguntas: {len(topic.quiz)}. "
            f"Aprobado mínimo: {course.metadata.mastery}%.",
            styles["body"],
        ))
        for i, q in enumerate(topic.quiz, 1):
            story.append(Paragraph(f"<b>Pregunta {i}.</b> {q.text}", styles["body"]))
            for idx, opt in enumerate(q.options):
                letter = chr(ord("A") + idx)
                marker = "▶" if idx == q.correct_index else "○"
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;{marker} <b>{letter}.</b> {opt}", styles["li"]))
            if q.explanation:
                story.append(Paragraph(f"<i>Explicación: {q.explanation}</i>", styles["quote"]))
            story.append(Spacer(1, 0.3 * cm))

    # Construir documento
    hf = _make_header_footer(course.metadata.title, topic.title, theme)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.3 * cm, bottomMargin=2 * cm,
        title=f"{course.metadata.title} · Tema {topic.number}",
        author=course.metadata.author or "Curso e-learning",
    )
    doc.build(story, onFirstPage=hf, onLaterPages=hf)

    return output_path
