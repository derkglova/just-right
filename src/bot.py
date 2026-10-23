"""Telegram bot (pyTelegramBotAPI).

TODO (build with Claude Code):
- bot = telebot.TeleBot(os.environ["TELEGRAM_TOKEN"])
- send_plan(): run planner.make_plan(), save it as "pending" (db), send the manager
  one message: each item with quantity, change and reason, plus inline buttons
  [Approve] [Edit].
- Callback "approve": only if call.from_user.id == MANAGER_TELEGRAM_ID.
  Otherwise reply "Only the manager can approve this plan." and log the attempt.
  On approve: mark plan approved, log it, send the bake list to BAKER_TELEGRAM_ID.
- Callback "edit": ask which item and the new number + reason; save and log.
- /count (staff): leftovers per item with -/+ buttons; for items at 0 ask
  "Sold out. Roughly when?" [Before 12] [12-2 PM] [2-4 PM] [After 4 PM]; save to daily_sales.
- /plan: send the plan right now (for demos).
- run(): bot.infinity_polling()
"""
