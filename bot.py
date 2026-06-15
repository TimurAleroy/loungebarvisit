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

(GUEST_NAME, SELECT_GUEST, CONFIRM_GUEST,
 NEW_FREQUENCY, NEW_HOOKAH_PREF, NEW_DRINKS_PREF, NEW_IMPORTANT,
 VISIT_HOOKAH, VISIT_DRINKS, VISIT_NOTES, VISIT_DATE) = range(11)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🛑 Остановлено. Напиши имя гостя чтобы начать заново.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👋 Напиши имя гостя:\n\n/stop — отменить в любой момент", reply_markup=ReplyKeyboardRemove())
    return GUEST_NAME

async def get_guest_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    res = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=HEADERS,
        json={"filter": {"property": "Имя Гостя", "title": {"contains": name}}}
    )
    results = res.json().get("results", [])

    if len(results) == 1:
        return await show_guest_card(update, context, results[0])
    elif len(results) > 1:
        context.user_data["search_results"] = [
            {"id": g["id"], "name": g["properties"]["Имя Гостя"]["title"][0]["plain_text"]}
            for g in results
        ]
        names = [g["name"] for g in context.user_data["search_results"]]
        keyboard = [[n] for n in names] + [["❌ Никто из них"]]
        await update.message.reply_text(
            f"Нашёл {len(results)} гостей «{name}». Выбери нужного:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return SELECT_GUEST
    else:
        context.user_data["new_guest_name"] = name
        keyboard = [["✅ Создать", "❌ Отмена"]]
        await update.message.reply_text(
            f"Гость *{name}* не найден.\nСоздать новую карточку?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return NEW_FREQUENCY

async def select_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Никто из них":
        await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
        return GUEST_NAME

    for g in context.user_data.get("search_results", []):
        if g["name"] == text:
            res = requests.get(f"https://api.notion.com/v1/pages/{g['id']}", headers=HEADERS)
            return await show_guest_card(update, context, res.json())

    await update.message.reply_text("Не понял выбор. Попробуй ещё раз.")
    return SELECT_GUEST

async def show_guest_card(update, context, guest):
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

    keyboard = [["✅ Добавить визит", "❌ Другой гость"]]
    await update.message.reply_text(
        f"{info}\n\nДобавить визит?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CONFIRM_GUEST

async def confirm_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Добавить визит":
        await update.message.reply_text("🪄 Что заказал по кальяну сегодня?", reply_markup=ReplyKeyboardRemove())
        return VISIT_HOOKAH
    else:
        await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
        return GUEST_NAME

# ─── НОВЫЙ ГОСТЬ ─────────────────────────────────────

async def new_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
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
    await update.message.reply_text("🪄 Предпочтения по кальяну?\n(Вкус и крепость)", reply_markup=ReplyKeyboardRemove())
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
    return NEW_IMPORTANT + 1

async def create_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    important = "" if text == "Пропустить" else text
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

    if res.status_code == 200:
        await update.message.reply_text(
            f"✅ Карточка *{name}* создана!\n\nКогда гость придёт снова — просто напиши его имя и добавь визит.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("❌ Ошибка при создании. Попробуй /stop и начни заново.", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END

# ─── ВИЗИТ ───────────────────────────────────────────

async def visit_hookah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["visit_hookah"] = update.message.text.strip()
    await update.message.reply_text("🍹 Что пил из напитков?")
    return VISIT_DRINKS

async def visit_drinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "📅 Дата визита?\n(Например: 10.06.2026)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return VISIT_DATE

async def visit_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "📅 Сегодня":
        visit_date_str = date.today().isoformat()
    else:
        try:
            parts = text.split(".")
            if len(parts) == 3:
                visit_date_str = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            else:
                raise ValueError
        except:
            await update.message.reply_text("❌ Неверный формат. Используй: 10.06.2026\nИли нажми 📅 Сегодня")
            return VISIT_DATE

    guest_name = context.user_data["guest_name"]
    guest_id = context.user_data["guest_id"]
    hookah = context.user_data.get("visit_hookah", "—")
    drinks = context.user_data.get("visit_drinks", "—")
    notes = context.user_data.get("visit_notes", "")

    page_data = {
        "parent": {"database_id": NOTION_VISITS_DB_ID},
        "properties": {
            "Визит": {"title": [{"text": {"content": f"{guest_name} — {visit_date_str}"}}]},
            "Гость": {"relation": [{"id": guest_id}]},
            "Дата": {"date": {"start": visit_date_str}},
            "Кальян": {"rich_text": [{"text": {"content": hookah}}]},
            "Напитки": {"rich_text": [{"text": {"content": drinks}}]},
            "Заметки": {"rich_text": [{"text": {"content": notes}}]},
        }
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)

    if res.status_code == 200:
        await update.message.reply_text(
            f"✅ Визит сохранён!\n\n"
            f"👤 {guest_name}\n"
            f"📅 {visit_date_str}\n"
            f"🪄 {hookah}\n"
            f"🍹 {drinks}\n"
            f"📝 {notes if notes else '—'}\n\n"
            f"Напиши имя гостя чтобы добавить новый визит.",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("❌ Ошибка при сохранении. Попробуй /stop", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END

CREATE_GUEST = NEW_IMPORTANT + 1

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_guest_name)
    ],
    states={
        GUEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_guest_name)],
        SELECT_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_guest)],
        CONFIRM_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_guest)],
        NEW_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_frequency)],
        NEW_HOOKAH_PREF: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_hookah_pref)],
        NEW_DRINKS_PREF: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_drinks_pref)],
        NEW_IMPORTANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_important)],
        CREATE_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_guest)],
        VISIT_HOOKAH: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_hookah)],
        VISIT_DRINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_drinks)],
        VISIT_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_notes)],
        VISIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, visit_date)],
    },
    fallbacks=[
        CommandHandler("stop", stop),
        CommandHandler("cancel", stop),
    ],
)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
app.run_polling()
