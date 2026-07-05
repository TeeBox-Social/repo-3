# TeeBox — Product Requirements Document

## Vision
A dedicated social community for golfers: log rounds, share course reviews, and follow fellow players through a live activity feed. TeeBox positions itself as the frictionless bridge from your on-course tracker (Garmin Golf, The Grint) to the group chat: tap Share in those apps and TeeBox opens pre-filled — no CSV export needed.

## Personas
- **Weekend Warrior** — plays 1–2 rounds a week, wants to share highlights and razz friends.
- **Grinder** — cares about stats (fairways, GIR, putts) and course conditions.
- **New Golfer** — welcoming aesthetic; low-friction sign-up.

## Core Features (v1 — this build)
1. **Auth** — email/password JWT auth; secure token storage via expo-secure-store.
2. **Feed** — glass sticky header, tactile round cards with score pill, photos, likes, comments, pull-to-refresh.
3. **Log a Round** — course, score, par, holes, fairways, GIR, putts, notes, up to 3 photos (base64). Accepts pre-fill via share deep link `teebox://share?course=...&score=...&par=...&notes=...`.
4. **Discover** — search Golfers and Courses (pill-style segmented control).
5. **User Profile** — cover image, avatar, stats (handicap/rounds/avg/best), your rounds.
6. **Other Profile** — follow/unfollow, follower counts.
7. **Post Detail** — hero photo, big scorecard, mini-stats, comment thread, sticky comment bar.
8. **Course Detail** — rating stars, write review, list reviews.

## Share Extension (Native — post-EAS build)
- Expo Go cannot host native share extensions. The app registers `teebox://` deep link + `NSExtensionActivationRule` config that will forward tapped Share data from Garmin Golf / The Grint into `teebox://share?course=...&score=...` on a custom dev/production build.
- The Log Round screen already handles the pre-fill and shows a "Pre-filled from …" banner.

## Growth Enhancement (Business Angle)
- **Course Ambassador program** — the golfer with the highest avg star-rating on a course is auto-featured on the course detail. Encourages high-quality reviews and creates a shareable badge (drives referrals to the app). Ready to layer on top of `/api/courses/{name}/reviews`.

## Iteration 3 additions
- **Fractional star ratings (0.25 step)** via `StarPicker` (drag or tap) — numeric value shown in a dark pill (e.g. `4.25 / 5.00`). `StarDisplay` renders fractional stars using a clipped overlay.
- **Handicap filter chips on reviews**: `All · Low (<10) · Mid (10–20) · High (20+)`. No-HC reviewers lumped into All.
- Each review card shows the reviewer's numeric rating (brand-green pill) and the current course average (`avg X.XX`), tinted green if their rating is above the average, warm-orange if below.
- **Master course catalog** — 30 famous real courses (Pebble Beach, TPC Sawgrass, Bandon Dunes, St Andrews Old, Bethpage Black, Augusta National, etc.) auto-seeded on empty DB with `city / region / country / lat / lng`.
- **OpenStreetMap Overpass bulk import** — `POST /api/courses/import-osm?bbox=...` pulls golf courses from the free OSM Overpass API (no key). Dedupes by name.
- **Open in Maps** pill on Course Detail hero — fires `Linking.openURL` to `google.com/maps/search/?api=1&query=<course>+<city>+<region>` (opens the Google Maps app on iOS/Android, browser on web).
- Discover Courses list shows `city, region` under each course.

## Iteration 3 API additions
- `GET /api/courses/{name}` — course metadata (city/region/country/lat/lng) + play_count + review_count + avg_rating.
- `POST /api/courses/import-osm?bbox=south,west,north,east` — OSM Overpass bulk import.
- `POST /api/courses/reviews` — `rating` is now `float` in [1.0, 5.0]; server rounds to nearest 0.25.
- `GET /api/courses/{name}/reviews` — each review's `author` now includes `handicap`.

## Iteration 4 — Security audit remediation
- **SEC-001 (Critical)** JWT secret rotated to 96-char random hex; server refuses to boot when `JWT_SECRET_KEY` is <32 chars or contains any of `change_me / changeme / placeholder / changethis / your-secret`.
- **SEC-002 (Medium)** Email field stripped from EVERY public user response (`/discover/users`, `/users/{id}`, feed / rounds / comments / reviews author payloads). `/auth/me` still returns the caller's own email since they own it.
- **SEC-003 (Medium)** Photo payloads capped at ~1 MB base64 each, avatars at ~600 KB, and rounds are hard-capped at 3 photos. Non-image data URIs rejected with 415.
- **SEC-004 (Medium)** All user-supplied search queries fed to Mongo `$regex` are now (a) length-capped at 60 chars and (b) meta-char-escaped, blocking ReDoS and pattern surprises like `.*`.
- **SEC-005 (Low)** Demo seed (both the manual `POST /api/seed` endpoint and the on-empty-DB startup autopull) is gated behind `ENABLE_DEMO_SEED` (`true` in dev, `false` for production deploys). When off, `POST /api/seed` returns 404 and no demo users are created.

## Iteration 5 — Hardening + Wishlist
- **Rate limiting** via `slowapi`: `/auth/login` = 10/min · 60/hour, `/auth/register` = 5/min · 20/hour, `/auth/refresh` = 60/min. Key function is proxy-aware — prefers `cf-connecting-ip` → `x-forwarded-for` → socket peer, so limits actually bind per real client behind Cloudflare / ingress.
- **CORS from env**: `CORS_ALLOWED_ORIGINS` (comma-separated). `*` in dev; set to your web origin in prod.
- **Short-lived access + rotating refresh tokens** — access = 15 min, refresh = 30 days. Refresh tokens tracked in `refresh_tokens` collection with `jti / family_id / is_rotated / is_revoked`. Every refresh mints a new pair and marks the old one rotated. **Reuse of a rotated refresh nukes the whole family** (compromised-device signal). TTL index expires records past `exp`. `/auth/logout` server-revokes the refresh. Access-token type-claim guards prevent using a refresh token as a bearer.
- **Frontend refresh flow** — `src/api.ts` transparently handles 401s: single-flight refresh queue (concurrent 401s only issue ONE refresh), swap in new access, replay the original request. On refresh failure the auth-context is notified via `setOnAuthLost` and the user returns to sign-in.
- **Wishlist** — per-user list of courses to play.
  - `POST /api/wishlist { course_name }`, `DELETE /api/wishlist/{course_name}`, `GET /api/wishlist/check/{course_name}`, `GET /api/users/{id}/wishlist`.
  - `GET /api/users/{id}` now returns `wishlist_count`.
  - Frontend: `WishlistButton` toggle pill next to "Open in Maps" on Course Detail; horizontal-scroll wishlist section on own Profile (with × remove) and read-only version on another user's profile.

## Iteration 6 — Profile editor, pinned rounds, friends
- **Profile editor** (`/profile/edit`) — modal form for display name, handicap, home course, bio, avatar (photo picker → base64). Handicap and other clearable fields can now be blanked out (`PATCH /api/auth/me` uses `exclude_unset=True` so an explicit `null` reaches Mongo `$set` while omitted fields stay untouched).
- **Handicap next to name** — Profile header shows `Reese Callahan · 8.4 HCP` (handicap inline, hidden when null).
- **New 4-stat row on both own Profile and other users' User Detail** — Rounds / Avg / Courses / Friends. Best score removed from UI (still stored per round). Courses = distinct `course_name` count. Friends = mutual-follow count.
- **Pin a round to your profile** — `POST /api/rounds/{id}/pin` (owner-only), `DELETE /api/users/me/pin`, both mediated by a "Pin to profile" ↔ "Pinned" pill in the Post Detail header for the round's owner. Pinned round appears with a **"Pinned round"** badge at the top of "Your rounds" on Profile / User Detail. Stale pins auto-clear server-side when the underlying round is deleted.
- **Friends screen** (`/user/[id]/friends`) — reachable by tapping the Friends stat on any profile. Lists mutual-follow friends of the profile owner with:
  - "Mutual friend" badge (viewer↔them mutual), "You follow" badge (viewer→them one-way), or "You" pill.
  - "X mutual with you" summary in the header when viewing someone else.
  - Per-item Follow/Following toggle button.
  - Tap the row to jump to that user's profile.
- Endpoint additions: `GET /api/users/{id}/friends`, `POST /api/rounds/{id}/pin`, `DELETE /api/users/me/pin`.

## Tech
- **Backend**: FastAPI + MongoDB (motor). JWT via python-jose. Bcrypt password hashing via passlib.
- **Frontend**: Expo SDK 54 + expo-router file-based routing. React Native only. `expo-image`, `expo-linear-gradient`, `expo-blur`, `@expo/vector-icons` (Ionicons), `expo-image-picker` (base64 photos), `expo-secure-store`.
- **Design**: `4 Tactile / Playful LIGHT` per design_guidelines.json — fairway green + warm off-white, chunky pill-radius CTAs, tactile shadows.

## Endpoints (all under `/api`)
Auth: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `PATCH /auth/me`
Rounds: `GET /feed`, `POST /rounds`, `GET /rounds/{id}`, `DELETE /rounds/{id}`, `POST /rounds/{id}/like`, `GET /rounds/{id}/comments`, `POST /rounds/{id}/comments`
Users: `GET /users/{id}`, `GET /users/{id}/rounds`, `POST /users/{id}/follow`
Discover: `GET /discover/users?q=`, `GET /discover/courses?q=`
Reviews: `GET /courses/{course_name}/reviews`, `POST /courses/reviews`
Utility: `POST /seed` (idempotent), `GET /` (health)
