import os
import logging
import asyncio
import gspread
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv
import jdatetime
from datetime import datetime

# --- 1. Initial Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = 'starry-center-456009-a7-90082ba64a87.json' # Your JSON file name
HOURLY_RATE = 70000

if not BOT_TOKEN or not SPREADSHEET_ID:
    raise ValueError("BOT_TOKEN and SPREADSHEET_ID must be set in the .env file.")

# --- 2. Google Sheets Connection ---
try:
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    worksheet = gc.open_by_key(SPREADSHEET_ID).sheet1
    logging.info("Successfully connected to Google Sheets.")
except Exception as e:
    logging.error(f"Failed to connect to Google Sheets: {e}")
    exit()

# --- 3. Helper Functions ---
def get_current_jalali_datetime():
    """Returns current Jalali date, 12-hour format time, and English weekday."""
    now_gregorian = datetime.now()
    j_now = jdatetime.datetime.fromgregorian(datetime=now_gregorian)
    date_str = j_now.strftime('%Y/%m/%d')
    time_str = now_gregorian.strftime("%I:%M:%S %p")
    weekday_map = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    gregorian_weekday = now_gregorian.weekday()
    weekday_str = weekday_map[gregorian_weekday]
    return date_str, time_str, weekday_str

def get_last_day_of_jalali_month(year, month):
    """Calculates the number of days in a given Jalali month."""
    if 1 <= month <= 6:
        return 31
    elif 7 <= month <= 11:
        return 30
    elif month == 12:
        return 29 if not jdatetime.date(year, 1, 1).isleap() else 30
    return 0
    
# ---- [تغییر کلیدی] ----
# این تابع اولین ردیف خالی در ستون اول (تاریخ) را پیدا می‌کند
# این کار از نوشتن اطلاعات در زیر جدول اصلی جلوگیری می‌کند
def find_first_empty_row(sheet):
    """Finds the first empty row in column A, starting from row 2."""
    all_dates = sheet.col_values(1) # Get all values from column A
    row_number = 2 # Start checking from row 2 (to skip header)
    for date in all_dates[1:]: # Iterate through dates, skipping header
        if not date: # If the cell is empty
            return row_number
        row_number += 1
    return len(all_dates) + 1 # If no empty row is found, return the next row number


def calculate_monthly_stats(sheet, j_now, hourly_rate):
    """Calculates comprehensive monthly stats from the sheet."""
    all_records = sheet.get_all_values()
    total_minutes = 0
    worked_days = set()
    current_jmonth = j_now.month
    current_jyear = j_now.year
    current_jday = j_now.day

    # This function reads the duration from the sheet (column E, index 4)
    # So it will work correctly with sheet-calculated durations
    for record in all_records[1:]:
        if len(record) >= 5 and record[0] and record[4]:
            try:
                date_parts = record[0].split('/')
                record_year, record_month, record_day = map(int, date_parts)
                if record_year == current_jyear and record_month == current_jmonth:
                    worked_days.add(record_day)
                    time_parts = record[4].split(':')
                    if len(time_parts) >= 2:
                        total_minutes += int(time_parts[0]) * 60 + int(time_parts[1])
            except (ValueError, IndexError):
                continue

    total_hours = total_minutes / 60.0
    total_hours_display = f"{int(total_hours):02d}:{int(total_minutes % 60):02d}"
    current_salary = total_hours * hourly_rate

    business_days_so_far = 0
    for day in range(1, current_jday + 1):
        if jdatetime.date(current_jyear, current_jmonth, day).weekday() != 6:
            business_days_so_far += 1
            
    expected_salary = (business_days_so_far * 8) * hourly_rate

    projected_salary = 0
    if len(worked_days) > 0:
        avg_hours_per_day = total_hours / len(worked_days)
        last_day_of_month = get_last_day_of_jalali_month(current_jyear, current_jmonth)
        
        total_business_days_in_month = 0
        for day in range(1, last_day_of_month + 1):
            if jdatetime.date(current_jyear, current_jmonth, day).weekday() != 6:
                total_business_days_in_month += 1
                
        remaining_business_days = total_business_days_in_month - business_days_so_far
        projected_total_hours = total_hours + (avg_hours_per_day * remaining_business_days)
        projected_salary = projected_total_hours * hourly_rate

    return {
        "total_hours": total_hours_display,
        "current_salary": int(current_salary),
        "expected_salary": int(expected_salary),
        "projected_salary": int(projected_salary)
    }

# --- 4. FSM and Keyboard Setup ---
class ActivityState(StatesGroup):
    waiting_for_activity = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⏰ Check In"), KeyboardButton(text="🏁 Check Out")]],
    resize_keyboard=True
)

# --- 5. Handlers (aiogram 3.x) ---
router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Hello! Use the buttons below to record your work hours.",
        reply_markup=main_keyboard
    )

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await message.answer("Calculating monthly stats... please wait.")
    try:
        jnow = jdatetime.datetime.now()
        month_name = jnow.strftime("%B")
        stats = calculate_monthly_stats(worksheet, jnow, HOURLY_RATE)
        
        stats_message = (
            f"📊 Stats for {month_name}\n\n"
            f"🕒 Total Work Hours: {stats['total_hours']}\n"
            f"💵 Current Salary: ${stats['current_salary']:,}\n\n"
            f"📈 Expected Salary (8hr/day): ${stats['expected_salary']:,}\n"
            f"🔮 Projected Month Salary: ${stats['projected_salary']:,}"
        )
        await message.answer(stats_message, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in cmd_stats: {e}")
        await message.answer("An error occurred while fetching stats.")

@router.message(F.text == "⏰ Check In")
async def handle_check_in(message: types.Message):
    # ---- [تغییر کلیدی] ----
    # به جای append_row، از تابع جدید برای پیدا کردن ردیف خالی استفاده می‌کنیم
    try:
        row_to_update = find_first_empty_row(worksheet)
        date_str, time_str, weekday_str = get_current_jalali_datetime()
        
        # اطلاعات در ردیف مشخص شده ثبت می‌شوند
        new_row_data = [date_str, weekday_str, time_str]
        worksheet.update(f'A{row_to_update}:C{row_to_update}', [new_row_data])
        
        await message.answer(f"✅ Check-in recorded at {time_str}.")
    except Exception as e:
        logging.error(f"Error in handle_check_in: {e}")
        await message.answer("Failed to record check-in. Please check the connection with Google Sheets.")


@router.message(F.text == "🏁 Check Out")
async def handle_check_out(message: types.Message, state: FSMContext):
    all_records = worksheet.get_all_values()
    row_to_update_index = -1
    
    # Find the last row with a check-in but no check-out
    for i in range(len(all_records) - 1, 0, -1):
        row = all_records[i]
        # Check if row has a check-in (column C) but is missing a check-out (column D)

    if len(row) > 2 and row[2] and (len(row) < 4 or not row[3]):
            row_to_update_index = i
            break
            
    if row_to_update_index == -1:
        await message.answer("⚠️ You need to check in first!")
        return
        
    row_number = row_to_update_index + 1
    _, time_str, _ = get_current_jalali_datetime()

    # ---- [تغییر کلیدی] ----
    # فقط سلول ساعت خروج (ستون چهارم) آپدیت می‌شود
    worksheet.update_cell(row_number, 4, time_str)
    
    # محاسبه مدت زمان حذف شده است، چون شیت خودش این کار را انجام می‌دهد

    await state.update_data(row_number=row_number)
    await state.set_state(ActivityState.waiting_for_activity)
    await message.answer(f"✅ Check-out recorded at {time_str}.\n\nPlease enter your activity for this session (or type skip).")


@router.message(ActivityState.waiting_for_activity)
async def process_activity(message: types.Message, state: FSMContext):
    data = await state.get_data()
    row_number = data.get("row_number")
    
    # ---- [تغییر کلیدی] ----
    # منطق این بخش برای خوانایی بهتر شده است
    activity = message.text
    if activity and activity.lower().strip() != 'skip':
        worksheet.update_cell(row_number, 6, activity) # Update activity in column F
        await message.answer("✅ Activity recorded.", reply_markup=main_keyboard)
    else:
        await message.answer("👍 Activity skipped.", reply_markup=main_keyboard)

    await state.clear()
    # Show updated stats automatically after finishing a session
    await cmd_stats(message)

# --- 6. Main Execution ---
async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "main":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by admin.")
