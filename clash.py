import logging
import sqlite3
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- НАСТРОЙКИ (КОНФИГУРАЦИЯ) ---
BOT_TOKEN = "8716865369:AAFLGUHrg6qVK1lPAQZvhUepyoN2xInfsik"
COC_API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjQyMmViN2U0LWY0NGEtNGY5NS1hNjMwLTBlZjAwNDgxYWMwMyIsImlhdCI6MTc5MTY1MTM4Niwic3ViIjoiZGV2ZWxvcGVyL2IzNjEzMGIyLTE1YjAtNGUzZC05YTc3LTIyMmZiMmY5NjY3ZSIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjAuMC4wLjAiXSwidHlwZSI6ImNsaWVudCJ9XX0.s5wkl7fzjYgvp9-Th6u0X2vI41Se-qxFn4TKPOnKJ6uRegm1tlbyqwOthu_JQ-umU4gjIHUEOYTBz9i39MzvDQ"
CLAN_TAG = "#2L80PP89C"

ADMIN_CHAT_ID = None 

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {COC_API_TOKEN}"
}

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("clan_capital.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raid_history (
            season_id TEXT,
            player_tag TEXT,
            player_name TEXT,
            attacks INTEGER,
            loot INTEGER,
            PRIMARY KEY (season_id, player_tag)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_clean_tag(tag: str) -> str:
    tag = tag.strip()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag.replace("#", "%23")

# ФУНКЦИЯ АВТОМАТИЧЕСКОГО СОХРАНЕНИЯ РЕЙДА
async def auto_save_raid(app):
    global ADMIN_CHAT_ID
    url = f"https://api.clashofclans.com/v1/clans/{get_clean_tag(CLAN_TAG)}/capitalraidseasons"

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            items = res.json().get("items", [])
            if not items:
                logging.warning("Авто-сохранение: Данные о рейдах не найдены.")
                return

            last_season = items[0]
            season_id = last_season.get("endTime")
            members = last_season.get("members", [])

            conn = sqlite3.connect("clan_capital.db")
            cursor = conn.cursor()

            saved_count = 0
            for m in members:
                tag = m.get("tag")
                name = m.get("name")
                attacks = m.get("attacks", 0)
                loot = m.get("capitalResourcesLooted", 0)

                cursor.execute("""
                    INSERT OR REPLACE INTO raid_history (season_id, player_tag, player_name, attacks, loot)
                    VALUES (?, ?, ?, ?, ?)
                """, (season_id, tag, name, attacks, loot))
                saved_count += 1

            conn.commit()
            conn.close()
            logging.info(f"Автоматически сохранен рейд для {saved_count} участников.")

            if ADMIN_CHAT_ID:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"📜 **Еженедельная клановая летопись обновлена!**\n\nРазведчики принесли свитки с результатами рейд-уикенда ({saved_count} воинов записано в историю). Вождь будет доволен, Сэр!",
                    parse_mode="Markdown"
                )
        else:
            logging.error(f"Авто-сохранение: Ошибка API {res.status_code}")
    except Exception as e:
        logging.error(f"Ошибка автоматического сохранения рейда: {e}")

# Главное меню в стиле CoC
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = update.effective_chat.id

    keyboard = [
        [
            InlineKeyboardButton("🛡 Деревня клана", callback_data="clan_info"),
            InlineKeyboardButton("⚔️ Карта войны (КВ)", callback_data="war_info")
        ],
        [
            InlineKeyboardButton("🏰 Штурм Столицы", callback_data="capital_last"),
            InlineKeyboardButton("💾 Летопись рейда (в БД)", callback_data="save_raid")
        ],
        [
            InlineKeyboardButton("📜 Доска почета и нарушителей", callback_data="player_history")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🏰 **Главная Ратуша клана на связи, Сэр!**\n\n"
        "Строители закончили подготовку отчетов, а варвары уже принесли свежие вести с полей сражений. "
        "Выберите приказ Вождя:"
    )
    
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# Ручное сохранение
async def save_raid_handler(query):
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Вернуться в Ратушу", callback_data="back_to_menu")]])
    url = f"https://api.clashofclans.com/v1/clans/{get_clean_tag(CLAN_TAG)}/capitalraidseasons"

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            items = res.json().get("items", [])
            if not items:
                await query.edit_message_text("Данные о рейдах не найдены, Сэр.", reply_markup=back_button)
                return

            last_season = items[0]
            season_id = last_season.get("endTime")
            members = last_season.get("members", [])

            conn = sqlite3.connect("clan_capital.db")
            cursor = conn.cursor()

            saved_count = 0
            for m in members:
                tag = m.get("tag")
                name = m.get("name")
                attacks = m.get("attacks", 0)
                loot = m.get("capitalResourcesLooted", 0)

                cursor.execute("""
                    INSERT OR REPLACE INTO raid_history (season_id, player_tag, player_name, attacks, loot)
                    VALUES (?, ?, ?, ?, ?)
                """, (season_id, tag, name, attacks, loot))
                saved_count += 1

            conn.commit()
            conn.close()

            text = f"🗡 **Подвиги внесены в летопись, Сэр!**\n\nСохранено воинов: **{saved_count}**.\nТеперь их результаты учтены в истории клана!"
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_button)
        else:
            await query.edit_message_text(f"❌ Ошибка API: {res.status_code}", reply_markup=back_button)
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при сохранении: {e}", reply_markup=back_button)

# Карточки игроков
async def player_history_handler(query):
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Вернуться в Ратушу", callback_data="back_to_menu")]])
    conn = sqlite3.connect("clan_capital.db")
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT player_name, player_tag FROM raid_history ORDER BY player_name ASC")
    players = cursor.fetchall()

    if not players:
        conn.close()
        await query.edit_message_text("Клановая летопись пока пуста, Сэр. Нажмите «💾 Летопись рейда (в БД)» или дождитесь понедельника.", reply_markup=back_button)
        return

    msg = ["📜 **Клановая летопись воинов за все сезоны:**\n"]

    for name, tag in players:
        cursor.execute("SELECT loot, attacks FROM raid_history WHERE player_tag = ? ORDER BY season_id ASC", (tag,))
        records = cursor.fetchall()

        loots = [r[0] for r in records]
        total_loot = sum(loots)
        avg_loot = total_loot // len(loots) if loots else 0

        if avg_loot >= 22000:
            status = "🟢 — Славный воин!"
        elif avg_loot >= 18000:
            status = "🟨 — Старайся лучше"
        else:
            status = "🔴 — Халтурщик / Нарушитель"

        msg.append(f"⚔️ **Воин {name}:**")
        msg.append("Результаты в рейдах:")
        for l in loots:
            msg.append(f"  • {l:,} 🪙")
        msg.append(f"**Средний куш за уикенд:**")
        msg.append(f"**{avg_loot:,}** {status}\n")

    conn.close()
    
    output_text = "\n".join(msg)
    if len(output_text) > 4000:
        output_text = output_text[:3900] + "\n\n_...свиток слишком длинный, часть данных сокращена._"

    await query.edit_message_text(output_text, parse_mode="Markdown", reply_markup=back_button)

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Вернуться в Ратушу", callback_data="back_to_menu")]])

    if query.data == "back_to_menu":
        await start(update, context)

    elif query.data == "clan_info":
        url = f"https://api.clashofclans.com/v1/clans/{get_clean_tag(CLAN_TAG)}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                d = res.json()
                text = (
                    f"🛡 **Клан:** {d.get('name')}\n"
                    f"🏷 **Тег:** {d.get('tag')}\n"
                    f"⭐ **Уровень клана:** {d.get('clanLevel')}\n"
                    f"👥 **Численность воинов:** {d.get('members')}/50\n"
                    f"🏆 **Кубки клана:** {d.get('clanPoints')}\n"
                    f"🏰 **Кубки Столицы:** {d.get('clanCapitalPoints')}\n\n"
                    f"📜 **Указ Вождя (Описание):**\n_{d.get('description', 'Нет описания')}_"
                )
            else:
                text = f"❌ Ошибка API: {res.status_code}"
        except Exception as e:
            text = f"❌ Ошибка запроса: {e}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_button)

    elif query.data == "war_info":
        url = f"https://api.clashofclans.com/v1/clans/{get_clean_tag(CLAN_TAG)}/currentwar"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                d = res.json()
                state = d.get("state")
                if state == "notInWar":
                    text = "⚔️ В деревне мирное время, Сэр! Клан пока не ведет войну."
                else:
                    clan = d.get("clan", {})
                    opponent = d.get("opponent", {})
                    text = (
                        f"⚔️ **Состояние войны:** {state.upper()}\n\n"
                        f"🛡 **{clan.get('name')}**: ⭐ {clan.get('stars', 0)} | {clan.get('destructionPercentage', 0):.1f}%\n"
                        f"🗡 **{opponent.get('name')}**: ⭐ {opponent.get('stars', 0)} | {opponent.get('destructionPercentage', 0):.1f}%\n\n"
                        f"🎯 Атак проведено: {clan.get('attacks', 0)}/{d.get('teamSize', 0) * 2}"
                    )
            else:
                text = f"❌ Ошибка API: {res.status_code}"
        except Exception as e:
            text = f"❌ Ошибка соединения: {e}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_button)

    elif query.data == "capital_last":
        url = f"https://api.clashofclans.com/v1/clans/{get_clean_tag(CLAN_TAG)}/capitalraidseasons"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                items = res.json().get("items", [])
                if items:
                    last_season = items[0]
                    text = (
                        f"🏰 **Сводка штурма Столицы (Последний уикенд)**\n\n"
                        f"⚔️ **Всего атак:** {last_season.get('totalAttacks')}\n"
                        f"💰 **Заработано золото столицы:** {last_season.get('capitalTotalLoot', 0):,}\n"
                        f"💥 **Разрушено районов врага:** {last_season.get('enemyDistrictsDestroyed')}"
                    )
                else:
                    text = "Данные по рейдам не найдены, Сэр."
            else:
                text = f"❌ Ошибка API: {res.status_code}"
        except Exception as e:
            text = f"❌ Ошибка: {e}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_button)

    elif query.data == "save_raid":
        await save_raid_handler(query)

    elif query.data == "player_history":
        await player_history_handler(query)

# Обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Произошла ошибка при обработке обновления: {context.error}")

# Запуск планировщика в цикле событий
async def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        auto_save_raid,
        trigger=CronTrigger(day_of_week='mon', hour=12, minute=0),
        args=[app]
    )
    scheduler.start()
    print("⏰ Планировщик авто-сохранений по понедельникам в 12:00 успешно запущен!")

if __name__ == "__main__":
    print("Ратуша готова, Сэр! Принудительно сбрасываем старые вебхуки в Telegram...")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_scheduler).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)

    app.run_polling()
