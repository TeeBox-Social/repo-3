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

## Iteration 2 additions
- **Log tab icon** normalized to standard `add-circle-outline` (matches sibling tabs, no floating pill).
- **Hole-by-hole scorecard** — Log Round: toggle-revealed 18-hole grid, auto-sums into total score. Post Detail: read-only color-coded grid (birdie / par / bogey / double).
- **Mentions in comments** — `@name` autocomplete driven by `/api/discover/users`, tap to insert `@Display_Name`, rendered in brand green inside the comment. Web caret handled declaratively (no `setNativeProps` crash).
- **Followers-only feed** — Home feed uses `GET /api/feed?scope=followers` (default). No "All" toggle in Home. "All rounds here" section only appears inside Course Detail (via `GET /api/courses/{name}/rounds`).
- **Achievements & badges** — computed on the fly per user: On the tee, Broke 100/90, First sub-80, Sub-70 club, Regular (10 rounds), Half-century (50 rounds), Course collector (5 courses), Hot streak (3 rounds ≤ 80 in a row).
- **Seed** now creates mutual follows across the 3 demo users so the followers-only feed is populated on first launch.

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
