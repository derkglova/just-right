# Just Right

An AI bake planner for small cafés and bakeries in Malaysia that tells the manager how much of each item to bake tomorrow, so less food is thrown away and fewer items sell out. Built as a bake-planning module for the Orbyte business hub (simulated).

## Team Information

| Field | Details |
|---|---|
| Team Name | Beginathon |
| Team Domain | Domain 2: Orbyte Smart SME Challenge |
| SDG Track (1–17) | SDG 8: Decent Work and Economic Growth (also SDG 12: Responsible Consumption and Production) |
| Domain Sponsor | Alpha Red Solutions (Orbyte) |
| Team Leader | Derek Chay Wen Hong |
| Leader Contact | pixel4470@gmail.com · 011-1246 2899 |
| University | Multimedia University (MMU), Cyberjaya |
| Number of Members | 2 |

## Links

| Resource | Link |
|---|---|
| GitHub Repository | https://github.com/derkglova/just-right |
| Replit Project | https://replit.com/@linegidid/just-right |
| Live Demo | https://just-right-linegidid.replit.app (dashboard) · Telegram bot: https://t.me/justright_bakery_bot |
| RunPod Endpoint | Not used (no GPU workload) |
| Slide Deck | TODO |
| Demo Video | TODO |

## Overview

### Problem
Small cafés and bakeries in Malaysia decide every day how many croissants, loaves and muffins to bake, and most decide from memory. Bake too much and leftovers go in the bin; bake too little and items sell out by lunch and sales are lost. Nobody records leftovers or sell-out times, so the same mistakes repeat every week.

- **National scale:** Malaysians discard about **6,000 tonnes of edible food every day** (2025), up from about 5,000 tonnes in 2024 (SWCorp data, reported by *New Straits Times*, 15 June 2026).
- **What we saw:** we visited three bakeries. Bakefield (independent) estimates its daily bake by rule of thumb and discounts unsold bread at closing. The chains rely on policy instead: La Boheme bases quantities on past sales and discounts daily; Hokkaido bakes again when items sell out and returns unsold stock to its factory. None of the three records a forecast.
- **The two mistakes don't cost the same:** throwing away a croissant loses its ingredient cost (about RM 2), while running out loses the profit on a sale (about RM 6). So "zero waste" is the wrong goal, and small shops have no analyst or forecasting tools to find the right amount.

### Solution
At closing, staff log leftovers in Telegram (about 30 seconds). Right after, an AI forecast learns from that day's sales and sends the manager tomorrow's bake plan, with a short reason for each number. The manager approves in one tap, and the baker gets the final list at a set time.

**The AI component:** a scikit-learn model predicts how many of each item customers will buy tomorrow from past sales, the day of the week and the weather forecast (Open-Meteo). It retrains after every closing count, so it keeps learning. It checks itself by comparing its past predictions with what really sold. On the sample data it misses by about 2.4 pieces per item, against 3.2 for a plain 28-day average (25% better).

Because running out usually costs more than a leftover, the planner then uses the newsvendor model to aim for the *right* amount of waste per item, not zero.

### Key Features
- **AI demand forecast:** predicts tomorrow's sales per item from past sales, the weekday and the weather, and explains each number (e.g. "~33 sell · rain -7, Sunday +3").
- **Daily bake plan:** a recommended quantity per item, compared with today's bake.
- **One-tap approval in Telegram:** only the manager can approve or edit; every action is logged.
- **One-off events:** when the manager edits a plan for a big order, the AI learns less from that unusual day.
- **Sell-out aware:** estimates hidden demand when items sell out, so it can say "bake more", not just "bake less".
- **Role-based Telegram bot:** manager, baker and staff each see only their own commands.
- **Close shop button or timer:** starts the staff closing count; the baker gets the approved list at a set time.
- **Manager dashboard:** today's and tomorrow's plan, AI accuracy, food waste in RM per week, sell-outs, activity log, item prices and costs.
- **Records + CSV export:** each day's plan next to what was baked, sold and left over.

## Impact

| | |
|---|---|
| **SDG targets** | **12.3:** halve per-capita food waste at retail and consumer levels by 2030. **8.2:** higher productivity through technological upgrading and innovation. |
| **Baseline** | About 6,000 tonnes of edible food discarded per day in Malaysia (SWCorp, 2025). None of the 3 bakeries we visited records a forecast. Our simulated bakery wastes about RM 340 per week across 3 items when it bakes its usual fixed batch. |
| **KPIs** | 1) Weekly food waste per shop in RM and pieces, tracked together with the number of sell-outs (so waste isn't cut by under-baking). 2) Forecast error: average pieces off per item per day, vs a plain 28-day average. |
| **Phase 2 targets** | 20% lower weekly food waste (RM) than the usual-batch baseline on our simulated test, with no increase in sell-outs. Forecast error at least 25% lower than a plain average (currently 2.4 vs 3.2 pieces). |

Figures are based on simulated data and will be re-checked with real shop data.

## Design Thinking
- **Empathise:** visited three bakeries (Bakefield, La Boheme, Hokkaido) to learn how quantities are decided and what happens to leftovers.
- **Define:** the real burden is daily overproduction and sell-outs, not selling leftovers.
- **Ideate:** our first idea, a clearance marketplace, was dropped after critique and mentor feedback (it needed a consumer audience and didn't fit Orbyte as a business hub).
- **Prototype:** the smallest loop that works end to end: closing count → forecast → plan → approval → bake list → log.
- **Test:** unit tests for the forecast, planner and database, plus a day-by-day backtest of the model on historical data.

Telegram was chosen because staff already use it: no training, and only one message a day for the manager.

## Tech Stack

| Layer | Technology |
|---|---|
| Messaging | Telegram Bot API (pyTelegramBotAPI) |
| Frontend | HTML + React (runtime from CDN) + Chart.js, served by Flask |
| Backend | Python, Flask, APScheduler |
| Database | SQLite |
| AI / Compute | scikit-learn (linear regression per item), runs on CPU |
| Weather | Open-Meteo API (free, no key) |
| Hosting / Dev | Replit Deployments (Reserved VM, Asia, 0.5 vCPU / 2 GiB), GitHub |

## Project Structure

```
.
├── docs/
│   └── documentation.md     # API documentation
├── scripts/
│   └── generate_data.py     # Creates the synthetic sales history
├── src/
│   ├── backend/
│   │   ├── main.py          # Entry point: dashboard + JSON API + bot + scheduler
│   │   ├── planner.py       # Bake-quantity logic (newsvendor model)
│   │   ├── forecast.py      # AI demand forecast (scikit-learn)
│   │   ├── weather.py       # Weather history + forecast (Open-Meteo, cached)
│   │   ├── bot.py           # Telegram bot
│   │   ├── db.py            # SQLite storage
│   │   ├── scheduler.py     # Daily timers (close shop, bake list to baker)
│   │   └── data/            # Simulated Orbyte data (items, shop, sales history, weather cache)
│   └── frontend/            # Manager dashboard (served by main.py)
├── submission/              # Required submission PDFs
├── tests/
│   ├── test_planner.py
│   ├── test_db.py
│   └── test_forecast.py
├── .env.example
├── .gitignore
├── .replit
├── LICENSE
├── pyproject.toml           # Python dependencies (uv)
└── README.md
```

## Architecture

```
Close shop (button or timer)
        │
        ▼
Staff closing count (Telegram) ──► SQLite (daily sales, plans, activity log)
        │                                   ▲
        ▼                                   │
AI forecast (scikit-learn) ◄── weather (Open-Meteo)
        │
        ▼
Planner (newsvendor) ──► Manager approves / edits in Telegram ──► Baker gets the bake list
                                            │
                                            ▼
                          Web dashboard (manager): plans, AI accuracy, waste, records
```

Everything runs in one Python process: the Flask dashboard + JSON API, the Telegram bot (polling) and the daily timers.
See [`docs/documentation.md`](docs/documentation.md) for every API endpoint.

Orbyte is simulated with synthetic data. In a real deployment, sales, costs and staff roles would come from the Orbyte hub.

## How to Run

### Option 1: Run on Replit (recommended)
1. Import this repository into Replit (Create Repl → Import from GitHub).
2. Open the Secrets tab and add the variables listed in `.env.example`.
3. Click Run. Replit uses `.replit` to start `python src/backend/main.py`.

### Option 2: Run locally
```bash
git clone https://github.com/derkglova/just-right.git
cd just-right
python -m venv venv             # Python 3.11+
source venv/bin/activate        # Windows: venv\Scripts\activate
uv sync                         # or: pip install flask==3.0.3 pyTelegramBotAPI==4.21.0 APScheduler==3.10.4 python-dotenv==1.0.1 requests scikit-learn
cp .env.example .env            # then fill in your values
python src/backend/main.py      # dashboard on http://localhost:8080 + Telegram bot
```

Other useful commands:
```bash
python scripts/generate_data.py  # regenerate the synthetic sales history
python src/backend/planner.py    # print tomorrow's plan in the terminal
python src/backend/db.py         # print the latest plan and the activity log
```

Only one copy of the bot can run per Telegram token. Stop the local one before running on Replit, and the other way round.

### Run tests
```bash
python -m unittest discover tests
```

## How We Use Replit (Required)
- **Hosting:** the bot, dashboard and daily timers run as one always-on Replit deployment (Reserved VM) at the Live Demo link above. Autoscale isn't used because the bot must stay awake.
- **Secrets:** the Telegram token and user IDs are stored in Replit Secrets, never in the code.
- **Dependencies:** Replit installs them from `pyproject.toml` / `uv.lock` (`uv sync`) when deploying.
- **Development:** code is pushed to GitHub, pulled into the Replit workspace, then redeployed.
- **Sponsor resource:** Replit Core (sponsor-provided platform and credits).

📄 Proof of use: `submission/SDC2026_Beginathon_Replit_POU.pdf`

## How We Use RunPod
Not used. Our app has no GPU workload (training, fine-tuning or GPU inference), which the committee confirmed is fine.

## Data
All sales data is **synthetic** (`scripts/generate_data.py`): 120 days for 3 items, with realistic patterns (weekends sell more, rainy days sell less). The weather is **real** past weather for Cyberjaya from Open-Meteo. No real personal, customer or company data is used. The dashboard labels everything as sample data.

## Third-Party Libraries & Data

| Name | Used for | License |
|---|---|---|
| Flask 3.0.3, APScheduler 3.10.4, python-dotenv 1.0.1 | Web server, timers, config | BSD-3-Clause, MIT |
| pyTelegramBotAPI 4.21.0 | Telegram bot client | GPL-2.0 |
| scikit-learn, NumPy, requests | ML library (model trained by us), HTTP | BSD-3-Clause, Apache-2.0 |
| React, Chart.js 4.4.1 (CDN) | Dashboard UI and charts | MIT |
| Open-Meteo weather data | Weather history and forecast | CC BY 4.0 |

No GenAI/LLM APIs are used in the app: the forecast model runs inside our own code.

## AI Tools Used in Development

| Tool | Used for | Extent |
|---|---|---|
| Claude Code (Anthropic) | Writing and debugging backend, bot and dashboard code | Major |
| Claude (Anthropic) chat | Brainstorming, critique, planning, documentation drafts, starter planner and forecast code | Major |
| Claude design (Anthropic) | Dashboard visual design mock-up | Moderate |
| Replit Agent | Initial project import set-up (its changes were later discarded) | Minor |

The problem, solution design and technical decisions (newsvendor rule, forecast features, roles, scope) were made by our team. We read and edited all AI-generated code, ran unit tests, back-tested the model and tested the bot and dashboard end to end on Replit.

## Privacy & Limitations
- **Data:** no customer data is collected. The app stores shop data (daily bake, sales and leftover counts, plans, activity log) and, for staff, their Telegram user ID, display name and role. The Telegram token and IDs live in Replit Secrets. Open-Meteo only receives the shop's coordinates.
- **Synthetic data:** the accuracy figures show the method, not real-shop performance.
- **Simple model:** a linear model is explainable but can miss unusual patterns; new shops use a plain average until there is enough history.
- **Safety nets:** weather forecasts can be wrong, so changes are capped at ±15% per day and the manager approves every plan. If Open-Meteo is down, cached weather is used.

## Challenges & Learnings
- **Telegram limits:** a bot can only message people who pressed Start, and button taps must be answered within about 15 seconds. We handle both cases.
- **One bot, one copy:** running the bot locally and on Replit at the same time makes Telegram reject one of them, so only one copy may run.
- **Hidden demand:** when an item sells out, sales understate demand, so we scale demand up based on how early it sold out.
- **Keeping the AI explainable:** we chose a linear model so every number can be explained to the manager ("Saturday +4, rain -3").
- **Unusual days:** one-off events (big orders) would mislead the model, so the manager can mark them and they count less.

## Future Improvements
- Real POS connection through Orbyte
- What to do with leftovers: discount, staff meal or donation
- Understanding messy staff notes in Manglish
- A WhatsApp version for hawkers and small stalls

## Acknowledgements
- SDC mentor Muhammad Fadli bin Md Khalid (KrackedDevs) for the idea review on 21 Oct 2026.
- The bakeries we visited: Bakefield, La Boheme and Hokkaido.

## Team

| Name | Role | GitHub |
|---|---|---|
| Derek Chay Wen Hong | Team lead / developer | [@derkglova](https://github.com/derkglova) |
| Tan Jun Hao | Product, research and pitch | [@tanjunhao2504-ai](https://github.com/tanjunhao2504-ai) |

## Submission Checklist
- [x] Team name, domain and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [x] RunPod not required (no GPU workload)
- [x] Preliminary submission completed (`SDC2026_Beginathon_Preliminary.pdf`)
- [x] Technology declaration completed (`SDC2026_Beginathon_TechDeclaration.pdf`)
- [ ] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License
This project is licensed under the Apache License 2.0.
