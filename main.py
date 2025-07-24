import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройки логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_PMR_RATE = 16.10  # Резервный курс рубля ПМР
CRYPTO_RATE_DEFAULT = 18.100  # Дефолтный курс крипты

# Глобальные переменные для хранения курсов
current_pmr_rate = DEFAULT_PMR_RATE
user_crypto_rates = {}  # user_id: rate


def get_pmr_exchange_rate():
    """Получение курса рубля ПМР с сайта bankipmr.ru"""
    global current_pmr_rate
    try:
        url = "https://bankipmr.ru/konverter-valjut/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Поиск блока с курсом USD/RUB ПМР
        rate_block = soup.find('div', class_='currency-rate')
        if rate_block:
            rate_text = rate_block.find('span', class_='rate').text.strip()
            current_pmr_rate = float(rate_text)
            return current_pmr_rate

        return current_pmr_rate
    except Exception as e:
        logger.error(f"Ошибка при получении курса: {e}")
        return current_pmr_rate


# Инициализация бота с вашим API-ключом
bot = Bot(token="7564150169:AAFcXszV_SsrCZkLilfFEicVSa3Pvh1tCCk")
dp = Dispatcher()
router = Router()
dp.include_router(router)


# Классы состояний
class ProfitStates(StatesGroup):
    earned = State()
    spent = State()
    currency = State()
    crypto_rate = State()


class ConvertStates(StatesGroup):
    amount = State()
    direction = State()


class CryptoRateState(StatesGroup):
    set_crypto_rate = State()


# Главное меню
def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Курс валют", callback_data="exchange_rate"),
        InlineKeyboardButton(text="🧮 Рассчитать прибыль", callback_data="calculate_profit"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Конвертировать", callback_data="convert_currency"),
        InlineKeyboardButton(text="⚙️ Задать курс крипты", callback_data="set_crypto_rate"),
    )
    return builder.as_markup()


# Меню курсов валют
def exchange_rate_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Рубль ПМР", callback_data="rate_pmr"),
        InlineKeyboardButton(text="Доллар", callback_data="rate_usd"),
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()


# Меню конвертации
def convert_currency_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💵 В рубли ПМР", callback_data="convert_to_pmr"),
        InlineKeyboardButton(text="💲 В доллары", callback_data="convert_to_usd"),
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()


# Меню выбора валюты для расчета прибыли
def currency_select_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Доллары ($)", callback_data="currency_usd"),
        InlineKeyboardButton(text="Рубли ПМР", callback_data="currency_pmr"),
    )
    return builder.as_markup()


# Обработка команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🏦 Бот для расчета прибыли и конвертации валют\n"
        "Выберите действие:",
        reply_markup=main_menu_kb()
    )


# Возврат в главное меню
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏦 Бот для расчета прибыли и конвертации валют\n"
        "Выберите действие:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


# Показ меню курсов валют
@dp.callback_query(F.data == "exchange_rate")
async def exchange_rate_menu(callback: CallbackQuery):
    pmr_rate = get_pmr_exchange_rate()
    await callback.message.edit_text(
        f"📊 Актуальные курсы валют:\n"
        f"• 1$ = {pmr_rate} руб. ПМР\n"
        "• 1 USDT = 1.00$ (стабильная привязка)\n"
        "Выберите валюту для просмотра:",
        reply_markup=exchange_rate_kb()
    )
    await callback.answer()


# Показ курса валюты
@dp.callback_query(F.data.startswith("rate_"))
async def show_rate(callback: CallbackQuery):
    currency = callback.data.split("_")[1]
    pmr_rate = get_pmr_exchange_rate()

    if currency == "pmr":
        text = f"📊 Текущий курс рубля ПМР:\n1$ = {pmr_rate} руб. ПМР"
    else:
        text = "📊 Текущий курс доллара:\n1 USDT = 1.00$ (Tether привязан к доллару)"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="exchange_rate")]
        ]
    )

    await callback.message.edit_text(
        text=text,
        reply_markup=keyboard
    )
    await callback.answer()


# Запуск расчета прибыли
@dp.callback_query(F.data == "calculate_profit")
async def start_profit_calculation(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💵 Введите сумму заработка:")
    await state.set_state(ProfitStates.earned)
    await callback.answer()


# Получение суммы заработка
@dp.message(ProfitStates.earned)
async def received_earned(message: Message, state: FSMContext):
    try:
        earned = float(message.text)
        await state.update_data(earned=earned)
        await message.answer("💸 Введите сумму затрат:")
        await state.set_state(ProfitStates.spent)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число. Попробуйте еще раз:")


# Получение суммы затрат
@dp.message(ProfitStates.spent)
async def received_spent(message: Message, state: FSMContext):
    try:
        spent = float(message.text)
        await state.update_data(spent=spent)
        await message.answer(
            "💰 Выберите валюту ввода:",
            reply_markup=currency_select_kb()
        )
        await state.set_state(ProfitStates.currency)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число. Попробуйте еще раз:")


# Получение валюты для расчета
@dp.callback_query(ProfitStates.currency, F.data.startswith("currency_"))
async def received_currency(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    await state.update_data(currency=currency)

    user_id = callback.from_user.id
    crypto_rate = user_crypto_rates.get(user_id, CRYPTO_RATE_DEFAULT)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Использовать текущий",
                callback_data="use_current_crypto_rate"
            )]
        ]
    )

    await callback.message.edit_text(
        f"⚙️ Текущий курс крипты: {crypto_rate} руб. ПМР за 1$\n"
        "Введите новый курс или нажмите 'Использовать текущий':",
        reply_markup=keyboard
    )
    await state.set_state(ProfitStates.crypto_rate)
    await callback.answer()


# Использование текущего курса крипты
@dp.callback_query(ProfitStates.crypto_rate, F.data == "use_current_crypto_rate")
async def use_current_crypto_rate(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    crypto_rate = user_crypto_rates.get(user_id, CRYPTO_RATE_DEFAULT)
    await calculate_and_show_profit(callback, state, crypto_rate)
    await callback.answer()


# Получение курса криптовалюты
@dp.message(ProfitStates.crypto_rate)
async def received_crypto_rate(message: Message, state: FSMContext):
    try:
        crypto_rate = float(message.text)
        await calculate_and_show_profit(message, state, crypto_rate)
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число. Попробуйте еще раз:")


# Расчет и показ прибыли
async def calculate_and_show_profit(source, state: FSMContext, crypto_rate: float):
    user_data = await state.get_data()
    user_id = source.from_user.id

    user_crypto_rates[user_id] = crypto_rate

    pmr_rate = get_pmr_exchange_rate()
    earned = user_data['earned']
    spent = user_data['spent']
    currency = user_data['currency']

    profit = earned - spent

    if currency == 'usd':
        profit_pmr = profit * pmr_rate
    else:
        profit_pmr = profit

    profit_crypto = profit_pmr / crypto_rate

    result = (
        f"📊 Результаты расчета:\n"
        f"• Заработок: {earned} {'$' if currency == 'usd' else 'руб. ПМР'}\n"
        f"• Затраты: {spent} {'$' if currency == 'usd' else 'руб. ПМР'}\n"
        f"• Чистая прибыль: {profit:.2f} {'$' if currency == 'usd' else 'руб. ПМР'}\n"
        f"• Прибыль в руб. ПМР: {profit_pmr:.2f}\n"
        f"• Прибыль в криптовалюте: {profit_crypto:.2f}$ (по курсу {crypto_rate} руб./$)"
    )

    if isinstance(source, Message):
        await source.answer(result)
        await source.answer(
            'Выберите следующее действие:',
            reply_markup=main_menu_kb()
        )
    elif isinstance(source, CallbackQuery):
        await source.message.answer(result)
        await source.message.answer(
            'Выберите следующее действие:',
            reply_markup=main_menu_kb()
        )

    await state.clear()


# Запуск конвертации валют
@dp.callback_query(F.data == "convert_currency")
async def start_convert_currency(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔄 Выберите направление конвертации:",
        reply_markup=convert_currency_kb()
    )
    await callback.answer()


# Обработка выбора направления конвертации
@dp.callback_query(F.data.startswith("convert_to_"))
async def convert_direction_selected(callback: CallbackQuery, state: FSMContext):
    direction = callback.data.split("_")[2]  # convert_to_pmr → pmr

    await state.update_data(direction=direction)

    if direction == "pmr":
        await callback.message.edit_text("💵 Введите сумму в долларах:")
    else:
        await callback.message.edit_text("💵 Введите сумму в рублях ПМР:")

    await state.set_state(ConvertStates.amount)
    await callback.answer()


# Получение суммы для конвертации
@dp.message(ConvertStates.amount)
async def convert_amount_received(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        user_data = await state.get_data()
        direction = user_data['direction']
        pmr_rate = get_pmr_exchange_rate()

        if direction == "pmr":
            result = amount * pmr_rate
            text = f"💱 {amount}$ = {result:.2f} руб. ПМР (курс: 1$ = {pmr_rate})"
        else:
            result = amount / pmr_rate
            text = f"💱 {amount} руб. ПМР = {result:.2f}$ (курс: 1$ = {pmr_rate})"

        await message.answer(text)
        await message.answer(
            'Выберите следующее действие:',
            reply_markup=main_menu_kb()
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число. Попробуйте еще раз:")


# Установка курса криптовалюты
@dp.callback_query(F.data == "set_crypto_rate")
async def set_crypto_rate(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    crypto_rate = user_crypto_rates.get(user_id, CRYPTO_RATE_DEFAULT)

    await callback.message.edit_text(
        f"⚙️ Текущий курс криптовалюты: {crypto_rate} руб. ПМР за 1$\n"
        "Введите новый курс:"
    )
    await state.set_state(CryptoRateState.set_crypto_rate)
    await callback.answer()


# Сохранение нового курса криптовалюты
@dp.message(CryptoRateState.set_crypto_rate)
async def save_crypto_rate(message: Message, state: FSMContext):
    try:
        new_rate = float(message.text)
        user_id = message.from_user.id
        user_crypto_rates[user_id] = new_rate
        await message.answer(f"✅ Новый курс криптовалюты установлен: {new_rate} руб. ПМР за 1$")
        await message.answer(
            'Выберите следующее действие:',
            reply_markup=main_menu_kb()
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число. Попробуйте еще раз:")


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())