#!/bin/python
# -*- coding: utf-8 -*-
# from fileinput import filename
import re
import telebot
import time
import subprocess
import os
from threading import Thread
from datetime import datetime
from textwrap import shorten
import requests

from config import abonent_id, callsign, chat_id, my_id, token, owm_api_key


message_dict = {}

def date_time_now():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return now


def bot_polling():
    now = date_time_now()
    print(f'{now} Bot polling is running')
    while True:
        try:
            bot.polling(interval=5)
        except Exception as ex:
            now = date_time_now()
            print(f'{now} Bot polling error: {ex}')


def hfpager_bot():
    now = date_time_now()
    print(f'{now} HFpager message parsing is running')
    while True:
        # date = datetime.now()
        # msg_dir = '/data/data/com.termux/files/home/storage/shared/
        # Documents/HFpager/' + date.strftime("%Y-%m-%d") + '.MSG/'
        # date_now = date.strftime("%Y-%m-%d")
        # msg_dir = f'/storage/emulated/0/Documents/HFpager/{date_now}.MSG/'
        pager_dir = '/storage/emulated/0/Documents/HFpager/'
        msg_dirs = [f.path for f in os.scandir(pager_dir)
                    if f.is_dir() and re.match(r'.*\.MSG', f.name)]
        last_dir = sorted(msg_dirs)[-1]
        nowt = time.time()
        if os.path.isdir(last_dir):
            try:
                for filename in os.scandir(last_dir):
                    # path_file = os.path.join(last_dir, filename)
                    if os.stat(filename).st_ctime > nowt - 5:
                        mesg = open(filename, 'r',
                                    encoding='cp1251')
                        text = mesg.read()
                        print(filename.path)
                        parse_file(filename.path.replace(pager_dir, ''), text)
            except Exception as ex:
                now = date_time_now()
                print(f'{now} HFpager send/receive message error: {ex}')
        time.sleep(5)


def parse_file(dir_filename, text):
    dirname, filename = dir_filename.split('/')
    date = dirname.split('.')[0]
    time = filename.split('-')[0]
    key = f'{date} {time}'
    if key in message_dict:
        print('Есть в базе', message_dict[key]['text'])
    else:
        print('Нет в базе, запомнили')
        message_dict[key]={'text': text}
    short_text = shorten(text, width=25, placeholder="...")
    if re.match(r'\d{6}-RO-0.+_' + str(my_id) + '.TXT', filename):
        now = date_time_now()
        print(f'{now} HFpager private message received: {text}')
        bot.send_message(chat_id=chat_id,
                         text=f'Private message received: {text}')
        detect_request(text)
    elif re.match(r'\d{6}-RO-[2,3].+_' + str(my_id) + '.TXT', filename):
        now = date_time_now()
        print(f'{now} HFpager private message received and acknowledgment '
              f'sent: {text}')
        bot.send_message(chat_id=chat_id, text='Private message received '
                         f'and acknowledgment sent: {text}')
        detect_request(text)
    elif re.match(r'\d{6}-R', filename):
        now = date_time_now()
        print(f'{now} HFpager message intercepted: {text}')
        bot.send_message(chat_id=chat_id, text=f'Message intercepted: {text}',
                         disable_notification=True)
        detect_request(text)
    elif re.match(r'\d{6}-S[1-9]-\dP', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent and acknowledgment '
              f'received: {short_text}')
        bot.send_message(chat_id=chat_id, text='Message sent and '
                         f'acknowledgment received: {short_text}',
                         disable_notification=True)
    elif re.match(r'\d{6}-S[1-9]-\dN', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent and not '
              f'acknowledgment received: {short_text}')
        bot.send_message(chat_id=chat_id, text='Message sent and not '
                         f'acknowledgment received: {short_text}',
                         disable_notification=True)
    elif re.match(r'\d{6}-S[1-9]-\d0', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent: {short_text}')
        bot.send_message(chat_id=chat_id,
                         text=f'Message sent: {short_text}',
                         disable_notification=True)


def detect_request(text):
    mesg_from = 0
    mesg_to = 0
    now = date_time_now()

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
        print(f'{now} HFpager -> MapLink: {message}')
        bot.send_message(chat_id=chat_id, text=message)

    # парсим =w{lat},{lon}: weather -> hf
    match = re.search(r'^=w(-{0,1}\d{1,2}\.\d{1,6}),(-{0,1}\d{1,3}\.\d{1,6})',
                      parse_message)
    if match and mesg_to == str(my_id):
        mlat = match[1]
        mlon = match[2]
        print(f'{now} HFpager -> Weather: {mlat} {mlon}')
        bot.send_message(chat_id=chat_id,
                         text=(f'{now} HFpager -> {mesg_from} '
                               f'Weather in: {mlat} {mlon}'))
        weather = get_weather(mlat, mlon)
        pager_transmit(weather, mesg_from, 1)


def get_weather(lat, lon):
    url = ('https://api.openweathermap.org/data/2.5/onecall?'
           f'lat={lat}&lon={lon}&exclude=minutely,hourly&appid={owm_api_key}'
           '&lang=ru&units=metric')
    resp = requests.get(url)
    data = resp.json()
    weather = ''
    for day in data['daily'][:2]:
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
                    f'Вет:{wind_direct} {wind_speed:.0f}…{wind_gust:.0f}м/с '
                    f'{weather_cond} '
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
    now = date_time_now()
    print(f'{now} HFpager send to ID:{abonent_id} repeat:{repeat} '
          f'message:\n{message.strip()}')
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


bot = telebot.TeleBot(token)


@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message, f"""Привет, я HFpager Bot.
Я отправляю сообщения с шлюза {callsign} через HFpager ID:{my_id}\n
Как меня использовать:\n
`>blah blah blah` - отправит _blah blah blah_ на ID:{abonent_id}\n
`>123 blah blah blah` - отправит _blah blah blah_ на ID:_123_\n
`! blah blah blah` - ! в сообщении равносилен опции "Повторять до подтв."\n
`>123! blahblah` - отправка на ID:123 будет повторятся до подтверждения
""", parse_mode='markdown')


@bot.message_handler(func=lambda message: True)
def echo_message(message):
    now = date_time_now()
    # обрабатываем начинающиеся с >
    # print(message)
    if message.date > start_time:
        reg = re.compile(f'^({my_id})*>(.+)')
        match = re.match(reg, message.text)
        if match:
            short_text = shorten(message.text, width=25, placeholder="...")
            print(f'{now} Bot receive message: {short_text}')
            parse_for_pager(match.group(2), abonent_id)
            bot.send_message(chat_id=chat_id, text=f'Recepied: {short_text}')


if __name__ == "__main__":
    name = "WEB->HFpager"
    start_time = int(time.time())
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    to_radio.start()
    to_web.start()
    to_radio.join()
    to_web.join()
