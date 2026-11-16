"""
DonationRecord - one row per donation a user confirms (static-NGO flow).

Stores the NGO's contact details AT THE TIME of donating so the donor can always
come back to My Donations and see who to call / where to drop the item off.
"""
from __future__ import annotations

from datetime import datetime
from extensions import db


class DonationRecord(db.Model):
    __tablename__ = "donation_records"

    id            = db.Column(db.Integer, primary_key=True)
    donor_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id    = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    ngo_ref       = db.Column(db.String(64))            # static NGO id (as string)
    ngo_name      = db.Column(db.String(200), nullable=False)
    ngo_phone     = db.Column(db.String(40))
    ngo_email     = db.Column(db.String(150))
    ngo_address   = db.Column(db.String(400))
    ngo_lat       = db.Column(db.Float)
    ngo_lng       = db.Column(db.Float)
    item_name     = db.Column(db.String(200))
    category      = db.Column(db.String(100))
    description   = db.Column(db.Text)
    status        = db.Column(db.String(30), default="pledged")   # pledged | delivered | cancelled
    confirmation_id = db.Column(db.String(80))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __init__(
        self,
        donor_id: int = 0,
        product_id: "int | None" = None,
        ngo_ref: str = "",
        ngo_name: str = "",
        ngo_phone: str = "",
        ngo_email: str = "",
        ngo_address: str = "",
        ngo_lat: "float | None" = None,
        ngo_lng: "float | None" = None,
        item_name: str = "",
        category: str = "",
        description: str = "",
        status: str = "pledged",
        confirmation_id: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.donor_id       = donor_id
        self.product_id     = product_id
        self.ngo_ref        = ngo_ref
        self.ngo_name       = ngo_name
        self.ngo_phone      = ngo_phone
        self.ngo_email      = ngo_email
        self.ngo_address    = ngo_address
        self.ngo_lat        = ngo_lat
        self.ngo_lng        = ngo_lng
        self.item_name      = item_name
        self.category       = category
        self.description    = description
        self.status         = status
        self.confirmation_id = confirmation_id

    def to_dict(self):
        return {
            "pledge_id":       f"don-{self.id}",
            "record_type":     "donation",
            "id":              self.id,
            "product_id":      self.product_id,
            "ngo_name":        self.ngo_name,
            "ngo_address":     self.ngo_address or "",
            "ngo_phone":       self.ngo_phone or "",
            "ngo_email":       self.ngo_email or "",
            "ngo_lat":         self.ngo_lat,
            "ngo_lng":         self.ngo_lng,
            "item_name":       self.item_name or "",
            "item_category":   self.category or "",
            "description":     self.description or "",
            "status":          self.status or "pledged",
            "confirmation_id": self.confirmation_id,
            "created_at":      self.created_at.isoformat(),
        }
