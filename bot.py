import asyncio
import os
import re
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import RetryAfter
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from downloader import (
    DownloadCancelled,
    download_quality,
)

from drive import (
    delete_file,
    list_files,
    rename_file,
    upload_file,
)


BOT_TOKEN = os.environ["BOT_TOKEN"]

DOWNLOAD_DIR = Path("/tmp/m3u8_downloads")
DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)

URL_RE = re.compile(
    r"https?://\S+\.m3u8(?:\?\S+)?",
    re.I
)

jobs = {}

# User ID -> selected Drive file ID
rename_states = {}


# =========================================================
# QUALITY KEYBOARD
# =========================================================

def quality_keyboard(job_id):

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "1080p",
                callback_data=f"q|1080|{job_id}"
            ),
            InlineKeyboardButton(
                "720p",
                callback_data=f"q|720|{job_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "480p",
                callback_data=f"q|480|{job_id}"
            ),
            InlineKeyboardButton(
                "360p",
                callback_data=f"q|360|{job_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📥 Download All",
                callback_data=f"all|0|{job_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"cancel_job|0|{job_id}"
            )
        ],
    ])


# =========================================================
# PROGRESS
# =========================================================

def make_progress_bar(
    percent,
    length=20
):

    percent = max(
        0.0,
        min(100.0, percent)
    )

    filled = int(
        length * percent / 100
    )

    empty = length - filled

    return (
        "█" * filled
        + "░" * empty
    )


def progress_text(
    height,
    percent,
    speed,
    eta
):

    bar = make_progress_bar(
        percent
    )

    speed = (
        speed
        or "Calculating..."
    )

    eta = (
        eta
        or "Calculating..."
    )

    return (
        f"⬇️ Downloading {height}p...\n\n"
        f"{bar} {percent:.1f}%\n\n"
        f"⚡ Speed: {speed}\n"
        f"⏳ ETA: {eta}"
    )


async def progress_updater(
    status,
    height,
    progress
):

    last_text = None

    while not progress["finished"]:

        percent = progress["percent"]
        speed = progress["speed"]
        eta = progress["eta"]

        text = progress_text(
            height,
            percent,
            speed,
            eta
        )

        if text != last_text:

            try:

                await status.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "❌ Cancel Download",
                                callback_data=(
                                    "cancel_running|0|"
                                    f"{progress['job_id']}"
                                )
                            )
                        ]
                    ])
                )

                last_text = text

            except RetryAfter as e:

                await asyncio.sleep(
                    e.retry_after
                )

            except Exception:

                pass

        await asyncio.sleep(2)


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Send a direct master .m3u8 link."
    )


# =========================================================
# DRIVE FILE MANAGER
# =========================================================

async def send_drive_files(
    target,
    edit=False
):

    try:

        files = await asyncio.to_thread(
            list_files
        )

    except Exception as e:

        text = (
            "❌ Failed to load Drive files.\n\n"
            f"{e}"
        )

        if edit:
            await target.edit_message_text(
                text
            )
        else:
            await target.message.reply_text(
                text
            )

        return

    if not files:

        text = (
            "📁 No files found in the "
            "Google Drive folder."
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data="rfresh|0"
                ),
                InlineKeyboardButton(
                    "❌ Close",
                    callback_data="rclose|0"
                ),
            ]
        ])

        if edit:

            await target.edit_message_text(
                text,
                reply_markup=keyboard
            )

        else:

            await target.message.reply_text(
                text,
                reply_markup=keyboard
            )

        return

    buttons = []

    for file in files:

        file_id = file["id"]
        file_name = file["name"]

        if len(file_name) > 45:

            display_name = (
                file_name[:42]
                + "..."
            )

        else:

            display_name = file_name

        buttons.append([
            InlineKeyboardButton(
                f"📄 {display_name}",
                callback_data=f"rf|{file_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="rfresh|0"
        ),
        InlineKeyboardButton(
            "❌ Close",
            callback_data="rclose|0"
        ),
    ])

    keyboard = InlineKeyboardMarkup(
        buttons
    )

    if edit:

        await target.edit_message_text(
            "📁 Select a file:",
            reply_markup=keyboard
        )

    else:

        await target.message.reply_text(
            "📁 Select a file:",
            reply_markup=keyboard
        )


async def rename_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await send_drive_files(
        update,
        edit=False
    )


async def drive_file_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        action, file_id = query.data.split(
            "|",
            1
        )

    except ValueError:

        await query.edit_message_text(
            "❌ Invalid request."
        )

        return

    # -----------------------------------------------------
    # FILE SELECTED
    # -----------------------------------------------------

    if action == "rf":

        await query.edit_message_text(
            "📁 File selected.\n\n"
            "Choose an action:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✏️ Rename",
                        callback_data=f"rr|{file_id}"
                    ),
                    InlineKeyboardButton(
                        "🗑️ Delete",
                        callback_data=f"rd|{file_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="rback|0"
                    )
                ],
            ])
        )

        return

    # -----------------------------------------------------
    # BACK
    # -----------------------------------------------------

    if action == "rback":

        await send_drive_files(
            query,
            edit=True
        )

        return

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    if action == "rfresh":

        await send_drive_files(
            query,
            edit=True
        )

        return

    # -----------------------------------------------------
    # CLOSE
    # -----------------------------------------------------

    if action == "rclose":

        rename_states.pop(
            query.from_user.id,
            None
        )

        await query.edit_message_text(
            "❌ File manager closed."
        )

        return

    # -----------------------------------------------------
    # RENAME
    # -----------------------------------------------------

    if action == "rr":

        rename_states[
            query.from_user.id
        ] = file_id

        await query.edit_message_text(
            "✏️ Send the new filename.\n\n"
            "Example:\n"
            "I Popstar Episode 01 360p.mp4",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data="rc|0"
                    )
                ]
            ])
        )

        return

    # -----------------------------------------------------
    # DELETE
    # -----------------------------------------------------

    if action == "rd":

        await query.edit_message_text(
            "⚠️ Are you sure you want to delete this file?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Yes, Delete",
                        callback_data=f"ry|{file_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Cancel",
                        callback_data=f"rf|{file_id}"
                    ),
                ]
            ])
        )

        return

    # -----------------------------------------------------
    # CONFIRM DELETE
    # -----------------------------------------------------

    if action == "ry":

        try:

            await asyncio.to_thread(
                delete_file,
                file_id
            )

            await query.edit_message_text(
                "✅ File deleted successfully.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📁 Back to Files",
                            callback_data="rfresh|0"
                        )
                    ]
                ])
            )

        except Exception as e:

            await query.edit_message_text(
                "❌ Failed to delete file.\n\n"
                f"{e}"
            )

        return

    # -----------------------------------------------------
    # CANCEL DRIVE ACTION
    # -----------------------------------------------------

    if action == "rc":

        rename_states.pop(
            query.from_user.id,
            None
        )

        await query.edit_message_text(
            "❌ Cancelled.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📁 Back to Files",
                        callback_data="rfresh|0"
                    )
                ]
            ])
        )

        return


# =========================================================
# RECEIVE TEXT
# =========================================================

async def receive_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    text = (
        update.message.text
        or ""
    ).strip()

    # -----------------------------------------------------
    # RENAME MODE
    # -----------------------------------------------------

    if user_id in rename_states:

        file_id = rename_states.pop(
            user_id
        )

        new_name = text.strip()

        if not new_name:

            await update.message.reply_text(
                "❌ Filename cannot be empty."
            )

            rename_states[
                user_id
            ] = file_id

            return

        if len(new_name) > 255:

            await update.message.reply_text(
                "❌ Filename is too long. "
                "Please use a shorter name."
            )

            rename_states[
                user_id
            ] = file_id

            return

        try:

            result = await asyncio.to_thread(
                rename_file,
                file_id,
                new_name
            )

            await update.message.reply_text(
                "✅ File renamed successfully.\n\n"
                f"📁 {result['name']}\n\n"
                f"🔗 {result['url']}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📁 Back to Files",
                            callback_data="rfresh|0"
                        )
                    ]
                ])
            )

        except Exception as e:

            await update.message.reply_text(
                "❌ Failed to rename file.\n\n"
                f"{e}"
            )

        return

    # -----------------------------------------------------
    # NORMAL M3U8 MESSAGE
    # -----------------------------------------------------

    match = URL_RE.search(text)

    if not match:

        await update.message.reply_text(
            "❌ Please send a valid direct .m3u8 link."
        )

        return

    url = match.group(0)

    job_id = (
        f"{update.effective_chat.id}:"
        f"{update.message.id}"
    )

    jobs[job_id] = {
        "url": url,
        "chat_id": update.effective_chat.id,
        "running": False,
        "cancel_event": asyncio.Event(),
    }

    await update.message.reply_text(
        "🎬 Link received.\n\n"
        "Available Qualities:",
        reply_markup=quality_keyboard(
            job_id
        )
    )


# =========================================================
# QUALITY CALLBACK
# =========================================================

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        action, value, job_id = (
            query.data.split(
                "|",
                2
            )
        )

    except ValueError:

        await query.edit_message_text(
            "❌ Invalid request."
        )

        return

    job = jobs.get(
        job_id
    )

    if not job:

        await query.edit_message_text(
            "❌ This link has expired. "
            "Please send the m3u8 link again."
        )

        return

    # -----------------------------------------------------
    # CANCEL BEFORE DOWNLOAD
    # -----------------------------------------------------

    if action == "cancel_job":

        job["cancel_event"].set()

        jobs.pop(
            job_id,
            None
        )

        await query.edit_message_text(
            "❌ Job cancelled."
        )

        return

    # -----------------------------------------------------
    # ALREADY RUNNING
    # -----------------------------------------------------

    if job["running"]:

        await query.answer(
            "A download is already running.",
            show_alert=True
        )

        return

    job["running"] = True

    if action == "q":

        qualities = [
            int(value)
        ]

    else:

        qualities = [
            1080,
            720,
            480,
            360
        ]

    await query.edit_message_text(
        "⏳ Job started.\n"
        f"Qualities: "
        f"{', '.join(str(q) + 'p' for q in qualities)}\n\n"
        "You can cancel the download from "
        "the progress message."
    )

    asyncio.create_task(
        process_job(
            context.application,
            job_id,
            job["url"],
            job["chat_id"],
            qualities
        )
    )


# =========================================================
# RUNNING DOWNLOAD CANCEL
# =========================================================

async def running_download_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        _, _, job_id = (
            query.data.split(
                "|",
                2
            )
        )

    except ValueError:

        await query.edit_message_text(
            "❌ Invalid request."
        )

        return

    job = jobs.get(
        job_id
    )

    if not job:

        await query.edit_message_text(
            "❌ This job is no longer running."
        )

        return

    job["cancel_event"].set()

    try:

        await query.edit_message_text(
            "🛑 Cancelling download..."
        )

    except Exception:

        pass


# =========================================================
# DOWNLOAD + UPLOAD
# =========================================================

async def process_job(
    application,
    job_id,
    url,
    chat_id,
    qualities
):

    job = jobs.get(
        job_id
    )

    if not job:
        return

    try:

        for height in qualities:

            if job["cancel_event"].is_set():

                raise DownloadCancelled(
                    "Download cancelled by user."
                )

            progress = {
                "percent": 0.0,
                "speed": "",
                "eta": "",
                "finished": False,
                "job_id": job_id,
            }

            status = await application.bot.send_message(
                chat_id=chat_id,
                text=progress_text(
                    height,
                    0.0,
                    "",
                    ""
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "❌ Cancel Download",
                            callback_data=(
                                "cancel_running|0|"
                                f"{job_id}"
                            )
                        )
                    ]
                ])
            )

            updater_task = asyncio.create_task(
                progress_updater(
                    status,
                    height,
                    progress
                )
            )

            try:

                output = await asyncio.to_thread(
                    download_quality,
                    url,
                    height,
                    DOWNLOAD_DIR,
                    progress,
                    job["cancel_event"],
                )

            finally:

                progress["finished"] = True

                try:
                    await updater_task

                except Exception:
                    pass

            if job["cancel_event"].is_set():

                try:
                    output.unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass

                raise DownloadCancelled(
                    "Download cancelled by user."
                )

            # -------------------------------------------------
            # FINAL DOWNLOAD STATUS
            # -------------------------------------------------

            try:

                await status.edit_text(
                    progress_text(
                        height,
                        100.0,
                        progress["speed"],
                        "00:00"
                    )
                )

            except Exception:

                pass

            await asyncio.sleep(1)

            # -------------------------------------------------
            # CHECK AGAIN BEFORE UPLOAD
            # -------------------------------------------------

            if job["cancel_event"].is_set():

                try:
                    output.unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass

                raise DownloadCancelled(
                    "Download cancelled by user."
                )

            # -------------------------------------------------
            # GOOGLE DRIVE UPLOAD
            # -------------------------------------------------

            await status.edit_text(
                f"☁️ {height}p downloaded.\n"
                "Uploading to Google Drive..."
            )

            drive_result = await asyncio.to_thread(
                upload_file,
                output
            )

            try:

                output.unlink(
                    missing_ok=True
                )

            except Exception:

                pass

            await status.edit_text(
                f"✅ {height}p uploaded.\n\n"
                f"🔗 {drive_result['url']}"
            )

    except DownloadCancelled:

        await application.bot.send_message(
            chat_id=chat_id,
            text="🛑 Download cancelled."
        )

    except Exception as e:

        await application.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Job failed:\n{e}"
        )

    finally:

        jobs.pop(
            job_id,
            None
        )


# =========================================================
# MAIN
# =========================================================

def main():

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # Drive File Manager
    app.add_handler(
        CommandHandler(
            "rename",
            rename_command
        )
    )

    # Drive file buttons
    app.add_handler(
        CallbackQueryHandler(
            drive_file_callback,
            pattern=(
                r"^(rf|rr|rd|ry|rc|rback|rfresh|rclose)\|"
            )
        )
    )

    # Running download cancel
    app.add_handler(
        CallbackQueryHandler(
            running_download_callback,
            pattern=r"^cancel_running\|"
        )
    )

    # Quality buttons
    app.add_handler(
        CallbackQueryHandler(
            quality_callback,
            pattern=r"^(q|all|cancel_job)\|"
        )
    )

    # Text messages
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
