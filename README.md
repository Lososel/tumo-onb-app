# TUMO Astana: Student Dashboard

A small, mobile-first app. Students type their name and see their personal TUMO schedule (self-study and workshops), a WhatsApp group link, and a short guide to how TUMO works.

- **Backend:** Python + FastAPI. It reads a Google Sheet and keeps the data in an in-memory cache that is also saved to disk.
- **Frontend:** Vue 3 + Vite + TypeScript + Tailwind CSS, with Vue Router and Axios.
- **Data:** a Google Sheet that the team edits. No database to look after.

```
backend/   FastAPI app, mock data, tests
frontend/  Vue 3 app (Home, Dashboard, Guide)
Dockerfile one image that serves both the API and the built frontend
```

## Quick start (mock data, no credentials needed)

```bash
# Backend: http://localhost:8000  (API docs at /docs)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# Frontend: http://localhost:5173  (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Names you can try from `backend/data/mock_sheet.json`:

| Name | Result |
|---|---|
| Aruzhan Smagulova | dashboard with 1 workshop |
| Daniyar Bekov | dashboard with 2 workshops |
| аружан касымова | Cyrillic name, falls back to the default WhatsApp link |
| Timur Akhmetov | "inactive" state |
| anything else | "not found" state |

Lookup ignores case, extra spaces, accents, and word order, so "bekov daniyar" also works.

Run the tests with `cd backend && pytest`.

## The Google Sheet

Create one spreadsheet with **three tabs**. The tab names must match exactly. Put the headers in row 1; header matching ignores case and spaces.

**Students**

| first_name | last_name | status | self_study_days | self_study_time | workshops | whatsapp_link |
|---|---|---|---|---|---|---|
| Aruzhan | Smagulova | active | Mon, Wed | 15:00–17:00 | ANIM-1 | *(optional)* |

- `status`: anything other than `inactive` / `no` / `0` / `false` / `left` / `paused` / `archived` counts as active.
- `workshops`: workshop ids or names, separated by commas.
- `whatsapp_link`: optional, for this student only. Without it, the app uses the workshop's link, then `whatsapp_default`.

**Workshops**

| id | name | teacher | room | days | time | whatsapp_link |
|---|---|---|---|---|---|---|
| ANIM-1 | 2D Animation | Madina K. | Lab 2 | Tue, Fri | 16:00–18:00 | https://chat.whatsapp.com/… |

**Links**

| key | value |
|---|---|
| whatsapp_default | https://chat.whatsapp.com/… |

To change a schedule, edit the row. The app picks up the change at the next sync (every 5 minutes by default).

### Connecting the real sheet

1. In Google Cloud, create a project, enable the **Google Sheets API**, and create a **service account**. Download its JSON key and save it as `backend/credentials.json`. This file is git-ignored; never commit it.
2. Share the spreadsheet with the service account's email address (`…@….iam.gserviceaccount.com`). **Viewer** access is enough.
3. Copy `backend/.env.example` to `backend/.env` and set:
   ```
   DATA_SOURCE=google
   GOOGLE_SHEET_ID=<the long id from the sheet URL>
   ```

## How it keeps running

- **No network on the request path.** Lookups read an in-memory index. The Google API is only called by a background sync, once per `SYNC_INTERVAL_SECONDS`, and that sync fetches all three tabs in a **single batched request**.
- **Falls back to the cache automatically.** If a sync fails (quota, network, bad credentials, broken sheet), the app keeps serving the last good data, and `/api/health` reports `degraded`.
- **Survives restarts.** Each good snapshot is written atomically to `data/cache/snapshot.json`. On startup this file loads first, so the app works straight away even if Google is down.
- **Optional instant refresh.** Set `ADMIN_TOKEN`, then `curl -X POST -H "X-Admin-Token: …" /api/admin/refresh` to sync right after editing the sheet. This endpoint is disabled when no token is set.

## Privacy

- **Only allow-listed columns are kept.** Columns are allow-listed (see `backend/app/sheet.py`). Any other column, such as an IIN or phone number added by mistake, is dropped during parsing. It is never cached, saved to disk, or returned by the API. Even so, **don't put IINs in the sheet**.
- **The API returns only what the dashboard shows:** first and last name, schedule, workshop name/teacher/room, and the WhatsApp link. There is no search-as-you-type or name listing, so the API can't be used to list students. Lookups are rate-limited per IP (`LOOKUP_RATE_LIMIT_PER_MINUTE`).
- **Names stay out of URLs and logs.** The frontend uses `POST`, so names never appear in URLs or access logs. A `GET` variant exists for convenience. The result is kept in `sessionStorage` only, so it is gone when the tab closes.

## Deploying

The simplest option is one container, which serves both the API and the built frontend:

```bash
docker build -t tumo-dashboard .
docker run -p 8000:8000 \
  -e DATA_SOURCE=google -e GOOGLE_SHEET_ID=… \
  -v $PWD/backend/credentials.json:/app/backend/credentials.json:ro \
  tumo-dashboard
```

Without Docker: run `npm run build` in `frontend/`, then run uvicorn in `backend/`. FastAPI serves `frontend/dist` automatically when it exists (`STATIC_DIR`).

Behind a reverse proxy, set `FORWARDED_ALLOW_IPS` to the proxy's IP so rate limiting sees each client's real IP.

All settings are listed in `backend/.env.example` and `frontend/.env.example`.
