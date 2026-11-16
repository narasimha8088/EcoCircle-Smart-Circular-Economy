from __future__ import annotations

from typing import Optional
from datetime import datetime
from extensions import db

class Listing(db.Model):
    __tablename__ = "listings"

    id          = db.Column(db.Integer, primary_key=True)
    product_id  = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    seller_id   = db.Column(db.Integer, db.ForeignKey("users.id"),    nullable=False)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price       = db.Column(db.Float, nullable=False)
    condition   = db.Column(db.String(50))
    category    = db.Column(db.String(100))
    listing_type= db.Column(db.String(20), default="sell")  # sell / rent / exchange
    location    = db.Column(db.String(150))
    status      = db.Column(db.String(20), default="active")  # active / sold / expired
    image       = db.Column(db.String(255))
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(
        self,
        product_id: int = 0,
        seller_id: int = 0,
        title: str = "",
        description: str = "",
        price: float = 0.0,
        condition: str = "Good",
        category: str = "",
        listing_type: str = "sell",
        location: str = "",
        status: str = "active",
        image: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            product_id=product_id,
            seller_id=seller_id,
            title=title,
            description=description,
            price=price,
            condition=condition,
            category=category,
            listing_type=listing_type,
            location=location,
            status=status,
            image=image,
            **kwargs,
        )

    def to_dict(self):
        from models.user_model import User
        seller = User.query.get(self.seller_id)
        return {
            "id":           self.id,
            "product_id":   self.product_id,
            "seller_id":    self.seller_id,
            "seller_name":  seller.name if seller else "Unknown",
            "title":        self.title,
            "description":  self.description,
            "price":        self.price,
            "condition":    self.condition,
            "category":     self.category,
            "listing_type": self.listing_type,
            "location":     self.location,
            "status":       self.status,
            "image":        self.image,
            "created_at":   self.created_at.strftime("%d %b %Y"),
        }
