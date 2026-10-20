"""Member statement as a PDF (A4), built with reportlab.

The built-in PDF fonts have no ₹ glyph, so amounts are written as "Rs." here; the
numbers come from the same StatementView the JSON statement uses.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domain.policy import (
    DESK_TIMEZONE,
    LATE_FEE_CAP_PER_LOAN_PAISE,
    LATE_FEE_PER_DAY_PAISE,
    PAISE_PER_RUPEE,
)
from app.domain.statuses import LoanStatus
from app.services.views import LoanView, StatementView

BRAND = colors.HexColor("#0f766e")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")

LOAN_STATUS_TEXT = {
    LoanStatus.RESERVED: "Reserved",
    LoanStatus.CHECKED_OUT: "Checked out",
    LoanStatus.OVERDUE: "Overdue",
    LoanStatus.RETURNED: "Returned",
    LoanStatus.CANCELLED: "Cancelled",
    LoanStatus.EXPIRED: "Hold expired",
}


def _money(paise: int) -> str:
    rupees, remainder = divmod(paise, PAISE_PER_RUPEE)
    return f"Rs. {rupees:,}.{remainder:02d}"


def _when(moment: datetime | None) -> str:
    return moment.astimezone(DESK_TIMEZONE).strftime("%d %b %Y %H:%M") if moment else "-"


def _loan_row(view: LoanView) -> list[str]:
    loan = view.loan
    if loan.fee_charged_paise is not None:
        fee = _money(loan.fee_charged_paise)
    elif view.status == LoanStatus.OVERDUE:
        fee = f"{_money(view.accrued_fee_paise)} (accruing)"
    else:
        fee = "-"
    return [
        f"#{loan.id}",
        loan.item.name,
        LOAN_STATUS_TEXT[view.status],
        _when(loan.checked_out_at or loan.reserved_at),
        _when(loan.returned_at or loan.due_at),
        fee,
    ]


def _table(rows: list[list[str]], widths: list[float], right_align_last: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BRAND),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if right_align_last:
        style.append(("ALIGN", (-1, 0), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def render_statement_pdf(statement: StatementView, *, generated_at: datetime) -> bytes:
    styles = getSampleStyleSheet()
    title = styles["Title"].clone("StatementTitle", alignment=0, textColor=BRAND, fontSize=18)
    heading = styles["Heading3"].clone("StatementHeading", spaceBefore=10, spaceAfter=4)
    small = styles["Normal"].clone("Small", fontSize=8.5, textColor=MUTED)

    member = statement.member
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Statement - {member.name}",
        author="Rental Desk",
    )

    summary = _table(
        [
            ["Fees charged", "Paid", "Balance", "Accruing on overdue loans"],
            [
                _money(statement.total_fees_charged_paise),
                _money(statement.total_paid_paise),
                _money(statement.balance_paise),
                _money(statement.accrued_unbilled_fees_paise),
            ],
        ],
        [40 * mm] * 4,
        right_align_last=False,
    )

    loans = [["Loan", "Item", "Status", "Out / reserved", "Returned / due", "Fee"]]
    loans += [_loan_row(view) for view in statement.loans]
    payments = [["Date", "Note", "Amount"]]
    payments += [
        [_when(p.paid_at), p.note or "-", _money(p.amount_paise)] for p in statement.payments
    ]

    story = [
        Paragraph("Rental Desk - member statement", title),
        Paragraph(
            f"<b>{member.name}</b> &nbsp; {member.phone} &nbsp; member #{member.id}, "
            f"joined {member.joined_on.strftime('%d %b %Y')}",
            styles["Normal"],
        ),
        Paragraph(f"Generated {_when(generated_at)} IST", small),
        Spacer(1, 6 * mm),
        summary,
        Paragraph("Loans", heading),
        _table(loans, [14 * mm, 52 * mm, 22 * mm, 30 * mm, 30 * mm, 26 * mm])
        if statement.loans
        else Paragraph("No loans.", small),
        Paragraph("Payments", heading),
        _table(payments, [40 * mm, 90 * mm, 44 * mm])
        if statement.payments
        else Paragraph("No payments.", small),
        Spacer(1, 6 * mm),
        Paragraph(
            f"Late fees are {_money(LATE_FEE_PER_DAY_PAISE)} per started day, capped at "
            f"{_money(LATE_FEE_CAP_PER_LOAN_PAISE)} per loan and at the item's replacement "
            "value. They are added to the balance when the item is returned.",
            small,
        ),
    ]
    document.build(story)
    return buffer.getvalue()
