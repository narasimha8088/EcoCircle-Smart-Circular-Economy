"""
NGO Needs-Matching Data Models
==============================
Three SQLAlchemy models that together power the live, need-driven donation
routing pipeline:

  • NGOProfile        — Verified NGO registry with geocoded coordinates.
  • NeedsBoardEntry   — Live board of per-category donation needs with
                        quantity tracking and staleness metadata.
  • PledgeRecord      — Donor ↔ NGO pledge lifecycle (pledged → in_transit
                        → delivered | cancelled) with auto-sync back to
                        NeedsBoardEntry.quantity_fulfilled.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from extensions import db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


# ── NGOProfile ────────────────────────────────────────────────────────────────

class NGOProfile(db.Model):
    """
    Verified NGO partner record.

    Columns
    -------
    ngo_id          UUID primary key (string).
    name            Official registered name.
    registration_no Societies Act / Trusts Act / Sec-8 registration number.
    address         Human-readable address string.
    latitude        Auto-geocoded latitude (may be None until geocoded).
    longitude       Auto-geocoded longitude.
    category_tags   JSON list of accepted item categories, e.g.
                    ["Clothes", "Electronics", "Books"].
    contact_phone   Primary contact phone.
    contact_email   Primary contact e-mail.
    verified        Admin-verified flag (default False).
    password_hash   Hashed portal password for NGO dashboard login.
    created_at      Row creation timestamp.
    updated_at      Last modification timestamp (auto-updated).
    """

    __tablename__ = "ngo_profiles"

    ngo_id          = db.Column(db.String(36), primary_key=True, default=_uuid)
    name            = db.Column(db.String(200), nullable=False)
    registration_no = db.Column(db.String(100), nullable=False, unique=True)
    address         = db.Column(db.String(400), nullable=False)
    latitude        = db.Column(db.Float, nullable=True)
    longitude       = db.Column(db.Float, nullable=True)
    category_tags   = db.Column(db.JSON, default=list)   # list[str]
    contact_phone   = db.Column(db.String(20), nullable=True)
    contact_email   = db.Column(db.String(150), nullable=True)
    verified        = db.Column(db.Boolean, default=False, nullable=False)
    password_hash   = db.Column(db.String(255), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    needs   = db.relationship("NeedsBoardEntry", backref="ngo", lazy=True,
                               cascade="all, delete-orphan")
    pledges = db.relationship("PledgeRecord",    backref="ngo", lazy=True)

    def __init__(
        self,
        name: str = "",
        registration_no: str = "",
        address: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        category_tags: list | None = None,
        contact_phone: str | None = None,
        contact_email: str | None = None,
        verified: bool = False,
        password_hash: str | None = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            registration_no=registration_no,
            address=address,
            latitude=latitude,
            longitude=longitude,
            category_tags=category_tags or [],
            contact_phone=contact_phone,
            contact_email=contact_email,
            verified=verified,
            password_hash=password_hash,
            **kwargs,
        )

    # ── Password helpers ──────────────────────────────────────────────────────
    def set_password(self, pwd: str) -> None:
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash or "", pwd)

    def to_dict(self) -> dict:
        open_needs = [n for n in self.needs if n.status != "closed"]
        return {
            "ngo_id":          self.ngo_id,
            "name":            self.name,
            "registration_no": self.registration_no,
            "address":         self.address,
            "latitude":        self.latitude,
            "longitude":       self.longitude,
            "category_tags":   self.category_tags or [],
            "contact_phone":   self.contact_phone,
            "contact_email":   self.contact_email,
            "verified":        self.verified,
            "open_needs_count": len(open_needs),
            "created_at":      self.created_at.isoformat(),
        }


# ── NeedsBoardEntry ───────────────────────────────────────────────────────────

VALID_CATEGORIES  = ["Clothes", "Books", "Electronics", "Furniture", "Toys", "Food", "General"]
VALID_URGENCIES   = ["low", "medium", "high"]
VALID_CONDITIONS  = ["new", "used-good", "any"]
VALID_NEED_STATUS = ["open", "partially_fulfilled", "closed"]


class NeedsBoardEntry(db.Model):
    """
    One row per item-category need posted by an NGO.

    Staleness calculation (used by scoring engine):
        days_since_update = (now - last_updated).days
        staleness_factor  = max(0.5, 1 - days_since_update / 60)

    Status auto-sync:
        After any PledgeRecord → delivered transition the route handler calls
        NeedsBoardEntry.sync_status() to recalculate and persist the status.
    """

    __tablename__ = "ngo_needs"

    need_id            = db.Column(db.String(36), primary_key=True, default=_uuid)
    ngo_id             = db.Column(db.String(36), db.ForeignKey("ngo_profiles.ngo_id"),
                                   nullable=False)
    item_category      = db.Column(db.String(50), nullable=False)   # Enum in VALID_CATEGORIES
    quantity_needed    = db.Column(db.Integer, default=1,  nullable=False)
    quantity_fulfilled = db.Column(db.Integer, default=0,  nullable=False)
    # Soft-hold: pledges in 'pledged' state (released on cancel, cleared on deliver)
    quantity_pledged   = db.Column(db.Integer, default=0,  nullable=False)
    urgency            = db.Column(db.String(20), default="medium", nullable=False)  # low|medium|high
    condition_accepted = db.Column(db.String(20), default="any",    nullable=False)  # new|used-good|any
    notes              = db.Column(db.Text, nullable=True)
    last_updated       = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    status             = db.Column(db.String(30), default="open", nullable=False)  # open|partially_fulfilled|closed

    # Relationships
    pledges = db.relationship("PledgeRecord", backref="need", lazy=True)

    def __init__(
        self,
        ngo_id: str = "",
        item_category: str = "",
        quantity_needed: int = 1,
        quantity_fulfilled: int = 0,
        quantity_pledged: int = 0,
        urgency: str = "medium",
        condition_accepted: str = "any",
        notes: str | None = None,
        status: str = "open",
        last_updated: datetime | None = None,
        **kwargs,
    ):
        super().__init__(
            ngo_id=ngo_id,
            item_category=item_category,
            quantity_needed=quantity_needed,
            quantity_fulfilled=quantity_fulfilled,
            quantity_pledged=quantity_pledged,
            urgency=urgency,
            condition_accepted=condition_accepted,
            notes=notes,
            status=status,
            last_updated=last_updated or datetime.utcnow(),
            **kwargs,
        )

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def quantity_remaining(self) -> int:
        """Unmet need minus soft-held pledges."""
        return max(0, self.quantity_needed - self.quantity_fulfilled - self.quantity_pledged)

    @property
    def unmet_need_score(self) -> float:
        """0–1 fraction of the need still unmet (used by scoring engine)."""
        if self.quantity_needed <= 0:
            return 0.0
        unmet = self.quantity_needed - self.quantity_fulfilled
        return max(0.0, min(1.0, unmet / self.quantity_needed))

    @property
    def urgency_score(self) -> float:
        """Numeric urgency score: low=0.33, medium=0.66, high=1.0."""
        return {"low": 0.33, "medium": 0.66, "high": 1.0}.get(self.urgency, 0.66)

    @property
    def staleness_factor(self) -> float:
        """Discount factor based on days since last_updated (0.5 – 1.0)."""
        days = (datetime.utcnow() - self.last_updated).days
        return max(0.5, 1.0 - days / 60.0)

    def sync_status(self) -> None:
        """Recalculate and persist .status based on fulfilled quantities."""
        if self.quantity_fulfilled >= self.quantity_needed:
            self.status = "closed"
        elif self.quantity_fulfilled > 0:
            self.status = "partially_fulfilled"
        else:
            self.status = "open"

    def to_dict(self) -> dict:
        return {
            "need_id":            self.need_id,
            "ngo_id":             self.ngo_id,
            "item_category":      self.item_category,
            "quantity_needed":    self.quantity_needed,
            "quantity_fulfilled": self.quantity_fulfilled,
            "quantity_pledged":   self.quantity_pledged,
            "quantity_remaining": self.quantity_remaining,
            "urgency":            self.urgency,
            "urgency_score":      self.urgency_score,
            "condition_accepted": self.condition_accepted,
            "notes":              self.notes,
            "last_updated":       self.last_updated.isoformat(),
            "staleness_factor":   round(self.staleness_factor, 3),
            "status":             self.status,
        }


# ── PledgeRecord ──────────────────────────────────────────────────────────────

VALID_PLEDGE_STATUSES = ["pledged", "in_transit", "delivered", "cancelled"]


class PledgeRecord(db.Model):
    """
    Donor ↔ NGO item pledge with 4-state lifecycle.

    State machine:
        pledged → in_transit → delivered   (increments quantity_fulfilled)
        pledged → cancelled                (releases quantity_pledged)
        in_transit → cancelled             (releases quantity_pledged)

    The route handler is responsible for calling the appropriate
    NeedsBoardEntry quantity methods after status transitions.
    """

    __tablename__ = "distribution_records"

    pledge_id          = db.Column(db.String(36),  primary_key=True, default=_uuid)
    donor_id           = db.Column(db.Integer,     db.ForeignKey("users.id"), nullable=False)
    ngo_id             = db.Column(db.String(36),  db.ForeignKey("ngo_profiles.ngo_id"), nullable=False)
    need_id            = db.Column(db.String(36),  db.ForeignKey("ngo_needs.need_id"), nullable=True)
    item_name          = db.Column(db.String(200), nullable=True)
    item_classification = db.Column(db.JSON, nullable=True)   # AI metadata: category, eco_score, condition, etc.
    quantity           = db.Column(db.Integer, default=1, nullable=False)
    status             = db.Column(db.String(20), default="pledged", nullable=False)
    donor_note         = db.Column(db.Text, nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at         = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __init__(
        self,
        donor_id: int = 0,
        ngo_id: str = "",
        need_id: str | None = None,
        item_name: str | None = None,
        item_classification: dict | None = None,
        quantity: int = 1,
        status: str = "pledged",
        donor_note: str | None = None,
        **kwargs,
    ):
        super().__init__(
            donor_id=donor_id,
            ngo_id=ngo_id,
            need_id=need_id,
            item_name=item_name,
            item_classification=item_classification,
            quantity=quantity,
            status=status,
            donor_note=donor_note,
            **kwargs,
        )

    def to_dict(self) -> dict:
        return {
            "pledge_id":           self.pledge_id,
            "donor_id":            self.donor_id,
            "ngo_id":              self.ngo_id,
            "need_id":             self.need_id,
            "item_name":           self.item_name,
            "item_classification": self.item_classification,
            "quantity":            self.quantity,
            "status":              self.status,
            "donor_note":          self.donor_note,
            "created_at":          self.created_at.isoformat(),
            "updated_at":          self.updated_at.isoformat(),
        }
