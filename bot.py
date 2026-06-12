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

(GUEST_NAME, CONFIRM_GUEST, NEW_FREQUENCY, NEW_HOOKAH_PREF, NEW_DRINKS_PREF,
 NEW_IMPORTANT, VISIT_HOOKAH, VISIT_DRINKS, VISIT_NOTES, VISIT_DATE) = range(10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Напиши имя гостя:",
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
        props = guest["properties"]
        guest_name = props["Имя Гостя"]["title"][0]["plain_text"]
        context.user_data["guest_id"] = guest["id"]
        context.user_data["guest_name"] = guest_name

        def get_text(p):
            items = props.get(p, {}).get("rich_text", [])
            return items[0]["plain_text"] if items else "не указано"
        def get_select(p):
            s = props.get(p, {}).get("select")
            return s["name"] if s else "не указано"

        info = (
            f"👤 *{guest_name}*\n"
            f"📊 Частота: {get_select('Частота визитов')}\n"
            f"🪄 Кальян: {get_text('Кальян — вкус и крепость')}\n"
            f"🍹 Напитки: {get_text('Напитки — предпочтения')}\n"
            f"⭐ Важно: {get_text('Что важно для гостя')}"
        )

        keyboard = [["✅ Да, добавить визит", "❌ Другой гость"]]
        await update.message.reply_text(
            f"{info}\n\nДобавить визит?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return CONFIRM_GUEST
    else:
        context.user_data["new_guest_name"] = name
        keyboard = [["✅ Создать", "❌ Отмена"]]
        await update.message.reply_text(
            f"Гость *{name}* не найден.\nСоздать новую карточку?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return NEW_FREQUENCY

async def confirm_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Да, добавить визит":
        await update.message.reply_text(
            "🪄 Что заказал по кальяну сегодня?",
            reply_markup=ReplyKeyboardRemove()
        )
        return VISIT_HOOKAH
    else:
        await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
        return GUEST_NAME

async def new_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await update.message.reply_text("Отменено. Напиши /start", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    keyboard = [["Постоянный", "Редкий", "Новый"]]
    await update.message.reply_text(
        f"Создаём карточку для *{context.user_data['new_guest_name']}*\n\n📊 Частота визитов?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return NEW_HOOKAH_PREF

async def new_hookah_pref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_frequency"] = update.message.text.strip()
    await update.message.reply_text(
        "🪄 Предпочтения по кальяну?\n(Вкус и крепость)",
        reply_markup=ReplyKeyboardRemove()
    )
    return NEW_DRINKS_PREF

async def new_drinks_pref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_hookah_pref"] = update.message.text.strip()
    await update.message.reply_text("🍹 Предпочтения по напиткам?")
    return NEW_IMPORTANT

async def new_important(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_drinks_pref"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "⭐ Что важно для гостя?\n(Сервис, место, атмосфера и т.д.)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return VISIT_HOOKAH

async def visit_hookah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    is_new = "new_guest_name" in context.user_data

    if is_new:
        # Сохраняем "что важно" и создаём карточку
        important = "" if text == "Пропустить" else text
        context.user_data["new_important"] = important

        name = context.user_data["new_guest_name"]
        page_data = {
            "parent": {"database_id": NOTION_DB_ID},
            "properties": {
                "Имя Гостя": {"title": [{"text": {"content": name}}]},
                "Частота визитов": {"select": {"name": context.user_data["new_frequency"]}},
                "Кальян — вкус и крепость": {"rich_text": [{"text": {"content": context.user_data["new_hookah_pref"]}}]},
                "Напитки — предпочтения": {"rich_text": [{"text": {"content": context.user_data["new_drinks_pref"]}}]},
                "Что важно для гостя": {"rich_text": [{"text": {"content": important}}]},
            }
        }
        res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)
        if res.status_code != 200:
            await update.message.reply_text("❌ Ошибка при создании гостя. Попробуй /start")
            return ConversationHandler.END

        guest = res.json()
        context.user_data["guest_id"] = guest["id"]
        context.user_data["guest_name"] = name
        await update.message.reply_text(
            f"✅ Карточка *{name}* создана!\n\nТеперь добавим первый визит.\n🪄 Что заказал по кальяну сегодня?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return VISIT_HOOKAH
    else:
        context.user_data["visit_hookah"] = text
        await update.message.reply_text("🍹 Что пил из напитков?")
        return VISIT_DRINKS

async def visit_drinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["visit_hookah"] = context.user_data.get("visit_hookah", update.message.text.strip())
    
    # Если только что пришли из создания карточки
    if "visit_hookah" not in context.user_data:
        context.user_data["visit_hookah"] = update.message.text.strip()
        await update.message.reply_text("🍹 Что пил из напитков?")
        return VISIT_DRINKS

    context.user_data["visit_drinks"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "📝 Заметки о визите?\n(Настроение, повод, пожелания)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return VISIT_NOTES

async def visit_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["visit_notes"] = "" if text == "Пропустить" else text
    keyboard = [["📅 Сегодня"]]
    await update.message.reply_text(
        "📅 Дата визита?",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return VISIT_DATE

async def visit_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    visit_date = date.today().isoformat() if text == "📅 Сегодня" else text

    guest_name = context.user_data["guest_name"]
    guest_id = context.user_data["guest_id"]
    hookah = context.user_data.get("visit_hookah", "—")
    drinks = context.user_data.get("visit_drinks", "—")
    notes = context.user_data.get("visit_notes", "")

    page_data = {
        "parent": {"database_id": NOTION_VISITS_DB_ID},
        "properties": {
            "Визит": {"title": [{"text": {"content": f"{guest_name} — {visit_date}"}}]},
            "Гость": {"relation": [{"id": guest_id}]},
            "Дата": {"date": {"start": visit_date}},
            "Кальян": {"rich_text": [{"text": {"content": hookah}}]},
            "Напитки": {"rich_text": [{"text": {"content": drinks}}]},
            "Заметки": {"rich_text": [{"text": {"content": notes}}]},
        }
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)

    if res.status_code == 200:
        await update.message.reply_text(
            f"✅ Готово!\n\n"
            f"👤 {guest_name}\n"
            f"📅 {visit_date}\n"
            f"🪄 {hookah}\n"
            f"🍹 {drinks}\n"
            f"📝 {notes if notes else '—'}\n\n"
            f"Для нового визита напиши /start",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("❌ Ошибка при сохранении. Попробуй /start", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено. Напиши /start", reply_markup=ReplyKeyboardRemove())
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
        NEW_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_frequency)],
        NEW_HOOKAH_PREF: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_hookah_pref)],
        NEW_DRINKS_PREF: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_drinks_pref)],
        NEW_IMPORTANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_important)],
        VISIT_HOOKAH: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_hookah)],
        VISIT_DRINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_drinks)],
        VISIT_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_notes)],
        VISIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_date)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
app.run_polling()
