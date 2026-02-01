"""
Ticket PDF Generation Service for Pronto App
Generates professional PDF tickets for printing and download.
"""

import io
import logging
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

# Ticket paper size (80mm thermal printer width, variable height)
TICKET_WIDTH = 80 * mm
TICKET_MIN_HEIGHT = 200 * mm


class TicketPDFService:
    """Service for generating PDF tickets."""

    def __init__(self, restaurant_name: str = "Pronto Restaurante"):
        self.restaurant_name = restaurant_name
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Configure custom styles for the ticket."""
        self.styles.add(
            ParagraphStyle(
                name="TicketHeader",
                parent=self.styles["Heading1"],
                fontSize=14,
                alignment=1,  # Center
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TicketSubheader",
                parent=self.styles["Normal"],
                fontSize=10,
                alignment=1,
                spaceAfter=4,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TicketItem",
                parent=self.styles["Normal"],
                fontSize=9,
                leftIndent=0,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TicketModifier",
                parent=self.styles["Normal"],
                fontSize=8,
                leftIndent=10,
                textColor=colors.gray,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TicketTotal",
                parent=self.styles["Normal"],
                fontSize=11,
                alignment=2,  # Right
                fontName="Helvetica-Bold",
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="TicketFooter",
                parent=self.styles["Normal"],
                fontSize=8,
                alignment=1,
                textColor=colors.gray,
            )
        )

    def generate_pdf(
        self,
        session_id: int,
        customer_name: str,
        table_number: str,
        orders: list,
        subtotal: Decimal,
        tax_amount: Decimal,
        tip_amount: Decimal,
        total_amount: Decimal,
        payment_method: str | None = None,
        payment_reference: str | None = None,
        is_paid: bool = False,
    ) -> bytes:
        """
        Generate a PDF ticket.

        Args:
            session_id: Session/ticket ID
            customer_name: Customer name
            table_number: Table number/label
            orders: List of order dicts with items
            subtotal: Subtotal amount
            tax_amount: Tax amount
            tip_amount: Tip amount
            total_amount: Total amount
            payment_method: Payment method used
            payment_reference: Payment reference number
            is_paid: Whether the session is paid

        Returns:
            PDF bytes
        """
        buffer = io.BytesIO()

        # Use letter size for better compatibility, will look like receipt
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(TICKET_WIDTH, letter[1]),
            leftMargin=5 * mm,
            rightMargin=5 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )

        elements = []

        # Header
        elements.append(Paragraph(self.restaurant_name, self.styles["TicketHeader"]))
        elements.append(
            Paragraph(
                datetime.now().strftime("%d/%m/%Y %H:%M"),
                self.styles["TicketSubheader"],
            )
        )
        elements.append(Spacer(1, 4 * mm))

        # Session info
        elements.append(Paragraph(f"<b>Ticket #{session_id}</b>", self.styles["TicketSubheader"]))
        elements.append(Paragraph(f"Cliente: {customer_name}", self.styles["TicketSubheader"]))
        elements.append(Paragraph(f"Mesa: {table_number}", self.styles["TicketSubheader"]))
        elements.append(Spacer(1, 4 * mm))

        # Separator line
        elements.append(self._create_separator())
        elements.append(Spacer(1, 2 * mm))

        # Orders
        for order in orders:
            elements.append(
                Paragraph(
                    f"<b>Orden #{order.get('id', 'N/A')}</b>",
                    self.styles["TicketItem"],
                )
            )
            if order.get("created_at"):
                created_at = order["created_at"]
                if isinstance(created_at, str):
                    time_str = created_at
                else:
                    time_str = created_at.strftime("%H:%M")
                elements.append(Paragraph(f"Hora: {time_str}", self.styles["TicketModifier"]))

            # Items table
            items_data = []
            for item in order.get("items", []):
                item_name = item.get("name", "Producto")
                quantity = item.get("quantity", 1)
                unit_price = Decimal(str(item.get("unit_price", 0)))
                item_total = unit_price * quantity
                items_data.append([f"{quantity}x {item_name}", f"${item_total:.2f}"])

                # Modifiers
                for mod in item.get("modifiers", []):
                    mod_name = mod.get("name", "Modificador")
                    mod_qty = mod.get("quantity", 1)
                    mod_price = Decimal(str(mod.get("unit_price_adjustment", 0)))
                    mod_total = mod_price * mod_qty
                    items_data.append([f"  + {mod_name} x{mod_qty}", f"${mod_total:.2f}"])

            if items_data:
                items_table = Table(items_data, colWidths=[50 * mm, 18 * mm])
                items_table.setStyle(
                    TableStyle(
                        [
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("LEFTPADDING", (0, 0), (0, -1), 0),
                            ("RIGHTPADDING", (1, 0), (1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                        ]
                    )
                )
                elements.append(items_table)

            # Order total
            order_total = order.get("total_amount")
            if order_total is not None:
                elements.append(
                    Paragraph(
                        f"<b>Subtotal orden: ${float(order_total):.2f}</b>",
                        self.styles["TicketItem"],
                    )
                )

            elements.append(Spacer(1, 2 * mm))
            elements.append(self._create_separator())
            elements.append(Spacer(1, 2 * mm))

        # Totals section
        elements.append(Paragraph("<b>--- TOTALES ---</b>", self.styles["TicketSubheader"]))
        elements.append(Spacer(1, 2 * mm))

        totals_data = [
            ["Subtotal:", f"${float(subtotal):.2f}"],
            ["IVA:", f"${float(tax_amount):.2f}"],
            ["Propina:", f"${float(tip_amount):.2f}"],
        ]

        totals_table = Table(totals_data, colWidths=[50 * mm, 18 * mm])
        totals_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ]
            )
        )
        elements.append(totals_table)

        # Grand total
        elements.append(Spacer(1, 2 * mm))
        grand_total_data = [["TOTAL:", f"${float(total_amount):.2f}"]]
        grand_total_table = Table(grand_total_data, colWidths=[50 * mm, 18 * mm])
        grand_total_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 12),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (1, 0), (1, -1), 0),
                    ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(grand_total_table)

        # Payment info
        if is_paid and payment_method:
            elements.append(Spacer(1, 4 * mm))
            elements.append(self._create_separator())
            elements.append(Spacer(1, 2 * mm))
            elements.append(Paragraph(f"Pagado con: {payment_method}", self.styles["TicketItem"]))
            if payment_reference:
                elements.append(
                    Paragraph(f"Referencia: {payment_reference}", self.styles["TicketItem"])
                )

        # Footer
        elements.append(Spacer(1, 6 * mm))
        elements.append(self._create_separator())
        elements.append(Spacer(1, 2 * mm))
        elements.append(Paragraph("Gracias por su preferencia", self.styles["TicketFooter"]))
        elements.append(Paragraph(self.restaurant_name, self.styles["TicketFooter"]))

        # Build PDF
        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated PDF ticket for session {session_id} ({len(pdf_bytes)} bytes)")
        return pdf_bytes

    def _create_separator(self) -> Table:
        """Create a dashed separator line."""
        separator = Table([["-" * 40]], colWidths=[70 * mm])
        separator.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.gray),
                ]
            )
        )
        return separator


def generate_ticket_pdf(session_id: int) -> tuple[bytes | None, int, str | None]:
    """
    Generate PDF ticket for a dining session.

    Args:
        session_id: DiningSession ID

    Returns:
        Tuple of (pdf_bytes or None, HTTP status code, error message or None)
    """
    from http import HTTPStatus

    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from shared.db import get_session
    from shared.models import DiningSession, Order, OrderItem, OrderItemModifier

    with get_session() as session:
        dining_session = (
            session.execute(
                select(DiningSession)
                .options(
                    joinedload(DiningSession.orders)
                    .joinedload(Order.items)
                    .joinedload(OrderItem.menu_item),
                    joinedload(DiningSession.orders)
                    .joinedload(Order.items)
                    .joinedload(OrderItem.modifiers)
                    .joinedload(OrderItemModifier.modifier),
                    joinedload(DiningSession.customer),
                )
                .where(DiningSession.id == session_id)
            )
            .unique()
            .scalars()
            .one_or_none()
        )

        if dining_session is None:
            return None, HTTPStatus.NOT_FOUND, "Cuenta no encontrada"

        dining_session.recompute_totals()

        customer_name = dining_session.customer.name if dining_session.customer else "Cliente"
        table_label = dining_session.table_number or "N/A"

        # Prepare orders data
        orders_data = []
        sorted_orders = sorted(
            dining_session.orders,
            key=lambda order: (order.created_at or datetime.min, order.id),
        )

        for order in sorted_orders:
            order_data = {
                "id": order.id,
                "created_at": order.created_at,
                "workflow_status": order.workflow_status,
                "total_amount": order.total_amount,
                "items": [],
            }

            for item in order.items:
                item_data = {
                    "name": item.menu_item.name if item.menu_item else "Producto",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "modifiers": [],
                }

                for mod in item.modifiers:
                    mod_data = {
                        "name": mod.modifier.name if mod.modifier else "Modificador",
                        "quantity": mod.quantity,
                        "unit_price_adjustment": mod.unit_price_adjustment,
                    }
                    item_data["modifiers"].append(mod_data)

                order_data["items"].append(item_data)

            orders_data.append(order_data)

        # Generate PDF
        try:
            pdf_service = TicketPDFService()
            pdf_bytes = pdf_service.generate_pdf(
                session_id=dining_session.id,
                customer_name=customer_name,
                table_number=table_label,
                orders=orders_data,
                subtotal=dining_session.subtotal,
                tax_amount=dining_session.tax_amount,
                tip_amount=dining_session.tip_amount,
                total_amount=dining_session.total_amount,
                payment_method=dining_session.payment_method,
                payment_reference=dining_session.payment_reference,
                is_paid=dining_session.status == "paid",
            )

            if not pdf_bytes:
                return None, HTTPStatus.INTERNAL_SERVER_ERROR, "Error generando PDF (archivo vacío)"

            return pdf_bytes, HTTPStatus.OK, None

        except Exception as e:
            return None, HTTPStatus.INTERNAL_SERVER_ERROR, f"Error generando PDF: {str(e)}"
