#!/usr/bin/env python

import json
import logging
import os
from pprint import pformat
import re
import subprocess
import time
from textwrap import shorten
from threading import Thread

import telebot
from telebot.util import smart_split

from utils import get_weather, get_speed

from config import (abonent_id, beacon_chat_id, callsign, chat_id, geo_delta,
                    hfpager_path, log_level, msg_end, my_id, system, token)


logging.basicConfig(
    filename='bot.log',
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(message)s')


message_dict = {}
bot_recieve_dict = {}
mailbox = {}


def bot_polling():
    logging.info('Bot polling is running')
    while True:
        try:
            logging.debug('Bot polling')
            bot.polling(interval=5)
        except Exception as ex:
            logging.error(f'Bot polling error: {ex}')
            logging.debug(f'Error: {ex}', exc_info=True)


def hfpager_restart():
    if system == 'ANDROID':
        logging.info('HFpager restart thread started')
        while True:
            try:
                subprocess.Popen(
                    'am start --user 0 '
                    '-n ru.radial.nogg.hfpager/'
                    'ru.radial.full.hfpager.MainActivity '
                    '-a "android.intent.action.SEND" '
                    '--es "android.intent.extra.TEXT" "notext" '
                    '-t "text/plain" '
                    '--ei "android.intent.extra.INDEX" "99999"',
                    stdout=subprocess.PIPE, shell=True)
                # time.sleep(300)
            except Exception as ex:
                logging.error(f'HFpager restart thread: {ex}')
                logging.debug(f'Error: {ex}', exc_info=True)
            finally:
                time.sleep(300)


def hfpager_bot():
    if system == 'ANDROID':
        pager_dir = ('/data/data/com.termux/files/home/storage/shared/'
                     'Documents/HFpager/')
    elif system == 'LINUX':
        pager_dir = hfpager_path + 'files/HFpager/'
    else:
        pager_dir = './'
    while True:
        try:
            start_hfpager()
            logging.info('HFpager message parsing is running')
            start_file_list = []
            for root, dirs, files in os.walk(pager_dir):
                for file in files:
                    start_file_list.append(os.path.join(root, file))
            while True:
                current_file_list = []
                for root, dirs, files in os.walk(pager_dir):
                    for file in files:
                        current_file_list.append(os.path.join(root, file))
                delta = list(set(current_file_list) - set(start_file_list))
                logging.debug(f'New files: {delta}')
                for file in delta:
                    try:
                        mesg = open(file, 'r', encoding='cp1251')
                        text = mesg.read()
                        parse_file(file.replace(pager_dir, ''), text)
                    except IOError as ex:
                        logging.error(f'HFpager read file error: {ex}')
                        logging.debug(f'Error: {ex}', exc_info=True)
                start_file_list = current_file_list.copy()
                time.sleep(2)

        except Exception as ex:
            logging.error(f'HFpager message parsing error: {ex}')
            logging.debug(f'Error: {ex}', exc_info=True)
        finally:
            time.sleep(2)


def start_hfpager():
    if system == 'ANDROID':
        subprocess.Popen(
            'am start --user 0 '
            '-n ru.radial.nogg.hfpager/'
            'ru.radial.full.hfpager.MainActivity ',
            stdout=subprocess.PIPE, shell=True)
    elif system == 'LINUX':
        subprocess.Popen(
            f'cd {hfpager_path}; ./start.sh',
            stdout=subprocess.PIPE, shell=True)
    logging.info('HFpager started')


def send_edit_msg(key, message):
    text = message.split('\n', maxsplit=1)[-1].strip()
    if text in bot_recieve_dict:
        result = bot.edit_message_text(
            chat_id=chat_id, text=message,
            message_id=bot_recieve_dict[text]['message_id'])
        message_dict[key] = {
            'message_id': bot_recieve_dict[text]['message_id']}
        del bot_recieve_dict[text]
    elif key in message_dict:
        bot.edit_message_text(chat_id=chat_id, text=message,
                              message_id=message_dict[key]['message_id'])
    else:
        result = bot.send_message(chat_id=chat_id,
                                  text=message)
        message_dict[key] = {'message_id': result.message_id}


def parse_file(dir_filename, text):
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

    date = dirname.split('.')[0]
    time = filename.split('-')[0]
    key = f'{date} {time}'
    short_text = shorten(text, width=35, placeholder="...")
    if re.match(r'\d{6}-RO-0.+_' + str(my_id) + '.TXT', filename):
        logging.info(f'HFpager private message received: {text}')
        bot.send_message(chat_id=chat_id,
                         text=text)
        detect_request(text)
    elif re.match(r'\d{6}-RO-[2,3].+_' + str(my_id) + '.TXT', filename):
        logging.info('HFpager private message received and acknowledgment '
                     f'sent: {short_text}')
        bot.send_message(chat_id=chat_id, text=f'√ {text}')
        detect_request(text)
    elif re.match(r'\d{6}-RE.+~_~.TXT', filename):
        logging.info(f'HFpager message intercepted: {text}')
        bot.send_message(chat_id=beacon_chat_id, text=text,
                         disable_notification=True)
        detect_request(text)
    elif re.match(r'\d{6}-R', filename):
        logging.info(f'HFpager message intercepted: {text}')
        bot.send_message(chat_id=chat_id, text=text,
                         disable_notification=True)
        detect_request(text)
    elif re.match(r'\d{6}-S[1-9]-\dP', filename):
        logging.info('HFpager message sent and acknowledgment '
                     f'received: {short_text}')
        send_edit_msg(key, f'√ {text}')
    elif re.match(r'\d{6}-S[1-9]-\dN', filename):
        logging.info('HFpager message sent and not '
                     f'acknowledgment received: {short_text}')
        send_edit_msg(key, f'X {text}')
    elif re.match(r'\d{6}-S[1-9]-\d0', filename):
        logging.info(f'HFpager message sent: {short_text}')
        send_edit_msg(key, f'{text}')
    elif re.match(r'\d{6}-B', filename):
        logging.info(f'HFpager beacon intercepted: {text}')
        bot.send_message(chat_id=beacon_chat_id, text=text,
                         disable_notification=True)


def detect_request(msg_full):
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
        msg_geo["LAT"] = round(float(msg_geo["LAT"]) + geo_delta, 4)
        msg_geo["LON"] = round(float(msg_geo["LON"]) + geo_delta, 4)
        message = ('https://www.openstreetmap.org/?'
                   f'mlat={msg_geo["LAT"]}&mlon={msg_geo["LON"]}&zoom=13&layers=Y')
        logging.info(f'HFpager -> MapLink: {message}')
        bot.send_message(chat_id=chat_id, text=message)
    # парсим =x{lat},{lon}: weather -> hf
    match = re.match(r'=[xX](?P<LAT>-{0,1}\d{1,2}\.\d{1,8}),'
                     r'(?P<LON>-{0,1}\d{1,3}\.\d{1,8})',
                     msg_text)
    if match:
        msg_geo = match.groupdict()
        msg_geo["LAT"] = round(float(msg_geo["LAT"]) + geo_delta, 4)
        msg_geo["LON"] = round(float(msg_geo["LON"]) + geo_delta, 4)
        if int(msg_meta["TO"]) == my_id:
            logging.info(f'HFpager -> Weather: {msg_geo["LAT"]} '
                         f'{msg_geo["LON"]}')
            bot.send_message(chat_id=chat_id,
                             text=(f'{my_id}>{msg_meta["FROM"]} '
                                   f'weather in {msg_geo["LAT"]},'
                                   f'{msg_geo["LON"]}'))
            weather = get_weather(msg_geo["LAT"], msg_geo["LON"]) + msg_end
            split = smart_split(weather, 250)
            for part in split:
                pager_transmit(part, msg_meta["FROM"], msg_meta['SPEED'], 0)

    match = re.match(r'=[gGtT]', msg_text)
    if match and msg_meta['TO'] == str(my_id):
        if msg_meta['FROM'] in mailbox.keys():
            logging.info(f'{msg_meta["FROM"]} request from mailbox')
            pager_transmit(mailbox[msg_meta['FROM']] + msg_end,
                           msg_meta["FROM"], msg_meta['SPEED'], 0)
        else:
            logging.info(f'No msg to {msg_meta["FROM"]} in mailbox')
            pager_transmit('No msg', msg_meta["FROM"], msg_meta['SPEED'], 0)


def pager_transmit(message, abonent_id, speed, resend):
    short_text = shorten(message, width=35, placeholder="...")
    logging.info(f'HFpager send to ID:{abonent_id} repeat:{resend} '
                 f'message: {short_text}')
    if system == 'ANDROID':
        subprocess.Popen(
            'am start --user 0 '
            '-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity '
            '-a "android.intent.action.SEND" '
            f'--es "android.intent.extra.TEXT" "{message.strip()}" '
            '-t "text/plain" '
            f'--ei "android.intent.extra.INDEX" "{abonent_id}" '
            f'--es "android.intent.extra.SUBJECT" "Flags:1,{resend}"',
            stdout=subprocess.PIPE, shell=True)
    elif system == 'LINUX':
        ackreq = 1
        msg_shablon = (f'to={abonent_id},speed={speed},'
                       f'askreq={ackreq},resend={resend}\n'
                       f'{message.strip()}')
        logging.info(msg_shablon)
        with open(hfpager_path + 'files/to_send/new.ms', 'w',
                  encoding='cp1251') as f:
            f.write(msg_shablon)
        os.rename(hfpager_path + 'files/to_send/new.ms',
                  hfpager_path + 'files/to_send/new.msg')
        time.sleep(1)


bot = telebot.TeleBot(token)


@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message, f"""Привет, я HFpager Bot.
Я отправляю сообщения с шлюза {callsign} мой ID:{my_id}\n
Как меня использовать:\n
`>blah blah blah` - отправит _blah blah blah_ на ID:{abonent_id}\n
`>123 blah blah blah` - отправит _blah blah blah_ на ID:_123_\n
`! blah blah blah` - ! в сообщении равносилен опции "Повторять до подтв."\n
`>123! blahblah` - отправка на ID:123 будет повторятся до подтверждения
""", parse_mode='markdown')


@bot.message_handler(commands=['bat', 'battery'])
def send_bat_status(message):
    try:
        battery = json.loads(
            subprocess.run(['timeout', '5', 'termux-battery-status'],
                           stdout=subprocess.PIPE).stdout.decode('utf-8'))
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
    except Exception as ex:
        logging.error(f'HFpager battery-status error: {ex}')
        bot.reply_to(message, 'Статус питания недоступен :-(')


@bot.message_handler(func=lambda message: True)
def input_message(message):
    # обрабатываем начинающиеся с > из чата chat_id
    if message.date > start_time and message.chat.id == chat_id:
        parse_bot_to_radio(message)


def parse_bot_to_radio(message):
    '''
    парсим сообщения типа 123>321! текст
    '''
    reg = re.compile('^(?P<FROM>[0-9]{0,5})>(?P<TO>[0-9]{0,5})'
                     '(?P<REPEAT>!{0,1})'
                     '\\s*(?P<SPEED>([sS]=[0-9]{1,2}\\.{0,1}[0-9]{0,1}){0,1})'
                     '(?P<TEXT>[\\s\\S]+)')
    match = re.match(reg, message.text)
    if match:
        msg_meta = match.groupdict()
        logging.info(pformat(msg_meta))
        if msg_meta['FROM'] == '' or msg_meta['FROM'] == str(my_id):
            msg_meta['TO'] = msg_meta['TO'] or str(abonent_id)
            msg_meta['TEXT'] = msg_meta['TEXT'].strip() + msg_end
            msg_meta['REPEAT'] = 1 if msg_meta['REPEAT'] else 0
            msg_meta['SPEED'] = get_speed(msg_meta['SPEED'].strip("sS="))
            short_text = shorten(message.text, width=35, placeholder="...")
            logging.info(f'Bot receive message: {short_text}')
            pager_transmit(msg_meta['TEXT'], msg_meta['TO'],
                           msg_meta['SPEED'], msg_meta['REPEAT'])
            message = bot.send_message(chat_id=chat_id,
                                       text=short_text)
            bot_recieve_dict[msg_meta['TEXT']] = {
                'message_id': message.message_id}
            mailbox[msg_meta['TO']] = msg_meta['TEXT']


if __name__ == "__main__":
    name = "WEB->HFpager"
    start_time = int(time.time())
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    to_antisleep = Thread(target=hfpager_restart)
    to_radio.start()
    to_web.start()
    to_antisleep.start()
    to_radio.join()
    to_web.join()
    to_antisleep.join()
