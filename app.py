import os
import logging
import traceback
import html
import json

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from agent import Agent

def get_logger(module_name: str):
    log = logging.getLogger(module_name)
    s_handler = logging.StreamHandler()
    s_handler.setLevel(logging.DEBUG)
    s_handler.setFormatter(logging.Formatter(f'[{module_name}] %(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    log.addHandler(s_handler)
    f_handler = logging.FileHandler(f'bbdc_telebot_{module_name}.log')
    f_handler.setLevel(logging.DEBUG)
    f_handler.setFormatter(logging.Formatter(f'[{module_name}] %(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    log.addHandler(f_handler)
    log.setLevel(logging.DEBUG)
    return log

agent_logger = get_logger('AGT')
agent = Agent(agent_logger)
userid = os.getenv('BBDCTELEBOTUSERID')
password = os.getenv('BBDCTELEBOTPASSWORD')
agent.authenticate(userid, password)

my_chat_id = None
all_booked_slots = []

app_logger = get_logger('APP')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    global my_chat_id
    # Log the error before we do anything else, so we can see it even if something breaks.
    app_logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    await context.bot.send_message(
        chat_id=my_chat_id, text=message, parse_mode=ParseMode.HTML
    )

async def get_available_practical_slots(context: ContextTypes.DEFAULT_TYPE) -> None:
    available_slots = agent.get_available_practical_slots()
    context.job.data['available_slots'] = available_slots
    if len(available_slots) == 0:
        return
    msg = f'Found {len(available_slots)} available practical slots:\n'
    msg += '\n'.join([f'{i+1}. {slot}' for i, slot in enumerate(available_slots)])
    await context.bot.send_message(chat_id=context.job.chat_id, text=msg)

async def handle_start_update_loop(update: Update, context: ContextTypes) -> None:
    # save chat id
    global my_chat_id
    my_chat_id = update.message.chat_id
    await update.message.reply_text('Starting update loop.')
    # remove existing jobs
    existing_jobs = context.job_queue.get_jobs_by_name('check_available_practical_slot')
    for job in existing_jobs:
        job.schedule_removal()
    # start new job
    context.job_queue.run_repeating(get_available_practical_slots, interval=2 * 60, first=1, name='check_available_practical_slot', chat_id=update.message.chat_id, data=context.user_data)

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
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()