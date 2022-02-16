#!/bin/python
# -*- coding: utf-8 -*-
import re
import json
import telebot
from telebot.util import smart_split
import time
import subprocess
import os
from threading import Thread
from datetime import datetime
from textwrap import shorten
import requests
import logging

from config import abonent_id, callsign, chat_id, my_id, token, owm_api_key


logging.basicConfig(
    filename='bot.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
)


message_dict = {}
bot_recieve_dict = {}


def date_time_now():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return now


def bot_polling():
    logging.info('Bot polling is running')
    while True:
        try:
            bot.polling(interval=5)
            logging.debug('Bot polling')
        except Exception as ex:
            logging.error(f'Bot polling error: {ex}')
            logging.debug(f'Error: {ex}', exc_info=True)


def hfpager_bot():
    subprocess.Popen(
        'am start --user 0 '
        '-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity ',
        stdout=subprocess.PIPE, shell=True)
    logging.info('HFpager started')
    logging.info('HFpager message parsing is running')
    power_stat_prev = 'UNKNOWN'
    while True:
        try:
            # msg_dir = '/data/data/com.termux/files/home/storage/shared/'
            #           'Documents/HFpager/'
            pager_dir = '/storage/emulated/0/Documents/HFpager/'
            msg_dirs = [f.path for f in os.scandir(pager_dir)
                        if f.is_dir() and re.match(r'.*\.MSG', f.name)]
            last_dir = sorted(msg_dirs)[-1]
            nowt = time.time()
            if os.path.isdir(last_dir):
                for filename in os.scandir(last_dir):
                    if os.stat(filename).st_ctime > nowt - 6:
                        mesg = open(filename, 'r',
                                    encoding='cp1251')
                        text = mesg.read()
                        parse_file(filename.path.replace(pager_dir, ''), text)
        except Exception as ex:
            logging.error(f'HFpager send/receive message error: {ex}')
            logging.debug(f'Error: {ex}', exc_info=True)
        power_stat = power_status()
        if power_stat != power_stat_prev:
            logging.info(f'Power status: {power_stat}')
            bot.send_message(
                chat_id=chat_id,
                text=f'Power status: {power_stat}')
            power_stat_prev = power_stat
        time.sleep(5)


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


def detect_request(text):
    mesg_from = 0
    mesg_to = 0
    parse_message = text.split('\n', maxsplit=1)[-1]
    # получаем id адресатов
    match = re.search(r'^(\d{1,5}) \(\d+\) > (\d+).*', text)
    if match:
        mesg_from = match[1]
        mesg_to = match[2]
    # парсим =x{lat},{lon}: map_link -> web
    match = re.search(r'^=x(-{0,1}\d{1,2}\.\d{1,6}),(-{0,1}\d{1,3}\.\d{1,6})',
                      parse_message)
    if match:
        mlat = match[1]
        mlon = match[2]
        message = ('https://www.openstreetmap.org/?'
                   f'mlat={mlat}&mlon={mlon}&zoom=12')
        logging.info(f'HFpager -> MapLink: {message}')
        bot.send_message(chat_id=chat_id, text=message)
    # парсим =w{lat},{lon}: weather -> hf
    match = re.search(r'^=w(-{0,1}\d{1,2}\.\d{1,6}),(-{0,1}\d{1,3}\.\d{1,6})',
                      parse_message)
    if match and mesg_to == str(my_id):
        mlat = match[1]
        mlon = match[2]
        logging.info(f'HFpager -> Weather: {mlat} {mlon}')
        bot.send_message(chat_id=chat_id,
                         text=(f'{my_id}>{mesg_from} '
                               f'weather in: {mlat} {mlon}'))
        weather = get_weather(mlat, mlon)
        split = smart_split(weather, 250)
        for part in split:
            pager_transmit(part, mesg_from, 1)


def get_weather(lat, lon):
    url = ('https://api.openweathermap.org/data/2.5/onecall?'
           f'lat={lat}&lon={lon}&exclude=minutely,hourly&appid={owm_api_key}'
           '&lang=ru&units=metric')
    resp = requests.get(url)
    data = resp.json()
    weather = ''
    if 'cod' in data:
        error = data['message']
        logging.error(f'HFpager get weather error: {error}')
        return 'Error in weather'
    else:
        for day in data['daily'][:3]:
            date = datetime.fromtimestamp(day['dt']).strftime('%m/%d')
            temp_min = day['temp']['min']
            temp_max = day['temp']['max']
            clouds = day['clouds']
            pop = day['pop']*100
            wind_speed = day['wind_speed']
            wind_gust = day['wind_gust']
            weather_cond = day['weather'][0]['description']
            wind_direct = get_wind_direction(day['wind_deg'])
            weather += (f'{date} '
                        f'Темп:{temp_min:.0f}…{temp_max:.0f}°C '
                        f'Вет:{wind_direct} {wind_speed:.0f}…'
                        f'{wind_gust:.0f}м/с {weather_cond} '
                        f'Обл:{clouds}% Вер.ос:{pop:.0f}% ')
            if 'rain' in day:
                rain = day['rain']
                weather += f'Дождь:{rain:.1f}мм '
            if 'snow' in day:
                rain = day['snow']
                weather += f'Снег:{rain:.1f}мм '
            weather += '\n'
        return weather


def get_wind_direction(deg):
    wind = ''
    direction = ['С ', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
    for i in range(0, 8):
        step = 45.
        min = i*step - 45/2.
        max = i*step + 45/2.
        if i == 0 and deg > 360-45/2.:
            deg = deg - 360
        if deg >= min and deg <= max:
            wind = direction[i]
            break
    return wind


def parse_for_pager(message, abonent_id):
    # > обрезаем заранее
    # сообщение >[id][text] -> [id]
    match = re.match(r'^(\d{1,5})(\D.+)', message)
    if match:
        abonent_id = match.group(1)
        message = match.group(2)

    # сообщение начинается с ! -> бит повтора 1
    match = re.match(r'^!(.+)', message)
    if match:
        repeat = 1
        message = match.group(1)
    else:
        repeat = 0

    pager_transmit(message, abonent_id, repeat)


def pager_transmit(message, abonent_id, repeat):
    short_text = shorten(message, width=35, placeholder="...")
    logging.info(f'HFpager send to ID:{abonent_id} repeat:{repeat} '
                 f'message: {short_text}')
    subprocess.Popen(
        'am start --user 0 '
        '-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity '
        '-a "android.intent.action.SEND" '
        f'--es "android.intent.extra.TEXT" "{message.strip()}" '
        '-t "text/plain" '
        f'--ei "android.intent.extra.INDEX" "{abonent_id}" '
        f'--es "android.intent.extra.SUBJECT" "Flags:1,{repeat}"',
        stdout=subprocess.PIPE, shell=True)
    # out = proc.stdout.read()
    # return out


def power_status():
    try:
        battery = json.loads(
            subprocess.run(['termux-battery-status'],
                           stdout=subprocess.PIPE).stdout.decode('utf-8'))
        b_status = battery['status']
    except Exception as ex:
        logging.error(f'HFpager battery-status error: {ex}')
        b_status = 'UNKNOWN'
    return b_status


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
            subprocess.run(['termux-battery-status'],
                           stdout=subprocess.PIPE).stdout.decode('utf-8'))
        b_level = battery['percentage']
        b_status = battery['status']
        b_current = battery['current']
        b_temp = battery['temperature']
        bot.reply_to(message, f"""
Уровень заряда батареи: {b_level}%
Статус батареи: {b_status}
Температура: {b_temp}°C
Ток потребления: {b_current}mA
""")
        logging.info('Запрошен статус питания')
    except Exception as ex:
        logging.error(f'HFpager battery-status error: {ex}')
        bot.reply_to(message, 'Статус питания недоступен :-(')


@bot.message_handler(func=lambda message: True)
def echo_message(message):
    # обрабатываем начинающиеся с >
    if message.date > start_time:
        reg = re.compile(f'^({my_id}' + ')*>(\\d{1,5})*(.+)')
        match = re.match(reg, message.text)
        if match:
            short_text = shorten(message.text, width=35, placeholder="...")
            logging.info(f'Bot receive message: {short_text}')
            if match.group(2):
                text_parse = match.group(2) + match.group(3)
            else:
                text_parse = match.group(3)
            parse_for_pager(text_parse, abonent_id)
            message = bot.send_message(chat_id=chat_id,
                                       text=short_text)
            bot_recieve_dict[match.group(3).strip()] = {
                'message_id': message.message_id}


if __name__ == "__main__":
    name = "WEB->HFpager"
    start_time = int(time.time())
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    to_radio.start()
    to_web.start()
    to_radio.join()
    to_web.join()
