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
    "roster": set(),          
    "poll_time": "19:00",  
    "poll_id": None,
    "voted_identifiers": set() 
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= COMMAND HANDLERS =================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 **Parade State Bot Help**\n\n"
        "**/addname @user/ID** - Add to roster.\n"
        "**/removename @user/ID** - Remove from roster.\n"
        "**/setroster @u1 @u2** - Overwrite full list.\n"
        "**/viewroster** - Show current list.\n"
        "**/whoami** - Get your Telegram ID (for users without handles).\n\n"
        "**/sendpoll** - Send poll to group now.\n"
        "**/checkvotes** - Run reminder now.\n"
        "**/viewtime** - Check scheduled poll time."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def who_am_i(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"👤 **Your Info:**\nID: `{user.id}`\nUsername: @{user.username}", parse_mode='Markdown')

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/addname @username` or `/addname 12345`")
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
    else:
        await update.message.reply_text(f"⚠️ {item} not found in roster.")

async def set_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    memory_data["roster"] = {name.replace('@', '').strip() for name in context.args if name.strip()}
    await update.message.reply_text(f"✅ Roster overwritten ({len(memory_data['roster'])} members).")

async def view_roster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roster = sorted(list(memory_data["roster"]))
    display = [(f"@{n}" if not n.isdigit() else f"ID:{n}") for n in roster]
    text = "📋 **Current Roster:**\n" + "\n".join([f"- {n}" for n in display]) if display else "Roster is empty."
    await update.message.reply_text(text)

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
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="⚠️ No active poll found.")
        return

    expected = memory_data["roster"]
    voted = memory_data["voted_identifiers"]
    missing = [item for item in expected if item not in voted]

    if not missing:
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text="✅ All parade states updated!")
    else:
        count = len(missing)
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID, 
            text=f"📢 **Reminder:** {count} personnel missing. Nudges have been sent!",
            parse_mode='Markdown'
        )
        for identifier in missing:
            try:
                await context.bot.send_message(chat_id=identifier, text="⚠️ Reminder: Update your Parade State status!")
            except: pass

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

# ================= MAIN =================

if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("whoami", who_am_i))
    application.add_handler(CommandHandler("addname", add_name))
    application.add_handler(CommandHandler("removename", remove_name))
    application.add_handler(CommandHandler("setroster", set_roster))
    application.add_handler(CommandHandler("viewroster", view_roster))
    application.add_handler(CommandHandler("sendpoll", lambda u, c: send_parade_poll(c)))
    application.add_handler(CommandHandler("checkvotes", lambda u, c: check_missing_votes(c)))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    h, m = map(int, memory_data["poll_time"].split(':'))
    application.job_queue.run_daily(send_parade_poll, time=datetime.time(hour=h, minute=m, tzinfo=SGT), days=ACTIVE_DAYS)
    application.job_queue.run_daily(check_missing_votes, time=datetime.time(hour=12, minute=0, tzinfo=SGT), days=CHECK_DAYS)

    print("Bot is running. Roster & ID management active.")
    application.run_polling(drop_pending_updates=True)