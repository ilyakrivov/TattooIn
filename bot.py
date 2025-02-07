import logging
import os
import json
import asyncio
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from oauth2client.service_account import ServiceAccountCredentials

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Инициализация Google Sheets
try:
    creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    sheet = spreadsheet.sheet1
except Exception as e:
    logger.error(f"Ошибка подключения к Google Sheets: {e}")
    raise

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Клавиатуры
start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Свой"), KeyboardButton(text="Студия")]
    ],
    resize_keyboard=True
)

category_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Плёнка"), KeyboardButton(text="Набор")],
        [KeyboardButton(text="Клиент ухаживает сам")]
    ],
    resize_keyboard=True
)

film_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="500"), KeyboardButton(text="1000"), KeyboardButton(text="1500")]
    ],
    resize_keyboard=True
)

kit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="500"), KeyboardButton(text="1000")]
    ],
    resize_keyboard=True
)

restart_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Новая запись")]
    ],
    resize_keyboard=True
)

# Состояния FSM
class Form(StatesGroup):
    type = State()
    amount = State()
    category = State()
    category_amount = State()

# Колонки в таблице
COLUMNS = {
    "Свой": 2,
    "Студия": 3,
    "Плёнка": 4,
    "Набор": 5
}

async def update_sheet(user: str, column: int, value: str):
    """Обновляем или создаем запись мастера с суммированием"""
    try:
        search_query = user.strip()

        # Попробуем найти ячейку с именем пользователя
        cell = None
        try:
            cell = sheet.find(search_query)
        except gspread.exceptions.APIError as e:
            if "CellNotFound" in str(e):
                pass  # Пропускаем ошибку, если ячейка не найдена

        # Если ячейка не найдена, добавляем новую строку
        if not cell:
            row_num = len(sheet.get_all_values()) + 1
            sheet.update_cell(row_num, 1, search_query)
        else:
            row_num = cell.row

        # Получаем текущее значение и обновляем
        current_value = sheet.cell(row_num, column).value
        current_value = int(current_value) if current_value and current_value.isdigit() else 0
        new_value = current_value + int(value)
        
        sheet.update_cell(row_num, column, new_value)
        return True

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return False

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.set_state(Form.type)
    await message.answer("Выберите тип дохода:", reply_markup=start_kb)

@dp.message(Form.type, F.text.in_(["Свой", "Студия"]))
async def process_type(message: types.Message, state: FSMContext):
    await state.update_data(type=message.text)
    await state.set_state(Form.amount)
    await message.answer("Введите сумму:", reply_markup=ReplyKeyboardRemove())

@dp.message(Form.type)
async def incorrect_type(message: types.Message):
    await message.answer("❌ Выберите тип из кнопок!")

@dp.message(Form.amount, F.text.regexp(r'^\d+$'))
async def process_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await state.set_state(Form.category)
    await message.answer("Выберите категорию:", reply_markup=category_kb)

@dp.message(Form.amount)
async def incorrect_amount(message: types.Message):
    await message.answer("❌ Введите число без символов!")

@dp.message(Form.category, F.text.in_(["Плёнка", "Набор", "Клиент ухаживает сам"]))
async def process_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    
    if message.text == "Клиент ухаживает сам":
        data = await state.get_data()
        user = message.from_user.full_name  # Используем Имя вместо логина
        
        success1 = await update_sheet(user, COLUMNS[data['type']], data['amount'])
        success2 = await update_sheet(user, COLUMNS["Плёнка"], "0")
        
        if success1 and success2:
            await message.answer(
                f"✅ Данные обновлены!\n"
                f"Тип: {data['type']} {data['amount']}\n"
                f"Категория: Клиент ухаживает сам",
                reply_markup=restart_kb
            )
        else:
            await message.answer("❌ Ошибка при сохранении данных!", reply_markup=restart_kb)
        
        await state.clear()
    else:
        await state.set_state(Form.category_amount)
        if message.text == "Плёнка":
            await message.answer("Выберите сумму для плёнки:", reply_markup=film_kb)
        else:
            await message.answer("Выберите сумму для набора:", reply_markup=kit_kb)

@dp.message(Form.category)
async def incorrect_category(message: types.Message):
    await message.answer("❌ Выберите категорию из кнопок!")

@dp.message(Form.category_amount, F.text.in_(["500", "1000", "1500"]))
@dp.message(Form.category_amount, F.text.in_(["500", "1000"]))
async def process_final(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        user = message.from_user.full_name  # Используем Имя вместо логина
        
        success1 = await update_sheet(user, COLUMNS[data['type']], data['amount'])
        success2 = await update_sheet(user, COLUMNS[data['category']], message.text)
        
        if success1 and success2:
            await message.answer(
                f"✅ Данные обновлены!\n"
                f"Тип: {data['type']} {data['amount']}\n"
                f"Категория: {data['category']} {message.text}",
                reply_markup=restart_kb
            )
        else:
            await message.answer("❌ Ошибка при сохранении данных!", reply_markup=restart_kb)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Произошла ошибка", reply_markup=restart_kb)
    finally:
        await state.clear()

@dp.message(F.text == "Новая запись")
async def restart_process(message: types.Message, state: FSMContext):
    await state.clear()
    await start(message, state)

@dp.message(Form.category_amount)
async def incorrect_category_amount(message: types.Message):
    await message.answer("❌ Выберите сумму из кнопок!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
