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
Staff log leftovers at closing in Telegram (about 30 seconds). Just Right learns what really sells and, every afternoon, sends the manager tomorrow's bake plan with a reason for each number. The manager approves in one tap, and the baker gets the final list. Because running out usually costs more than a leftover, the planner uses the newsvendor model to aim for the *right* amount of waste per item, not zero. TODO: describe the AI component.

### Key Features
- **Daily bake plan:** a recommended quantity per item, with a plain-language reason.
- **One-tap approval in Telegram:** only the manager can approve or edit; every action is logged.
- **Sell-out aware:** estimates hidden demand when items sell out, so it can say "bake more", not just "bake less".
- **Manager dashboard:** plan status, activity log, food waste in RM per week, item prices and costs.

## Tech Stack

| Layer | Technology |
|---|---|
| Messaging | Telegram Bot API (pyTelegramBotAPI) |
| Frontend | HTML + Chart.js (served by Flask) |
| Backend | Python, Flask, APScheduler |
| Database | SQLite |
| AI / Compute | TODO |
| Hosting / Dev | Replit |

## Project Structure

```
.
├── docs/                    # Screenshots, diagrams
├── scripts/
│   └── generate_data.py     # Creates the synthetic sales history
├── src/
│   ├── main.py              # Entry point: dashboard + bot
│   ├── planner.py           # Bake-quantity logic (newsvendor model)
│   ├── bot.py               # Telegram bot
│   ├── db.py                # SQLite storage
│   ├── templates/           # Dashboard page
│   └── data/                # Simulated Orbyte data (items, shop, sales history)
├── submission/              # Required submission PDFs
├── tests/
│   └── test_planner.py
├── .env.example
├── .gitignore
├── .replit
├── LICENSE
├── pyproject.toml           # Python dependencies (uv)
└── README.md
```

## Architecture

```
Simulated Orbyte data (sales, prices, costs, roles)
        │
        ▼
   Planner ──► Telegram bot ──► Manager approves / edits ──► Baker gets bake list
        │                              │
        ▼                              ▼
     SQLite  ◄──────────── activity log, plans, daily counts
        │
        ▼
 Web dashboard (manager only)
```

Orbyte is simulated with synthetic data. In a real deployment, sales, costs and staff roles would come from the Orbyte hub.

## How to Run

### Option 1: Run on Replit (recommended)
1. Import this repository into Replit (Create Repl → Import from GitHub).
2. Open the Secrets tab and add the variables listed in `.env.example`.
3. Click Run. Replit uses `.replit` to start `python src/main.py`.

### Option 2: Run locally
```bash
git clone TODO
cd just-right
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
uv sync                         # or: pip install flask==3.0.3 pyTelegramBotAPI==4.21.0 APScheduler==3.10.4 python-dotenv==1.0.1
cp .env.example .env            # then fill in your values
python src/main.py
```

### Run tests
```bash
python -m unittest discover tests
```

## How We Use Replit (Required)
- **Hosting:** the bot and dashboard run as one Replit deployment at the Live Demo link above.
- **Secrets:** the Telegram token and user IDs are stored in Replit Secrets, never in the code.
- TODO: add anything else.

📄 Proof of use: `submission/SDC2026_Beginathon_Replit_POU.pdf`

## How We Use RunPod
Not used. Our app has no GPU workload (training, fine-tuning or GPU inference), which the committee confirmed is fine.

## Data
All data is **synthetic** (`scripts/generate_data.py`). No real personal, customer or company data is used.

## Challenges & Learnings
- TODO

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
- [ ] No API keys or secrets committed to the repository

## License
This project is licensed under the Apache License 2.0.
