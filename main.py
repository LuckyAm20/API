import sqlite3
import telebot
from telebot import types
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_API_TOKEN"))

values = None


# Функция для создания базы данных пользователя
def create_user_reminders_table(user_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f'''CREATE TABLE IF NOT EXISTS user_{user_id}
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  description TEXT,
                  date TEXT,
                  attachment_folder TEXT,
                  done INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()


def add_to_database(user_id, description, date, attachment_folder):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"INSERT INTO user_{user_id} (description, date, attachment_folder) VALUES (?, ?, ?)",
              (description, date, attachment_folder))
    conn.commit()
    conn.close()


def get_user_reminders(user_id, done=False):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"SELECT * FROM user_{user_id} WHERE done = ?", (1 if done else 0,))
    reminders = c.fetchall()
    conn.close()
    return reminders


def update_attachment_folder(user_id, attachment_folder):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"UPDATE user_{user_id} SET attachment_folder = ? WHERE id = (SELECT MAX(id) FROM user_{user_id})",
              (attachment_folder,))
    conn.commit()
    conn.close()


def send_main_menu(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    current_button = types.KeyboardButton('Посмотреть список текущих дел')
    completed_button = types.KeyboardButton('Посмотреть список выполненных дел')
    keyboard.add(current_button, completed_button)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text == 'Посмотреть список текущих дел')
def show_current_reminders(message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id, done=False)
    if reminders:
        for reminder in reminders:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("Изменить описание", callback_data=f"edit_description_{reminder[0]}"),
                types.InlineKeyboardButton("Изменить дату", callback_data=f"edit_date_{reminder[0]}"),
            )
            keyboard.row(
                types.InlineKeyboardButton("Редактировать файлы", callback_data=f"edit_files_{reminder[0]}"),
                types.InlineKeyboardButton("Удалить", callback_data=f"delete_{reminder[0]}"),
                types.InlineKeyboardButton("Выполнено", callback_data=f"complete_{reminder[0]}")
            )
            bot.send_message(message.chat.id, f"Описание: {reminder[1]}, Дата: {reminder[2]}", reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "У вас пока нет текущих дел.")


@bot.callback_query_handler(lambda query: query.data.startswith("complete_"))
def handle_complete_query(query):
    user_id = query.from_user.id
    reminder_id = int(query.data.split("_")[1])
    mark_as_done(user_id, reminder_id)
    bot.send_message(query.message.chat.id, "Напоминание помечено как выполненное.")


def mark_as_done(user_id, reminder_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"UPDATE user_{user_id} SET done = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


@bot.callback_query_handler(lambda query: query.data.startswith("delete_"))
def handle_delete_query(query):
    user_id = query.from_user.id
    reminder_id = int(query.data.split("_")[1])
    delete_reminder(user_id, reminder_id)
    bot.send_message(query.message.chat.id, "Напоминание удалено.")


def delete_reminder(user_id, reminder_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"DELETE FROM user_{user_id} WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


@bot.callback_query_handler(lambda query: query.data.startswith("edit_description_"))
def handle_edit_description_query(query):
    user_id = query.from_user.id
    reminder_id = int(query.data.split("_")[2])
    msg = bot.send_message(query.message.chat.id, "Введите новое описание:")
    bot.register_next_step_handler(msg, lambda m: process_edit_description(m, user_id, reminder_id))


def process_edit_description(message, user_id, reminder_id):
    new_description = message.text
    update_description(user_id, reminder_id, new_description)
    bot.send_message(message.chat.id, "Описание успешно обновлено.")


def update_description(user_id, reminder_id, new_description):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute(f"UPDATE user_{user_id} SET description = ? WHERE id = ?", (new_description, reminder_id))
    conn.commit()
    conn.close()


@bot.message_handler(func=lambda message: message.text == 'Посмотреть список выполненных дел')
def show_completed_reminders(message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id, done=True)
    if reminders:
        response = "Выполненные дела:\n"
        for reminder in reminders:
            response += f"- {reminder[1]} ({reminder[2]})\n"
    else:
        response = "У вас пока нет выполненных дел."
    bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    create_user_reminders_table(user.id)
    welcome_message = (
        f"Привет, {user.first_name}!\n"
        "Я бот напоминалка. Я могу помочь тебе организовать твои дела и напомнить о них в нужное время.\n"
        "Для добавления нового напоминания используй команду /add.\n"
        "Приятного использования!"
    )
    bot.send_message(message.chat.id, welcome_message)
    send_main_menu(message)


@bot.callback_query_handler(func=DetailedTelegramCalendar.func())
def cal(c):
    global values
    if c.message.text.startswith('Выберите дату для напоминания '):
        values = c.message.text[30:-1]
    result, key, step = DetailedTelegramCalendar().process(c.data)
    if not result and key:
        bot.edit_message_text(f"Выберите {LSTEP[step]}",
                              c.message.chat.id,
                              c.message.message_id,
                              reply_markup=key)
    elif result:
        bot.edit_message_text(f"Вы выбрали {result}",
                              c.message.chat.id,
                              c.message.message_id)
        msg = bot.send_message(c.message.chat.id, f"Теперь выберите время:")
        bot.register_next_step_handler(msg, set_time, result, values)


def validate_time_format(time_str):
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False


def set_time(message, chosen_date, text):
    try:
        chat_id = message.chat.id
        time_chosen = message.text
        if not validate_time_format(time_chosen):
            msg = bot.send_message(chat_id, "Неверный формат времени. Пожалуйста, введите время в формате HH:MM.")
            bot.register_next_step_handler(msg, set_time, chosen_date, text)
            return

        reminder_time = f"{chosen_date} {time_chosen}"
        msg = bot.send_message(chat_id, f"Вы выбрали время {time_chosen}. Напоминание будет установлено на {reminder_time}")
        set_date(msg, text, reminder_time)
    except Exception:
        bot.send_message(message.chat.id, 'Ошибка выбора времени. Попробуйте еще раз.')


@bot.message_handler(commands=['add'])
def add_reminder(message):
    msg = bot.send_message(message.chat.id, "Введите описание напоминания:")
    bot.register_next_step_handler(msg, set_description)


def set_description(message):
    description = message.text
    chat_id = message.chat.id
    calendar, step = DetailedTelegramCalendar().build()

    bot.send_message(chat_id, f"Выберите дату для напоминания {description}:", reply_markup=calendar)


def set_date(message, description, result):
    try:
        chat_id = message.chat.id
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton("Да", callback_data="attach_yes"),
                   telebot.types.InlineKeyboardButton("Нет", callback_data="attach_no"))
        bot.send_message(chat_id, f"Напоминание '{description}' успешно добавлено на {result}."
                                  "Хотите прикрепить вложения?", reply_markup=markup)
        add_to_database(message.chat.id, description, result, None)
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, 'Ошибка выбора даты. Попробуйте еще раз.')


@bot.callback_query_handler(func=lambda call: call.data.startswith('attach'))
def handle_attachment(call):
    chat_id = call.message.chat.id
    if call.data == 'attach_yes':
        bot.send_message(chat_id, "Отправьте мне нужные вложения.")

        attachment_folder = "path/to/attachment/folder"
        update_attachment_folder(chat_id, attachment_folder)
    elif call.data == 'attach_no':
        bot.send_message(chat_id, "Напоминание успешно создано!")
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=None)


@bot.message_handler(commands=['current'])
def show_current_reminders(message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id, done=False)
    if reminders:
        response = "Текущие дела:\n"
        for reminder in reminders:
            response += f"- {reminder[1]} ({reminder[2]})\n"
    else:
        response = "У вас пока нет текущих дел."
    bot.send_message(message.chat.id, response)


@bot.message_handler(commands=['completed'])
def show_completed_reminders(message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id, done=True)
    if reminders:
        response = "Выполненные дела:\n"
        for reminder in reminders:
            response += f"- {reminder[1]} ({reminder[2]})\n"
    else:
        response = "У вас пока нет выполненных дел."
    bot.send_message(message.chat.id, response)


def main():
    bot.polling()


if __name__ == '__main__':
    main()





