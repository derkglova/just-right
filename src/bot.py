"""Telegram bot (pyTelegramBotAPI).

Commands:
- /start: say hello and show the user their Telegram ID (handy for filling in .env).
- /plan:  send tomorrow's plan to the manager right now (for demos).

The plan message has [Approve] and [Edit] buttons. Only the manager can use them.
On approve, the bake list goes to the baker.

For now the current plan is kept in memory. The database (db.py) comes in the next step.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import telebot
from dotenv import load_dotenv
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from planner import load_data, make_plan

load_dotenv()

TZ = ZoneInfo(os.environ.get("TZ", "Asia/Kuala_Lumpur"))
MANAGER_ID = int(os.environ["MANAGER_TELEGRAM_ID"])
BAKER_ID = int(os.environ.get("BAKER_TELEGRAM_ID") or MANAGER_ID)

bot = telebot.TeleBot(os.environ["TELEGRAM_TOKEN"])

# The plan waiting for approval: {"date": ..., "status": ..., "items": [Recommendation, ...]}
current_plan = None


def is_manager(user_id: int) -> bool:
    return user_id == MANAGER_ID


def plan_text(plan: dict) -> str:
    lines = [f"Bake plan for {plan['date']} (sample data, estimated)", ""]
    for rec in plan["items"]:
        sign = f"+{rec.change}" if rec.change > 0 else str(rec.change)
        lines.append(f"{rec.name}: {rec.quantity} ({sign} vs usual {rec.usual})")
        lines.append(f"  {rec.reason}")
    lines.append("")
    lines.append(f"Status: {plan['status']}")
    return "\n".join(lines)


def plan_buttons() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Approve", callback_data="approve"),
        InlineKeyboardButton("Edit", callback_data="edit"),
    )
    return markup


def send_plan(chat_id: int = MANAGER_ID) -> None:
    """Work out tomorrow's plan and send it with Approve/Edit buttons."""
    global current_plan
    items, history = load_data()
    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date().isoformat()
    current_plan = {"date": tomorrow, "status": "Pending approval", "items": make_plan(items, history)}
    bot.send_message(chat_id, plan_text(current_plan), reply_markup=plan_buttons())


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
    send_plan(message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "approve")
def handle_approve(call):
    if not is_manager(call.from_user.id):
        bot.answer_callback_query(call.id, "Only the manager can approve this plan.", show_alert=True)
        return
    if current_plan is None or current_plan["status"] == "Approved":
        bot.answer_callback_query(call.id, "Nothing to approve. Send /plan first.")
        return

    current_plan["status"] = "Approved"
    bot.answer_callback_query(call.id, "Plan approved.")
    # Replace the buttons with the final status so nobody taps twice.
    bot.edit_message_text(plan_text(current_plan), call.message.chat.id, call.message.message_id)

    bake_list = "\n".join(f"{rec.name}: {rec.quantity}" for rec in current_plan["items"])
    bot.send_message(BAKER_ID, f"Approved bake list for {current_plan['date']}:\n\n{bake_list}")


@bot.callback_query_handler(func=lambda call: call.data == "edit")
def handle_edit(call):
    if not is_manager(call.from_user.id):
        bot.answer_callback_query(call.id, "Only the manager can edit this plan.", show_alert=True)
        return
    if current_plan is None or current_plan["status"] == "Approved":
        bot.answer_callback_query(call.id, "Nothing to edit. Send /plan first.")
        return

    markup = InlineKeyboardMarkup()
    for rec in current_plan["items"]:
        markup.add(InlineKeyboardButton(rec.name, callback_data=f"edit:{rec.item_id}"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Which item do you want to change?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit:"))
def handle_edit_item(call):
    if not is_manager(call.from_user.id):
        bot.answer_callback_query(call.id, "Only the manager can edit this plan.", show_alert=True)
        return

    item_id = call.data.split(":", 1)[1]
    rec = next((r for r in current_plan["items"] if r.item_id == item_id), None) if current_plan else None
    if rec is None:
        bot.answer_callback_query(call.id, "That plan is gone. Send /plan again.")
        return

    bot.answer_callback_query(call.id)
    prompt = bot.send_message(
        call.message.chat.id,
        f"{rec.name} is at {rec.quantity}. Send the new number and a reason, e.g.\n30 school holiday",
    )
    bot.register_next_step_handler(prompt, save_edit, item_id)


def save_edit(message, item_id: str):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        prompt = bot.reply_to(message, "Please send a number and a reason, e.g.\n30 school holiday")
        bot.register_next_step_handler(prompt, save_edit, item_id)
        return

    rec = next(r for r in current_plan["items"] if r.item_id == item_id)
    new_quantity, reason = int(parts[0]), parts[1]
    rec.change = new_quantity - rec.usual
    rec.quantity = new_quantity
    rec.reason = f"Edited by manager: {reason}"

    bot.send_message(message.chat.id, plan_text(current_plan), reply_markup=plan_buttons())


def run() -> None:
    bot.infinity_polling()


if __name__ == "__main__":
    print("Bot running. Press Ctrl+C to stop.")
    run()
