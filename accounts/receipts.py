from html import escape
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Font za ReportLab hizi zinaunga mkono majina yenye herufi zaidi ya ASCII.
_FONT_DIRECTORY = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('ReceiptSans', str(_FONT_DIRECTORY / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('ReceiptSans-Bold', str(_FONT_DIRECTORY / 'VeraBd.ttf')))


class VerificationQRCode(Flowable):
    def __init__(self, value, size=30 * mm):
        super().__init__()
        self.value = value
        self.width = size
        self.height = size

    def draw(self):
        qr = QrCodeWidget(
            self.value,
            barWidth=self.width,
            barHeight=self.height,
        )
        drawing = Drawing(self.width, self.height)
        drawing.add(qr)
        renderPDF.draw(drawing, self.canv, 0, 0)


def build_payment_receipt_pdf(*, booking, receipt_number, verification_url):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f'Payment Receipt {receipt_number}',
        author='SUA Student Housing',
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReceiptTitle',
        parent=styles['Title'],
        fontName='ReceiptSans-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#0f766e'),
        alignment=TA_LEFT,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name='ReceiptBrand',
        parent=styles['Normal'],
        fontName='ReceiptSans',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4b5563'),
    ))
    styles.add(ParagraphStyle(
        name='ReceiptLabel',
        parent=styles['Normal'],
        fontName='ReceiptSans',
        fontSize=7.5,
        textColor=colors.HexColor('#6b7280'),
        leading=10,
    ))
    styles.add(ParagraphStyle(
        name='ReceiptValue',
        parent=styles['Normal'],
        fontName='ReceiptSans',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1f2937'),
    ))
    styles.add(ParagraphStyle(
        name='ReceiptAmount',
        parent=styles['ReceiptValue'],
        fontName='ReceiptSans-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0f766e'),
    ))
    styles.add(ParagraphStyle(
        name='ReceiptBody',
        parent=styles['Normal'],
        fontName='ReceiptSans',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#4b5563'),
    ))
    styles.add(ParagraphStyle(
        name='ReceiptMeta',
        parent=styles['Normal'],
        fontName='ReceiptSans',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#4b5563'),
        alignment=TA_LEFT,
    ))

    logo_path = Path(settings.BASE_DIR) / 'static' / 'images' / 'sua-logo.png'
    logo_source = ImageReader(str(logo_path))
    logo_width, logo_height = logo_source.getSize()
    max_logo_width = 22 * mm
    max_logo_height = 22 * mm
    logo_scale = min(max_logo_width / logo_width, max_logo_height / logo_height)
    logo = Image(
        str(logo_path),
        width=logo_width * logo_scale,
        height=logo_height * logo_scale,
    )
    confirmed_at = timezone.localtime(booking.updated_at)
    brand_details = [
        Paragraph(
            'PAYMENT CONFIRMATION RECEIPT',
            styles['ReceiptTitle'],
        ),
        Paragraph('SUA Student Housing', styles['ReceiptBrand']),
    ]
    receipt_meta = [
        Paragraph(
            f'Receipt No: {escape(receipt_number)}<br/>'
            f'Confirmed: {confirmed_at.strftime("%d %b %Y, %I:%M %p")}',
            styles['ReceiptMeta'],
        ),
    ]
    header = Table(
        [[logo, brand_details, receipt_meta]],
        colWidths=[28 * mm, 88 * mm, 54 * mm],
    )
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'LEFT'),
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))

    def field(label, value):
        value_style = (
            styles['ReceiptAmount']
            if label == 'Amount paid'
            else styles['ReceiptValue']
        )
        return [
            Paragraph(escape(label.upper()), styles['ReceiptLabel']),
            Paragraph(escape(str(value or 'Not provided')), value_style),
        ]

    student_name = booking.student.get_full_name() or booking.student.username
    landlord_name = (
        booking.room.house.landlord.get_full_name()
        or booking.room.house.landlord.username
    )
    fields = [
        field('Student', student_name),
        field('Landlord', landlord_name),
        field('Property', booking.room.house.title),
        field('Room', booking.room.get_room_type_display()),
        field('Amount paid', f'TZS {booking.room.price:,}'),
        field('Payment reference', booking.payment_reference),
        field('Phone used', booking.payment_phone_number),
        field('Payment status', 'Confirmed by landlord'),
    ]
    detail_rows = []
    for row_index in range(0, len(fields), 2):
        detail_rows.append([
            item
            for entry in fields[row_index:row_index + 2]
            for item in entry
        ])
    details = Table(
        detail_rows,
        colWidths=[27 * mm, 58 * mm, 27 * mm, 58 * mm],
    )
    details.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
    ]))

    signature = Table(
        [
            [Paragraph('Landlord confirmation', styles['ReceiptLabel'])],
            [''],
            [Paragraph(escape(landlord_name), styles['ReceiptAmount'])],
            [Paragraph('Confirmed in the booking system', styles['ReceiptLabel'])],
        ],
        colWidths=[75 * mm],
        rowHeights=[7 * mm, 10 * mm, 6 * mm, 6 * mm],
    )
    signature.setStyle(TableStyle([
        ('LINEABOVE', (0, 2), (0, 2), 0.8, colors.HexColor('#374151')),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    verification_block = Table(
        [[
            VerificationQRCode(verification_url, size=23 * mm),
            Paragraph(
                '<b>Verify receipt</b><br/>Scan the QR code to confirm the '
                'payment status, amount, property, room and confirmation date.',
                styles['ReceiptBody'],
            ),
        ]],
        colWidths=[28 * mm, 55 * mm],
    )
    verification_block.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    footer = Table(
        [[signature, verification_block]],
        colWidths=[85 * mm, 85 * mm],
    )
    footer.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (-1, -1), 0.6, colors.HexColor('#d1d5db')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))

    story = [
        header,
        Spacer(1, 7 * mm),
        details,
        Spacer(1, 7 * mm),
        Paragraph(
            'This receipt confirms that payment for the room booking was received '
            'and verified by the landlord. It is a payment confirmation record '
            'from SUA Student Housing.',
            styles['ReceiptBody'],
        ),
        Spacer(1, 8 * mm),
        KeepTogether([footer]),
    ]
    document.build(story)
    return buffer.getvalue()
