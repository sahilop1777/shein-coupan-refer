import telebot
from telebot import types
import sqlite3

API_TOKEN = "7990432307:AAENMxxQF5Dufg7KV89PGNcjkOqk0LNz0Ts"
CHANNEL = "@channelforsellings"
ADMIN_ID = 6416481890

bot = telebot.TeleBot(API_TOKEN)

# ---------------- DATABASE ----------------

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    referred_by INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    amount INTEGER,
    used INTEGER DEFAULT 0,
    user_id INTEGER
)
""")

db.commit()

# ---------------- HELPERS ----------------

def init_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    db.commit()

def joined(uid):
    try:
        s = bot.get_chat_member(CHANNEL, uid).status
        return s in ["member", "administrator", "creator"]
    except:
        return False

def get_points(uid):
    cur.execute("SELECT points FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()[0]

def add_points(uid, pts):
    cur.execute("UPDATE users SET points = points + ? WHERE user_id=?", (pts, uid))
    db.commit()

def deduct_points(uid, pts):
    cur.execute("UPDATE users SET points = points - ? WHERE user_id=?", (pts, uid))
    db.commit()

# ---------------- START ----------------

@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    init_user(uid)

    args = m.text.split()
    if len(args) > 1:
        try:
            ref = int(args[1])
            cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,))
            if ref != uid and cur.fetchone()[0] is None:
                cur.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref, uid))
                db.commit()
        except:
            pass

    if joined(uid):
        verify_success(uid, m.chat.id)
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL[1:]}"),
            types.InlineKeyboardButton("Verify ✅", callback_data="verify")
        )
        bot.send_message(m.chat.id, "🚨 Join channel then verify", reply_markup=kb)

# ---------------- VERIFY ----------------

@bot.callback_query_handler(func=lambda c: c.data == "verify")
def verify(c):
    uid = c.from_user.id
    if not joined(uid):
        bot.answer_callback_query(c.id, "❌ Join channel first", show_alert=True)
        return
    verify_success(uid, c.message.chat.id)
    bot.delete_message(c.message.chat.id, c.message.message_id)

def verify_success(uid, chat_id):
    cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,))
    ref = cur.fetchone()[0]

    if ref:
        add_points(ref, 2)
        cur.execute("UPDATE users SET referred_by=NULL WHERE user_id=?", (uid,))
        db.commit()
        bot.send_message(ref, "🎉 You earned 2 referral points!")

    menu(chat_id)

# ---------------- MENU ----------------

def menu(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎁 Redeem", "⭐ Points")
    kb.add("🔗 My Referral Link", "📜 Coupon History")
    if chat_id == ADMIN_ID:
        kb.add("🛠 Admin Panel")
    bot.send_message(chat_id, "✅ Main Menu", reply_markup=kb)

# ---------------- USER ----------------

@bot.message_handler(func=lambda m: m.text == "⭐ Points")
def points(m):
    bot.send_message(m.chat.id, f"⭐ Points: {get_points(m.from_user.id)}")

@bot.message_handler(func=lambda m: m.text == "🔗 My Referral Link")
def ref(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    bot.send_message(
        m.chat.id,
        f"🔗 Share this referral link:\n{link}\n\n🎁 Earn 2 points per successful referral!"
    )

# ---------------- REDEEM ----------------

@bot.message_handler(func=lambda m: m.text == "🎁 Redeem")
def redeem(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("6 pts → ₹500", callback_data="r_500"),
        types.InlineKeyboardButton("12 pts → ₹1000", callback_data="r_1000"),
        types.InlineKeyboardButton("25 pts → ₹4000", callback_data="r_4000")
    )
    bot.send_message(m.chat.id, "🎁 Choose redeem option", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("r_"))
def do_redeem(c):
    uid = c.from_user.id
    amount = int(c.data.split("_")[1])
    cost = {500:6, 1000:12, 4000:25}[amount]

    if get_points(uid) < cost:
        bot.answer_callback_query(c.id, "❌ Not enough points", show_alert=True)
        return

    cur.execute("SELECT code FROM coupons WHERE amount=? AND used=0 LIMIT 1", (amount,))
    row = cur.fetchone()
    if not row:
        bot.answer_callback_query(c.id, "🚫 Coupons finished", show_alert=True)
        return

    coupon = row[0]
    deduct_points(uid, cost)
    cur.execute("UPDATE coupons SET used=1, user_id=? WHERE code=?", (uid, coupon))
    db.commit()

    bot.send_message(
        c.message.chat.id,
        f"🎟 Coupon ({amount}):\n`{coupon}`",
        parse_mode="Markdown"
    )

# ---------------- HISTORY ----------------

@bot.message_handler(func=lambda m: m.text == "📜 Coupon History")
def history(m):
    cur.execute("SELECT code FROM coupons WHERE user_id=?", (m.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        bot.send_message(m.chat.id, "📜 No coupons yet")
    else:
        bot.send_message(m.chat.id, "📜 Your Coupons:\n" + "\n".join(r[0] for r in rows))

# ---------------- ADMIN ----------------

@bot.message_handler(func=lambda m: m.text == "🛠 Admin Panel" and m.from_user.id == ADMIN_ID)
def admin(m):
    bot.send_message(
        m.chat.id,
        "/addcoupon AMOUNT CODE\n/addpoints USERID POINTS\n/stock"
    )

@bot.message_handler(commands=["addcoupon"])
def add_coupon(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(m.chat.id, "❌ /addcoupon AMOUNT CODE")
        return
    _, amt, code = parts
    cur.execute(
        "INSERT OR IGNORE INTO coupons (code, amount) VALUES (?, ?)",
        (code, int(amt))
    )
    db.commit()
    bot.send_message(m.chat.id, "✅ Coupon added")

@bot.message_handler(commands=["addpoints"])
def add_points_admin(m):
    if m.from_user.id != ADMIN_ID:
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(m.chat.id, "❌ /addpoints USERID POINTS")
        return
    _, uid, pts = parts
    add_points(int(uid), int(pts))
    bot.send_message(m.chat.id, "✅ Points added")

@bot.message_handler(commands=["stock"])
def stock(m):
    if m.from_user.id != ADMIN_ID:
        return
    cur.execute("SELECT amount, COUNT(*) FROM coupons WHERE used=0 GROUP BY amount")
    rows = cur.fetchall()
    msg = "📦 Coupon Stock:\n"
    for amt, cnt in rows:
        msg += f"₹{amt}: {cnt}\n"
    bot.send_message(m.chat.id, msg)

# ---------------- RUN ----------------

print("🤖 Bot Running on Railway")
bot.infinity_polling(skip_pending=True)


