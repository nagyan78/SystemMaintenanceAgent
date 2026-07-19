import os
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_FONT_NAME = "TaxonomyReportChinese"


class PdfReportService:
    """Render the persisted Markdown report as a readable, paginated PDF."""

    def render(self, markdown: str, output_path: Path, *, title: str) -> Path:
        font_name = _register_chinese_font()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        page_size = landscape(A4)
        document = SimpleDocTemplate(
            str(output_path),
            pagesize=page_size,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=16 * mm,
            bottomMargin=15 * mm,
            title=title,
            author="产品标准体系维护智能体",
            subject="产品标准体系诊断与维护报告",
        )
        styles = _build_styles(font_name)
        story = _markdown_story(markdown, styles, document.width)
        document.build(
            story,
            onFirstPage=lambda canvas, doc: _draw_page(canvas, doc, font_name, title),
            onLaterPages=lambda canvas, doc: _draw_page(canvas, doc, font_name, title),
        )
        return output_path


def _register_chinese_font() -> str:
    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FONT_NAME
    configured = os.getenv("REPORT_PDF_FONT_PATH")
    windows_dir = Path(os.getenv("WINDIR", r"C:\Windows"))
    candidates = [
        Path(configured) if configured else None,
        windows_dir / "Fonts" / "msyh.ttc",
        windows_dir / "Fonts" / "simhei.ttf",
        windows_dir / "Fonts" / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    font_path = next((path for path in candidates if path and path.is_file()), None)
    if font_path is None:
        raise RuntimeError(
            "未找到可用于 PDF 的中文字体；请通过 REPORT_PDF_FONT_PATH 配置 TTF/TTC 字体文件。"
        )
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path), subfontIndex=0))
    return _FONT_NAME


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    common = {
        "fontName": font_name,
        "wordWrap": "CJK",
    }
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], fontSize=19, leading=25,
            alignment=TA_CENTER, spaceAfter=8 * mm,
            textColor=colors.HexColor("#1F2937"), **common,
        ),
        "h1": ParagraphStyle(
            "ReportH1", parent=base["Heading1"], fontSize=15, leading=20,
            textColor=colors.HexColor("#0F4C81"), spaceBefore=5 * mm, spaceAfter=3 * mm, **common,
        ),
        "h2": ParagraphStyle(
            "ReportH2", parent=base["Heading2"], fontSize=12, leading=17,
            textColor=colors.HexColor("#155E75"), spaceBefore=4 * mm, spaceAfter=3 * mm, **common,
        ),
        "h3": ParagraphStyle(
            "ReportH3", parent=base["Heading3"], fontSize=10.5, leading=15,
            textColor=colors.HexColor("#334155"), spaceBefore=3 * mm, spaceAfter=3 * mm, **common,
        ),
        "body": ParagraphStyle(
            "ReportBody", parent=base["BodyText"], fontSize=9, leading=14,
            textColor=colors.HexColor("#1F2937"), spaceAfter=3 * mm, **common,
        ),
        "bullet": ParagraphStyle(
            "ReportBullet", parent=base["BodyText"], fontSize=9, leading=14,
            leftIndent=5 * mm, firstLineIndent=-3 * mm, bulletIndent=1 * mm,
            textColor=colors.HexColor("#1F2937"), spaceAfter=3 * mm, **common,
        ),
        "quote": ParagraphStyle(
            "ReportQuote", parent=base["BodyText"], fontSize=8.5, leading=13,
            leftIndent=5 * mm, rightIndent=5 * mm, borderColor=colors.HexColor("#94A3B8"),
            borderWidth=0.8, borderPadding=3 * mm, backColor=colors.HexColor("#F8FAFC"),
            textColor=colors.HexColor("#1F2937"), spaceAfter=3 * mm, **common,
        ),
        "table": ParagraphStyle(
            "ReportTable", parent=base["BodyText"], fontSize=6.8, leading=9,
            textColor=colors.HexColor("#1F2937"), spaceAfter=0, **common,
        ),
    }


def _markdown_story(markdown: str, styles: dict[str, ParagraphStyle], width: float) -> list:
    story: list = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0
    first_heading = True
    while index < len(lines):
        raw = lines[index].strip()
        if not raw:
            index += 1
            continue
        if raw.startswith("|") and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            table_lines = [raw]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.extend(_render_table(table_lines, styles["table"], width))
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", raw)
        if heading:
            level = len(heading.group(1))
            text = _inline_markup(heading.group(2))
            style_name = "title" if first_heading and level == 1 else f"h{min(level, 3)}"
            story.append(Paragraph(text, styles[style_name]))
            first_heading = False
        elif raw in {"---", "***"}:
            story.append(Spacer(1, 2 * mm))
        elif raw.startswith(">"):
            story.append(Paragraph(_inline_markup(raw.lstrip("> ")), styles["quote"]))
        elif re.match(r"^[-*+]\s+", raw):
            story.append(Paragraph(_inline_markup(re.sub(r"^[-*+]\s+", "", raw)), styles["bullet"], bulletText="•"))
        elif re.match(r"^\d+[.)]\s+", raw):
            marker, text = raw.split(maxsplit=1)
            story.append(Paragraph(_inline_markup(text), styles["bullet"], bulletText=marker))
        elif raw == "<!-- pagebreak -->":
            story.append(PageBreak())
        else:
            story.append(Paragraph(_inline_markup(raw), styles["body"]))
        index += 1
    return story or [Paragraph("当前报告没有可展示内容。", styles["body"])]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_table_row(line: str) -> list[str]:
    placeholder = "\u0000PIPE\u0000"
    protected = line.strip().strip("|").replace(r"\|", placeholder)
    return [cell.strip().replace(placeholder, "|") for cell in protected.split("|")]


def _render_table(lines: list[str], style: ParagraphStyle, width: float) -> list:
    rows = [_split_table_row(line) for line in lines]
    column_count = max((len(row) for row in rows), default=1)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]
    cells = [[Paragraph(_inline_markup(value), style) for value in row] for row in normalized]
    table = Table(cells, colWidths=[width / column_count] * column_count, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), style.fontName),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F3557")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    return [table, Spacer(1, 3 * mm)]


def _inline_markup(value: str) -> str:
    text = escape(value.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font color='#7C2D12'>\1</font>", text)
    return text


def _draw_page(canvas, document, font_name: str, title: str) -> None:
    canvas.saveState()
    page_width, _ = landscape(A4)
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(document.leftMargin, 11 * mm, page_width - document.rightMargin, 11 * mm)
    canvas.setFont(font_name, 7.5)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(document.leftMargin, 7 * mm, title[:48])
    canvas.drawRightString(page_width - document.rightMargin, 7 * mm, f"第 {document.page} 页")
    canvas.restoreState()
