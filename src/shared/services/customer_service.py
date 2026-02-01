"""
Customer service for anonymous and registered users.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.models import Customer
from shared.security import encrypt_string, hash_identifier

logger = logging.getLogger(__name__)


def create_anonymous_customer(db: Session) -> Customer:
    """Create a new anonymous customer with generated anon_id."""
    anon_id = secrets.token_urlsafe(32)

    customer = Customer(
        anon_id=anon_id,
        name_encrypted=encrypt_string("Cliente Anónimo"),
        email_encrypted=None,
        email_hash=None,
        phone_encrypted=None,
        created_at=datetime.utcnow(),
    )

    try:
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer
    except IntegrityError:
        db.rollback()
        logger.warning(f"IntegrityError creating customer with anon_id, retrying once")
        # Retry with new anon_id
        anon_id = secrets.token_urlsafe(32)
        customer = Customer(
            anon_id=anon_id,
            name_encrypted=encrypt_string("Cliente Anónimo"),
            email_encrypted=None,
            email_hash=None,
            phone_encrypted=None,
            created_at=datetime.utcnow(),
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer


def get_customer_by_anon_id(db: Session, anon_id: str) -> Optional[Customer]:
    """Find customer by anonymous ID."""
    return db.query(Customer).filter(Customer.anon_id == anon_id).first()


def get_customer_by_email(db: Session, email: str) -> Optional[Customer]:
    """Find customer by email hash."""
    email_hash = hash_identifier(email)
    return db.query(Customer).filter(Customer.email_hash == email_hash).first()
