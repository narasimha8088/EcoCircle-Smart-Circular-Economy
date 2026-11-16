from __future__ import annotations

from typing import Optional
from extensions import db
from datetime import datetime

class RepairCenter(db.Model):
    __tablename__ = "repair_centers"
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    location     = db.Column(db.String(200))
    service_type = db.Column(db.String(100))
    rating       = db.Column(db.Float, default=0.0)
    lat          = db.Column(db.Float)
    lng          = db.Column(db.Float)
    contact      = db.Column(db.String(50))

    def __init__(
        self,
        name: str = "",
        location: Optional[str] = None,
        service_type: Optional[str] = None,
        rating: float = 0.0,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        contact: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            location=location,
            service_type=service_type,
            rating=rating,
            lat=lat,
            lng=lng,
            contact=contact,
            **kwargs,
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "location": self.location,
                "service_type": self.service_type, "rating": self.rating,
                "lat": self.lat, "lng": self.lng, "contact": self.contact}
