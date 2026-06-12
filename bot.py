import os
import requests
from datetime import date
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = os.environ["NOTION_DB_ID"]
NOTION_VISITS_DB_ID = os.environ["NOTION_VISITS_DB_ID"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Шаги диалога
GUEST_NAME, CONFIRM_GUEST, NEW_GUEST_CONFIRM, NEW_GUEST_FREQUENCY, HOOKAH, DRINKS, NOTES, VISIT_DATE = range(8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Напиши имя гостя:",
        reply_markup=ReplyKeyboardRemove()
    )
    return GUEST_NAME

async def get_guest_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    res = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=HEADERS,
        json={"filter": {"property": "Имя Гостя", "title": {"contains": name}}}
    )
    results = res.json().get("results", [])

    if results:
        guest = results[0]
        guest_name = guest["properties"]["Имя Гостя"]["title"][0]["plain_text"]
        context.user_data["guest_id"] = guest["id"]
        context.user_data["guest_name"] = guest_name

        keyboard = [["✅ Да, верно", "❌ Другой гость"]]
        await update.message.reply_text(
            f"Нашёл гостя: *{guest_name}*\nЭто он?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CONFIRM_GUEST
    else:
        context.user_data["new_guest_name"] = name
        keyboard = [["✅ Создать нового гостя", "❌ Отмена"]]
        await update.message.reply_text(
            f"Гость «{name}» не найден в базе.\n\nСоздать нового гостя?",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return NEW_GUEST_CONFIRM

async def confirm_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Да, верно":
        await update.message.reply_text(
            "🪄 Что заказал по кальяну?\n(Вкус и крепость, например: Лимон средняя)",
            reply_markup=ReplyKeyboardRemove()
        )
        return HOOKAH
    else:
        await update.message.reply_text(
            "Напиши имя гостя ещё раз:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GUEST_NAME

async def new_guest_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Создать нового гостя":
        keyboard = [["Постоянный", "Редкий", "Новый"]]
        await update.message.reply_text(
            "📊 Частота визитов гостя?",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return NEW_GUEST_FREQUENCY
    else:
        await update.message.reply_text(
            "Отменено. Напиши /start чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

async def new_guest_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frequency = update.message.text.strip()
    name = context.user_data["new_guest_name"]

    # Создаём карточку гостя в Notion
    page_data = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Имя Гостя": {
                "title": [{"text": {"content": name}}]
            },
            "Частота визитов": {
                "select": {"name": frequency}
            }
        }
    }

    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS,
        json=page_data
    )

    if res.status_code == 200:
        guest = res.json()
        context.user_data["guest_id"] = guest["id"]
        context.user_data["guest_name"] = name
        await update.message.reply_text(
            f"✅ Гость *{name}* создан!\n\nТеперь добавим первый визит.\n\n🪄 Что заказал по кальяну?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return HOOKAH
    else:
        await update.message.reply_text(
            "❌ Ошибка при создании гостя. Попробуй /start",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

async def get_hookah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["hookah"] = update.message.text.strip()
    await update.message.reply_text("🍹 Что пил из напитков?")
    return DRINKS

async def get_drinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drinks"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "📝 Заметки о визите?\n(Настроение, особые пожелания, повод)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return NOTES

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["notes"] = "" if text == "Пропустить" else text
    keyboard = [["📅 Сегодня"]]
    await update.message.reply_text(
        "📅 Дата визита?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return VISIT_DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    visit_date = date.today().isoformat() if text == "📅 Сегодня" else text

    guest_name = context.user_data["guest_name"]
    guest_id = context.user_data["guest_id"]
    hookah = context.user_data["hookah"]
    drinks = context.user_data["drinks"]
    notes = context.user_data.get("notes", "")

    page_data = {
        "parent": {"database_id": NOTION_VISITS_DB_ID},
        "properties": {
            "Визит": {
                "title": [{"text": {"content": f"{guest_name} — {visit_date}"}}]
            },
            "Гость": {
                "relation": [{"id": guest_id}]
            },
            "Дата": {
                "date": {"start": visit_date}
            },
            "Кальян": {
                "rich_text": [{"text": {"content": hookah}}]
            },
            "Напитки": {
                "rich_text": [{"text": {"content": drinks}}]
            },
            "Заметки": {
                "rich_text": [{"text": {"content": notes}}]
            }
        }
    }

    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers=HEADERS,
        json=page_data
    )

    if res.status_code == 200:
        await update.message.reply_text(
            f"✅ Визит сохранён!\n\n"
            f"👤 {guest_name}\n"
            f"📅 {visit_date}\n"
            f"🪄 {hookah}\n"
            f"🍹 {drinks}\n"
            f"📝 {notes if notes else '—'}\n\n"
            f"Для нового визита напиши /start",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении. Попробуй /start",
            reply_markup=ReplyKeyboardRemove()
        )

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отменено. Напиши /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_guest_name)
    ],
    states={
        GUEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_guest_name)],
        CONFIRM_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_guest)],
        NEW_GUEST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_guest_confirm)],
        NEW_GUEST_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_guest_frequency)],
        HOOKAH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_hookah)],
        DRINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_drinks)],
        NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes)],
        VISIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
app.run_polling()
