"""Service for managing customer feedback."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import joinedload

from shared.constants import FeedbackCategory
from shared.db import get_session
from shared.models import DiningSession, Employee, Feedback


class FeedbackService:
    """Service for managing feedback."""

    @staticmethod
    def create_feedback(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new feedback entry."""
        with get_session() as session:
            # Validate session exists
            session_obj = (
                session.execute(select(DiningSession).where(DiningSession.id == data["session_id"]))
                .scalars()
                .first()
            )

            if not session_obj:
                raise ValueError(f"Session with ID {data['session_id']} not found")

            # If employee_id provided, validate it exists
            if data.get("employee_id"):
                employee = (
                    session.execute(select(Employee).where(Employee.id == data["employee_id"]))
                    .scalars()
                    .first()
                )

                if not employee:
                    raise ValueError(f"Employee with ID {data['employee_id']} not found")

            # Create feedback
            feedback = Feedback(**data)
            session.add(feedback)
            session.flush()
            session.refresh(feedback)

            return FeedbackService._feedback_to_dict(feedback)

    @staticmethod
    def create_bulk_feedback(
        session_id: int,
        employee_id: int | None,
        feedback_items: list[dict[str, Any]],
        is_anonymous: bool = False,
    ) -> list[dict[str, Any]]:
        """Create multiple feedback entries at once."""
        result = []
        for item in feedback_items:
            feedback_data = {
                "session_id": session_id,
                "employee_id": employee_id,
                "category": item["category"],
                "rating": item["rating"],
                "comment": item.get("comment"),
                "is_anonymous": is_anonymous,
            }
            feedback = FeedbackService.create_feedback(feedback_data)
            result.append(feedback)
        return result

    @staticmethod
    def get_feedback_by_id(feedback_id: int) -> dict[str, Any] | None:
        """Get a feedback entry by ID."""
        with get_session() as session:
            feedback = (
                session.execute(
                    select(Feedback)
                    .options(
                        joinedload(Feedback.session),
                        joinedload(Feedback.customer),
                        joinedload(Feedback.employee),
                    )
                    .where(Feedback.id == feedback_id)
                )
                .unique()
                .scalars()
                .first()
            )

            if not feedback:
                return None

            return FeedbackService._feedback_to_dict(feedback, include_relations=True)

    @staticmethod
    def get_feedback_by_session(session_id: int) -> list[dict[str, Any]]:
        """Get all feedback for a session."""
        with get_session() as session:
            feedbacks = (
                session.execute(
                    select(Feedback)
                    .options(joinedload(Feedback.employee))
                    .where(Feedback.session_id == session_id)
                    .order_by(Feedback.created_at.desc())
                )
                .unique()
                .scalars()
                .all()
            )

            return [FeedbackService._feedback_to_dict(f, include_relations=True) for f in feedbacks]

    @staticmethod
    def get_feedback_by_employee(
        employee_id: int, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """Get all feedback for an employee with pagination."""
        with get_session() as session:
            # Count total
            total_count = session.execute(
                select(func.count(Feedback.id)).where(Feedback.employee_id == employee_id)
            ).scalar()

            # Get feedbacks
            feedbacks = (
                session.execute(
                    select(Feedback)
                    .options(joinedload(Feedback.session), joinedload(Feedback.customer))
                    .where(Feedback.employee_id == employee_id)
                    .order_by(Feedback.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .unique()
                .scalars()
                .all()
            )

            return {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "feedback": [
                    FeedbackService._feedback_to_dict(f, include_relations=True) for f in feedbacks
                ],
            }

    @staticmethod
    def get_employee_stats(employee_id: int, days: int = 30) -> dict[str, Any]:
        """Get aggregated feedback statistics for an employee."""
        with get_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)

            # Get all feedback for employee in date range
            feedbacks = (
                session.execute(
                    select(Feedback).where(
                        and_(Feedback.employee_id == employee_id, Feedback.created_at >= since_date)
                    )
                )
                .scalars()
                .all()
            )

            if not feedbacks:
                return {
                    "employee_id": employee_id,
                    "period_days": days,
                    "total_feedback": 0,
                    "average_rating": 0,
                    "by_category": {},
                    "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                }

            # Calculate stats
            total = len(feedbacks)
            avg_rating = sum(f.rating for f in feedbacks) / total

            # By category
            by_category = {}
            for category in FeedbackCategory:
                cat_feedbacks = [f for f in feedbacks if f.category == category.value]
                if cat_feedbacks:
                    by_category[category.value] = {
                        "count": len(cat_feedbacks),
                        "average_rating": sum(f.rating for f in cat_feedbacks) / len(cat_feedbacks),
                    }

            # Rating distribution
            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for f in feedbacks:
                rating_dist[f.rating] += 1

            return {
                "employee_id": employee_id,
                "period_days": days,
                "total_feedback": total,
                "average_rating": round(avg_rating, 2),
                "by_category": by_category,
                "rating_distribution": rating_dist,
            }

    @staticmethod
    def get_overall_stats(days: int = 30, category: str | None = None) -> dict[str, Any]:
        """Get overall feedback statistics for the business."""
        with get_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)

            query = select(Feedback).where(Feedback.created_at >= since_date)
            if category:
                query = query.where(Feedback.category == category)

            feedbacks = session.execute(query).scalars().all()

            if not feedbacks:
                return {
                    "period_days": days,
                    "category": category,
                    "total_feedback": 0,
                    "average_rating": 0,
                    "by_category": {},
                    "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                }

            # Calculate stats
            total = len(feedbacks)
            avg_rating = sum(f.rating for f in feedbacks) / total

            # By category
            by_category = {}
            for cat in FeedbackCategory:
                cat_feedbacks = [f for f in feedbacks if f.category == cat.value]
                if cat_feedbacks:
                    by_category[cat.value] = {
                        "count": len(cat_feedbacks),
                        "average_rating": sum(f.rating for f in cat_feedbacks) / len(cat_feedbacks),
                    }

            # Rating distribution
            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for f in feedbacks:
                rating_dist[f.rating] += 1

            return {
                "period_days": days,
                "category": category,
                "total_feedback": total,
                "average_rating": round(avg_rating, 2),
                "by_category": by_category,
                "rating_distribution": rating_dist,
            }

    @staticmethod
    def get_top_rated_employees(
        limit: int = 10, days: int = 30, category: str | None = None
    ) -> list[dict[str, Any]]:
        """Get top-rated employees based on recent feedback."""
        with get_session() as session:
            since_date = datetime.utcnow() - timedelta(days=days)

            query = (
                select(
                    Feedback.employee_id,
                    func.count(Feedback.id).label("feedback_count"),
                    func.avg(Feedback.rating).label("avg_rating"),
                )
                .where(and_(Feedback.employee_id.isnot(None), Feedback.created_at >= since_date))
                .group_by(Feedback.employee_id)
                .order_by(desc("avg_rating"))
                .limit(limit)
            )

            if category:
                query = query.where(Feedback.category == category)

            results = session.execute(query).all()

            # Get employee details
            top_employees = []
            for employee_id, count, avg_rating in results:
                employee = (
                    session.execute(select(Employee).where(Employee.id == employee_id))
                    .scalars()
                    .first()
                )

                if employee:
                    top_employees.append(
                        {
                            "employee_id": employee.id,
                            "employee_name": employee.name,
                            "feedback_count": count,
                            "average_rating": round(float(avg_rating), 2),
                        }
                    )

            return top_employees

    @staticmethod
    def _feedback_to_dict(feedback: Feedback, include_relations: bool = False) -> dict[str, Any]:
        """Convert feedback model to dictionary."""
        result = {
            "id": feedback.id,
            "session_id": feedback.session_id,
            "customer_id": feedback.customer_id,
            "employee_id": feedback.employee_id,
            "category": feedback.category,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "is_anonymous": feedback.is_anonymous,
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        }

        if include_relations:
            if feedback.employee:
                result["employee_name"] = feedback.employee.name
            if feedback.customer and not feedback.is_anonymous:
                result["customer_name"] = feedback.customer.name

        return result
