from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


FONT_NAME = "NotoSansTC"
FONT_PATH = Path(__file__).resolve().parent / "fonts" / "NotoSansTC.ttf"
INK = colors.HexColor("#17372D")
MUTED = colors.HexColor("#687870")
GREEN = colors.HexColor("#2F6B58")
PALE_GREEN = colors.HexColor("#EAF2ED")
GOLD = colors.HexColor("#B58A3C")
LINE = colors.HexColor("#DDE5E0")
PAPER = colors.HexColor("#F7F9F7")

ITEM_TYPE_LABELS = {
    "hotel": "飯店",
    "flight": "航班",
    "transfer": "接送",
    "activity": "活動",
    "dining": "餐飲",
    "other": "其他",
}
STATUS_LABELS = {
    "draft": "草稿",
    "pending_approval": "待核准",
    "approved": "已核准",
    "rejected": "已退回",
    "cancelled": "已取消",
}


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value))


def _date(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y/%m/%d")
    return str(value)[:10].replace("-", "/")


def _money(value: Any, currency: str) -> str:
    amount = Decimal(str(value or 0))
    return f"{currency} {amount:,.0f}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "Brand", parent=base["Normal"], fontName=FONT_NAME, fontSize=9,
            textColor=GOLD, leading=12, spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName=FONT_NAME, fontSize=24,
            textColor=INK, leading=29, spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName=FONT_NAME, fontSize=10,
            textColor=MUTED, leading=17,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName=FONT_NAME, fontSize=13,
            textColor=INK, leading=17, spaceBefore=6, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName=FONT_NAME, fontSize=9,
            textColor=INK, leading=15,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"], fontName=FONT_NAME, fontSize=7.5,
            textColor=MUTED, leading=12,
        ),
        "right": ParagraphStyle(
            "Right", parent=base["Normal"], fontName=FONT_NAME, fontSize=9,
            textColor=INK, leading=14, alignment=TA_RIGHT,
        ),
        "right_total": ParagraphStyle(
            "RightTotal", parent=base["Normal"], fontName=FONT_NAME, fontSize=14,
            textColor=GREEN, leading=18, alignment=TA_RIGHT,
        ),
    }


def _page_frame(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 16 * mm, width - 20 * mm, 16 * mm)
    canvas.setFont(FONT_NAME, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 10.5 * mm, "VOYAGEOPS AI · TRAVEL OPERATIONS")
    canvas.drawRightString(width - 20 * mm, 10.5 * mm, f"第 {document.page} 頁")
    canvas.restoreState()


def build_quote_proposal_pdf(context: dict[str, Any]) -> bytes:
    """Render a quote snapshot into a client-facing Traditional Chinese PDF."""
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=23 * mm,
        title=f"VoyageOps {context['quote_number']}",
        author="VoyageOps AI",
        subject="旅遊提案與報價",
    )

    currency = context.get("currency") or "TWD"
    status = STATUS_LABELS.get(context.get("status"), context.get("status") or "—")
    story = [
        Paragraph("VOYAGEOPS AI · TRAVEL PROPOSAL", styles["brand"]),
        Paragraph("旅遊提案與報價", styles["title"]),
        Paragraph(
            f"報價編號 {_text(context.get('quote_number'))}　｜　版本 {context.get('version', 1)}　｜　{_text(status)}",
            styles["subtitle"],
        ),
        Spacer(1, 6 * mm),
    ]

    overview = [
        [Paragraph("旅客", styles["small"]), Paragraph("目的地", styles["small"]), Paragraph("旅遊日期", styles["small"]), Paragraph("人數", styles["small"])],
        [
            Paragraph(_text(context.get("member_name")), styles["body"]),
            Paragraph(_text(context.get("destination")), styles["body"]),
            Paragraph(f"{_date(context.get('start_date'))} – {_date(context.get('end_date'))}", styles["body"]),
            Paragraph(f"{context.get('party_size') or '—'} 位", styles["body"]),
        ],
    ]
    overview_table = Table(overview, colWidths=[42 * mm, 43 * mm, 55 * mm, 28 * mm])
    overview_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.7, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([
        overview_table,
        Spacer(1, 3 * mm),
        Paragraph(_text(context.get("trip_name"), "行程規劃"), styles["section"]),
        Paragraph(
            f"本文件依報價 {_text(context.get('quote_number'))} 的不可變快照產生；後續行程調整將建立新版本，不會覆寫本報價。",
            styles["body"],
        ),
        Spacer(1, 2 * mm),
        Paragraph("行程與費用明細", styles["section"]),
    ])

    item_rows = [[
        Paragraph("項目", styles["small"]),
        Paragraph("類型", styles["small"]),
        Paragraph("單價", styles["small"]),
        Paragraph("數量", styles["small"]),
        Paragraph("小計", styles["small"]),
    ]]
    for item in context.get("items", []):
        item_rows.append([
            Paragraph(_text(item.get("title")), styles["body"]),
            Paragraph(_text(ITEM_TYPE_LABELS.get(item.get("item_type"), item.get("item_type"))), styles["body"]),
            Paragraph(_money(item.get("unit_price"), currency), styles["right"]),
            Paragraph(str(item.get("quantity") or 1), styles["right"]),
            Paragraph(_money(item.get("line_total"), currency), styles["right"]),
        ])
    item_table = Table(item_rows, repeatRows=1, colWidths=[69 * mm, 24 * mm, 30 * mm, 15 * mm, 30 * mm])
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([item_table, Spacer(1, 3 * mm)])

    totals = Table([
        [Paragraph("未稅小計", styles["body"]), Paragraph(_money(context.get("subtotal"), currency), styles["right"])],
        [Paragraph("稅額", styles["body"]), Paragraph(_money(context.get("tax"), currency), styles["right"])],
        [Paragraph("含稅總額", styles["section"]), Paragraph(_money(context.get("total"), currency), styles["right_total"])],
    ], colWidths=[44 * mm, 44 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("LINEABOVE", (0, 2), (-1, 2), 1, GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([totals, Spacer(1, 2 * mm)])

    notes = _text(context.get("notes"), "此版本未附加其他備註。")
    validity = _date(context.get("expires_at"))
    disclaimer = KeepTogether([
        Paragraph("報價說明", styles["section"]),
        Paragraph(f"有效期限：{validity}<br/>{notes}", styles["body"]),
        Spacer(1, 2 * mm),
        Table([[Paragraph(
            "此為作品集示範文件。AI 產生的行程草稿須經人工審核；價格與供應商庫存並非即時資料。MockPay 僅模擬付款流程，不會進行真實扣款。",
            styles["small"],
        )]], colWidths=[168 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
            ("BOX", (0, 0), (-1, -1), 0.6, GREEN),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])),
    ])
    story.append(disclaimer)

    document.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
    return buffer.getvalue()
