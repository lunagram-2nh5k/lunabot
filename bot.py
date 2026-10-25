import os, random, sqlite3, asyncio, hmac, hashlib
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.environ["BOT_TOKEN"]
SECRET = os.environ["SECRET"]          # общий секрет между сервером LunaGram и ботом
PORT = int(os.environ.get("PORT", 10000))
DB = os.environ.get("DB_PATH", "numbers.db")

db = sqlite3.connect(DB, check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS numbers(phone TEXT PRIMARY KEY, tg_id INTEGER)")
db.commit()

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Получить номер")], [KeyboardButton(text="📋 Мои номера")]],
    resize_keyboard=True)

def new_number():
    while True:
        phone = "+7977" + "".join(random.choices("0123456789", k=7))
        if not db.execute("SELECT 1 FROM numbers WHERE phone=?", (phone,)).fetchone():
            return phone

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("LunaGram Auth. Получите номер и введите его в клиенте LunaGram — код придёт сюда.", reply_markup=kb)

@dp.message(F.text == "📱 Получить номер")
async def get_number(m: Message):
    n = db.execute("SELECT COUNT(*) FROM numbers WHERE tg_id=?", (m.from_user.id,)).fetchone()[0]
    if n >= 3:
        return await m.answer("Лимит: 3 номера на аккаунт.")
    phone = new_number()
    db.execute("INSERT INTO numbers VALUES(?,?)", (phone, m.from_user.id)); db.commit()
    await m.answer(f"✅ Ваш номер: {phone}\nВведите его в LunaGram. Код подтверждения придёт в этот чат.")

@dp.message(F.text == "📋 Мои номера")
async def my_numbers(m: Message):
    rows = db.execute("SELECT phone FROM numbers WHERE tg_id=?", (m.from_user.id,)).fetchall()
    await m.answer("\n".join(r[0] for r in rows) or "Номеров пока нет.")

# Сервер OwpenGram шлёт сюда код (Webhook v1: POST /v1/otp/deliveries)
async def otp_delivery(request: web.Request):
    raw = await request.read()
    ts = request.headers.get("X-Telesrv-Timestamp", "")
    sig = request.headers.get("X-Telesrv-Signature", "")
    expected = "sha256=" + hmac.new(SECRET.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return web.json_response({"accepted": False, "error_code": "BAD_SIGNATURE", "retryable": False}, status=403)
    data = await request.json()
    digits = "".join(c for c in str(data.get("recipient", "")) if c.isdigit())
    code = data.get("code")
    row = db.execute("SELECT tg_id FROM numbers WHERE phone=?", ("+" + digits,)).fetchone()
    if not row:
        return web.json_response({"accepted": False, "error_code": "RECIPIENT_INVALID", "retryable": False})
    await bot.send_message(row[0], f"🔔 Код авторизации LunaGram\n📱 Номер: +{digits}\n🔑 Код: {code}\n\nДействителен 5 минут.")
    return web.json_response({"accepted": True, "message_id": str(data.get("delivery_id", ""))})

async def health(request): return web.Response(text="ok")

async def main():
    app = web.Application()
    app.add_routes([web.post("/v1/otp/deliveries", otp_delivery), web.get("/", health)])
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
