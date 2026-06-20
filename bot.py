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

(ROLE, GUEST_NAME, SELECT_GUEST, CONFIRM_GUEST,
 NEW_STATUS, NEW_BIRTHDAY, NEW_PHONE, NEW_IMPORTANT, CREATE_GUEST,
 HOOKAH_INPUT, HOOKAH_NOTES,
 BAR_INPUT, BAR_NOTES) = range(13)

def cleanup_old_visits(guest_id, keep=3):
    res = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_VISITS_DB_ID}/query",
        headers=HEADERS,
        json={
            "filter": {"property": "Гость", "relation": {"contains": guest_id}},
            "sorts": [{"property": "Дата", "direction": "descending"}],
            "page_size": 100
        }
    )
    visits = res.json().get("results", [])
    if len(visits) > keep:
        for old_visit in visits[keep:]:
            requests.patch(f"https://api.notion.com/v1/pages/{old_visit['id']}", headers=HEADERS, json={"archived": True})

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🛑 Остановлено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [["🪄 Кальянщик", "🍹 Бармен"]]
    await update.message.reply_text("👋 Привет! Кто ты?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return ROLE

async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🪄 Кальянщик":
        context.user_data["role"] = "hookah"
    elif text == "🍹 Бармен":
        context.user_data["role"] = "bar"
    else:
        keyboard = [["🪄 Кальянщик", "🍹 Бармен"]]
        await update.message.reply_text("Выбери роль:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return ROLE
    await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
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
        await update.message.reply_text("Нашёл несколько. Выбери:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return SELECT_GUEST
    else:
        context.user_data["new_guest_name"] = name
        keyboard = [["✅ Создать", "❌ Отмена"]]
        await update.message.reply_text(
            f"Гость *{name}* не найден.\nСоздать карточку?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return NEW_STATUS

async def select_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ Никто из них":
        await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
        return GUEST_NAME
    for g in context.user_data.get("search_results", []):
        if g["name"] == text:
            res = requests.get(f"https://api.notion.com/v1/pages/{g['id']}", headers=HEADERS)
            return await show_guest_card(update, context, res.json())
    await update.message.reply_text("Не понял выбор.")
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
        f"🏷 Статус: {get_select('Частота визитов')}\n"
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
        role = context.user_data.get("role")
        today = date.today().isoformat()
        res = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_VISITS_DB_ID}/query",
            headers=HEADERS,
            json={
                "filter": {
                    "and": [
                        {"property": "Гость", "relation": {"contains": context.user_data["guest_id"]}},
                        {"property": "Дата", "date": {"equals": today}}
                    ]
                }
            }
        )
        visits = res.json().get("results", [])

        if visits:
            context.user_data["visit_id"] = visits[0]["id"]
            context.user_data["visit_exists"] = True
            existing = visits[0]["properties"]
            hookah = existing.get("Кальян", {}).get("rich_text", [])
            drinks = existing.get("Напитки", {}).get("rich_text", [])
            hookah_text = hookah[0]["plain_text"] if hookah else "не указан"
            drinks_text = drinks[0]["plain_text"] if drinks else "не указаны"

            if role == "hookah":
                await update.message.reply_text(
                    f"✅ Визит найден.\n🍹 Напитки: {drinks_text}\n\n🪄 Что заказал по кальяну?",
                    reply_markup=ReplyKeyboardRemove()
                )
                return HOOKAH_INPUT
            else:
                await update.message.reply_text(
                    f"✅ Визит найден.\n🪄 Кальян: {hookah_text}\n\n🍹 Что заказал из напитков?",
                    reply_markup=ReplyKeyboardRemove()
                )
                return BAR_INPUT
        else:
            context.user_data["visit_exists"] = False
            if role == "hookah":
                await update.message.reply_text("🪄 Что заказал по кальяну?", reply_markup=ReplyKeyboardRemove())
                return HOOKAH_INPUT
            else:
                await update.message.reply_text("🍹 Что заказал из напитков?", reply_markup=ReplyKeyboardRemove())
                return BAR_INPUT
    else:
        await update.message.reply_text("Напиши имя гостя:", reply_markup=ReplyKeyboardRemove())
        return GUEST_NAME

# ─── НОВЫЙ ГОСТЬ ─────────────────────────────────────

async def new_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    keyboard = [["VIP", "Постоянный"], ["Редкий", "Новый"]]
    await update.message.reply_text(
        f"Создаём карточку для *{context.user_data['new_guest_name']}*\n\n🏷 Статус гостя?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return NEW_BIRTHDAY

async def new_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_status"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "🎂 Дата рождения?\n(Например: 15.06.1990, или пропусти)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return NEW_PHONE

async def new_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "Пропустить":
        try:
            parts = text.split(".")
            if len(parts) == 3:
                context.user_data["new_birthday"] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            else:
                context.user_data["new_birthday"] = None
        except:
            context.user_data["new_birthday"] = None
    else:
        context.user_data["new_birthday"] = None

    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "📱 Номер телефона?\n(Или пропусти)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return NEW_IMPORTANT

async def new_important(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_phone"] = None if text == "Пропустить" else text
    keyboard = [["Пропустить"]]
    await update.message.reply_text(
        "⭐ Что важно для гостя?\n(Сервис, место, атмосфера и т.д.)",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return CREATE_GUEST

async def create_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    important = "" if text == "Пропустить" else text
    name = context.user_data["new_guest_name"]

    properties = {
        "Имя Гостя": {"title": [{"text": {"content": name}}]},
        "Частота визитов": {"select": {"name": context.user_data["new_status"]}},
        "Что важно для гостя": {"rich_text": [{"text": {"content": important}}]},
    }
    if context.user_data.get("new_birthday"):
        properties["Дата рождения"] = {"date": {"start": context.user_data["new_birthday"]}}
    if context.user_data.get("new_phone"):
        properties["Телефон"] = {"phone_number": context.user_data["new_phone"]}

    page_data = {"parent": {"database_id": NOTION_DB_ID}, "properties": properties}
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)

    if res.status_code == 200:
        await update.message.reply_text(
            f"✅ Карточка *{name}* создана!\n\nКогда придёт снова — нажми /start и добавь визит.",
            parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text("❌ Ошибка. Попробуй /stop", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ─── КАЛЬЯНЩИК ───────────────────────────────────────

async def hookah_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["hookah"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text("📝 Заметки?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return HOOKAH_NOTES

async def hookah_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    notes = "" if text == "Пропустить" else text
    guest_name = context.user_data["guest_name"]
    guest_id = context.user_data["guest_id"]
    hookah = context.user_data["hookah"]
    today = date.today().isoformat()

    if context.user_data.get("visit_exists"):
        visit_id = context.user_data["visit_id"]
        existing_res = requests.get(f"https://api.notion.com/v1/pages/{visit_id}", headers=HEADERS)
        existing_notes = ""
        if existing_res.status_code == 200:
            rt = existing_res.json()["properties"].get("Заметки", {}).get("rich_text", [])
            existing_notes = rt[0]["plain_text"] if rt else ""
        combined_notes = f"{existing_notes} / {notes}".strip(" /") if existing_notes and notes else (notes or existing_notes)
        requests.patch(f"https://api.notion.com/v1/pages/{visit_id}", headers=HEADERS, json={
            "properties": {
                "Кальян": {"rich_text": [{"text": {"content": hookah}}]},
                "Заметки": {"rich_text": [{"text": {"content": combined_notes}}]},
            }
        })
        await update.message.reply_text(
            f"✅ Кальян добавлен!\n👤 {guest_name}\n🪄 {hookah}\n📝 {combined_notes if combined_notes else '—'}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        page_data = {
            "parent": {"database_id": NOTION_VISITS_DB_ID},
            "properties": {
                "Визит": {"title": [{"text": {"content": f"{guest_name} — {today}"}}]},
                "Гость": {"relation": [{"id": guest_id}]},
                "Дата": {"date": {"start": today}},
                "Кальян": {"rich_text": [{"text": {"content": hookah}}]},
                "Заметки": {"rich_text": [{"text": {"content": notes}}]},
            }
        }
        requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)
        cleanup_old_visits(guest_id, keep=3)
        await update.message.reply_text(
            f"✅ Визит создан!\n👤 {guest_name}\n📅 {today}\n🪄 {hookah}\n📝 {notes if notes else '—'}",
            reply_markup=ReplyKeyboardRemove()
        )

    context.user_data.clear()
    return ConversationHandler.END

# ─── БАРМЕН ──────────────────────────────────────────

async def bar_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["drinks"] = update.message.text.strip()
    keyboard = [["Пропустить"]]
    await update.message.reply_text("📝 Заметки?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return BAR_NOTES

async def bar_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    notes = "" if text == "Пропустить" else text
    guest_name = context.user_data["guest_name"]
    guest_id = context.user_data["guest_id"]
    drinks = context.user_data["drinks"]
    today = date.today().isoformat()

    if context.user_data.get("visit_exists"):
        visit_id = context.user_data["visit_id"]
        existing_res = requests.get(f"https://api.notion.com/v1/pages/{visit_id}", headers=HEADERS)
        existing_notes = ""
        if existing_res.status_code == 200:
            rt = existing_res.json()["properties"].get("Заметки", {}).get("rich_text", [])
            existing_notes = rt[0]["plain_text"] if rt else ""
        combined_notes = f"{existing_notes} / {notes}".strip(" /") if existing_notes and notes else (notes or existing_notes)
        requests.patch(f"https://api.notion.com/v1/pages/{visit_id}", headers=HEADERS, json={
            "properties": {
                "Напитки": {"rich_text": [{"text": {"content": drinks}}]},
                "Заметки": {"rich_text": [{"text": {"content": combined_notes}}]},
            }
        })
        await update.message.reply_text(
            f"✅ Напитки добавлены!\n👤 {guest_name}\n🍹 {drinks}\n📝 {combined_notes if combined_notes else '—'}",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        page_data = {
            "parent": {"database_id": NOTION_VISITS_DB_ID},
            "properties": {
                "Визит": {"title": [{"text": {"content": f"{guest_name} — {today}"}}]},
                "Гость": {"relation": [{"id": guest_id}]},
                "Дата": {"date": {"start": today}},
                "Напитки": {"rich_text": [{"text": {"content": drinks}}]},
                "Заметки": {"rich_text": [{"text": {"content": notes}}]},
            }
        }
        requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=page_data)
        cleanup_old_visits(guest_id, keep=3)
        await update.message.reply_text(
            f"✅ Визит создан!\n👤 {guest_name}\n📅 {today}\n🍹 {drinks}\n📝 {notes if notes else '—'}",
            reply_markup=ReplyKeyboardRemove()
        )

    context.user_data.clear()
    return ConversationHandler.END

# ─── ЗАПУСК ──────────────────────────────────────────

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_role)],
        GUEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_guest_name)],
        SELECT_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_guest)],
        CONFIRM_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_guest)],
        NEW_STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_status)],
        NEW_BIRTHDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_birthday)],
        NEW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_phone)],
        NEW_IMPORTANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_important)],
        CREATE_GUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_guest)],
        HOOKAH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, hookah_input)],
        HOOKAH_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, hookah_notes)],
        BAR_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bar_input)],
        BAR_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, bar_notes)],
    },
    fallbacks=[
        CommandHandler("stop", stop),
        CommandHandler("cancel", stop),
    ],
)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(conv_handler)
app.run_polling()
