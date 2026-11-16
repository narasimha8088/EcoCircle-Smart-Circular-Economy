from __future__ import annotations

from typing import Optional
from datetime import datetime, date
from extensions import db

class Product(db.Model):
    __tablename__ = "products"

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(200), nullable=False)
    category        = db.Column(db.String(100), nullable=False)
    brand           = db.Column(db.String(100))
    description     = db.Column(db.Text)
    purchase_date   = db.Column(db.Date)
    condition       = db.Column(db.String(50))          # New / Good / Fair / Poor
    lifecycle_stage = db.Column(db.String(50), default="In Use")  # Purchase/Usage/Repair/Reuse/Recycle
    purchase_price  = db.Column(db.Float)
    weight_kg       = db.Column(db.Float)
    image           = db.Column(db.String(255))
    owner_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    # ── Phase 2 fields ─────────────────────────────────────────────────────────
    material        = db.Column(db.String(100))         # Primary material (for carbon estimator)
    co2_saved_kg    = db.Column(db.Float)               # Last computed carbon saving (M5)
    resale_estimate = db.Column(db.Float)               # Last computed resale price (M6)
    # ── AI-scan tracking fields (added in v3; auto-migrated in app.py) ─────────
    source          = db.Column(db.String(30), default="manual")   # manual | ai_scan
    ai_recommendation = db.Column(db.String(30))        # Repair / Resell / Recycle / Donate / Keep Using
    ai_score        = db.Column(db.Integer)             # 0-100 sustainability score
    ai_analysis     = db.Column(db.Text)                # full AI result as JSON (so it can be restored)
    analysis_ref    = db.Column(db.String(64), index=True)  # client-generated id -> prevents duplicates
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow)

    listings = db.relationship("Listing", backref="product", lazy=True)

    def __init__(
        self,
        name: str = "",
        category: str = "",
        brand: str = "",
        description: str = "",
        purchase_date: Optional[date] = None,
        condition: str = "Good",
        lifecycle_stage: str = "In Use",
        purchase_price: float = 0.0,
        weight_kg: float = 0.0,
        image: Optional[str] = None,
        owner_id: int = 0,
        material: Optional[str] = None,
        co2_saved_kg: Optional[float] = None,
        resale_estimate: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            category=category,
            brand=brand,
            description=description,
            purchase_date=purchase_date,
            condition=condition,
            lifecycle_stage=lifecycle_stage,
            purchase_price=purchase_price,
            weight_kg=weight_kg,
            image=image,
            owner_id=owner_id,
            material=material,
            co2_saved_kg=co2_saved_kg,
            resale_estimate=resale_estimate,
            **kwargs,
        )

    def age_years(self):
        if self.purchase_date:
            delta = datetime.utcnow().date() - self.purchase_date
            return round(delta.days / 365, 1)
        return 0

    def to_dict(self):
        return {
            "id":              self.id,
            "name":            self.name,
            "category":        self.category,
            "brand":           self.brand,
            "description":     self.description,
            "condition":       self.condition,
            "lifecycle_stage": self.lifecycle_stage,
            "purchase_price":  self.purchase_price,
            "weight_kg":       self.weight_kg,
            "age_years":       self.age_years(),
            "image":           self.image,
            "owner_id":        self.owner_id,
            # Phase 2 fields
            "material":        self.material,
            "co2_saved_kg":    self.co2_saved_kg,
            "resale_estimate": self.resale_estimate,
            # AI-scan tracking
            "source":            self.source or "manual",
            "ai_recommendation": self.ai_recommendation,
            "ai_score":          self.ai_score,
            "analysis_ref":      self.analysis_ref,
            "created_at":        self.created_at.isoformat() if self.created_at else None,
            "updated_at":        self.updated_at.isoformat() if self.updated_at else None,
        }


class ProductEvent(db.Model):
    """Timeline entry for one tracked item (added, AI-analyzed, listed, donated ...)."""
    __tablename__ = "product_events"

    id         = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    owner_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stage      = db.Column(db.String(50), nullable=False)
    note       = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id, "product_id": self.product_id, "stage": self.stage,
            "note": self.note, "created_at": self.created_at.isoformat(),
        }


def log_product_event(product, stage: str, note: str = ""):
    """Append a timeline event (caller commits)."""
    db.session.add(ProductEvent(product_id=product.id, owner_id=product.owner_id,
                                stage=stage, note=(note or "")[:400]))
