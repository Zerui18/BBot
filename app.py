import os

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from agent import Agent

agent = Agent()
userid = os.getenv('BBDCTELEBOTUSERID')
password = os.getenv('BBDCTELEBOTPASSWORD')
agent.authenticate(userid, password)

all_booked_slots = []

async def get_available_practical_slots(context: ContextTypes.DEFAULT_TYPE) -> None:
    # await context.bot.send_message(chat_id=context.job.chat_id, text='Checking available practical slots...')
    available_slots = agent.get_available_practical_slots()
    if len(available_slots) == 0:
        # await context.bot.send_message(chat_id=context.job.chat_id, text='No available practical slots.')
        return
    context.user_data['available_slots'] = available_slots
    msg = f'Found {len(available_slots)} available practical slots:\n'
    msg += '\n'.join([f'{i+1}. {slot}' for i, slot in enumerate(available_slots)])
    await context.bot.send_message(chat_id=context.job.chat_id, text=msg)

async def handle_start_update_loop(update: Update, context: ContextTypes) -> None:
    await update.message.reply_text('Starting update loop.')
    # remove existing jobs
    existing_jobs = context.job_queue.get_jobs_by_name('check_available_practical_slot')
    for job in existing_jobs:
        job.schedule_removal()
    # start new job
    context.job_queue.run_repeating(get_available_practical_slots, interval=5 * 60, first=1, name='check_available_practical_slot', chat_id=update.message.chat_id)

async def handle_get_all_booked_slots(update: Update, context: ContextTypes) -> None:
    global all_booked_slots
    all_booked_slots = agent.get_all_booked_slots()
    if len(all_booked_slots) == 0:
        await update.message.reply_text('No booked slots.')
        return
    msg = f'Found {len(all_booked_slots)} booked slots:\n'
    msg += '\n'.join([f'{i+1}. {lesson}' for i, lesson in enumerate(all_booked_slots)])
    await update.message.reply_text(msg)

async def handle_book_practical_slot(update: Update, context: ContextTypes) -> None:
    if 'available_slots' not in context.user_data:
        await update.message.reply_text('No available slots.')
        return
    available_slots = context.user_data['available_slots']
    if len(available_slots) == 0:
        await update.message.reply_text('No available slots.')
        return
    choice = int(context.args[0])
    if choice < 1 or choice > len(available_slots):
        await update.message.reply_text('Invalid choice.')
        return
    slot = available_slots[choice - 1]
    await update.message.reply_text(f'Booking {slot}...')
    success = agent.book_practical_slot(slot)
    if not success:
        await update.message.reply_text('Failed to book slot.')
        return
    await update.message.reply_text('Successfully booked slot.')

async def handle_delete_booking(update: Update, context: ContextTypes) -> None:
    if len(all_booked_slots) == 0:
        await update.message.reply_text('No booked slots.')
        return
    choice = int(context.args[0])
    if choice < 1 or choice > len(all_booked_slots):
        await update.message.reply_text('Invalid choice.')
        return
    lesson = all_booked_slots[choice - 1]
    await update.message.reply_text(f'Cancelling {lesson}...')
    success = agent.cancel_practical_slot(lesson)
    if not success:
        await update.message.reply_text('Failed to cancel lesson.')
        return
    await update.message.reply_text('Successfully cancelled lesson.')

def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(os.getenv('BBDCTELEBOTTOKEN')).build()

    application.add_handler(CommandHandler('start', handle_start_update_loop))
    application.add_handler(CommandHandler('booked', handle_get_all_booked_slots))
    application.add_handler(CommandHandler('book', handle_book_practical_slot))
    application.add_handler(CommandHandler('delete', handle_delete_booking))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()