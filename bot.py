import asyncio
import os
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import download_quality
from drive import upload_file

BOT_TOKEN = os.environ["BOT_TOKEN"]

DOWNLOAD_DIR = Path("/tmp/m3u8_downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

URL_RE = re.compile(r"https?://\S+\.m3u8(?:\?\S+)?", re.I)

jobs = {}


def quality_keyboard(job_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1080p", callback_data=f"q|1080|{job_id}"),
            InlineKeyboardButton("720p", callback_data=f"q|720|{job_id}"),
        ],
        [
            InlineKeyboardButton("480p", callback_data=f"q|480|{job_id}"),
            InlineKeyboardButton("360p", callback_data=f"q|360|{job_id}"),
        ],
        [
            InlineKeyboardButton(
                "📥 Download All",
                callback_data=f"all|0|{job_id}"
            )
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send a direct master .m3u8 link."
    )


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    match = URL_RE.search(text)

    if not match:
        await update.message.reply_text(
            "❌ Please send a valid direct .m3u8 link."
        )
        return

    url = match.group(0)
    job_id = f"{update.effective_chat.id}:{update.message.id}"

    jobs[job_id] = {
        "url": url,
        "chat_id": update.effective_chat.id,
        "running": False,
    }

    await update.message.reply_text(
        "🎬 Link received.\n\n"
        "Available Qualities:",
        reply_markup=quality_keyboard(job_id),
    )


async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        action, value, job_id = query.data.split("|", 2)
    except ValueError:
        await query.edit_message_text("❌ Invalid request.")
        return

    job = jobs.get(job_id)

    if not job:
        await query.edit_message_text(
            "❌ This link has expired. Please send the m3u8 link again."
        )
        return

    if job["running"]:
        await query.answer(
            "A download is already running.",
            show_alert=True
        )
        return

    job["running"] = True

    if action == "q":
        qualities = [int(value)]
    else:
        qualities = [1080, 720, 480, 360]

    await query.edit_message_text(
        "⏳ Job started.\n"
        f"Qualities: {', '.join(str(q) + 'p' for q in qualities)}"
    )

    asyncio.create_task(
        process_job(
            context.application,
            job_id,
            job["url"],
            job["chat_id"],
            qualities,
        )
    )


async def process_job(application, job_id, url, chat_id, qualities):
    try:
        for height in qualities:

            status = await application.bot.send_message(
                chat_id=chat_id,
                text=f"⬇️ Downloading {height}p..."
            )

            output = await asyncio.to_thread(
                download_quality,
                url,
                height,
                DOWNLOAD_DIR,
            )

            await status.edit_text(
                f"☁️ {height}p downloaded.\n"
                "Uploading to Google Drive..."
            )

            drive_result = await asyncio.to_thread(
                upload_file,
                output
            )

            try:
                output.unlink(missing_ok=True)
            except Exception:
                pass

            await status.edit_text(
                f"✅ {height}p uploaded.\n\n"
                f"🔗 {drive_result['url']}"
            )

    except Exception as e:
        await application.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Job failed:\n{e}"
        )

    finally:
        jobs.pop(job_id, None)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(
            quality_callback,
            pattern=r"^(q|all)\|"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_url
        )
    )

    print("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
