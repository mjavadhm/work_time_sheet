import os
import logging
from datetime import datetime
from pytz import timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import jdatetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Setup bot token and sheet info
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Setup Iran timezone
iran_tz = timezone("Asia/Tehran")

# Initialize bot and dispatcher with MemoryStorage for FSM
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage, bot=bot)

# Google Sheets setup
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name(
    'starry-center-456009-a7-90082ba64a87.json', scope)
gc = gspread.authorize(credentials)

def get_sheet():
    sheet = gc.open_by_key(SPREADSHEET_ID)
    return sheet.sheet1

def get_persian_weekday(date):
    weekday_map = {
        0: "دوشنبه",
        1: "سه‌شنبه",
        2: "چهارشنبه",
        3: "پنج‌شنبه",
        4: "جمعه",
        5: "شنبه",
        6: "یکشنبه"
    }
    return weekday_map[date.weekday()]

def format_time(time_obj):
    return time_obj.strftime("%I:%M:%S %p")

def calculate_monthly_stats(sheet, current_month, hourly_rate=55000):
    all_records = sheet.get_all_values()
    total_minutes = 0
    worked_days = set()  # Track unique days worked
    
    # Parse records
    for record in all_records[1:]:  # Skip header row
        if len(record) >= 5 and record[4] and record[0] and '/' in record[0]:  # Has total hours and valid date
            try:
                date_parts = record[0].split('/')
                if len(date_parts) >= 3:
                    # Convert the month part to integer
                    record_year = int(date_parts[0])
                    record_month = int(date_parts[1])
                    record_day = int(date_parts[2])
                    
                    if record_month == current_month:
                        
                        # Add this day to worked days set
                        worked_days.add(record_day)
                        
                        if ':' in record[4]:
                            time_parts = record[4].split(':')
                            if len(time_parts) >= 2:
                                hours = int(time_parts[0])
                                minutes = int(time_parts[1])
                                
                                total_minutes += hours * 60 + minutes
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing record {record}: {e}")
    
    # Calculate total hours worked
    total_hours = total_minutes / 60  # Use floating point for accurate salary calculation
    total_hours_display = f"{int(total_hours):02d}:{int(total_minutes % 60):02d}"
    
    # Calculate current salary
    current_salary = total_hours * hourly_rate
    
    # Calculate expected salary based on 8 hours per workday
    now = jdatetime.datetime.now()
    # first_day_of_month = jdatetime.datetime(now.year, current_month, 1)
    
    # Get the current day of the month or use the last day if we're calculating for a past month
    current_day = now.day 
    
    
    # Count business days (excluding Fridays) until today
    business_days = 0
    for day in range(1, current_day + 1):
        date = jdatetime.date(now.year, current_month, day)
        # Convert to Gregorian to use weekday()
        g_date = date.togregorian()
        # In Iran, Friday is the weekend (weekday 4)
        if g_date.weekday() != 4:  # 4 is Friday
            business_days += 1
    
    
    # Calculate projected salary based on daily average
    days_worked = len(worked_days)
    
    # Avoid division by zero
    if days_worked > 0:
        avg_hours_per_day = total_hours / days_worked
    else:
        avg_hours_per_day = 0
    
    # Calculate total business days in the month (excluding Fridays)
    
    month_length = get_last_day_of_month(now.year, current_month)
    total_business_days = 0
    for day in range(1, month_length + 1):
        date = jdatetime.date(now.year, current_month, day)
        g_date = date.togregorian()
        if g_date.weekday() != 4:  
            total_business_days += 1
    
    
    remainig_days = total_business_days - current_day
    projected_hours = avg_hours_per_day * remainig_days
    projected_salary = (projected_hours * hourly_rate) + current_salary
    expected_hours = remainig_days * 8
    expected_salary = (expected_hours * hourly_rate) + current_salary
    
    return {
        "total_hours": total_hours_display,
        "current_salary": current_salary,
        "expected_salary": expected_salary,
        "projected_salary": projected_salary
    }
    
    
    
def get_last_day_of_month(year, month):
    # If it's the last month of the year
    if month == 12:
        # Esfand has 29 days in normal years, 30 in leap years
        if jdatetime.date(year, 12, 29).togregorian().year % 4 == 0:
            return 30
        else:
            return 29
    
    # For months 1-6, there are 31 days
    elif 1 <= month <= 6:
        return 31
    
    # For months 7-11, there are 30 days
    elif 7 <= month <= 11:
        return 30
    
    # Handle invalid input
    else:
        raise ValueError("Month must be between 1 and 12")
    
    
def get_days_in_month(year, month):
    # Get the first day of the next month
    if month == 12:
        next_month = jdatetime.date(year + 1, 1, 1)
    else:
        next_month = jdatetime.date(year, month + 1, 1)
    
    # Subtract one day to get the last day of the current month
    last_day = next_month - jdatetime.timedelta(days=1)
    return last_day.day


def calculate_monthly_hours(sheet, current_month):
    all_records = sheet.get_all_values()
    total_minutes = 0
    
    for record in all_records[1:]:  # Skip header row
        if len(record) >= 5 and record[4] and record[0] and '/' in record[0]:  # Has total hours and valid date
            try:
                date_parts = record[0].split('/')
                if len(date_parts) >= 2:
                    # Convert the month part to integer
                    record_month = int(date_parts[1])
                    if record_month == current_month:
                        if ':' in record[4]:
                            time_parts = record[4].split(':')
                            if len(time_parts) >= 2:
                                hours = int(time_parts[0])
                                minutes = int(time_parts[1])
                                total_minutes += hours * 60 + minutes
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing record {record}: {e}")
    
    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60
    return f"{total_hours:02d}:{remaining_minutes:02d}"

def get_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏰ Check In")],
            [KeyboardButton(text="🏁 Check Out")]
        ],
        resize_keyboard=True
    )
    return keyboard

class ActivityState(StatesGroup):
    waiting_for_activity = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Hello! Use the buttons below to record your work hours:",
        reply_markup=get_keyboard()
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Command to get current month statistics"""
    try:
        sheet = get_sheet()
        now = datetime.now(iran_tz)
        jnow = jdatetime.datetime.fromgregorian(datetime=now)
        
        monthly_stats = calculate_monthly_stats(sheet, jnow.month)
        
        stats_message = (
            f"📊 Monthly Statistics ({jnow.year}/{jnow.month:02d}):\n\n"
            f"Total Hours: {monthly_stats['total_hours']}\n"
            f"Current Salary: {int(monthly_stats['current_salary']):,}\n"
            f"Expected Salary (8hr/day): {int(monthly_stats['expected_salary']):,}\n"
            f"Projected Month Salary: {int(monthly_stats['projected_salary']):,}"
        )
        await message.answer(stats_message)
    except Exception as e:
        logger.error("Error getting monthly stats: %s", e)
        await message.answer("Error getting statistics. Please try again later.")
        
@dp.message(ActivityState.waiting_for_activity)
async def process_activity(message: types.Message, state: FSMContext):
    logger.info("Entering process_activity")
    try:
        data = await state.get_data()
        logger.info("FSM data: %s", data)
        row_number = data.get("row_number")
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        total_hours = data.get("total_hours")
        
        activity = message.text
        sheet = get_sheet()
        sheet.update_cell(row_number, 6, activity)
        
        # Get current month's total hours
        now = datetime.now(iran_tz)
        monthly_total = calculate_monthly_hours(sheet, now.month)
        
        # Send summary message
        summary = (
            f"✅ Session Summary:\n"
            f"Start Time: {start_time}\n"
            f"End Time: {end_time}\n"
            f"Session Duration: {total_hours}\n"
            f"Total Hours This Month: {monthly_total}"
        )
        # calculate_monthly_stats(sheet,)
        await message.answer(summary)
        
        logger.info("Activity '%s' recorded in row %s", activity, row_number)
        await state.clear()
    except Exception as e:
        logger.error("Error processing activity: %s", e)

@dp.message()
async def handle_time_logging(message: types.Message, state: FSMContext):
    now = datetime.now(iran_tz)
    jdate = jdatetime.datetime.fromgregorian(datetime=now)
    persian_date = f"{jdate.year}/{str(jdate.month).zfill(2)}/{str(jdate.day).zfill(2)}"
    current_time = format_time(now)
    sheet = get_sheet()
    
    if message.text == "⏰ Check In":
        weekday = get_persian_weekday(now)
        sheet.append_row([
            persian_date,   # تاریخ
            weekday,        # روز هفته
            current_time,   # زمان ورود
            "",            # زمان خروج
            "",            # کل ساعات کاری
            ""            # فعالیت
        ])
        await message.answer(f"Check-in time recorded: {current_time}")
        logger.info("Check-in recorded: %s", current_time)
        
    elif message.text == "🏁 Check Out":
        all_records = sheet.get_all_values()
        for i in range(len(all_records)-1, -1, -1):
            if all_records[i][3] == "":  # Find last row without check-out time
                row_number = i + 1
                sheet.update_cell(row_number, 4, current_time)
                
                # Calculate total work hours
                try:
                    time_in = datetime.strptime(all_records[i][2], "%I:%M:%S %p")
                    time_out = datetime.strptime(current_time, "%I:%M:%S %p")
                    if time_out < time_in:  # If passed midnight
                        time_out = time_out.replace(day=time_out.day + 1)
                    total_hours = time_out - time_in
                    total_hours_str = f"{total_hours.seconds // 3600}:{(total_hours.seconds // 60) % 60:02d}:00"
                    sheet.update_cell(row_number, 5, total_hours_str)
                    
                    # Store times for summary
                    await state.update_data(
                        row_number=row_number,
                        start_time=all_records[i][2],
                        end_time=current_time,
                        total_hours=total_hours_str
                    )
                except Exception as e:
                    logger.error("Error calculating total hours: %s", e)
                
                await message.answer(f"Check-out time recorded: {current_time}\nPlease enter your activity:")
                await state.set_state(ActivityState.waiting_for_activity)
                logger.info("FSM state changed to waiting for activity. row_number=%s", row_number)
                break
        else:
            await message.answer("You need to check in first!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
