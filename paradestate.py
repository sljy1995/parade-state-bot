import logging
import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, PollAnswerHandler, ContextTypes

# ================= CONFIGURATION =================
# Security Note: Keep your token private! 
BOT_TOKEN = '8431373969:AAEyuKDcU3Mhniew-BS3RKxCj59Zenw83Lg'
GROUP_CHAT_ID = -5140261147 
SGT = pytz.timezone('Asia/Singapore')

# Poll days: Sun-Thu (to cover Mon-Fri states)
ACTIVE_DAYS = (0, 1, 2, 3, 6)
# Reminder days: Mon-Fri
CHECK_DAYS = (0, 1, 2, 3, 4)

# ================= GLOBAL MEMORY =================
memory_data = {
    "roster": set(),          # Changed to set to allow easy add/remove
    "poll_time": "19:00",  
    "poll_id": None,
    "voted_usernames": set()
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= CORE LOGIC =================

async def send_parade_poll(context: ContextTypes.DEFAULT_TYPE):
    """Sends the poll to the group and resets tracking"""
    tomorrow = datetime.datetime.now(SGT) + datetime.timedelta(days=1)
    date_str = tomorrow.strftime("%d %b %Y (%A)")
    
    question = f"Parade State for {date_str}"
    options = ["In Office", "LL/OSL", "Working - in other location", "MC/Others (PM Ops Warrant)", "On Course"]

    message = await context.bot.send_poll(
        chat_id=GROUP_CHAT_ID,
        question=question,
        options=options,
        is_anonymous=False, 
        allows_multiple_answers=False
    )
    
    memory_data["poll_id"] = message.poll.id
    memory_data["voted_usernames"] = set()
    logging.info(f"Poll sent for {date_str} ID: {message.poll.id}")

async def check_missing_votes(context: ContextTypes.DEFAULT_TYPE):
    """Checks the current poll status and posts the reminder to the group"""
    if not memory_data["poll_id"]:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⚠️ No active poll found in memory to check.")
        return

    expected = memory_data["roster"]
    voted = memory_data["voted_usernames"]
    missing = [name for name in expected if name not in voted]

    if not missing:
        msg = "Thank you all for providing your parade state timely!"
    else:
        list_text = "\n".join([f"- @{name}" for name in missing])
        msg = f"Hello what time already why y'all still haven't update your parade state.\n\n{list_text}"
    
    await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg)

# ================= COMMAND HANDLERS =================

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a single name to the roster"""
    if not context.args:
        await update.message.reply_text("❌ Usage: `/addname @username`")
        return
    name = context.args[0].replace('@', '').strip()
    memory_data["roster"].add(name)
    await update.message.reply_text(f"✅ Added **@{name}** to the roster.", parse_mode='Markdown')

async def remove_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a single name from the roster"""
    if not context.args:
        await update.message.reply_text("❌ Usage: `/removename @username`")
        return
    name = context.args[0].replace('@', '').strip()
    if name in memory_data["roster"]:
        memory_data["roster"].remove(name)
        await update.message.reply_text(f"🗑️ Removed **@{name}** from the roster.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"⚠️ **@{name}** not found in roster.")

async def set_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/setroster @user1 @user2`")
        return
    memory_data["roster"] = {name.replace('@', '').strip() for name in context.args if name.strip()}
    await update.message.reply_text(f"✅ Roster set ({len(memory_data['roster'])} members).")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 **Parade State Bot Help**\n\n"
        "**Roster Management:**\n"
        "**/addname @user** - Add one person.\n"
        "**/removename @user** - Remove one person.\n"
        "**/setroster @u1 @u2** - Overwrite full list.\n"
        "**/viewroster** - Show current list.\n\n"
        "**Automation:**\n"
        "**/settime HH:MM** - Set poll time (SGT).\n"
        "**/sendpoll** - Manual poll now.\n"
        "**/checkvotes** - Manual reminder now."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def manual_send_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_parade_poll(context)

async def manual_check_votes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await check_missing_votes(context)

async def set_poll_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    try:
        time_input = context.args[0]
        h, m = map(int, time_input.split(':'))
        new_time = datetime.time(hour=h, minute=m, tzinfo=SGT)
        for job in context.job_queue.get_jobs_by_name("daily_poll_job"): job.schedule_removal()
        context.job_queue.run_daily(send_parade_poll, time=new_time, days=ACTIVE_DAYS, name="daily_poll_job")
        memory_data["poll_time"] = time_input
        await update.message.reply_text(f"✅ Schedule updated to {time_input} SGT.")
    except: await update.message.reply_text("❌ Error setting time. Use HH:MM.")

async def view_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roster = sorted(list(memory_data["roster"]))
    text = "📋 **Current Roster:**\n" + "\n".join([f"- @{name}" for name in roster]) if roster else "Roster is empty."
    await update.message.reply_text(text, parse_mode='Markdown')

async def view_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⏰ Schedule: *{memory_data['poll_time']} SGT* (Sun-Thu).")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    if answer.poll_id == memory_data["poll_id"]:
        username = answer.user.username
        if username:
            if answer.option_ids: memory_data["voted_usernames"].add(username)
            else: memory_data["voted_usernames"].discard(username)

# ================= MAIN =================

if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addname", add_name))
    application.add_handler(CommandHandler("removename", remove_name))
    application.add_handler(CommandHandler("setroster", set_roster))
    application.add_handler(CommandHandler("viewroster", view_roster))
    application.add_handler(CommandHandler("sendpoll", manual_send_poll))
    application.add_handler(CommandHandler("checkvotes", manual_check_votes))
    application.add_handler(CommandHandler("settime", set_poll_time))
    application.add_handler(CommandHandler("viewtime", view_time))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    h, m = map(int, memory_data["poll_time"].split(':'))
    application.job_queue.run_daily(send_parade_poll, time=datetime.time(hour=h, minute=m, tzinfo=SGT), days=ACTIVE_DAYS, name="daily_poll_job")
    application.job_queue.run_daily(check_missing_votes, time=datetime.time(hour=12, minute=0, tzinfo=SGT), days=CHECK_DAYS, name="check_votes_job")

    print("Bot is running. Sun-Thu schedule active.")
    application.run_polling()