from html import escape
from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " | ".join(str(item).strip() for item in value if item is not None).strip()
    return ""


def _text_list(value):
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _resume_blocks(resume):
    header = resume.get("header") if isinstance(resume.get("header"), dict) else {}
    name = _text(header.get("name"))
    if name:
        yield "title", name

    contact = _text(header.get("contact"))
    if contact:
        yield "contact", contact

    headline = _text(header.get("headline"))
    if headline:
        yield "subheading", headline

    summary = _text(resume.get("summary"))
    if summary:
        yield "heading", "Professional Summary"
        yield "body", summary

    skills = resume.get("skills") if isinstance(resume.get("skills"), list) else []
    if skills:
        yield "heading", "Skills"
        for group in skills:
            if not isinstance(group, dict):
                continue
            category = _text(group.get("category"))
            items = _text_list(group.get("items"))
            if items:
                yield "body", f"{category}: {', '.join(items)}" if category else ", ".join(items)

    for key, title, labels, list_field in (
        ("experience", "Experience", ("title", "company", "location", "dates"), "bullets"),
        ("projects", "Projects", ("name", "technologies"), "bullets"),
        ("education", "Education", ("degree", "institution", "location", "dates"), "details")
    ):
        records = resume.get(key) if isinstance(resume.get(key), list) else []
        if not records:
            continue
        yield "heading", title
        for record in records:
            if not isinstance(record, dict):
                continue
            heading = " | ".join(
                value for label in labels if (value := _text(record.get(label)))
            )
            if heading:
                yield "entry", heading
            for detail in _text_list(record.get(list_field)):
                yield "bullet", detail


def create_docx_resume(resume):
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    normal_style = document.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10)

    for kind, text in _resume_blocks(resume):
        if kind == "title":
            document.add_heading(text, level=0)
        elif kind == "heading":
            document.add_heading(text, level=1)
        elif kind == "bullet":
            document.add_paragraph(text, style="List Bullet")
        else:
            paragraph = document.add_paragraph()
            run = paragraph.add_run(text)
            if kind == "entry":
                run.bold = True
            elif kind == "subheading":
                run.italic = True

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output


def create_pdf_resume(resume):
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResumeTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=19, leading=23, alignment=TA_LEFT, textColor=colors.HexColor("#14213d"),
        spaceAfter=3
    )
    contact_style = ParagraphStyle(
        "ResumeContact", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=colors.HexColor("#46536e"), spaceAfter=3
    )
    heading_style = ParagraphStyle(
        "ResumeSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=colors.HexColor("#244fbb"),
        spaceBefore=10, spaceAfter=4
    )
    body_style = ParagraphStyle(
        "ResumeBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9, leading=12, textColor=colors.HexColor("#202b42"), spaceAfter=3
    )
    entry_style = ParagraphStyle(
        "ResumeEntry", parent=body_style, fontName="Helvetica-Bold", spaceBefore=3
    )

    story = []
    for kind, text in _resume_blocks(resume):
        safe_text = escape(text)
        if kind == "title":
            story.append(Paragraph(safe_text, title_style))
        elif kind == "contact":
            story.append(Paragraph(safe_text, contact_style))
        elif kind == "heading":
            story.append(Paragraph(safe_text.upper(), heading_style))
        elif kind == "entry":
            story.append(Paragraph(safe_text, entry_style))
        elif kind == "bullet":
            story.append(Paragraph(safe_text, body_style, bulletText="-"))
        else:
            story.append(Paragraph(safe_text, body_style))
    story.append(Spacer(1, 4))

    SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=_text(resume.get("header", {}).get("name")) or "Tailored Resume"
    ).build(story)
    output.seek(0)
    return output
