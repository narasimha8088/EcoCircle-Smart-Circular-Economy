from __future__ import annotations

from typing import Optional
from extensions import db
from datetime import datetime, timezone, date
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = "users"

    id          = db.Column(db.Integer, primary_key=True)
    user_number = db.Column(db.String(20), unique=True, nullable=True)  # ECO-XXXX format
    name        = db.Column(db.String(100), nullable=False)
    email       = db.Column(db.String(120), unique=True, nullable=False)
    password    = db.Column(db.String(255), nullable=False)
    location    = db.Column(db.String(150))
    avatar      = db.Column(db.String(255), default="default.png")
    is_admin    = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    last_login  = db.Column(db.DateTime, nullable=True)
    # Gamification
    eco_score        = db.Column(db.Integer, default=0, nullable=False)
    login_streak     = db.Column(db.Integer, default=0, nullable=False)
    last_streak_date = db.Column(db.Date, nullable=True)   # date of last streak increment
    # Camera-based Face Recognition
    face_descriptor  = db.Column(db.Text, nullable=True)   # JSON array of 128 floats (face-api.js descriptor)

    products = db.relationship("Product", backref="owner",  lazy=True)
    listings = db.relationship("Listing", backref="seller", lazy=True)

    def __init__(
        self,
        name: str = "",
        email: str = "",
        password: str = "",
        user_number: Optional[str] = None,
        location: Optional[str] = None,
        avatar: str = "default.png",
        is_admin: bool = False,
        eco_score: int = 0,
        login_streak: int = 0,
        last_streak_date: Optional[date] = None,
        face_descriptor: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            email=email,
            password=password,
            user_number=user_number,
            location=location,
            avatar=avatar,
            is_admin=is_admin,
            eco_score=eco_score,
            login_streak=login_streak,
            last_streak_date=last_streak_date,
            face_descriptor=face_descriptor,
            **kwargs,
        )

    def set_password(self, pwd):
        self.password = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password, pwd)

    def update_streak(self):
        """Call on each login to keep consecutive-day streak accurate."""
        today = datetime.now(timezone.utc).date()
        if self.last_streak_date is None:
            self.login_streak     = 1
            self.last_streak_date = today
        elif self.last_streak_date == today:
            pass  # already updated today
        elif (today - self.last_streak_date).days == 1:
            self.login_streak    += 1
            self.last_streak_date = today
        else:
            # streak broken
            self.login_streak     = 1
            self.last_streak_date = today

    def badge(self):
        """Return the user's gamification rank based on eco_score."""
        s = self.eco_score or 0
        if s >= 1000: return {"label": "Eco Champion 🏆", "level": 5}
        if s >= 500:  return {"label": "Green Hero 🌿",    "level": 4}
        if s >= 200:  return {"label": "Earth Saver 🌍",   "level": 3}
        if s >= 50:   return {"label": "Eco Starter 🌱",   "level": 2}
        return             {"label": "Newcomer 🌰",         "level": 1}

    def to_dict(self):
        from models.product_model import Product
        product_count = Product.query.filter_by(owner_id=self.id).count()
        is_new = product_count == 0
        b = self.badge()
        return {
            "id":                  self.id,
            "user_number":         self.user_number,
            "name":                self.name,
            "email":               self.email,
            "location":            self.location,
            "avatar":              self.avatar,
            "is_admin":            self.is_admin,
            "joined":              self.created_at.strftime("%B %Y"),
            "last_login":          self.last_login.isoformat() if self.last_login else None,
            "is_new_user":         is_new,
            "face_unlock_enabled": self.face_descriptor is not None,
            "eco_score":           self.eco_score or 0,
            "login_streak":        self.login_streak or 0,
            "badge_label":         b["label"],
            "badge_level":         b["level"],
        }
