from __future__ import annotations

from typing import Optional
from extensions import db
from datetime import datetime

class RecyclingCenter(db.Model):
    __tablename__ = "recycling_centers"
    id                 = db.Column(db.Integer, primary_key=True)
    name               = db.Column(db.String(200), nullable=False)
    location           = db.Column(db.String(200))
    accepted_materials = db.Column(db.String(300))
    lat                = db.Column(db.Float)
    lng                = db.Column(db.Float)
    contact            = db.Column(db.String(50))

    def __init__(
        self,
        name: str = "",
        location: Optional[str] = None,
        accepted_materials: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        contact: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            location=location,
            accepted_materials=accepted_materials,
            lat=lat,
            lng=lng,
            contact=contact,
            **kwargs,
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "location": self.location,
                "accepted_materials": self.accepted_materials,
                "lat": self.lat, "lng": self.lng, "contact": self.contact}
