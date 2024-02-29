#!/usr/bin/env python
"""Telegram bot for HFpager"""
import argparse
import configparser
import json
import logging
import os
from pprint import pformat
import random
import re
import subprocess
from sys import exit as sysexit
from time import sleep, time
from datetime import datetime
from textwrap import shorten
from threading import Thread

import telebot
from telebot.util import smart_split

from utils import get_weather, get_speed

parser = argparse.ArgumentParser(
    description="Telegram bot for HFpager/gate (see dxsoft.com)."
)
parser.add_argument(
    "-c", "--conf", dest="configfile", type=str, required=True, default=None
)
args = parser.parse_args()

try:
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    config.read(args.configfile)

    MY_ID = config.getint("hfpager", "my_id")
    ABONENT_ID = config.getint("hfpager", "abonent_id", fallback=999)
    CALLSIGN = config.get("hfpager", "callsign")
    MSG_END = config.get("hfpager", "msg_end", fallback="")
    MSG_END = " " + MSG_END if MSG_END != "" else ""
    GEO_DELTA = config.getfloat("hfpager", "geo_delta", fallback=0.0)

    TOKEN = config.get("telegram", "token")
    CHAT_ID = config.getint("telegram", "chat_id")
    BEACON_CHAT_ID = config.getint("telegram", "beacon_chat_id", fallback=CHAT_ID)
    OWNER_CHAT_ID = config.getint("telegram", "owner_chat_id", fallback=CHAT_ID)

    OS_TYPE = config.get("system", "os_type")
    RUN_PAGER = config.getboolean("system", "run_pager", fallback=False)
    HFPGATE = config.getboolean("system", "hfpgate", fallback=False)
    HFPAGER_PATH = config.get("system", "hfpager_path")
    LOG_LEVEL = config.get("system", "log_level", fallback="WARNING")
    OWM_API_KEY = config.get("system", "owm_api_key", fallback="NO_OWM_API_TOKEN")
except configparser.Error as e:
    print(f"ERROR: {e} in configfile {args.configfile} or file not exist.")
    sysexit(1)

logging.basicConfig(
    filename="bot.log",
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


message_dict = {}
bot_recieve_dict = {}
mailbox = {}


def bot_polling():
    """Function start bot polling."""
    logging.info("Bot polling is running")
    while True:
        try:
            logging.debug("Bot polling")
            bot.polling(interval=5)
        except Exception as ex:
            logging.error("Bot polling error: %s", ex)
            logging.debug("Error: %s", ex, exc_info=True)


def hfpager_restart():
    """Function periodicaly restart HFpager.app on Android."""
    logging.info("HFpager restart thread started")
    start_hfpager()
    while True:
        try:
            subprocess.run(
                "am start --user 0 "
                "-n ru.radial.nogg.hfpager/"
                "ru.radial.full.hfpager.MainActivity "
                '-a "android.intent.action.SEND" '
                '--es "android.intent.extra.TEXT" "notext" '
                '-t "text/plain" '
                '--ei "android.intent.extra.INDEX" "99999"',
                stdout=subprocess.PIPE,
                shell=True,
                check=False,
                timeout=10,
            )

            # sleep(300)
        except subprocess.SubprocessError as ex:
            logging.error("HFpager restart thread: %s", ex)
            logging.debug("Error: %s", ex, exc_info=True)
        finally:
            sleep(300)


def hfpager_bot():
    """Function for checking new msg files on the file system.

    This function walks through the directory specified by the OS-specific
    pager_dir variable, looking for new msg files that have been added since
    the last iteration. When new files are found, they are opened, read, and
    parsed by the parse_file function.

    The function runs indefinitely, with a 2-second sleep interval between
    iterations, unless an exception is raised.
    """
    if OS_TYPE == "ANDROID":
        pager_dir = (
            "/data/data/com.termux/files/home/storage/shared/" "Documents/HFpager/"
        )
    elif OS_TYPE == "LINUX":
        pager_dir = HFPAGER_PATH + "data/MESSAGES.DIR/"
    else:
        pager_dir = "./"

    while True:
        try:
            logging.info("HFpager message parsing is running")

            # Initialize list of starting files
            start_file_list = []
            for root, _, files in os.walk(pager_dir):
                for file in files:
                    start_file_list.append(os.path.join(root, file))

            while True:
                # Initialize list of current files
                current_file_list = []
                for root, _, files in os.walk(pager_dir):
                    for file in files:
                        current_file_list.append(os.path.join(root, file))

                # Calculate the difference between current and starting files
                delta = list(set(current_file_list) - set(start_file_list))
                logging.debug("New files: %s", delta)

                # Parse new files
                for file in delta:
                    mesg = open(file, "r", encoding="cp1251")
                    text = mesg.read()
                    parse_file(file.replace(pager_dir, ""), text)

                # Update starting files
                start_file_list = current_file_list.copy()
                sleep(2)
        except Exception as ex:
            logging.error("HFpager file parsing error: %s", ex)
            logging.debug("Error: %s", ex, exc_info=True)
        finally:
            sleep(2)


def start_hfpager():
    """Function start HFpager app."""
    if OS_TYPE == "ANDROID":
        subprocess.run(
            "am start --user 0 "
            "-n ru.radial.nogg.hfpager/"
            "ru.radial.full.hfpager.MainActivity ",
            stdout=subprocess.PIPE,
            shell=True,
            check=False,
            timeout=10,
        )
        logging.info("HFpager started")
    elif OS_TYPE == "LINUX" and RUN_PAGER is True:
        subprocess.run(
            f"cd {HFPAGER_PATH}/bin/; ./start.sh; exit",
            shell=True,
            check=False,
            timeout=10,
        )
        logging.info("HFpager started")


def send_edit_msg(key, message):
    """Function: send_edit_msg(key, message)
    -------------------------------------
    This function is used to send or update a message to a Telegram (TG) chat.
    It determines whether to send a new message or edit an existing one based
    on the content of the message and the current state of the bot_recieve_dict
    and message_dict dictionaries.

    Parameters:
    key (str): A unique identifier for the message.
    message (str): The text of the message to be sent or updated.

    Returns:
    None

    The function performs the following steps:
    1. Extracts the text from the message by splitting it on newline characters
    and selecting the last item.
    2. Checks if the text exists in the bot_recieve_dict.
    If it does, the function edits the existing message using the message_id
    associated with the text in bot_recieve_dict.
    3. If the text is not in bot_recieve_dict but is in message_dict,
    the function edits the existing message using the message_id associated
    with the text in message_dict.
    4. If the text is not in either dictionary, the function sends a new message
    using the message_id returned by the Telegram bot and stores it in
    message_dict."""
    # Split the message by newline character and keep the last part
    text = message.split("\n", maxsplit=1)[-1].strip()

    # Check if the text exists in the bot's received dictionary
    if text in bot_recieve_dict:
        # Edit the message with the given text and update the message_dict
        result = bot.edit_message_text(
            chat_id=CHAT_ID,
            text=message,
            message_id=bot_recieve_dict[text]["message_id"],
        )
        message_dict[key] = {"message_id": bot_recieve_dict[text]["message_id"]}
        # Remove the text from the bot's received dictionary
        del bot_recieve_dict[text]

    # Check if the key exists in the message_dict
    elif key in message_dict:
        # Edit the message with the given text and message_id
        bot.edit_message_text(
            chat_id=CHAT_ID, text=message, message_id=message_dict[key]["message_id"]
        )

    # If the text is not in the bot's received dictionary and the key is not in the message_dict
    else:
        # Send the message with the given text and store the message_id in the message_dict
        result = bot.send_message(chat_id=CHAT_ID, text=message)
        message_dict[key] = {"message_id": result.message_id}


def parse_file(dir_filename, text):
    """
    Function parse_file: This function parses a file based on the provided directory and filename.
    It extracts metadata from the filename and logs some information.

    Parameters:
    dir_filename (str): The full path of the file to be parsed.
    text (str): The content of the file to be parsed.

    The function performs the following steps:
    1. Split the dir_filename into dirname and filename.
    2. Log the dir_filename for debugging purposes.
    3. Define a regular expression pattern to match the filename structure.
    4. Search for a match in the dir_filename using the pattern.
    5. If a match is found, extract the metadata into a dictionary and log it for debugging purposes.
    6. Extract the current date and time from dirname and filename.
    7. Shorten the text if necessary.
    8. Perform various actions based on the filename pattern and send/log messages accordingly.
    """
    # Split dir_filename into dirname and filename
    dirname, filename = dir_filename.split("/")

    # Log the dir_filename for debugging purposes
    logging.debug(dir_filename)

    # Define a regular expression pattern to match the filename structure
    pattern = (
        r"(?P<DT_DATE>[\d-]{10})\.(?P<MSG_TYPE>[\D]{3})/"
        r"(?P<DT_TIME>[\d]{6})-(?P<F1>[\D])(?P<F2>[\D])-"
        r"(?P<F3>[\d]{0,1})(?P<F4>[\d])-(?P<MSG_NUM>[\d]{3})-"
        r"(?P<MSG_LEN>[0-9A-F]{2})-"
        r"(?P<HEAD_CRC>[0-9A-F]{4})-(?P<MSG_CRC>[0-9A-F]{4})-"
        r"(?P<ID_FROM>[\d]{1,5}|~)_(?P<ID_TO>[\d]{1,5}|~)\.TXT"
    )

    # Search for a match in the dir_filename using the pattern
    match_object = re.search(pattern, dir_filename)

    # If a match is found, extract the metadata into a dictionary and log it for debugging purposes
    if match_object:
        msg_meta = match_object.groupdict()
        logging.debug(pformat(msg_meta))

    # Extract the current date and time from dirname and filename
    cur_date = dirname.split(".")[0]
    cur_time = filename.split("-")[0]

    # Create a key for logging
    key = f"{cur_date} {cur_time}"

    # Shorten the text if necessary
    short_text = shorten(text, width=35, placeholder="...")

    # Perform various actions based on the filename pattern and send/log messages accordingly
    if re.match(r"\d{6}-RO-0.+_" + str(MY_ID) + ".TXT", filename):
        logging.info("HFpager private message received: %s", text)
        bot.send_message(chat_id=CHAT_ID, text=text)
        detect_request(text)
    elif re.match(r"\d{6}-RO-[2,3].+_" + str(MY_ID) + ".TXT", filename):
        logging.info(
            "HFpager private message received and acknowledgment " "sent: %s",
            short_text,
        )
        bot.send_message(chat_id=CHAT_ID, text=f"√ {text}")
        detect_request(text)
    elif re.match(r"\d{6}-RE.+~_~.TXT", filename):
        logging.info("HFpager message intercepted: %s", text)
        bot.send_message(chat_id=BEACON_CHAT_ID, text=text, disable_notification=True)
        detect_request(text)
    elif re.match(r"\d{6}-R", filename):
        logging.info("HFpager message intercepted: %s", text)
        bot.send_message(chat_id=CHAT_ID, text=text, disable_notification=True)
        detect_request(text)
    elif re.match(r"\d{6}-S[1-9]-\dP", filename):
        logging.info(
            "HFpager message sent and acknowledgment " "received: %s", short_text
        )
        send_edit_msg(key, f"√ {text}")
    elif re.match(r"\d{6}-S[1-9]-\dN", filename):
        logging.info(
            "HFpager message sent and not " "acknowledgment received: %s", short_text
        )
        send_edit_msg(key, f"X {text}")
    elif re.match(r"\d{6}-S[1-9]-\d0", filename):
        logging.info("HFpager message sent: %s", short_text)
        send_edit_msg(key, f"{text}")
    elif re.match(r"\d{6}-B", filename):
        logging.info("HFpager beacon intercepted: %s", text)
        bot.send_message(chat_id=BEACON_CHAT_ID, text=text, disable_notification=True)


def detect_request(msg_full):
    """Function detect request in radio msg."""
    msg_meta = {}
    msg_meta["FROM"], msg_meta["TO"] = 0, 0
    msg_text = msg_full.split("\n", maxsplit=1)[-1]
    # получаем метаданные сообщения
    match = re.match(
        r"(?P<FROM>\d{1,5}) \(\d{3}\) > "
        r"(?P<TO>[0-9]{1,5}), "
        r"(?P<SPEED>\d{1,2}\.{0,1}\d{0,1}) Bd,ER="
        r"(?P<ERR>\d{1,2}\.{0,1}\d{0,1})",
        msg_full,
    )
    if match:
        msg_meta = match.groupdict()
        logging.info(pformat(msg_meta))
        msg_meta["SPEED"] = get_speed(msg_meta["SPEED"])
        # logging.info(pformat(msg_meta))

    # парсим {lat},{lon}: map_link -> web
    match = re.search(
        r"(?P<LAT>-{0,1}\d{1,2}\.\d{1,8})," r"(?P<LON>-{0,1}\d{1,3}\.\d{1,8})", msg_text
    )
    if match:
        msg_geo = match.groupdict()
        msg_geo["LAT"] = round(float(msg_geo["LAT"]) + GEO_DELTA, 4)
        msg_geo["LON"] = round(float(msg_geo["LON"]) + GEO_DELTA, 4)
        dt_string = datetime.now().strftime("%d-%b-%Y%%20%H:%M")
        message = (
            f'https://nakarte.me/#m=13/{msg_geo["LAT"]}/{msg_geo["LON"]}'
            f'&l=Otm/Wp&nktp={msg_geo["LAT"]}/{msg_geo["LON"]}/{dt_string}'
        )
        logging.info("HFpager -> MapLink: %s", message)
        bot.send_message(chat_id=CHAT_ID, text=message)

    # парсим =x{lat},{lon}: weather -> hf
    if not HFPGATE:
        match = re.match(
            r"=[xX](?P<LAT>-{0,1}\d{1,2}\.\d{1,8})," r"(?P<LON>-{0,1}\d{1,3}\.\d{1,8})",
            msg_text,
        )
        if match:
            msg_geo = match.groupdict()
            msg_geo["LAT"] = round(float(msg_geo["LAT"]) + GEO_DELTA, 4)
            msg_geo["LON"] = round(float(msg_geo["LON"]) + GEO_DELTA, 4)
            if int(msg_meta["TO"]) == MY_ID:
                logging.info(
                    "HFpager -> Weather: %s %s", msg_geo["LAT"], msg_geo["LON"]
                )
                bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f'{MY_ID}>{msg_meta["FROM"]} '
                        f'weather in {msg_geo["LAT"]},'
                        f'{msg_geo["LON"]}'
                    ),
                )
                if OWM_API_KEY != "NO_OWM_API_TOKEN":
                    weather = (
                        get_weather(OWM_API_KEY, msg_geo["LAT"], msg_geo["LON"])
                        + MSG_END
                    )
                else:
                    weather = "Sorry, no weather :("
                split = smart_split(weather, 250)
                for part in split:
                    pager_transmit(part, msg_meta["FROM"], msg_meta["SPEED"], 0)

    # парсим =[gGtT]: last msg to id -> hf
    if not HFPGATE:
        match = re.match(r"=[gGtT]", msg_text)
        if match and msg_meta["TO"] == str(MY_ID):
            if msg_meta["FROM"] in mailbox:
                logging.info("%s request from mailbox", msg_meta["FROM"])
                pager_transmit(
                    mailbox[msg_meta["FROM"]] + MSG_END,
                    msg_meta["FROM"],
                    msg_meta["SPEED"],
                    0,
                )
            else:
                logging.info("No msg to %s in mailbox", msg_meta["FROM"])
                pager_transmit("No msg", msg_meta["FROM"], msg_meta["SPEED"], 0)

    # парсим /ping:
    match = re.match(r"^/ping", msg_text)
    if match:
        text = msg_full.split(":", maxsplit=1)[0].strip()
        sleep(random.randrange(2, 30))
        pager_transmit(
            f'ACK ERR={msg_meta["ERR"]}%{MSG_END}',
            msg_meta["FROM"],
            msg_meta["SPEED"],
            0,
        )


# Function: pager_transmit(message, abonent_id, speed, resend)
# ---------------------------------------------------------------
# This function is used to transmit a pager message via HFpager.
# The function takes four arguments: message, abonent_id, speed, and resend.
#
# Arguments:
# message (str): The message to be sent.
# abonent_id (str): The ID of the pager recipient.
# speed (int): The speed of the message.
# resend (int): The number of times the message should be resent.
#
# The function first shortens the message using the 'shorten' function
# with a width of 35 characters and a placeholder of "...".
#
# The function then logs the action using the 'logging' module,
# providing the abonent_id, the number of times the message will be resent,
# and the shortened message.
#
# Depending on the OS_TYPE, the function takes different actions:
#
# - If the OS_TYPE is 'ANDROID', the function executes a subprocess
#   that starts an Android intent. The intent sends a text message
#   containing the original message, with the recipient ID as an
#   extra, and with the specified speed and number of retries.
#
# - If the OS_TYPE is 'LINUX', the function constructs a message
#   string with the specified parameters and writes it to a file
#   in the HFPAGER_PATH/data/to_send directory. The file is renamed
#   with a '.msg' extension, indicating it is ready to be sent.
#
# The function waits for 1 second before returning, allowing time
# for the message to be processed.


def pager_transmit(message, abonent_id, speed, resend):
    """Function send HFpager msg."""
    short_text = shorten(message, width=35, placeholder="...")
    logging.info(
        "HFpager send to ID:%s repeat:%s " "message: %s", abonent_id, resend, short_text
    )
    if OS_TYPE == "ANDROID":
        subprocess.run(
            "am start --user 0 "
            "-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity "
            '-a "android.intent.action.SEND" '
            f'--es "android.intent.extra.TEXT" "{message.strip()}" '
            '-t "text/plain" '
            f'--ei "android.intent.extra.INDEX" "{abonent_id}" '
            f'--es "android.intent.extra.SUBJECT" "Flags:1,{resend}"',
            stdout=subprocess.PIPE,
            shell=True,
            check=False,
            timeout=10,
        )
    elif OS_TYPE == "LINUX":
        ackreq = 1
        msg_shablon = (
            f"to={abonent_id},speed={speed},"
            f"askreq={ackreq},resend={resend}\n"
            f"{message.strip()}"
        )
        logging.info(msg_shablon)
        with open(HFPAGER_PATH + "data/to_send/new.ms", "w", encoding="cp1251") as f:
            f.write(msg_shablon)
        os.rename(
            HFPAGER_PATH + "data/to_send/new.ms", HFPAGER_PATH + "data/to_send/new.msg"
        )
        sleep(1)


bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=["help", "start"])
def send_welcome(message):
    """Function send bot welcome msg."""
    bot.reply_to(
        message,
        f"""Привет, я HFpager Bot.
Я отправляю сообщения с шлюза {CALLSIGN} мой ID:{MY_ID}\n
Как меня использовать:\n
`>blah blah blah` - отправит _blah blah blah_ на ID:{ABONENT_ID}\n
`>123 blah blah blah` - отправит _blah blah blah_ на ID:_123_\n
`! blah blah blah` - ! в сообщении равносилен опции "Повторять до подтв."\n
`>123! blahblah` - отправка на ID:123 будет повторятся до подтверждения
""",
        parse_mode="markdown",
    )


@bot.message_handler(commands=["bat", "battery"])
def send_bat_status(message):
    """Function send battery status."""
    try:
        battery = json.loads(
            subprocess.run(
                ["termux-battery-status"],
                stdout=subprocess.PIPE,
                check=False,
                timeout=10,
            ).stdout.decode("utf-8")
        )
        b_level = battery["percentage"]
        b_status = battery["status"]
        b_current = battery["current"] / 1000
        b_temp = battery["temperature"]
        bot.reply_to(
            message,
            f"""
Уровень заряда батареи: {b_level}%
Статус батареи: {b_status}
Температура: {b_temp:.0f}°C
Ток потребления: {b_current:.0f}mA
""",
        )
        logging.info("Запрошен статус питания")
    except subprocess.SubprocessError as ex:
        logging.error("HFpager battery-status error: %s", ex)
        bot.reply_to(message, "Статус питания недоступен :-(")


@bot.message_handler(func=lambda message: True)
def input_message(message):
    """Function for msg."""
    # обрабатываем начинающиеся с > из чата chat_id
    if message.date > start_time and message.chat.id == CHAT_ID:
        parse_bot_to_radio(message)


# This function, parse_bot_to_radio, is responsible for parsing messages in the format: 123>321! text
# It takes a message object as an argument and returns None, while also processing the message accordingly.
def parse_bot_to_radio(message):
    # Compile a regular expression pattern to match the desired message format
    reg = re.compile(
        "^(?P<FROM>[0-9]{0,5})>(?P<TO>[0-9]{0,5})"
        "(?P<REPEAT>!{0,1})"
        "\\s*(?P<SPEED>([sS]=[0-9]{1,2}\\.{0,1}[0-9]{0,1}){0,1})"
        "(?P<TEXT>[\\s\\S]+)"
    )

    # Attempt to match the message text with the compiled pattern
    match = re.match(reg, message.text)

    # If a match is found, proceed with parsing and processing the message
    if match:
        # Store the matched groups in a dictionary called msg_meta
        msg_meta = match.groupdict()
        # Log the msg_meta dictionary for debugging and monitoring purposes
        logging.info(pformat(msg_meta))

        # Check if the FROM value is empty or equal to MY_ID, and set TO if it's empty
        if msg_meta["FROM"] == "" or msg_meta["FROM"] == str(MY_ID):
            msg_meta["TO"] = msg_meta["TO"] or str(ABONENT_ID)
            # Add the MSG_END suffix to the TEXT value
            msg_meta["TEXT"] = msg_meta["TEXT"].strip() + MSG_END
            # Set the REPEAT value to 1 if it's empty or 0
            msg_meta["REPEAT"] = 1 if msg_meta["REPEAT"] else 0
            # Convert the SPEED value to a numeric format
            msg_meta["SPEED"] = get_speed(msg_meta["SPEED"].strip("sS="))

            # Shorten the message text for display purposes
            short_text = shorten(message.text, width=35, placeholder="...")
            # Log the shortened message text for debugging and monitoring purposes
            logging.info("Bot receive message: %s", short_text)

            # Call the pager_transmit function with the appropriate arguments
            pager_transmit(
                msg_meta["TEXT"], msg_meta["TO"], msg_meta["SPEED"], msg_meta["REPEAT"]
            )

            # Send a shortened version of the message text back to the user
            message = bot.send_message(chat_id=CHAT_ID, text=short_text)

            # Update the bot_recieve_dict dictionary with the message data
            bot_recieve_dict[msg_meta["TEXT"]] = {"message_id": message.message_id}

            # Update the mailbox dictionary with the new message data
            mailbox[msg_meta["TO"]] = msg_meta["TEXT"]


start_time = int(time())

if __name__ == "__main__":
    print("Bot starting...")
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    if OS_TYPE == "ANDROID":
        antisleep = Thread(target=hfpager_restart)
    to_radio.start()
    to_web.start()
    if OS_TYPE == "ANDROID":
        antisleep.start()
    to_radio.join()
    to_web.join()
    if OS_TYPE == "ANDROID":
        antisleep.join()
