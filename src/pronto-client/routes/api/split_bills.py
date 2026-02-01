"""
Split bill endpoints for clients API.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request

split_bills_bp = Blueprint("client_split_bills", __name__)


def _calculate_equal_split(session, split_bill_id: int, dining_session):
    """Helper function to calculate equal split for all people."""
    from shared.models import SplitBill

    split_bill = session.query(SplitBill).filter(SplitBill.id == split_bill_id).first()
    if not split_bill:
        return

    number_of_people = split_bill.number_of_people
    people_list = list(split_bill.people)

    session_subtotal = Decimal(str(dining_session.subtotal))
    session_tax = Decimal(str(dining_session.tax_amount or 0))
    session_tip = Decimal(str(dining_session.tip_amount or 0))
    session_total = Decimal(str(dining_session.total_amount))

    per_person_subtotal = (session_subtotal / number_of_people).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    per_person_tax = (session_tax / number_of_people).quantize(Decimal("0.01"), ROUND_HALF_UP)
    per_person_tip = (session_tip / number_of_people).quantize(Decimal("0.01"), ROUND_HALF_UP)
    per_person_total = (session_total / number_of_people).quantize(Decimal("0.01"), ROUND_HALF_UP)

    for person in people_list[:-1]:
        person.subtotal = float(per_person_subtotal)
        person.tax_amount = float(per_person_tax)
        person.tip_amount = float(per_person_tip)
        person.total_amount = float(per_person_total)

    if people_list:
        last_person = people_list[-1]
        total_assigned_subtotal = per_person_subtotal * (number_of_people - 1)
        total_assigned_tax = per_person_tax * (number_of_people - 1)
        total_assigned_tip = per_person_tip * (number_of_people - 1)
        total_assigned_total = per_person_total * (number_of_people - 1)

        last_person.subtotal = float(session_subtotal - total_assigned_subtotal)
        last_person.tax_amount = float(session_tax - total_assigned_tax)
        last_person.tip_amount = float(session_tip - total_assigned_tip)
        last_person.total_amount = float(session_total - total_assigned_total)


@split_bills_bp.post("/sessions/<int:session_id>/split-bill")
def create_split_bill(session_id: int):
    """Create a split bill for a dining session."""
    from shared.db import get_session
    from shared.models import DiningSession, SplitBill, SplitBillPerson

    try:
        payload = request.get_json(silent=True) or {}
        number_of_people = payload.get("number_of_people", 2)
        split_type = payload.get("split_type", "by_items")

        if number_of_people < 2:
            return jsonify(
                {"error": "El número de personas debe ser al menos 2"}
            ), HTTPStatus.BAD_REQUEST

        if split_type not in ["by_items", "equal"]:
            return jsonify({"error": "Tipo de división inválido"}), HTTPStatus.BAD_REQUEST

        with get_session() as db_session:
            dining_session = (
                db_session.query(DiningSession).filter(DiningSession.id == session_id).first()
            )

            if not dining_session:
                return jsonify({"error": "Sesión no encontrada"}), HTTPStatus.NOT_FOUND

            existing_split = (
                db_session.query(SplitBill)
                .filter(SplitBill.session_id == session_id, SplitBill.status == "active")
                .first()
            )

            if existing_split:
                return jsonify(
                    {"error": "Ya existe una división activa para esta sesión"}
                ), HTTPStatus.CONFLICT

            split_bill = SplitBill(
                session_id=session_id,
                split_type=split_type,
                number_of_people=number_of_people,
                status="active",
            )
            db_session.add(split_bill)
            db_session.flush()

            for i in range(number_of_people):
                person = SplitBillPerson(
                    split_bill_id=split_bill.id,
                    person_name=f"Persona {i + 1}",
                    person_number=i + 1,
                    subtotal=0,
                    tax_amount=0,
                    tip_amount=0,
                    total_amount=0,
                )
                db_session.add(person)

            if split_type == "equal":
                db_session.flush()
                _calculate_equal_split(db_session, split_bill.id, dining_session)

            db_session.commit()

            return jsonify(
                {
                    "split_bill_id": split_bill.id,
                    "session_id": session_id,
                    "number_of_people": number_of_people,
                    "split_type": split_type,
                    "status": "active",
                }
            ), HTTPStatus.CREATED

    except Exception as e:
        current_app.logger.error(f"Error creating split bill: {e}")
        return jsonify(
            {"error": "Error al crear división de cuenta"}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@split_bills_bp.get("/split-bills/<int:split_id>")
def get_split_bill(split_id: int):
    """Get split bill details including all people and their assignments."""
    from shared.db import get_session
    from shared.models import SplitBill

    try:
        with get_session() as db_session:
            split_bill = db_session.query(SplitBill).filter(SplitBill.id == split_id).first()

            if not split_bill:
                return jsonify({"error": "División no encontrada"}), HTTPStatus.NOT_FOUND

            people_data = []
            for person in split_bill.people:
                assigned_items = []
                for assignment in person.assignments:
                    order_item = assignment.order_item
                    menu_item = order_item.menu_item

                    assigned_items.append(
                        {
                            "assignment_id": assignment.id,
                            "order_item_id": order_item.id,
                            "menu_item_name": menu_item.name,
                            "quantity_portion": float(assignment.quantity_portion),
                            "amount": float(assignment.amount),
                        }
                    )

                people_data.append(
                    {
                        "id": person.id,
                        "person_name": person.person_name,
                        "person_number": person.person_number,
                        "subtotal": float(person.subtotal),
                        "tax_amount": float(person.tax_amount),
                        "tip_amount": float(person.tip_amount),
                        "total_amount": float(person.total_amount),
                        "payment_status": person.payment_status,
                        "assigned_items": assigned_items,
                    }
                )

            return jsonify(
                {
                    "split_bill": {
                        "id": split_bill.id,
                        "session_id": split_bill.session_id,
                        "split_type": split_bill.split_type,
                        "number_of_people": split_bill.number_of_people,
                        "status": split_bill.status,
                        "created_at": split_bill.created_at.isoformat()
                        if split_bill.created_at
                        else None,
                    },
                    "people": people_data,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching split bill: {e}")
        return jsonify({"error": "Error al obtener división"}), HTTPStatus.INTERNAL_SERVER_ERROR


@split_bills_bp.post("/split-bills/<int:split_id>/assign")
def assign_item_to_person(split_id: int):
    """Assign an order item to a person in the split."""
    from shared.db import get_session
    from shared.models import OrderItem, SplitBill, SplitBillAssignment, SplitBillPerson

    try:
        payload = request.get_json(silent=True) or {}
        person_id = payload.get("person_id")
        order_item_id = payload.get("order_item_id")
        quantity_portion = Decimal(str(payload.get("quantity_portion", 1.0)))

        if not person_id or not order_item_id:
            return jsonify({"error": "Faltan parámetros requeridos"}), HTTPStatus.BAD_REQUEST

        with get_session() as db_session:
            split_bill = db_session.query(SplitBill).filter(SplitBill.id == split_id).first()
            if not split_bill:
                return jsonify({"error": "División no encontrada"}), HTTPStatus.NOT_FOUND

            if split_bill.status != "active":
                return jsonify({"error": "La división no está activa"}), HTTPStatus.BAD_REQUEST

            person = (
                db_session.query(SplitBillPerson)
                .filter(SplitBillPerson.id == person_id, SplitBillPerson.split_bill_id == split_id)
                .first()
            )

            if not person:
                return jsonify(
                    {"error": "Persona no encontrada en esta división"}
                ), HTTPStatus.NOT_FOUND

            order_item = db_session.query(OrderItem).filter(OrderItem.id == order_item_id).first()
            if not order_item:
                return jsonify({"error": "Item no encontrado"}), HTTPStatus.NOT_FOUND

            item_price = Decimal(str(order_item.unit_price)) * Decimal(str(order_item.quantity))
            for modifier in order_item.modifiers:
                modifier_price = Decimal(str(modifier.unit_price_adjustment)) * Decimal(
                    str(modifier.quantity)
                )
                item_price += modifier_price

            amount = (item_price * quantity_portion).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            existing_assignments = (
                db_session.query(SplitBillAssignment)
                .filter(
                    SplitBillAssignment.split_bill_id == split_id,
                    SplitBillAssignment.order_item_id == order_item_id,
                )
                .all()
            )

            total_assigned = sum(Decimal(str(a.quantity_portion)) for a in existing_assignments)
            if total_assigned + quantity_portion > Decimal("1.001"):
                return jsonify(
                    {"error": "El item ya está completamente asignado"}
                ), HTTPStatus.CONFLICT

            assignment = SplitBillAssignment(
                split_bill_id=split_id,
                person_id=person_id,
                order_item_id=order_item_id,
                quantity_portion=float(quantity_portion),
                amount=float(amount),
            )
            db_session.add(assignment)
            db_session.commit()

            return jsonify(
                {
                    "assignment_id": assignment.id,
                    "person_id": person_id,
                    "order_item_id": order_item_id,
                    "quantity_portion": float(quantity_portion),
                    "amount": float(amount),
                }
            ), HTTPStatus.CREATED

    except Exception as e:
        current_app.logger.error(f"Error assigning item: {e}")
        return jsonify({"error": "Error al asignar item"}), HTTPStatus.INTERNAL_SERVER_ERROR


@split_bills_bp.post("/split-bills/<int:split_id>/calculate")
def calculate_split_totals(split_id: int):
    """Recalculate totals for all people in the split based on their assignments."""
    from shared.db import get_session
    from shared.models import SplitBill

    try:
        with get_session() as db_session:
            split_bill = db_session.query(SplitBill).filter(SplitBill.id == split_id).first()
            if not split_bill:
                return jsonify({"error": "División no encontrada"}), HTTPStatus.NOT_FOUND

            dining_session = split_bill.session

            session_subtotal = Decimal(str(dining_session.subtotal))
            session_tax = Decimal(str(dining_session.tax_amount or 0))
            session_tip = Decimal(str(dining_session.tip_amount or 0))

            for person in split_bill.people:
                person_subtotal = sum(Decimal(str(a.amount)) for a in person.assignments)

                if session_subtotal > 0:
                    proportion = person_subtotal / session_subtotal
                    person_tax = session_tax * proportion
                    person_tip = session_tip * proportion
                else:
                    person_tax = Decimal(0)
                    person_tip = Decimal(0)

                person_total = person_subtotal + person_tax + person_tip

                person.subtotal = float(person_subtotal)
                person.tax_amount = float(person_tax)
                person.tip_amount = float(person_tip)
                person.total_amount = float(person_total)

            db_session.commit()

            people_summary = []
            for person in split_bill.people:
                people_summary.append(
                    {
                        "person_id": person.id,
                        "person_name": person.person_name,
                        "subtotal": float(person.subtotal),
                        "tax_amount": float(person.tax_amount),
                        "tip_amount": float(person.tip_amount),
                        "total_amount": float(person.total_amount),
                    }
                )

            return jsonify({"split_bill_id": split_id, "people": people_summary}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error calculating split totals: {e}")
        return jsonify({"error": "Error al calcular totales"}), HTTPStatus.INTERNAL_SERVER_ERROR


@split_bills_bp.get("/split-bills/<int:split_id>/summary")
def get_split_summary(split_id: int):
    """Get a summary of the split including session info and all people with their totals."""
    from shared.db import get_session
    from shared.models import SplitBill

    try:
        with get_session() as db_session:
            split_bill = db_session.query(SplitBill).filter(SplitBill.id == split_id).first()
            if not split_bill:
                return jsonify({"error": "División no encontrada"}), HTTPStatus.NOT_FOUND

            dining_session = split_bill.session

            people_summary = []
            for person in split_bill.people:
                people_summary.append(
                    {
                        "person_id": person.id,
                        "person_name": person.person_name,
                        "person_number": person.person_number,
                        "subtotal": float(person.subtotal),
                        "tax_amount": float(person.tax_amount),
                        "tip_amount": float(person.tip_amount),
                        "total_amount": float(person.total_amount),
                        "payment_status": person.payment_status,
                        "items_count": len(person.assignments),
                    }
                )

            return jsonify(
                {
                    "split_bill": {
                        "id": split_bill.id,
                        "split_type": split_bill.split_type,
                        "number_of_people": split_bill.number_of_people,
                        "status": split_bill.status,
                    },
                    "session": {
                        "id": dining_session.id,
                        "table_number": dining_session.table_number,
                        "subtotal": float(dining_session.subtotal),
                        "tax_amount": float(dining_session.tax_amount or 0),
                        "tip_amount": float(dining_session.tip_amount or 0),
                        "total_amount": float(dining_session.total_amount),
                    },
                    "people": people_summary,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching split summary: {e}")
        return jsonify({"error": "Error al obtener resumen"}), HTTPStatus.INTERNAL_SERVER_ERROR


@split_bills_bp.post("/split-bills/<int:split_id>/people/<int:person_id>/pay")
def pay_split_person(split_id: int, person_id: int):
    """Process payment for an individual person in a split bill."""
    from shared.db import get_session
    from shared.models import SplitBill, SplitBillPerson

    try:
        payload = request.get_json(silent=True) or {}
        payment_method = payload.get("payment_method", "cash")
        payment_reference = payload.get("payment_reference")

        valid_methods = ["cash", "clip", "stripe"]
        if payment_method not in valid_methods:
            return jsonify(
                {"error": f"Método de pago no válido. Use: {', '.join(valid_methods)}"}
            ), HTTPStatus.BAD_REQUEST

        with get_session() as db_session:
            split_bill = db_session.query(SplitBill).filter(SplitBill.id == split_id).first()
            if not split_bill:
                return jsonify({"error": "División no encontrada"}), HTTPStatus.NOT_FOUND

            if split_bill.status != "active":
                return jsonify({"error": "La división no está activa"}), HTTPStatus.BAD_REQUEST

            person = (
                db_session.query(SplitBillPerson)
                .filter(SplitBillPerson.id == person_id, SplitBillPerson.split_bill_id == split_id)
                .first()
            )

            if not person:
                return jsonify(
                    {"error": "Persona no encontrada en esta división"}
                ), HTTPStatus.NOT_FOUND

            if person.payment_status == "paid":
                return jsonify({"error": "Esta persona ya pagó su parte"}), HTTPStatus.CONFLICT

            if not payment_reference:
                timestamp = int(datetime.utcnow().timestamp())
                payment_reference = (
                    f"{payment_method}-split-{split_id}-person-{person_id}-{timestamp}"
                )

            person.payment_status = "paid"
            person.payment_method = payment_method
            person.payment_reference = payment_reference
            person.paid_at = datetime.utcnow()

            all_paid = all(p.payment_status == "paid" for p in split_bill.people)

            if all_paid:
                split_bill.status = "completed"
                split_bill.completed_at = datetime.utcnow()

                dining_session = split_bill.session
                dining_session.status = "closed"
                dining_session.closed_at = datetime.utcnow()
                dining_session.payment_method = "split_bill"
                dining_session.payment_reference = f"split-{split_id}"

                total_paid = sum(Decimal(str(p.total_amount)) for p in split_bill.people)
                dining_session.total_paid = float(total_paid)

                for order in dining_session.orders:
                    order.payment_status = "paid"
                    order.payment_method = "split_bill"
                    order.payment_reference = f"split-{split_id}"
                    order.paid_at = datetime.utcnow()

            db_session.commit()

            return jsonify(
                {
                    "person_id": person_id,
                    "person_name": person.person_name,
                    "payment_status": person.payment_status,
                    "payment_method": person.payment_method,
                    "payment_reference": person.payment_reference,
                    "amount_paid": float(person.total_amount),
                    "split_completed": all_paid,
                    "session_closed": all_paid,
                }
            ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error processing split payment: {e}")
        return jsonify({"error": "Error al procesar pago"}), HTTPStatus.INTERNAL_SERVER_ERROR
