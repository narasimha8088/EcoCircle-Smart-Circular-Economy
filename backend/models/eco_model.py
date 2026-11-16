"""
EcoAction — Audit log for all sustainable actions.
===================================================
Every time a user donates, repairs, recycles, sells or buys on the
platform, one EcoAction row is appended. This table:

  • Drives the accurate eco_score increment (awarded_points column).
  • Feeds the Phase-2 Model-7 (XGBoost eco-trend predictor) with
    real per-user history instead of synthetic data.
  • Powers the profile activity feed.

The User.eco_score column is the running sum of awarded_points for
that user and is updated atomically via award_eco_points().
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime
from extensions import db

# Points awarded per action type
ECO_POINTS = {
    "donated":        30,
    "recycled":       25,
    "repaired":       20,
    "sold":           15,
    "listed":         15,
    "bought":         10,
    "repair_booked":  20,
    "recycle_booked": 20,
    "ai_scan":         5,
    "added_item":      5,
}


class EcoAction(db.Model):
    """One row per sustainable action performed by a user."""

    __tablename__ = "eco_actions"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action_type  = db.Column(db.String(50), nullable=False)   # donated | recycled | repaired | sold | bought | listed | ai_scan
    category     = db.Column(db.String(100), nullable=True)   # product category (electronics, clothing …)
    description  = db.Column(db.String(300), nullable=True)   # human-readable detail
    awarded_pts  = db.Column(db.Integer, default=0, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __init__(
        self,
        user_id: int = 0,
        action_type: str = "",
        category: str | None = None,
        description: str | None = None,
        awarded_pts: int = 0,
        **kwargs,
    ):
        super().__init__(
            user_id=user_id,
            action_type=action_type,
            category=category,
            description=description,
            awarded_pts=awarded_pts,
            **kwargs,
        )

    def to_dict(self):
        return {
            "id":          self.id,
            "action_type": self.action_type,
            "category":    self.category,
            "description": self.description,
            "awarded_pts": self.awarded_pts,
            "created_at":  self.created_at.isoformat(),
        }


def award_eco_points(user, action_type: str, category: str = "", description: str = "") -> int:
    """
    Append an EcoAction row and increment user.eco_score atomically.

    Returns the number of points awarded.

    Usage (inside a route, before db.session.commit()):
        pts = award_eco_points(user, "donated", category="Clothes",
                               description="Donated to Goonj Donation Hub")
    """
    pts = ECO_POINTS.get(action_type, 5)

    log = EcoAction(
        user_id     = user.id,
        action_type = action_type,
        category    = category,
        description = description,
        awarded_pts = pts,
    )
    db.session.add(log)

    # Increment running total on User
    current = getattr(user, "eco_score", 0) or 0
    user.eco_score = current + pts

    return pts
