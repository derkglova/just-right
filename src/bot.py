"""Telegram bot (pyTelegramBotAPI).

Commands:
- /start: say hello and show the user their Telegram ID (handy for filling in .env).
- /plan:  send tomorrow's plan right now (for demos).

The plan message has [Approve] and [Edit] buttons. Only the manager can use them.
On approve, the bake list goes to the baker. Plans and every action are saved in
the database (db.py), so they survive a restart and show up in the activity log.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from dotenv import load_dotenv
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import db
from planner import load_data, make_plan

load_dotenv()

TZ = ZoneInfo(os.environ.get("TZ", "Asia/Kuala_Lumpur"))
MANAGER_ID = int(os.environ["MANAGER_TELEGRAM_ID"])
BAKER_ID = int(os.environ.get("BAKER_TELEGRAM_ID") or MANAGER_ID)

bot = telebot.TeleBot(os.environ["TELEGRAM_TOKEN"])

STATUS_LABEL = {"pending": "Pending approval", "approved": "Approved"}


def is_manager(user_id: int) -> bool:
    return user_id == MANAGER_ID


def role_of(user) -> str:
    return "manager" if is_manager(user.id) else "staff"


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
    bot.reply_to(
        message,
        "Hi! I'm Just Right. I suggest how many of each item to bake tomorrow.\n"
        f"Your Telegram ID is {message.from_user.id}.\n\n"
        "/plan - send tomorrow's plan now",
    )


@bot.message_handler(commands=["plan"])
def handle_plan(message):
    user = message.from_user
    send_plan(message.chat.id, name_of(user), role_of(user))


@bot.callback_query_handler(func=lambda call: call.data.startswith("approve:"))
def handle_approve(call):
    plan_date = call.data.split(":", 1)[1]
    plan = check_can_change(call, plan_date, "approve")
    if plan is None:
        return

    manager = name_of(call.from_user)
    db.approve_plan(plan_date, manager)
    plan = db.get_plan(plan_date)
    bake_list = "\n".join(f"{p['item_name']}: {p['final']}" for p in plan)
    db.log(manager, "manager", "Plan approved", f"Plan for {plan_date}: " + ", ".join(
        f"{p['item_name']} {p['final']}" for p in plan))

    answer(call, "Plan approved.")
    # Replace the buttons with the final status so nobody taps twice.
    bot.edit_message_text(plan_text(plan), call.message.chat.id, call.message.message_id)

    bot.send_message(BAKER_ID, f"Approved bake list for {plan_date}:\n\n{bake_list}")
    db.log("Just Right", "system", "Bake list sent", f"Bake list for {plan_date} sent to the baker")


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
    # skip_pending: ignore messages and taps sent while the bot was offline.
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    db.init()
    print("Bot running. Press Ctrl+C to stop.")
    run()
