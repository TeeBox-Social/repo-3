"""MongoDB client + collection handles used across the codebase.

Centralised so routers/helpers can import the collections they need without
tangling with FastAPI or duplicating config.
"""
from motor.motor_asyncio import AsyncIOMotorClient

from config import DB_NAME, MONGO_URL

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_col = db.users
rounds_col = db.rounds
likes_col = db.likes
comments_col = db.comments
follows_col = db.follows
reviews_col = db.course_reviews
courses_col = db.courses
refresh_tokens_col = db.refresh_tokens
wishlists_col = db.wishlists
import_jobs_col = db.import_jobs
notifications_col = db.notifications
lfg_interests_col = db.lfg_interests
