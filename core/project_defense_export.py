from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate


CHEAT_SHEET_SECTIONS = (
    ("elevator_pitch", "30-Second Elevator Pitch"),
    ("tradeoffs_and_stack", "Key Trade-offs & Why This Stack"),
    ("scaling_bottlenecks", "Scaling & Bottleneck Answers"),
    ("security_edge_cases", "Security & Edge-Case Defenses")
)


def normalize_cheat_sheet(value):
    if not isinstance(value, dict):
        raise ValueError("Provide a valid defense cheat sheet.")

    normalized = {}
    for key, _ in CHEAT_SHEET_SECTIONS:
        content = value.get(key)
        if not isinstance(content, str) or not content.strip() or len(content) > 8000:
            raise ValueError("The defense cheat sheet has an invalid or oversized section.")
        normalized[key] = content.strip()

    gotchas = value.get("gotcha_follow_ups")
    if not isinstance(gotchas, list) or len(gotchas) != 3:
        raise ValueError("The cheat sheet must contain three follow-up questions.")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in gotchas):
        raise ValueError("The cheat sheet contains an invalid follow-up question.")
    normalized["gotcha_follow_ups"] = [item.strip() for item in gotchas]
    return normalized


def create_cheat_sheet_pdf(cheat_sheet, project_name):
    cheat_sheet = normalize_cheat_sheet(cheat_sheet)
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DefenseTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=25,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#18315f"),
        spaceAfter=5
    )
    subtitle_style = ParagraphStyle(
        "DefenseSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64718b"),
        spaceAfter=16
    )
    heading_style = ParagraphStyle(
        "DefenseSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#3459a8"),
        spaceBefore=11,
        spaceAfter=5
    )
    body_style = ParagraphStyle(
        "DefenseBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#26344d"),
        spaceAfter=5
    )

    story = [
        Paragraph("Project Defense Cheat Sheet", title_style),
        Paragraph(escape(project_name), subtitle_style)
    ]
    for key, title in CHEAT_SHEET_SECTIONS:
        story.append(Paragraph(escape(title), heading_style))
        story.append(Paragraph(escape(cheat_sheet[key]).replace("\n", "<br/>"), body_style))

    story.append(Paragraph("Top 3 Gotcha Follow-Ups to Prepare For", heading_style))
    for question in cheat_sheet["gotcha_follow_ups"]:
        story.append(Paragraph(escape(question), body_style, bulletText="-"))

    SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=f"Project Defense Cheat Sheet - {project_name[:120]}"
    ).build(story)
    output.seek(0)
    return output
