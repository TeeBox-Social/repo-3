"""Pydantic v1 request/response models for the TeeBox API."""
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=1, max_length=40)
    home_course: Optional[str] = None
    handicap: Optional[float] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshIn(BaseModel):
    refresh_token: str


class RoundIn(BaseModel):
    course_name: str = Field(default="", max_length=120)
    date: Optional[str] = None  # ISO date
    total_score: Optional[int] = None
    par: Optional[int] = 72
    holes_played: Optional[int] = 18
    fairways_hit: Optional[int] = None
    greens_in_regulation: Optional[int] = None
    putts: Optional[int] = None
    notes: Optional[str] = ""
    photos: List[str] = []  # base64 data URIs
    weather: Optional[str] = None
    hole_scores: List[int] = []
    hole_pars: List[int] = []
    # NEW: post-type discriminator + LFG-only fields
    post_type: Optional[str] = Field(default="round", pattern="^(round|text|lfg)$")
    meetup_date: Optional[str] = None
    looking_for_count: Optional[int] = Field(default=None, ge=1, le=8)


class RoundUpdate(BaseModel):
    """Partial update — only supplied fields are patched. Author-only."""
    course_name: Optional[str] = Field(default=None, max_length=120)
    date: Optional[str] = None
    total_score: Optional[int] = None
    par: Optional[int] = None
    holes_played: Optional[int] = None
    fairways_hit: Optional[int] = None
    greens_in_regulation: Optional[int] = None
    putts: Optional[int] = None
    notes: Optional[str] = None
    photos: Optional[List[str]] = None
    weather: Optional[str] = None
    hole_scores: Optional[List[int]] = None
    hole_pars: Optional[List[int]] = None
    post_type: Optional[str] = Field(default=None, pattern="^(round|text|lfg)$")
    meetup_date: Optional[str] = None
    looking_for_count: Optional[int] = Field(default=None, ge=1, le=8)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    mentions: List[str] = []


class CommentUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    mentions: Optional[List[str]] = None


class ReviewIn(BaseModel):
    course_name: str
    rating: float = Field(ge=1.0, le=5.0)
    text: str = Field(min_length=1, max_length=1000)


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    home_course: Optional[str] = Field(default=None, max_length=120)
    handicap: Optional[float] = Field(default=None, ge=-10, le=54)
    bio: Optional[str] = Field(default=None, max_length=280)
    avatar: Optional[str] = None  # base64
    notification_prefs: Optional[dict] = None


class WishlistIn(BaseModel):
    course_name: str = Field(min_length=1, max_length=120)


class NewCourseIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    par: int = Field(ge=27, le=90)
    city: Optional[str] = Field(default=None, max_length=80)
    region: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=60)


class RejectIn(BaseModel):
    reason: Optional[str] = Field(default="", max_length=280)


class PurgeIn(BaseModel):
    domains: Optional[List[str]] = None
    dry_run: bool = False


class RequestResetIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=200)


class TokenIn(BaseModel):
    token: str


class ResendVerifyIn(BaseModel):
    email: EmailStr


class GoogleAuthIn(BaseModel):
    """Payload from the mobile/web client after Emergent OAuth redirect.

    ``session_id`` is the temporary token from the ``#session_id=`` fragment
    returned by ``auth.emergentagent.com``. The backend swaps it once with
    Emergent's session-data API to fetch the verified Google identity.
    """
    session_id: str = Field(min_length=8, max_length=200)
