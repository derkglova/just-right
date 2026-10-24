# Just Right: API documentation

The backend (`src/backend/main.py`) serves the manager dashboard and a small JSON API.
The dashboard (`src/frontend/`) calls these endpoints. You can also open any `GET` endpoint in a browser.

- **Base URL:** `http://localhost:8080` locally, or the Replit deployment URL.
- **Format:** JSON in and out (except the CSV download).
- **Login:** none (hackathon MVP). Anyone with the URL can call the API.
- **Data:** synthetic sample data (simulated Orbyte). Numbers are estimates.
- **Time zone:** Asia/Kuala_Lumpur.

> After changing backend code, restart `python src/backend/main.py` (or redeploy on Replit).
> A `405 Method Not Allowed` on a new endpoint usually means the server is still running old code.

---

## Overview

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | [`/api/plan`](#get-apiplan) | Tomorrow's plan |
| `GET` | [`/api/plan/today`](#get-apiplantoday) | Today's plan (what is being baked today) |
| `POST` | [`/api/recalculate`](#post-apirecalculate) | Work out tomorrow's plan fresh (no Telegram message) |
| `POST` | [`/api/send-plan`](#post-apisend-plan) | Send tomorrow's plan to the manager's Telegram |
| `GET` | [`/api/log`](#get-apilog) | Activity log, newest first |
| `GET` | [`/api/waste`](#get-apiwaste) | Waste and sell-outs (this week, last week, earlier weeks) |
| `GET` | [`/api/forecast`](#get-apiforecast) | AI accuracy, what it learned, tomorrow's weather |
| `GET` | [`/api/records`](#get-apirecords) | Day by day: plan vs closing count |
| `GET` | [`/api/records.csv`](#get-apirecordscsv) | Same as records, as a CSV download |
| `GET` | [`/api/items`](#get-apiitems) | Items with price, cost, usual batch |
| `POST` | [`/api/items`](#post-apiitems) | Save edited prices, costs, usual batches |
| `POST` | [`/api/telegram/close`](#post-apitelegramclose) | Close shop: ask staff for the closing count now |
| `POST` | [`/api/telegram/baker`](#post-apitelegrambaker) | Send the approved bake list to the baker now |
| `GET` | [`/api/schedule`](#get-apischedule) | Daily timers (close shop, baker list) |
| `POST` | [`/api/schedule`](#post-apischedule) | Change the daily timers |

Approving and editing the plan happen **only in Telegram**, not through the API.

---

## Plans

### `GET /api/plan`
Tomorrow's plan. If none exists yet, one is worked out (pending, no Telegram message).

```json
{
  "date": "2026-10-25",
  "status": "pending",
  "approved_by": null,
  "approved_at": null,
  "bake_list_sent": false,
  "items": [
    {
      "item_id": "croissant",
      "item": "Croissant",
      "usual": 40,
      "recommended": 35,
      "bake": 35,
      "edited": false,
      "reason": "~33 sell · rain -7, Sunday +3"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `status` | `pending` or `approved` |
| `recommended` | What the planner suggested |
| `bake` | Final amount, after any manager edit |
| `edited` | `true` if the manager changed it |
| `bake_list_sent` | `true` once the baker has received this plan |
| `reason` | Expected sales and what pushes it up or down vs a usual day |

### `GET /api/plan/today`
Today's plan, in the same shape. If there was no plan for today: `"status": "none"` and `"items": []`.

### `POST /api/recalculate`
Works out tomorrow's plan again from the latest sales and weather. It replaces any earlier
edits and approval for tomorrow. Nothing is sent to Telegram. Returns the new plan (same shape as `GET /api/plan`).

### `POST /api/send-plan`
Sends tomorrow's plan, as it is, to the manager's Telegram with **Approve** / **Edit** buttons.
Returns the plan (same shape as `GET /api/plan`).

---

## Activity log

### `GET /api/log`
Who did what and when, newest first.

| Query | Default | Meaning |
|---|---|---|
| `limit` | `30` | How many entries |

```json
[
  {
    "who": "Line",
    "role": "manager",
    "type": "approval",
    "action": "Plan approved: Plan for 2026-10-25: Croissant 35, Sourdough loaf 13, Banana muffin 20",
    "at": "2026-10-24T18:32:10+08:00"
  }
]
```

- `role`: `manager`, `staff` or `system`
- `type` (used by the dashboard filters): `approval`, `edit`, `count` or `plan`

---

## Waste and AI forecast

### `GET /api/waste`
"This week" = the last 7 days with data; "last week" = the 7 days before.

```json
{
  "this_week": [{ "item": "Croissant", "cost": 2.0, "leftovers": 24, "last_week": 26 }],
  "sellouts": [{ "item": "Croissant", "day": "Fri", "time": "17:00" }],
  "last_week_sellouts": 1,
  "weekly": [{ "week": "26 Jun", "rm": 334.0 }]
}
```

- Waste in RM = `leftovers × cost`.
- `sellouts.time` is a rough time from the staff's sell-out bucket (before 12 → 11:00, 12–2 → 13:00, 2–4 → 15:00, after 4 → 17:00).
- `weekly` lists the older full weeks, oldest first.

### `GET /api/forecast`
How accurate the AI is. For each past day, the model was trained **only on earlier days**,
then compared with what really sold (a backtest), next to the old 28-day average.

```json
{
  "ai_miss": 2.4,
  "old_miss": 3.2,
  "days": [{ "date": "2026-08-24", "ai": 1.84, "old": 2.37 }],
  "trained_days": 120,
  "event_days": 0,
  "effects": [
    {
      "item": "Croissant",
      "weekday": { "Mon": -2.6, "Tue": -3.2, "Wed": -1.6, "Thu": -0.6, "Fri": 1.1, "Sat": 4.1, "Sun": 2.8 },
      "rain_10mm": -4.6,
      "temp_1c": 0.1,
      "error": 3.2,
      "days": 120
    }
  ],
  "tomorrow": { "date": "2026-10-25", "rain": 21.0, "temp": 30.1 }
}
```

| Field | Meaning |
|---|---|
| `ai_miss` / `old_miss` | Average miss in pieces per item over the last 30 days |
| `days` | Miss per day (last 60 days), for the chart |
| `effects.weekday` | Extra pieces sold on that weekday vs an average day |
| `effects.rain_10mm` | Change in pieces for 10 mm of rain |
| `event_days` | One-off event days, which count 5× less when the model learns |
| `tomorrow` | Weather forecast for tomorrow (Open-Meteo) |

---

## Records

### `GET /api/records`
One entry per day, newest first: that day's plan next to its closing count.

| Query | Default | Meaning |
|---|---|---|
| `days` | `30` | How many days |

```json
[
  {
    "date": "2026-10-24",
    "source": "count",
    "counted": true,
    "event": null,
    "plan": { "status": "approved", "approved_by": "Line", "approved_at": "2026-10-23T18:32:10+08:00" },
    "items": [
      { "item": "Croissant", "planned": 43, "recommended": 43, "baked": 43,
        "sold": 42, "leftover": 1, "sold_out": null, "waste_rm": 2.0 }
    ],
    "leftover": 3,
    "waste_rm": 10.0,
    "sellouts": 0
  }
]
```

- `source`: `count` (staff counted on Telegram), `sample` (generated data) or `null` (not counted yet)
- `event`: the note if the manager marked the day as a one-off event, else `null`
- `sold_out`: rough sell-out time, or `null`

### `GET /api/records.csv`
The same records as a CSV download (`just-right-records.csv`), one row per day per item.
Opens in Excel or Google Sheets. Default `days=365`.

```
date,item,planned,approved_by,baked,sold,leftover,sold_out_around,waste_rm,source
2026-10-24,Croissant,43,Line,43,42,1,,2.0,staff count
```

---

## Items

### `GET /api/items`
```json
[{ "id": "croissant", "name": "Croissant", "price": 8.0, "cost": 2.0,
   "usual_batch": 40, "lead_time": "day before", "target_level": 0.75 }]
```
`target_level` is the share of days we aim to have enough: `(price − cost) / price`.

### `POST /api/items`
Saves edited items to `data/items.json`; the planner uses them from the next plan on.
Items are matched by `id` or `name`.

```json
[{ "id": "croissant", "price": 8.5, "cost": 2.0, "usual_batch": 42 }]
```

Returns the updated items. **400** if a number is invalid or the cost isn't between 0 and the price.

---

## Telegram actions

### `POST /api/telegram/close`
Close shop now: every staff member (or the manager, if no staff are set) gets the closing count on Telegram.
When the count is done, the manager gets the summary and then tomorrow's new plan.

```json
{ "sent_to": 1 }
```

### `POST /api/telegram/baker`
Sends the approved bake list to the baker now.

```json
{ "sent": true }
```

**409** if the plan isn't approved yet, or the baker can't be reached:
```json
{ "error": "Approve the plan first." }
```

---

## Timers

### `GET /api/schedule`
```json
{
  "close": { "time": "18:00", "auto": true, "next_run": "2026-10-24T18:00:00+08:00" },
  "baker": { "time": "20:00", "auto": true, "next_run": "2026-10-24T20:00:00+08:00" }
}
```

- `close`: daily close-shop message (starts the closing count).
- `baker`: daily time the approved bake list goes to the baker. Approving after this time sends it right away.
- `next_run` is `null` when the timer is off.

### `POST /api/schedule`
Change one or both timers. Send only what you want to change.

```json
{ "close": { "time": "18:30", "auto": true }, "baker": { "auto": false } }
```

Returns the new schedule. **400** if a time isn't `HH:MM`.

---

## Telegram bot commands

| Command | Who | What it does |
|---|---|---|
| `/start` | Everyone | Shows what you can do, and your Telegram ID |
| `/plan` | Manager | Tomorrow's plan with **Approve** / **Edit** buttons |
| `/bakelist` | Baker | The approved bake list |
| `/count` | Staff | Closing count: leftovers per item, and when sold-out items ran out |

Roles come from the Telegram IDs in `.env` / Replit Secrets: `MANAGER_TELEGRAM_ID`, `BAKER_TELEGRAM_ID`, `STAFF_TELEGRAM_IDS`.

## Daily loop

1. **Close shop:** the dashboard button or the close timer.
2. **Staff count** leftovers on Telegram. The manager gets the summary.
3. **The AI retrains** with today's count and the manager gets **tomorrow's plan** right away.
4. **The manager approves** (or edits) in Telegram.
5. **The baker gets the bake list** at the baker timer (or right away if the timer is off or has passed).
