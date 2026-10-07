# TUMO Astana: Learner Schedule Lookup

A single bilingual page (RU / ҚАЗ) where parents and learners type a learner's full name and see their schedule card: schedule, coach, room, TUMO email, a status badge, and optionally the temporary first-login password. Below the search are an FAQ and the contact block.

- **Backend:** Python + FastAPI. It reads every tab of a Google Sheet and keeps the data in an in-memory cache that is also saved to disk.
- **Frontend:** Vue 3 + Vite + TypeScript + Tailwind CSS, with Axios. Translations use a small built-in helper (`src/i18n.ts`), not a library.
- **Data:** a Google Sheet that the team edits, with any number of tabs. No database to look after.

```
backend/
  app/main.py                  app factory: health, admin refresh, serves the built frontend
  app/api/endpoints/schedule.py  POST /api/schedule/lookup
  app/schemas/schedule.py      public response shapes (the only data sent to browsers)
  app/services/sheets.py       dynamic multi-tab sheet parser
  app/core/config.py           settings (env vars / .env)
  app/store.py, app/sources.py cache + background sync, mock / Google Sheets sources
  data/mock_sheet.json         sample sheet (made-up data)
frontend/  Vue 3 page: search + ScheduleCard, FAQ, support block
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
| `нурлан айбар` | finds "Айбар Нұрлан Серікұлы", badge "Активный график" |
| `асел толеген` | another learner from the same tab (Russian headers, title row above them) |
| `тимур ахметов` | tab with English headers in a different order, badge "График изменён" |
| `алия серикова` | tab with no header row at all (positional columns) |
| `мадина ержанова` | no schedule yet, so the badge reads "График уточняется" |
| `данияр беков` | learner marked inactive |
| `алия сер` | too vague (more than 3 matches), so nothing is shown |
| `Айбар` | asks for both first name and surname |

To see the temporary password on the card, start the backend with `EXPOSE_TEMP_PASSWORD=true`.

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

Every tab is read, so you can keep one tab per batch or group. Columns are matched **by header name**, in any order. Matching ignores case, extra spaces and Russian word endings, and partial headers work, so "ФИО ученика" counts as ФИО.

| Field | Header examples | On the card? |
|---|---|---|
| Full name (**required**) | `ФИО ребенка`, `ФИО`, `ФИО ученика`, `Full Name` | yes |
| Schedule | `Расписание`, `График`, `Schedule` | yes |
| Coach | `Coach`, `Коуч` (falls back to `ex-Coach` when empty) | yes |
| Room | `Зона`, `Кабинет`, `Комната`, `Room` | yes |
| Email | `Почта TUMO`, `Почта`, `Email` | yes |
| Temporary password | `Пароль`, `Временный пароль`, `Password` | only if `EXPOSE_TEMP_PASSWORD=true` |
| TUMO ID | `TUMO ID`, `ID` | never (used to spot the same learner in two tabs) |
| Status | `Статус`, `Status` (optional) | as the badge |

- **Header row:** title rows above the headers are fine; the parser looks for the header row in the top 5 rows. A tab with no header row is read in the order of the table above, and rows with fewer than 3 filled cells (notes, titles) are skipped. Tabs with no names, such as notes, are ignored.
- **Multi-line cells** are joined with ", ", so a `Зона` of "WR 5" + new line + "3 этаж" shows as "WR 5, 3 этаж".
- **Batch export layout** ("Batch №N - Распределение между коучами"): two capacity rows, then the header at row 3. The parent and child personal columns (ФИО/ИИН/почта/номер родителя, почта/номер/ИИН/ДР ребенка) are ignored completely, as are columns with an empty header. Supported as-is.
- **Badge:**
  - With no `Статус` column, the badge shows **"Активный график"** when a schedule is filled in and **"График уточняется"** when it isn't. A schedule containing "(лист ожидания)" shows **"Лист ожидания"**.
  - Recognised status values: `График изменен`, `Коуч изменен`, `В обработке`, `Неактивен`.
  - `Неактивен` hides the learner's card. Any other status text is shown as typed.
- **Ambiguous headers:** a header that mentions two fields, such as "Email коуча", isn't treated as the learner's email. It's kept server-side only.
- **Kazakh mode:** weekday names in the schedule are translated automatically (Вторник → Сейсенбі).
- **Columns never kept:** columns whose header looks like an IIN (ИИН/ЖСН), phone, birth date, address or parent details are dropped. So are 12-digit IIN-shaped values in other columns. Even so, **don't put IINs in the sheet**.

### Serving CSV exports instead

Export each tab with *File → Download → CSV* and put the files in `backend/data/csv/`, which is git-ignored. Then set `DATA_SOURCE=csv` (and optionally `CSV_PATH`, which can be a single file or a folder). Each file counts as one tab, named after the file. **These exports contain IINs and phone numbers: never commit them.** The parser drops those columns, but the files themselves are still sensitive.

### Connecting the real sheet

1. In Google Cloud, create a project, enable the **Google Sheets API**, and create a **service account**. Download its JSON key and save it as `backend/credentials.json`. This file is git-ignored; never commit it.
2. Share the spreadsheet with the service account's email address (`…@….iam.gserviceaccount.com`). **Viewer** access is enough.
3. Copy `backend/.env.example` to `backend/.env` and set:
   ```
   DATA_SOURCE=google
   GOOGLE_SHEET_ID=<the long id from the sheet URL>
   ```

## How it keeps running

- **No network on the request path.** Lookups read an in-memory index. The Google API is only called by a background sync, once per `SYNC_INTERVAL_SECONDS`, and each sync makes two requests: one to list the tabs (so new tabs are picked up) and one **batched read of all tabs**.
- **Falls back to the cache automatically.** If a sync fails (quota, network, bad credentials, broken sheet), the app keeps serving the last good data, and `/api/health` reports `degraded`.
- **Survives restarts.** Each good snapshot is written atomically to `data/cache/snapshot.json`. On startup this file loads first, so the app works straight away even if Google is down.
- **Optional instant refresh.** Set `ADMIN_TOKEN`, then `curl -X POST -H "X-Admin-Token: …" /api/admin/refresh` to sync right after editing the sheet. This endpoint is disabled when no token is set.

## Editing the page text

- **All text:** `frontend/src/locales/ru.ts` and `kk.ts` hold every piece of text on the page, including the FAQ questions and answers. Add an FAQ entry to both files.
- **Contacts:** the email, WhatsApp number, Instagram and website are in `frontend/src/config.ts`. The "написать в WhatsApp" button opens a chat with a pre-filled message that includes the name typed in the search box.

## Privacy

- **The API returns only what the card shows.** The response shape (`app/schemas/schedule.py`) has no field for TUMO ID, IIN or other extra columns, so they can't be returned.
- **Temporary passwords are off by default.** They are returned only when `EXPOSE_TEMP_PASSWORD=true`.
  - **Risk while it's on:** anyone who knows a learner's full name can see that learner's password until they change it. Turn it on for onboarding, and off again afterwards.
  - **On the card:** the password is masked until "Показать" is pressed.
- **The cache file is owner-only.** `data/cache/snapshot.json` is written with `0600` permissions because it can contain temporary passwords.
- **Sensitive columns are dropped** during parsing (see "The Google Sheet" above).
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
