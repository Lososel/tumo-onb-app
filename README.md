# TUMO Astana: Learner Schedule Lookup

A single bilingual page (RU / ҚАЗ) where parents and learners type a learner's full name and see their current schedule, coach, learning stage, and the status of their schedule-change request. Below the search are an FAQ and the contact block.

- **Backend:** Python + FastAPI. It reads a Google Sheet and keeps the data in an in-memory cache that is also saved to disk.
- **Frontend:** Vue 3 + Vite + TypeScript + Tailwind CSS, with Axios. Translations use a small built-in helper (`src/i18n.ts`), not a library.
- **Data:** one Google Sheet tab that the team edits. No database to look after.

```
backend/   FastAPI app, mock data, tests
frontend/  Vue 3 page: search + learner card, FAQ, support block
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

Searches you can try from `backend/data/mock_sheet.json` (all names are made up):

| Search | Result |
|---|---|
| `нурлан айбар` | finds "Айбар Нұрлан Серікұлы", badge "Коуч без изменений" |
| `асел толеген` | "График изменён", with the team's own note in RU and KK |
| `тимур ахметов` / `мадина ержанова` | "Коуч изменён" / "Заявка в обработке" |
| `данияр беков` | learner marked inactive |
| `алия сер` | too vague (more than 3 matches), so nothing is shown |
| `Айбар` | asks for both first name and surname |

### How name search works

`POST /api/schedule/lookup` with `{"query": "нуртас елмурат"}` finds "Елмұрат Нұртас Медеуұлы":

- Matching ignores case, extra spaces, and word order.
- Kazakh letters are matched to their Russian look-alikes (ұ→у, қ→к, ә→а, і→и, ...). ё matches е, and й matches и.
- Each word you type must be the start of a *different* word in the name, so `нурт елму` also matches.
- Privacy rules:
  - At least two words of 2+ letters are required.
  - If more than 3 learners match, the search returns nothing and asks for the full name.
  - Lookups are rate-limited per IP.
  - There is no autocomplete or name list, so the API can't be used to list learners.

## The Google Sheet

Create a tab named **`Learners`**. Put the headers in row 1; header matching ignores case and spaces, and Russian header names also work.

| full_name | schedule | self_study_day | coach | coach_email | stage | status | note | active |
|---|---|---|---|---|---|---|---|---|
| Айбар Нұрлан Серікұлы | Вторник/Пятница 16:30-18:30 | Пятница | Aliya | coach@… | Самообучение | Коуч без изменений | *(optional)* | *(blank = active)* |

- **`status`:** shown as the badge, with a standard explanation underneath. Recognised values:
  - `Коуч без изменений`
  - `Коуч изменен`
  - `График изменен`
  - `Без изменений`
  - `В обработке`

  Any other text is shown as typed, without an explanation.
- **`stage`:** `Самообучение`, `Воркшоп` or `Проект` (other text is shown as typed).
- **`note`:** a free-text note from the team, shown in a blue box. Add `note_kk` to give a Kazakh version.
- **Kazakh schedule text:** in Kazakh mode, weekday names in `schedule` and `self_study_day` are translated automatically (Вторник → Сейсенбі). To write the Kazakh text yourself, add `schedule_kk` / `self_study_day_kk` columns.
- **`active`:** `нет` / `no` / `0` hides the learner's schedule.

Any other column is ignored and never cached. Even so, **don't put IINs in the sheet**.

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

## Editing the page text

- **All text:** `frontend/src/locales/ru.ts` and `kk.ts` hold every piece of text on the page, including the FAQ questions and answers. Add an FAQ entry to both files.
- **Contacts:** the email, WhatsApp number, Instagram and website are in `frontend/src/config.ts`. The "написать в WhatsApp" button opens a chat with a pre-filled message that includes the name typed in the search box.

## Privacy

- **Only allow-listed columns are kept** (see `backend/app/sheet.py`). Any other column, such as an IIN or phone number added by mistake, is dropped during parsing.
- **The API returns only what the card shows.**
- **Names stay out of URLs and logs.** The search uses `POST`, and nothing about the learner is stored in the browser. Only the chosen language is remembered.

## Deploying

The simplest option is one container, which serves both the API and the built frontend:

```bash
docker build -t tumo-schedule .
docker run -p 8000:8000 \
  -e DATA_SOURCE=google -e GOOGLE_SHEET_ID=… \
  -v $PWD/backend/credentials.json:/app/backend/credentials.json:ro \
  tumo-schedule
```

Without Docker: run `npm run build` in `frontend/`, then run uvicorn in `backend/`. FastAPI serves `frontend/dist` automatically when it exists (`STATIC_DIR`).

Behind a reverse proxy, set `FORWARDED_ALLOW_IPS` to the proxy's IP so rate limiting sees each client's real IP.

All settings are listed in `backend/.env.example` and `frontend/.env.example`.
