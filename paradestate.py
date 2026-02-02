import logging
import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, PollAnswerHandler, ContextTypes

# ================= CONFIGURATION =================
BOT_TOKEN = '8431373969:AAEyuKDcU3Mhniew-BS3RKxCj59Zenw83Lg'
GROUP_CHAT_ID = -5110759100
SGT = pytz.timezone('Asia/Singapore')

ACTIVE_DAYS = (0, 1, 2, 3, 6)
CHECK_DAYS = (0, 1, 2, 3, 4)

# ================= GLOBAL MEMORY =================
memory_data = {
    "roster": set(),          # Can contain 'john_doe' or '12345678'
    "poll_time": "19:00",  
    "poll_id": None,
    "voted_identifiers": set() 
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= CORE LOGIC =================

async def send_parade_poll(context: ContextTypes.DEFAULT_TYPE):
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
    memory_data["voted_identifiers"] = set()

async def check_missing_votes(context: ContextTypes.DEFAULT_TYPE):
    if not memory_data["poll_id"]:
        return

    expected = memory_data["roster"]
    voted = memory_data["voted_identifiers"]
    
    # A person is missing ONLY if neither their handle nor their ID is in the 'voted' set
    missing = [item for item in expected if item not in voted]

    if not missing:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="✅ All parade states updated!")
        return

    # 1. Send Count Summary to Group
    count = len(missing)
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID, 
        text=f"📢 **Reminder:** {count} personnel have not updated their status. Check your DMs for a nudge!",
        parse_mode='Markdown'
    )

    # 2. Private Nudge (Only works if they have /start-ed the bot)
    for identifier in missing:
        try:
            # If identifier is numeric ID, it works directly. 
            # If it's a handle, this will fail (Bots cannot PM by handle alone).
            await context.bot.send_message(
                chat_id=identifier, 
                text="⚠️ **Reminder:** You haven't updated your Parade State in the group yet!"
            )
        except Exception:
            # Silent fail if user hasn't messaged the bot or identifier is just a handle string
            pass

# ================= COMMAND HANDLERS =================

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/addname @username` OR `/addname 12345`")
        return
    item = context.args[0].replace('@', '').strip()
    memory_data["roster"].add(item)
    await update.message.reply_text(f"✅ Added {item} to roster.")

async def remove_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    item = context.args[0].replace('@', '').strip()
    if item in memory_data["roster"]:
        memory_data["roster"].remove(item)
        await update.message.reply_text(f"🗑️ Removed {item}.")

async def view_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roster = sorted(list(memory_data["roster"]))
    display = [(f"@{n}" if not n.isdigit() else f"ID:{n}") for n in roster]
    text = "📋 **Roster:**\n" + "\n".join([f"- {n}" for n in display]) if display else "Empty."
    await update.message.reply_text(text)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    if answer.poll_id == memory_data["poll_id"]:
        user_id = str(answer.user.id)
        username = answer.user.username
        
        if answer.option_ids:
            memory_data["voted_identifiers"].add(user_id)
            if username: memory_data["voted_identifiers"].add(username)
        else:
            memory_data["voted_identifiers"].discard(user_id)
            if username: memory_data["voted_identifiers"].discard(username)

async def set_poll_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    try:
        time_input = context.args[0]
        h, m = map(int, time_input.split(':'))
        new_time = datetime.time(hour=h, minute=m, tzinfo=SGT)
        for job in context.job_queue.get_jobs_by_name("daily_poll_job"): job.schedule_removal()
        context.job_queue.run_daily(send_parade_poll, time=new_time, days=ACTIVE_DAYS, name="daily_poll_job")
        memory_data["poll_time"] = time_input
        await update.message.reply_text(f"✅ Time set to {time_input} SGT.")
    except: await update.message.reply_text("❌ Use HH:MM.")

async def who_am_i(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Your ID: `{user.id}`\nUsername: @{user.username}", parse_mode='Markdown')

# ================= MAIN =================

if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", who_am_i))
    application.add_handler(CommandHandler("whoami", who_am_i))
    application.add_handler(CommandHandler("addname", add_name))
    application.add_handler(CommandHandler("removename", remove_name))
    application.add_handler(CommandHandler("viewroster", view_roster))
    application.add_handler(CommandHandler("sendpoll", lambda u, c: send_parade_poll(c)))
    application.add_handler(CommandHandler("checkvotes", lambda u, c: check_missing_votes(c)))
    application.add_handler(CommandHandler("settime", set_poll_time))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    h, m = map(int, memory_data["poll_time"].split(':'))
    application.job_queue.run_daily(send_parade_poll, time=datetime.time(hour=h, minute=m, tzinfo=SGT), days=ACTIVE_DAYS, name="daily_poll_job")
    application.job_queue.run_daily(check_missing_votes, time=datetime.time(hour=12, minute=0, tzinfo=SGT), days=CHECK_DAYS, name="check_votes_job")

    application.run_polling()