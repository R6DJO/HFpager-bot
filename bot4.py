#!/usr/bin/env python
'''Telegram bot for HFpager'''
import argparse
import configparser
import json
import logging
import os
from pprint import pformat
import re
import subprocess
from sys import exit
from time import sleep, time
from datetime import datetime
from textwrap import shorten
from threading import Thread

import telebot
# from telebot import ExceptionHandler, TeleBot
from telebot.util import smart_split

from utils import get_weather, get_speed

parser = argparse.ArgumentParser(
    description='Telegram bot for HFpager/gate (see dxsoft.com).')
parser.add_argument('-c', '--conf', dest="configfile",
                    type=str, required=True, default=None)
args = parser.parse_args()

# config = configparser.ConfigParser(
#     allow_no_value=True, default_section=False, inline_comment_prefixes=('#', ';'))

try:
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    config.read(args.configfile)

    MY_ID = config.getint('hfpager', 'my_id')
    ABONENT_ID = config.getint('hfpager', 'abonent_id', fallback=999)
    CALLSIGN = config.get('hfpager', 'callsign')
    MSG_END = ' ' + config.get('hfpager', 'msg_end')
    GEO_DELTA = config.getfloat('hfpager', 'geo_delta', fallback=0.0)

    TOKEN = config.get('telegram', 'token')
    CHAT_ID = config.getint('telegram', 'chat_id')
    BEACON_CHAT_ID = config.getint(
        'telegram', 'beacon_chat_id', fallback=CHAT_ID)
    OWNER_CHAT_ID = config.getint(
        'telegram', 'owner_chat_id', fallback=CHAT_ID)

    OS_TYPE = config.get('system', 'system')
    RUN_PAGER = config.getboolean('system', 'run_pager', fallback=False)
    HFPAGER_PATH = config.get('system', 'hfpager_path')
    LOG_LEVEL = config.get('system', 'log_level', fallback='WARNING')
    OWM_API_KEY = config.get('system', 'owm_api_key')
except configparser.Error as e:
    print(
        f'ERROR: {e} in configfile {args.configfile} or file not exist.')
    exit(1)

print(RUN_PAGER)

logging.basicConfig(
    filename='bot.log',
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s')


message_dict = {}
bot_recieve_dict = {}
mailbox = {}


def bot_polling():
    """Function start bot polling."""
    logging.info('Bot polling is running')
    while True:
        try:
            logging.debug('Bot polling')
            bot.polling(interval=5)
        except Exception as ex:
            logging.error('Bot polling error: %s', ex)
            logging.debug('Error: %s', ex, exc_info=True)


def hfpager_restart():
    """Function periodicaly restart HFpager.app on Android."""
    logging.info('HFpager restart thread started')
    while True:
        try:
            subprocess.run(
                'am start --user 0 '
                '-n ru.radial.nogg.hfpager/'
                'ru.radial.full.hfpager.MainActivity '
                '-a "android.intent.action.SEND" '
                '--es "android.intent.extra.TEXT" "notext" '
                '-t "text/plain" '
                '--ei "android.intent.extra.INDEX" "99999"',
                stdout=subprocess.PIPE, shell=True, check=False,
                timeout=10)

            # sleep(300)
        except subprocess.SubprocessError as ex:
            logging.error('HFpager restart thread: %s', ex)
            logging.debug('Error: %s', ex, exc_info=True)
        finally:
            sleep(300)


def hfpager_bot():
    """Function for check new msg file on FS."""
    if OS_TYPE == 'ANDROID':
        pager_dir = ('/data/data/com.termux/files/home/storage/shared/'
                     'Documents/HFpager/')
    elif OS_TYPE == 'LINUX':
        pager_dir = HFPAGER_PATH + 'data/MESSAGES.DIR/'
    else:
        pager_dir = './'
    while True:
        try:
            start_hfpager()
            logging.info('HFpager message parsing is running')
            start_file_list = []
            for root, _, files in os.walk(pager_dir):
                for file in files:
                    start_file_list.append(os.path.join(root, file))
            while True:
                current_file_list = []
                for root, _, files in os.walk(pager_dir):
                    for file in files:
                        current_file_list.append(os.path.join(root, file))
                delta = list(set(current_file_list) - set(start_file_list))
                logging.debug('New files: %s', delta)
                for file in delta:
                    try:
                        mesg = open(file, 'r', encoding='cp1251')
                        text = mesg.read()
                        parse_file(file.replace(pager_dir, ''), text)
                    except IOError as ex:
                        logging.error('HFpager read file error: %s', ex)
                        logging.debug('Error: %s', ex, exc_info=True)
                start_file_list = current_file_list.copy()
                sleep(2)

        except Exception as ex:
            logging.error('HFpager message parsing error: %s', ex)
            logging.debug('Error: %s', ex, exc_info=True)
        finally:
            sleep(2)


def start_hfpager():
    """Function start HFpager app."""
    if OS_TYPE == 'ANDROID':
        subprocess.run(
            'am start --user 0 '
            '-n ru.radial.nogg.hfpager/'
            'ru.radial.full.hfpager.MainActivity ',
            stdout=subprocess.PIPE, shell=True, check=False,
            timeout=10)
        logging.info('HFpager started')
    elif OS_TYPE == 'LINUX' and RUN_PAGER is True:
        subprocess.run(
            f'cd {HFPAGER_PATH}/bin/; ./start.sh; exit', shell=True, check=False,
            timeout=10)
        logging.info('HFpager started')


def send_edit_msg(key, message):
    """Function send or update message to TG."""
    text = message.split('\n', maxsplit=1)[-1].strip()
    if text in bot_recieve_dict:
        result = bot.edit_message_text(
            chat_id=CHAT_ID, text=message,
            message_id=bot_recieve_dict[text]['message_id'])
        message_dict[key] = {
            'message_id': bot_recieve_dict[text]['message_id']}
        del bot_recieve_dict[text]
    elif key in message_dict:
        bot.edit_message_text(chat_id=CHAT_ID, text=message,
                              message_id=message_dict[key]['message_id'])
    else:
        result = bot.send_message(chat_id=CHAT_ID,
                                  text=message)
        message_dict[key] = {'message_id': result.message_id}


def parse_file(dir_filename, text):
    """Function parse file."""
    dirname, filename = dir_filename.split('/')
    logging.info(dir_filename)
    #
    # F1+F2 RO RE принято OK или ERROR
    # F1+F2 S1-S5 - отправлено сколько раз
    # F3 0 2 3 Flags: ACK REPEAT (0=!ACK+!REPEAT, 2=ACK+!REPEAT, 3=ACK+REPEAT)
    # F3+F4 2P/3P=ACK 2N/3N=NACK 20/30=ACK запрошен, но не получен
    #
    pattern = (r'(?P<DT_DATE>[\d-]{10})\.(?P<MSG_TYPE>[\D]{3})/'
               r'(?P<DT_TIME>[\d]{6})-(?P<F1>[\D])(?P<F2>[\D])-'
               r'(?P<F3>[\d]{0,1})(?P<F4>[\d])-(?P<MSG_NUM>[\d]{3})-'
               r'(?P<MSG_LEN>[0-9A-F]{2})-'
               r'(?P<HEAD_CRC>[0-9A-F]{4})-(?P<MSG_CRC>[0-9A-F]{4})-'
               r'(?P<ID_FROM>[\d]{1,5}|~)_(?P<ID_TO>[\d]{1,5}|~)\.TXT')
    match_object = re.search(pattern, dir_filename)
    if match_object:
        msg_meta = match_object.groupdict()
        logging.info(pformat(msg_meta))

    cur_date = dirname.split('.')[0]
    cur_time = filename.split('-')[0]
    key = f'{cur_date} {cur_time}'
    short_text = shorten(text, width=35, placeholder="...")
    if re.match(r'\d{6}-RO-0.+_' + str(MY_ID) + '.TXT', filename):
        logging.info('HFpager private message received: %s', text)
        bot.send_message(chat_id=CHAT_ID,
                         text=text)
        detect_request(text)
    elif re.match(r'\d{6}-RO-[2,3].+_' + str(MY_ID) + '.TXT', filename):
        logging.info('HFpager private message received and acknowledgment '
                     'sent: %s', short_text)
        bot.send_message(chat_id=CHAT_ID, text=f'√ {text}')
        detect_request(text)
    elif re.match(r'\d{6}-RE.+~_~.TXT', filename):
        logging.info('HFpager message intercepted: %s', text)
        bot.send_message(chat_id=BEACON_CHAT_ID, text=text,
                         disable_notification=True)
        detect_request(text)
    elif re.match(r'\d{6}-R', filename):
        logging.info('HFpager message intercepted: %s', text)
        bot.send_message(chat_id=CHAT_ID, text=text,
                         disable_notification=True)
        detect_request(text)
    elif re.match(r'\d{6}-S[1-9]-\dP', filename):
        logging.info('HFpager message sent and acknowledgment '
                     'received: %s', short_text)
        send_edit_msg(key, f'√ {text}')
    elif re.match(r'\d{6}-S[1-9]-\dN', filename):
        logging.info('HFpager message sent and not '
                     'acknowledgment received: %s', short_text)
        send_edit_msg(key, f'X {text}')
    elif re.match(r'\d{6}-S[1-9]-\d0', filename):
        logging.info('HFpager message sent: %s', short_text)
        send_edit_msg(key, f'{text}')
    elif re.match(r'\d{6}-B', filename):
        logging.info('HFpager beacon intercepted: %s', text)
        bot.send_message(chat_id=BEACON_CHAT_ID, text=text,
                         disable_notification=True)


def detect_request(msg_full):
    """Function detect request in msg."""
    msg_meta = {}
    msg_meta["FROM"], msg_meta["TO"] = 0, 0
    msg_text = msg_full.split('\n', maxsplit=1)[-1]
    # получаем id адресатов
    match = re.match(r'(?P<FROM>\d{1,5}) \(\d{3}\) > '
                     r'(?P<TO>[0-9]{1,5}), '
                     r'(?P<SPEED>\d{1,2}\.{0,1}\d{0,1}) Bd',
                     msg_full)
    if match:
        msg_meta = match.groupdict()
        logging.info(pformat(msg_meta))
        msg_meta['SPEED'] = get_speed(msg_meta['SPEED'])
        # logging.info(pformat(msg_meta))
    # парсим {lat},{lon}: map_link -> web
    match = re.search(r'(?P<LAT>-{0,1}\d{1,2}\.\d{1,8}),'
                      r'(?P<LON>-{0,1}\d{1,3}\.\d{1,8})',
                      msg_text)
    if match:
        msg_geo = match.groupdict()
        msg_geo["LAT"] = round(float(msg_geo["LAT"]) + GEO_DELTA, 4)
        msg_geo["LON"] = round(float(msg_geo["LON"]) + GEO_DELTA, 4)
        dt_string = datetime.now().strftime('%d-%b-%Y%%20%H:%M')
        message = (f'https://nakarte.me/#m=13/{msg_geo["LAT"]}/{msg_geo["LON"]}'
                   f'&l=Otm/Wp&nktp={msg_geo["LAT"]}/{msg_geo["LON"]}/{dt_string}')
        logging.info('HFpager -> MapLink: %s', message)
        bot.send_message(chat_id=CHAT_ID, text=message)
    # парсим =x{lat},{lon}: weather -> hf
    match = re.match(r'=[xX](?P<LAT>-{0,1}\d{1,2}\.\d{1,8}),'
                     r'(?P<LON>-{0,1}\d{1,3}\.\d{1,8})',
                     msg_text)
    if match:
        msg_geo = match.groupdict()
        msg_geo["LAT"] = round(float(msg_geo["LAT"]) + GEO_DELTA, 4)
        msg_geo["LON"] = round(float(msg_geo["LON"]) + GEO_DELTA, 4)
        if int(msg_meta["TO"]) == MY_ID:
            logging.info('HFpager -> Weather: %s %s',
                         msg_geo["LAT"], msg_geo["LON"])
            bot.send_message(chat_id=CHAT_ID,
                             text=(f'{MY_ID}>{msg_meta["FROM"]} '
                                   f'weather in {msg_geo["LAT"]},'
                                   f'{msg_geo["LON"]}'))
            weather = get_weather(
                OWM_API_KEY, msg_geo["LAT"], msg_geo["LON"]) + MSG_END
            split = smart_split(weather, 250)
            for part in split:
                pager_transmit(part, msg_meta["FROM"], msg_meta['SPEED'], 0)

    match = re.match(r'=[gGtT]', msg_text)
    if match and msg_meta['TO'] == str(MY_ID):
        if msg_meta['FROM'] in mailbox:
            logging.info('%s request from mailbox', msg_meta["FROM"])
            pager_transmit(mailbox[msg_meta['FROM']] + MSG_END,
                           msg_meta["FROM"], msg_meta['SPEED'], 0)
        else:
            logging.info('No msg to %s in mailbox', msg_meta["FROM"])
            pager_transmit('No msg', msg_meta["FROM"], msg_meta['SPEED'], 0)


def pager_transmit(message, abonent_id, speed, resend):
    """Function send HFpager msg."""
    short_text = shorten(message, width=35, placeholder="...")
    logging.info('HFpager send to ID:%s repeat:%s '
                 'message: %s', abonent_id, resend, short_text)
    if OS_TYPE == 'ANDROID':
        subprocess.run(
            'am start --user 0 '
            '-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity '
            '-a "android.intent.action.SEND" '
            f'--es "android.intent.extra.TEXT" "{message.strip()}" '
            '-t "text/plain" '
            f'--ei "android.intent.extra.INDEX" "{abonent_id}" '
            f'--es "android.intent.extra.SUBJECT" "Flags:1,{resend}"',
            stdout=subprocess.PIPE, shell=True, check=False, timeout=10)
    elif OS_TYPE == 'LINUX':
        ackreq = 1
        msg_shablon = (f'to={abonent_id},speed={speed},'
                       f'askreq={ackreq},resend={resend}\n'
                       f'{message.strip()}')
        logging.info(msg_shablon)
        with open(HFPAGER_PATH + 'data/to_send/new.ms', 'w',
                  encoding='cp1251') as f:
            f.write(msg_shablon)
        os.rename(HFPAGER_PATH + 'data/to_send/new.ms',
                  HFPAGER_PATH + 'data/to_send/new.msg')
        sleep(1)


bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    """Function send bot welcome msg."""
    bot.reply_to(message, f"""Привет, я HFpager Bot.
Я отправляю сообщения с шлюза {CALLSIGN} мой ID:{MY_ID}\n
Как меня использовать:\n
`>blah blah blah` - отправит _blah blah blah_ на ID:{ABONENT_ID}\n
`>123 blah blah blah` - отправит _blah blah blah_ на ID:_123_\n
`! blah blah blah` - ! в сообщении равносилен опции "Повторять до подтв."\n
`>123! blahblah` - отправка на ID:123 будет повторятся до подтверждения
""", parse_mode='markdown')


@bot.message_handler(commands=['bat', 'battery'])
def send_bat_status(message):
    """Function send battery status."""
    try:
        battery = json.loads(
            subprocess.run(['termux-battery-status'],
                           stdout=subprocess.PIPE, check=False,
                           timeout=10).stdout.decode('utf-8'))
        b_level = battery['percentage']
        b_status = battery['status']
        b_current = battery['current']/1000
        b_temp = battery['temperature']
        bot.reply_to(message, f"""
Уровень заряда батареи: {b_level}%
Статус батареи: {b_status}
Температура: {b_temp:.0f}°C
Ток потребления: {b_current:.0f}mA
""")
        logging.info('Запрошен статус питания')
    except subprocess.SubprocessError as ex:
        logging.error('HFpager battery-status error: %s', ex)
        bot.reply_to(message, 'Статус питания недоступен :-(')


@bot.message_handler(func=lambda message: True)
def input_message(message):
    """Function for msg."""
    # обрабатываем начинающиеся с > из чата chat_id
    if message.date > start_time and message.chat.id == CHAT_ID:
        parse_bot_to_radio(message)


def parse_bot_to_radio(message):
    """парсим сообщения типа 123>321! текст"""
    reg = re.compile('^(?P<FROM>[0-9]{0,5})>(?P<TO>[0-9]{0,5})'
                     '(?P<REPEAT>!{0,1})'
                     '\\s*(?P<SPEED>([sS]=[0-9]{1,2}\\.{0,1}[0-9]{0,1}){0,1})'
                     '(?P<TEXT>[\\s\\S]+)')
    match = re.match(reg, message.text)
    if match:
        msg_meta = match.groupdict()
        logging.info(pformat(msg_meta))
        if msg_meta['FROM'] == '' or msg_meta['FROM'] == str(MY_ID):
            msg_meta['TO'] = msg_meta['TO'] or str(ABONENT_ID)
            msg_meta['TEXT'] = msg_meta['TEXT'].strip() + MSG_END
            msg_meta['REPEAT'] = 1 if msg_meta['REPEAT'] else 0
            msg_meta['SPEED'] = get_speed(msg_meta['SPEED'].strip("sS="))
            short_text = shorten(message.text, width=35, placeholder="...")
            logging.info('Bot receive message: %s', short_text)
            pager_transmit(msg_meta['TEXT'], msg_meta['TO'],
                           msg_meta['SPEED'], msg_meta['REPEAT'])
            message = bot.send_message(chat_id=CHAT_ID,
                                       text=short_text)
            bot_recieve_dict[msg_meta['TEXT']] = {
                'message_id': message.message_id}
            mailbox[msg_meta['TO']] = msg_meta['TEXT']


start_time = int(time())

if __name__ == "__main__":
    print('Bot starting...')
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    if OS_TYPE == 'ANDROID':
        antisleep = Thread(target=hfpager_restart)
    to_radio.start()
    to_web.start()
    if OS_TYPE == 'ANDROID':
        antisleep.start()
    to_radio.join()
    to_web.join()
    if OS_TYPE == 'ANDROID':
        antisleep.join()
