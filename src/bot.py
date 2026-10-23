"""Telegram bot (pyTelegramBotAPI).

Each person only sees their own role's commands (set by Telegram ID in .env):
- everyone: /start  says hello; unknown users get their ID to send to the manager.
- manager:  /plan   tomorrow's plan with [Approve] and [Edit] buttons.
- baker:    /bakelist  the approved bake list.
- staff:    /count  closing count: leftovers per item, and when sold-out items ran out.

Only the manager can use the Approve and Edit buttons.
On approve, the bake list goes to the baker. Plans and every action are saved in
the database (db.py), so they survive a restart and show up in the activity log.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from dotenv import load_dotenv
from telebot.apihelper import ApiTelegramException
from telebot.types import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup

import db
from planner import load_data, make_plan

load_dotenv()

TZ = ZoneInfo(os.environ.get("TZ", "Asia/Kuala_Lumpur"))
MANAGER_ID = int(os.environ["MANAGER_TELEGRAM_ID"])
BAKER_ID = int(os.environ.get("BAKER_TELEGRAM_ID") or MANAGER_ID)   # no baker set: manager gets the list
STAFF_IDS = {int(x) for x in os.environ.get("STAFF_TELEGRAM_IDS", "").split(",") if x.strip()}

bot = telebot.TeleBot(os.environ["TELEGRAM_TOKEN"])

STATUS_LABEL = {"pending": "Pending approval", "approved": "Approved"}

# What each role can do. This drives /start and the "/" command menu.
ROLE_COMMANDS = {
    "manager": [BotCommand("plan", "See tomorrow's plan and approve or edit it")],
    "baker": [BotCommand("bakelist", "See the approved bake list")],
    "staff": [BotCommand("count", "Closing count: enter today's leftovers")],
}

# Sell-out time buckets (keys match SOLD_OUT_UPLIFT in planner.py).
SOLD_OUT_BUCKETS = {"before_12": "Before 12", "12_2": "12-2 PM", "2_4": "2-4 PM", "after_4": "After 4 PM"}

# Closing counts in progress, one per chat: {chat_id: {"date", "items", "index", "results"}}
counts = {}


def is_manager(user_id: int) -> bool:
    return user_id == MANAGER_ID


def roles_of(user_id: int) -> list[str]:
    """One person can have several roles (e.g. in testing, the same ID everywhere)."""
    roles = []
    if user_id == MANAGER_ID:
        roles.append("manager")
    if user_id == BAKER_ID:
        roles.append("baker")
    if user_id in STAFF_IDS:
        roles.append("staff")
    return roles


def role_of(user) -> str:
    """The main role, for the activity log."""
    roles = roles_of(user.id)
    return roles[0] if roles else "unknown"


def commands_for(user_id: int) -> list[BotCommand]:
    commands = [BotCommand("start", "What I can do for you")]
    for role in roles_of(user_id):
        commands += ROLE_COMMANDS[role]
    return commands


def set_menu(user_id: int) -> None:
    """Show this person only their own commands when they type "/"."""
    try:
        bot.set_my_commands(commands_for(user_id), scope=BotCommandScopeChat(user_id))
    except ApiTelegramException as e:
        # Happens if they never opened the bot. They get their menu when they send /start.
        print(f"Could not set the menu for {user_id}: {e.description}")


def set_all_menus() -> None:
    bot.set_my_commands([BotCommand("start", "What I can do for you")])   # everyone else
    for user_id in {MANAGER_ID, BAKER_ID, *STAFF_IDS}:
        set_menu(user_id)


def name_of(user) -> str:
    return user.first_name or user.username or str(user.id)


def answer(call, text: str = None, alert: bool = False) -> None:
    """Reply to a button tap (the small popup). Telegram only accepts this for about
    15 seconds, so for an old tap it fails. That is harmless: log it and carry on."""
    try:
        bot.answer_callback_query(call.id, text, show_alert=alert)
    except ApiTelegramException as e:
        print(f"Could not answer button tap: {e.description}")


def plan_text(plan: list[dict]) -> str:
    """plan is the list of rows from db.get_plan(), one per item."""
    first = plan[0]
    lines = [f"Bake plan for {first['plan_date']} (sample data, estimated)", ""]
    for p in plan:
        change = p["final"] - p["usual"]
        sign = f"+{change}" if change > 0 else str(change)
        lines.append(f"{p['item_name']}: {p['final']} ({sign} vs usual {p['usual']})")
        lines.append(f"  {p['reason']}")
    lines.append("")
    lines.append(f"Status: {STATUS_LABEL[first['status']]}")
    if first["status"] == "approved":
        lines.append(f"Approved by {first['decided_by']} at {first['decided_at'][11:16]}")
    return "\n".join(lines)


def plan_buttons(plan_date: str) -> InlineKeyboardMarkup:
    # The plan date is part of each button, so a button always acts on its own plan.
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Approve", callback_data=f"approve:{plan_date}"),
        InlineKeyboardButton("Edit", callback_data=f"edit:{plan_date}"),
    )
    return markup


def send_plan(chat_id: int = MANAGER_ID, actor_name: str = "Scheduler", role: str = "system") -> None:
    """Work out tomorrow's plan, save it as pending, and send it with Approve/Edit buttons."""
    items, _ = load_data()
    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date().isoformat()
    db.save_plan(tomorrow, make_plan(items, db.sales_history()))
    db.log(actor_name, role, "Plan sent", f"Plan for {tomorrow} sent for approval")
    bot.send_message(chat_id, plan_text(db.get_plan(tomorrow)), reply_markup=plan_buttons(tomorrow))


def check_can_change(call, plan_date: str, action: str):
    """Shared checks for Approve and Edit. Returns the plan rows, or None if blocked."""
    user = call.from_user
    if not is_manager(user.id):
        db.log(name_of(user), role_of(user), "Blocked", f"Tried to {action} the plan for {plan_date}")
        answer(call, f"Only the manager can {action} this plan.", alert=True)
        return None
    plan = db.get_plan(plan_date)
    if not plan:
        answer(call, "That plan is gone. Send /plan again.")
        return None
    if plan[0]["status"] == "approved":
        answer(call, "This plan is already approved.")
        return None
    return plan


@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    roles = roles_of(user_id)
    set_menu(user_id)

    if not roles:
        bot.reply_to(
            message,
            "Hi! I'm Just Right, the bakery's planning bot.\n"
            "You're not set up yet. Send this ID to your manager:\n"
            f"{user_id}",
        )
        return

    lines = [f"Hi! I'm Just Right. You're set up as: {', '.join(roles)}.", ""]
    for command in commands_for(user_id)[1:]:   # skip /start itself
        lines.append(f"/{command.command} - {command.description}")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["plan"])
def handle_plan(message):
    user = message.from_user
    if not is_manager(user.id):
        bot.reply_to(message, "Only the manager can see and approve the plan.")
        return
    send_plan(message.chat.id, name_of(user), role_of(user))


@bot.message_handler(commands=["bakelist"])
def handle_bakelist(message):
    if "baker" not in roles_of(message.from_user.id):
        bot.reply_to(message, "Only the baker can see the bake list.")
        return
    plan = db.latest_plan()
    if not plan or plan[0]["status"] != "approved":
        bot.reply_to(message, "No approved bake list yet. You'll get it here as soon as the manager approves.")
        return
    bot.reply_to(message, bake_list_text(plan))


def bake_list_text(plan: list[dict]) -> str:
    items = "\n".join(f"{p['item_name']}: {p['final']}" for p in plan)
    return f"Approved bake list for {plan[0]['plan_date']}:\n\n{items}"


# ---- Closing count (staff) ----

def count_recipients() -> set[int]:
    """Who does the closing count: the staff, or the manager if no staff are set."""
    return STAFF_IDS or {MANAGER_ID}


def start_count(actor_name: str = "Scheduler", role: str = "system") -> int:
    """Ask everyone who counts to do the closing count now. Returns how many got the message."""
    sent = 0
    for chat_id in count_recipients():
        try:
            begin_count(chat_id)
            sent += 1
        except ApiTelegramException as e:
            # Telegram won't let a bot message someone who never opened it.
            print(f"Could not start the count for {chat_id}: {e.description}")
    db.log(actor_name, role, "Count requested", f"Closing count sent to {sent} staff")
    return sent


def begin_count(chat_id: int) -> None:
    today = datetime.now(TZ).date().isoformat()
    # How many were baked today: the approved plan if there is one, else the usual batch.
    plan = db.get_plan(today)
    baked = {p["item_id"]: p["final"] for p in plan if p["status"] == "approved"}
    items, _ = load_data()
    counts[chat_id] = {
        "date": today,
        "items": [{"id": i["id"], "name": i["name"], "baked": baked.get(i["id"], i["usual_batch"])} for i in items],
        "index": 0,
        "results": [],
    }
    bot.send_message(chat_id, f"Shop's closed! Time for the closing count ({today}).")
    ask_next_item(chat_id)


def ask_next_item(chat_id: int, user=None) -> None:
    state = counts[chat_id]
    if state["index"] == len(state["items"]):
        finish_count(chat_id, user)
        return
    item = state["items"][state["index"]]
    prompt = bot.send_message(chat_id, f"{item['name']} (baked {item['baked']}): how many are left? Send a number.")
    bot.register_next_step_handler(prompt, receive_leftover)


def receive_leftover(message):
    chat_id = message.chat.id
    state = counts.get(chat_id)
    if state is None:
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        del counts[chat_id]
        bot.reply_to(message, "Count stopped. Send /count to start again.")
        return

    item = state["items"][state["index"]]
    if not text.isdigit() or int(text) > item["baked"]:
        prompt = bot.reply_to(message, f"Please send a number from 0 to {item['baked']}.")
        bot.register_next_step_handler(prompt, receive_leftover)
        return

    leftover = int(text)
    if leftover == 0:
        markup = InlineKeyboardMarkup()
        markup.row(*[InlineKeyboardButton(label, callback_data=f"soldout:{key}")
                     for key, label in SOLD_OUT_BUCKETS.items()])
        bot.send_message(chat_id, f"{item['name']} sold out. Roughly when?", reply_markup=markup)
        return   # the answer comes from handle_sold_out below

    state["results"].append({**item, "leftover": leftover, "bucket": None})
    state["index"] += 1
    ask_next_item(chat_id, message.from_user)


@bot.callback_query_handler(func=lambda call: call.data.startswith("soldout:"))
def handle_sold_out(call):
    chat_id = call.message.chat.id
    state = counts.get(chat_id)
    if state is None or state["index"] == len(state["items"]):
        answer(call, "No count in progress. Send /count to start.")
        return

    bucket = call.data.split(":", 1)[1]
    item = state["items"][state["index"]]
    state["results"].append({**item, "leftover": 0, "bucket": bucket})
    state["index"] += 1
    answer(call)
    # Replace the buttons with the answer so they can't be tapped twice.
    bot.edit_message_text(f"{item['name']} sold out: {SOLD_OUT_BUCKETS[bucket]}", chat_id, call.message.message_id)
    ask_next_item(chat_id, call.from_user)


def finish_count(chat_id: int, user) -> None:
    state = counts.pop(chat_id)
    lines = []
    for r in state["results"]:
        db.save_count(state["date"], r["id"], r["baked"], r["leftover"], r["bucket"])
        if r["bucket"]:
            lines.append(f"{r['name']}: sold out ({SOLD_OUT_BUCKETS[r['bucket']]})")
        else:
            lines.append(f"{r['name']}: {r['leftover']} left")
    summary = "\n".join(lines)

    name = name_of(user) if user else "Staff"
    db.log(name, role_of(user) if user else "staff", "Closing count", summary.replace("\n", ", "))
    bot.send_message(chat_id, f"Thanks! Saved the closing count for {state['date']}:\n\n{summary}")
    if chat_id != MANAGER_ID:
        bot.send_message(MANAGER_ID, f"Closing count from {name} ({state['date']}):\n\n{summary}")


@bot.message_handler(commands=["count"])
def handle_count(message):
    if message.from_user.id not in count_recipients():
        bot.reply_to(message, "Only staff can do the closing count.")
        return
    begin_count(message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("approve:"))
def handle_approve(call):
    plan_date = call.data.split(":", 1)[1]
    plan = check_can_change(call, plan_date, "approve")
    if plan is None:
        return

    manager = name_of(call.from_user)
    db.approve_plan(plan_date, manager)
    plan = db.get_plan(plan_date)
    db.log(manager, "manager", "Plan approved", f"Plan for {plan_date}: " + ", ".join(
        f"{p['item_name']} {p['final']}" for p in plan))

    answer(call, "Plan approved.")
    # Replace the buttons with the final status so nobody taps twice.
    bot.edit_message_text(plan_text(plan), call.message.chat.id, call.message.message_id)

    try:
        bot.send_message(BAKER_ID, bake_list_text(plan))
        db.log("Just Right", "system", "Bake list sent", f"Bake list for {plan_date} sent to the baker")
    except ApiTelegramException:
        # Telegram won't let a bot message someone who never opened it.
        bot.send_message(call.message.chat.id,
                         "Couldn't send the bake list: the baker needs to open the bot and press Start first.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit:"))
def handle_edit(call):
    plan_date = call.data.split(":", 1)[1]
    plan = check_can_change(call, plan_date, "edit")
    if plan is None:
        return

    markup = InlineKeyboardMarkup()
    for p in plan:
        markup.add(InlineKeyboardButton(p["item_name"], callback_data=f"edititem:{plan_date}:{p['item_id']}"))
    answer(call)
    bot.send_message(call.message.chat.id, "Which item do you want to change?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edititem:"))
def handle_edit_item(call):
    _, plan_date, item_id = call.data.split(":", 2)
    plan = check_can_change(call, plan_date, "edit")
    if plan is None:
        return

    p = next(p for p in plan if p["item_id"] == item_id)
    answer(call)
    prompt = bot.send_message(
        call.message.chat.id,
        f"{p['item_name']} is at {p['final']}. Send the new number and a reason, e.g.\n30 school holiday",
    )
    bot.register_next_step_handler(prompt, save_edit, plan_date, item_id)


def save_edit(message, plan_date: str, item_id: str):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        prompt = bot.reply_to(message, "Please send a number and a reason, e.g.\n30 school holiday")
        bot.register_next_step_handler(prompt, save_edit, plan_date, item_id)
        return

    plan = db.get_plan(plan_date)
    if not plan or plan[0]["status"] == "approved":
        bot.reply_to(message, "This plan was already approved or replaced, so nothing was changed.")
        return

    old = next(p for p in plan if p["item_id"] == item_id)
    new_quantity, reason = int(parts[0]), parts[1]
    db.edit_item(plan_date, item_id, new_quantity, f"Edited by manager: {reason}")
    db.log(name_of(message.from_user), "manager", "Plan edited",
           f"{old['item_name']} {old['final']} -> {new_quantity}: {reason}")

    bot.send_message(message.chat.id, plan_text(db.get_plan(plan_date)), reply_markup=plan_buttons(plan_date))


def run() -> None:
    try:
        set_all_menus()
    except Exception as e:
        # The menus are a nice-to-have; never let them stop the bot from starting.
        print(f"Could not set command menus: {e}")
    print("Telegram bot polling started.")
    # skip_pending: ignore messages and taps sent while the bot was offline.
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    db.init()
    print("Bot running. Press Ctrl+C to stop.")
    run()
