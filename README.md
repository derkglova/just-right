# Just Right

A bake planner for small cafés and bakeries in Malaysia that tells the manager how much of each item to bake tomorrow, so less food is thrown away and fewer items sell out.

## Team Information

| Field | Details |
|---|---|
| Team Name | Beginathon |
| Team Domain | Domain 2: Orbyte Smart SME Challenge |
| SDG Track (1–17) | SDG 8: Decent Work and Economic Growth (also SDG 12: Responsible Consumption and Production) |
| Team Leader | Derek Chay Wen Hong |
| University | Multimedia University, Cyberjaya |
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
Small cafés and bakeries guess how much to bake each day. Bake too much and leftovers go in the bin; bake too little and items sell out by lunch and sales are lost. Nobody tracks leftovers or sell-outs, so the same mistakes repeat every week. TODO: add survey findings and a cited figure.

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

## Tech Stack

| Layer | Technology |
|---|---|
| Messaging | Telegram Bot API (pyTelegramBotAPI) |
| Frontend | HTML + React (runtime from CDN) + Chart.js, served by Flask |
| Backend | Python, Flask, APScheduler |
| Database | SQLite |
| AI / Compute | scikit-learn (linear regression per item), runs on CPU |
| Weather | Open-Meteo API (free, no key) |
| Hosting / Dev | Replit |

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

📄 Proof of use: `submission/SDC2026_Beginathon_Replit_POU.pdf`

## How We Use RunPod
Not used. Our app has no GPU workload (training, fine-tuning or GPU inference), which the committee confirmed is fine.

## Data
All sales data is **synthetic** (`scripts/generate_data.py`): 120 days for 3 items, with realistic patterns (weekends sell more, rainy days sell less). The weather is **real** past weather for Cyberjaya from Open-Meteo. No real personal, customer or company data is used. The dashboard labels everything as sample data.

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

## Team

| Name | Role | GitHub |
|---|---|---|
| Derek Chay Wen Hong | Team lead / developer | @TODO |
| Tan Jun Hao | Product, research and pitch | @TODO |

## Submission Checklist
- [x] Team name, domain and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [x] RunPod not required (no GPU workload)
- [ ] Preliminary submission completed (`SDC2026_Beginathon_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_Beginathon_TechDeclaration.pdf`)
- [ ] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License
This project is licensed under the Apache License 2.0.
