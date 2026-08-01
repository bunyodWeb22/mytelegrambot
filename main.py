import logging
import random
import io
import json
import os
import asyncio
import html
from gtts import gTTS

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from words import UNITS

# --- ADMIN SOZLAMASI ---
ADMIN_ID = 6466373319

# Foydalanuvchilarni saqlash uchun fayl
USERS_FILE = "users.json"
# Faol duellar bazasi
ACTIVE_DUELS = {}

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_data(user, score=None, add_hard_word=None):
    users = load_users()
    user_id = str(user.id)
    
    if user_id not in users:
        users[user_id] = {
            "name": user.first_name,
            "username": user.username if user.username else "Yo'q",
            "score": 0,
            "hard_words": []
        }
    
    users[user_id]["name"] = user.first_name
    users[user_id]["username"] = user.username if user.username else "Yo'q"
    
    if score is not None:
        users[user_id]["score"] = score
        
    if add_hard_word:
        if "hard_words" not in users[user_id]:
            users[user_id]["hard_words"] = []
        if not any(w['word'] == add_hard_word['word'] for w in users[user_id]["hard_words"]):
            users[user_id]["hard_words"].append(add_hard_word)

    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

CHOOSE_UNIT, QUIZ = range(2)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📚 Mashq boshlash"), KeyboardButton("⚔️ Do'st bilan Duel")],
        [KeyboardButton("🏆 Reyting"), KeyboardButton("📊 Natijalarim")],
        [KeyboardButton("🔥 Qiyin so'zlarim"), KeyboardButton("🔄 Takrorlash")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_unit_keyboard():
    keyboard = []
    row = []
    for i in range(1, 29):
        row.append(KeyboardButton(f"Unit {i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton("🔙 Asosiy menyu")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_data(context: ContextTypes.DEFAULT_TYPE):
    if 'score' not in context.user_data:
        context.user_data['score'] = 0
    if 'total_solved' not in context.user_data:
        context.user_data['total_solved'] = 0
    if 'total_correct' not in context.user_data:
        context.user_data['total_correct'] = 0
    if 'has_practiced' not in context.user_data:
        context.user_data['has_practiced'] = False

async def setup_bot_commands(app):
    commands = [
        BotCommand("start", "🚀 Botni qayta ishga tushirish"),
        BotCommand("practice", "📚 So'z yodlash"),
        BotCommand("review", "🔄 Xato so'zlarni takrorlash"),
        BotCommand("qiyin", "🔥 Qiyin so'zlarim"),
        BotCommand("battle", "⚔️ Do'st bilan duel"),
        BotCommand("leaderboard", "🏆 Reyting"),
        BotCommand("mystats", "📊 Mening natijalarim"),
        BotCommand("help", "❓ Yordam")
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user_data(user)
    get_user_data(context)

    # Agar do'st bilan duel havolasi orqali kirgan bo'lsa
    if context.args and context.args[0].startswith("duel_"):
        duel_id = context.args[0].replace("duel_", "")
        if duel_id in ACTIVE_DUELS:
            duel = ACTIVE_DUELS[duel_id]
            if duel['p2'] is None and duel['p1_id'] != user.id:
                duel['p2'] = user.id
                duel['p2_name'] = user.first_name
                duel['p2_score'] = 0
                duel['p2_index'] = 0
                
                await update.message.reply_text(
                    f"⚔️ <b>Duel qabul qilindi!</b>\n\n"
                    f"Raqibingiz: <b>{html.escape(duel['p1_name'])}</b>\n"
                    f"O'yin boshlanmoqda. Tayyor turing! 🚀",
                    parse_mode="HTML"
                )
                await send_friend_battle_question(context, duel_id, user.id, 0)
                return CHOOSE_UNIT
            elif duel['p2'] == user.id:
                await update.message.reply_text("Siz allaqachon bu duelga qo'shilgansiz!")
                return CHOOSE_UNIT

    total_units = len(UNITS)
    total_words = sum(len(words) for words in UNITS.values())
    score = context.user_data['score']

    text = (
        f"👋 Salom, <b>{html.escape(user.first_name)}</b>!\n\n"
        f"🎓 <b>Essential English Lug'at Boti</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 {total_units} ta unit | {total_words} ta so'z\n"
        f"💰 Achkongiz: <b>{score}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"/practice — 📚 so'z yodlash\n"
        f"/battle — ⚔️ do'st bilan duel\n"
        f"/mystats — 📊 mening natijalarim\n"
        f"/leaderboard — 🏆 reyting"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )
    return CHOOSE_UNIT

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Bu buyruq faqat admin uchun!")
        return

    users = load_users()
    total_users = len(users)

    msg = f"📊 <b>Bot statistikasi:</b>\n\n👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n\n"
    for u_id, u_info in users.items():
        name = html.escape(u_info.get('name', 'User'))
        msg += f"• {name} | ID: <code>{u_id}</code> | Achko: {u_info.get('score', 0)}\n"

    await update.message.reply_text(msg, parse_mode="HTML")

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)
    total = context.user_data['total_solved']
    correct = context.user_data['total_correct']
    score = context.user_data['score']
    percent = round((correct / total * 100)) if total > 0 else 0

    users = load_users()
    u_id = str(update.effective_user.id)
    hard_words_count = len(users.get(u_id, {}).get("hard_words", []))

    await update.message.reply_text(
        f"📊 <b>Mening Natijalarim:</b>\n\n"
        f"💰 Achkolar: <b>{score}</b>\n"
        f"❓ Jami yechilgan: <b>{total} ta</b>\n"
        f"✅ To'g'ri topilgan: <b>{correct} ta</b>\n"
        f"📈 Aniqlik darajasi: <b>{percent}%</b>\n"
        f"🔥 Qiyin so'zlar: <b>{hard_words_count} ta</b>",
        parse_mode="HTML"
    )

async def generic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0]
    user = update.effective_user
    
    if cmd in ["/review", "/qiyin", "🔥 Qiyin so'zlarim", "🔄 Takrorlash"]:
        users = load_users()
        u_id = str(user.id)
        hard_words = users.get(u_id, {}).get("hard_words", [])
        
        if not hard_words:
            await update.message.reply_text("🎉 <b>Ajoyib!</b> Sizda hozircha qiyin so'zlar mavjud emas.", parse_mode="HTML")
            return
            
        msg = "🔥 <b>Sizning qiyin so'zlaringiz:</b>\n\n"
        for idx, item in enumerate(hard_words, 1):
            msg += f"{idx}. <b>« {html.escape(str(item['word']))} »</b> — {html.escape(str(item['trans']))}\n"
            
        await update.message.reply_text(msg, parse_mode="HTML")
    elif cmd == "/help":
        await update.message.reply_text("❓ Botdan foydalanish uchun tugmalardan foydalaning.", parse_mode="HTML")

# --- DO'ST BILAN BATTLE (DUEL) MANTIQI ---

async def start_friend_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    all_words = [w for unit in UNITS.values() for w in unit if 'word' in w]
    if len(all_words) < 5:
        await update.message.reply_text("Battle uchun bazada so'zlar yetarli emas.")
        return CHOOSE_UNIT

    battle_questions = random.sample(all_words, 5)
    duel_id = str(random.randint(10000, 99999))

    ACTIVE_DUELS[duel_id] = {
        'questions': battle_questions,
        'p1_id': user.id,
        'p1_name': user.first_name,
        'p1_score': 0,
        'p1_index': 0,
        'p2': None,
        'p2_name': None,
        'p2_score': 0,
        'p2_index': 0
    }

    bot_username = (await context.bot.get_me()).username
    duel_link = f"https://t.me/{bot_username}?start=duel_{duel_id}"

    keyboard = [[InlineKeyboardButton("⚔️ Duelga qo'shilish", url=duel_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"⚔️ <b>Do'st bilan Duel tashkil qilindi!</b>\n\n"
        f"👤 Taklif qiluvchi: <b>{html.escape(user.first_name)}</b>\n"
        f"Quyidagi tugmani bosing va bu havolani **do'stingizga yuboring**. Do'stingiz bosishi bilan o'yin boshlanadi!",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

    await send_friend_battle_question(context, duel_id, user.id, 0)
    return CHOOSE_UNIT

async def send_friend_battle_question(context: ContextTypes.DEFAULT_TYPE, duel_id: str, user_id: int, idx: int):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        return

    questions = duel['questions']
    if idx >= len(questions):
        if user_id == duel['p1_id']:
            duel['p1_finished'] = True
        else:
            duel['p2_finished'] = True

        await context.bot.send_message(
            chat_id=user_id,
            text="🏁 <b>Siz barcha savollarga javob berdingiz!</b>\nNatijangiz saqlandi. Raqibingiz ham tugatgach yakuniy natija e'lon qilinadi.",
            parse_mode="HTML"
        )
        
        if duel.get('p2') and duel.get('p1_finished') and duel.get('p2_finished'):
            await finish_friend_battle(context, duel_id)
        return

    current = questions[idx]
    all_words = [w['word'] for unit in UNITS.values() for w in unit if 'word' in w]
    wrong_options = list(set([w for w in all_words if w != current['word']]))
    options = random.sample(wrong_options, 3) + [current['word']]
    random.shuffle(options)

    buttons = []
    for opt in options:
        is_correct = "1" if opt == current['word'] else "0"
        buttons.append([InlineKeyboardButton(opt, callback_data=f"fbtl_{duel_id}_{is_correct}_{opt}_{idx}")])

    reply_markup = InlineKeyboardMarkup(buttons)
    trans_text = html.escape(str(current['trans']))
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"⚔️ <b>Do'stlar dueli | Raund {idx + 1}/5</b>\n\n❓ <b>« {trans_text} »</b> so'zining inglizcha tarjimasi qaysi?",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def handle_friend_battle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    duel_id = data[1]
    is_correct = data[2]
    chosen_word = data[3]
    idx = int(data[4])

    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        await query.edit_message_text("⚠️ Bu duel allaqachon yakunlangan yoki topilmadi.")
        return

    user_id = query.from_user.id
    is_p1 = (user_id == duel['p1_id'])

    msg = query.message.text + f"\n\nSizning tanlovingiz: {chosen_word} — "
    if is_correct == "1":
        if is_p1:
            duel['p1_score'] += 10
        else:
            duel['p2_score'] += 10
        msg += "✅ To'g'ri! (+10 ball)"
    else:
        msg += "❌ Noto'g'ri!"

    await query.edit_message_text(msg)

    next_idx = idx + 1
    if is_p1:
        duel['p1_index'] = next_idx
    else:
        duel['p2_index'] = next_idx

    await send_friend_battle_question(context, duel_id, user_id, next_idx)

async def finish_friend_battle(context: ContextTypes.DEFAULT_TYPE, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel:
        return

    p1_id = duel['p1_id']
    p2_id = duel['p2']
    p1_score = duel['p1_score']
    p2_score = duel['p2_score']
    p1_name = duel['p1_name']
    p2_name = duel['p2_name']

    p1_res = ""
    p2_res = ""

    if p1_score > p2_score:
        p1_res = "🎉 G'olib bo'ldingiz! 🏆"
        p2_res = "🤖 Yutqazdingiz. Keyingi safar omad!"
    elif p1_score < p2_score:
        p1_res = "🤖 Yutqazdingiz. Keyingi safar omad!"
        p2_res = "🎉 G'olib bo'ldingiz! 🏆"
    else:
        p1_res = "🤝 Durang!"
        p2_res = "🤝 Durang!"

    text_p1 = f"🏁 <b>Duel Yakunlandi!</b>\n\n👤 Sizning ballingiz: <b>{p1_score}</b>\n👥 Raqib ({p2_name}) balli: <b>{p2_score}</b>\n\n{p1_res}"
    text_p2 = f"🏁 <b>Duel Yakunlandi!</b>\n\n👤 Sizning ballingiz: <b>{p2_score}</b>\n👥 Raqib ({p1_name}) balli: <b>{p1_score}</b>\n\n{p2_res}"

    await context.bot.send_message(chat_id=p1_id, text=text_p1, parse_mode="HTML", reply_markup=get_main_keyboard())
    await context.bot.send_message(chat_id=p2_id, text=text_p2, parse_mode="HTML", reply_markup=get_main_keyboard())

    del ACTIVE_DUELS[duel_id]

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remaining_words = context.user_data.get('remaining_words', [])

    if not remaining_words:
        unit_num = context.user_data.get('unit')
        total = context.user_data.get('total_questions', 0)
        correct_count = context.user_data.get('correct_answers', 0)
        percentage = round((correct_count / total * 100)) if total > 0 else 0

        retry_keyboard = [
            [KeyboardButton(f"Unit {unit_num}")],
            [KeyboardButton("🔙 Asosiy menyu")]
        ]

        await update.message.reply_text(
            f"🎉 <b>Unit {unit_num} testi yakunlandi!</b>\n\n"
            f"✅ To'g'ri javoblar: <b>{correct_count} / {total}</b>\n"
            f"📈 Aniqlik: <b>{percentage}%</b>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(retry_keyboard, resize_keyboard=True)
        )
        return CHOOSE_UNIT

    correct_item = random.choice(remaining_words)
    remaining_words.remove(correct_item)
    context.user_data['remaining_words'] = remaining_words
    context.user_data['current_item'] = correct_item

    all_words = [w['word'] for unit in UNITS.values() for w in unit if 'word' in w]
    wrong_options = list(set([w for w in all_words if w != correct_item['word']]))

    if len(wrong_options) >= 3:
        options = random.sample(wrong_options, 3) + [correct_item['word']]
    else:
        options = [correct_item['word'], "Option B", "Option C", "Option D"]

    random.shuffle(options)

    quiz_keyboard = [
        [KeyboardButton(options[0]), KeyboardButton(options[1])],
        [KeyboardButton(options[2]), KeyboardButton(options[3])],
        [KeyboardButton("🗣 Talaffuz qilish"), KeyboardButton("💡 Maslahat (Hint)")],
        [KeyboardButton("🛑 Testni to'xtatish")]
    ]

    trans_text = html.escape(str(correct_item['trans']))
    await update.message.reply_text(
        f"❓ <b>« {trans_text} »</b> so'zining inglizcha tarjimasi qaysi?",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(quiz_keyboard, resize_keyboard=True)
    )
    return QUIZ

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    get_user_data(context)
    save_user_data(update.effective_user)

    if text in ["📚 Mashq boshlash", "/practice"]:
        await update.message.reply_text("Qaysi Unit bo'yicha mashq qilamiz? Tanlang:", reply_markup=get_unit_keyboard())
        return CHOOSE_UNIT

    elif text in ["📊 Natijalarim", "/mystats"]:
        await mystats(update, context)
        return CHOOSE_UNIT

    elif text in ["🏆 Reyting", "/leaderboard"]:
        users = load_users()
        msg = "🏆 <b>Top foydalanuvchilar reytingi:</b>\n\n"
        if users:
            sorted_users = sorted(users.values(), key=lambda x: x.get("score", 0), reverse=True)[:10]
            for idx, u in enumerate(sorted_users, 1):
                msg += f"{idx}. {html.escape(u.get('name', 'User'))} — <b>{u.get('score', 0)}</b> achko\n"
        else:
            msg += "Hali hech kim achko yig'madi."
        await update.message.reply_text(msg, parse_mode="HTML")
        return CHOOSE_UNIT

    elif text in ["⚔️ Do'st bilan Duel", "/battle"]:
        return await start_friend_battle(update, context)

    elif text in ["🔥 Qiyin so'zlarim", "/qiyin", "🔄 Takrorlash", "/review"]:
        await generic_command_handler(update, context)
        return CHOOSE_UNIT

    elif text == "🔙 Asosiy menyu":
        return await start(update, context)

    elif text.startswith("Unit "):
        try:
            unit_num = int(text.split(" ")[1])
            words = UNITS.get(unit_num, [])

            if not words:
                await update.message.reply_text(f"⚠️ Unit {unit_num} da so'zlar hali yo'q.")
                return CHOOSE_UNIT

            context.user_data['remaining_words'] = list(words)
            context.user_data['unit'] = unit_num
            context.user_data['total_questions'] = len(words)
            context.user_data['correct_answers'] = 0
            context.user_data['has_practiced'] = True

            await update.message.reply_text(f"📖 <b>Unit {unit_num}</b> testi boshlandi! Jami so'zlar: <b>{len(words)} ta</b>", parse_mode="HTML")
            return await ask_question(update, context)
        except (IndexError, ValueError):
            pass

    await update.message.reply_text("Iltimos, pastdagi menyudan birini tanlang.")
    return CHOOSE_UNIT

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_answer = update.message.text
    current_item = context.user_data.get('current_item', {})
    correct_answer = current_item.get('word', '')
    get_user_data(context)

    if user_answer == "🛑 Testni to'xtatish":
        await update.message.reply_text("Test to'xtatildi.", reply_markup=get_main_keyboard())
        return CHOOSE_UNIT

    if user_answer == "🗣 Talaffuz qilish":
        try:
            tts = gTTS(text=correct_answer, lang='en')
            voice_file = io.BytesIO()
            tts.write_to_fp(voice_file)
            voice_file.seek(0)
            await update.message.reply_voice(voice=voice_file, caption=f"🔊 Talaffuzi: <b>{correct_answer}</b>", parse_mode="HTML")
        except Exception:
            await update.message.reply_text("⚠️ Talaffuzni yuklashda xatolik yuz berdi.")
        return QUIZ

    if user_answer == "💡 Maslahat (Hint)":
        hint_word = correct_answer[0] + "..." + correct_answer[-1] if len(correct_answer) > 2 else correct_answer[0] + "..."
        await update.message.reply_text(f"💡 <b>Maslahat:</b> <b>{hint_word}</b> ({len(correct_answer)} ta harf).", parse_mode="HTML")
        return QUIZ

    context.user_data['total_solved'] += 1

    if user_answer == correct_answer:
        context.user_data['correct_answers'] += 1
        context.user_data['total_correct'] += 1
        context.user_data['score'] += 10
        save_user_data(update.effective_user, score=context.user_data['score'])
        await update.message.reply_text("✅ <b>To'g'ri!</b> (+10 achko 💰)", parse_mode="HTML")
    else:
        save_user_data(update.effective_user, score=context.user_data['score'], add_hard_word=current_item)
        await update.message.reply_text(f"❌ <b>Noto'g'ri!</b> To'g'ri javob: <b>{html.escape(str(correct_answer))}</b>", parse_mode="HTML")

    return await ask_question(update, context)

def main():
    TOKEN = "8949503703:AAGEB7MEDSGiuOyrR1OsFImg_-XEOB3u8ZE"  # Bot tokeningizni yozing

    app = ApplicationBuilder().token(TOKEN).post_init(setup_bot_commands).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("admin", admin_stats),
            CommandHandler("practice", handle_menu),
            CommandHandler("mystats", handle_menu),
            CommandHandler("leaderboard", handle_menu),
            CommandHandler("battle", handle_menu),
            CommandHandler("review", generic_command_handler),
            CommandHandler("qiyin", generic_command_handler),
            CommandHandler("help", generic_command_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)
        ],
        states={
            CHOOSE_UNIT: [
                CommandHandler("start", start),
                CommandHandler("admin", admin_stats),
                CommandHandler("review", generic_command_handler),
                CommandHandler("qiyin", generic_command_handler),
                CommandHandler("help", generic_command_handler),
                CallbackQueryHandler(handle_friend_battle_callback, pattern="^fbtl_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)
            ],
            QUIZ: [
                CommandHandler("start", start),
                CommandHandler("admin", admin_stats),
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_answer)
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(conv_handler)

    print("Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling()

if __name__ == '__main__':
    main()