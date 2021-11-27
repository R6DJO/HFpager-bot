#!/bin/python
# -*- coding: utf-8 -*-
import re
import telebot
import time
import subprocess
import os
from threading import Thread
from datetime import datetime
from config import abonent_id, chat_id, my_id, token


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
        date = datetime.now()
        # msg_dir = '/data/data/com.termux/files/home/storage/shared/
        # Documents/HFpager/' + date.strftime("%Y-%m-%d") + '.MSG/'
        date_now = date.strftime("%Y-%m-%d")
        msg_dir = f'/storage/emulated/0/Documents/HFpager/{date_now}.MSG/'
        nowt = time.time()
        if os.path.isdir(msg_dir):
            try:
                for filename in os.listdir(msg_dir):
                    path_file = os.path.join(msg_dir, filename)
                    if os.stat(path_file).st_ctime > nowt - 5:
                        mesg = open(msg_dir + filename, 'r',
                                    encoding='cp1251')
                        text = mesg.read()
                        parse_file(filename, text)
            except Exception as ex:
                now = date_time_now()
                print(f'{now} HFpager send/receive message error: {ex}')
        time.sleep(5)


def parse_file(filename, text):
    if re.match(r'\d{6}-RO-0.*_' + str(my_id) + '.TXT', filename):
        now = date_time_now()
        print(f'{now} HFpager private message received: {text}')
        bot.send_message(chat_id=chat_id,
                         text=f'Private message received: {text}')
    elif re.match(r'\d{6}-RO-[2,3].*_' + str(my_id) + '.TXT', filename):
        now = date_time_now()
        print(f'{now} HFpager private message received and acknowledgment '
              f'sent: {text}')
        bot.send_message(chat_id=chat_id, text='Private message received '
                         f'and acknowledgment sent: {text}')
    elif re.match(r'\d{6}-R', filename):
        now = date_time_now()
        print(f'{now} HFpager message intercepted: {text}')
        bot.send_message(chat_id=chat_id, text=f'Message intercepted: {text}',
                         disable_notification=True)
    elif re.match(r'\d{6}-S[1-9]-\dP', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent and acknowledgment '
              f'received: {text}')
        bot.send_message(chat_id=chat_id, text='Message sent and '
                         f'acknowledgment received: {text}',
                         disable_notification=True)
    elif re.match(r'\d{6}-S[1-9]-\dN', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent and not '
              f'acknowledgment received: {text}')
        bot.send_message(chat_id=chat_id, text='Message sent and not '
                         f'acknowledgment received: {text}',
                         disable_notification=True)
    elif re.match(r'\d{6}-S[1-9]-\d0', filename):
        now = date_time_now()
        print(f'{now} HFpager message sent: {text}')
        bot.send_message(chat_id=chat_id, text=f'Message sent: {text}',
                         disable_notification=True)


def send_pager(message, abonent_id):
    # сообщение >[id][text] -> [id]
    if re.match(r'^>(\d{1,5})', message):
        abonent_id = re.match(r'^>(\d{1,5})', message).group(1)
        message = re.split(r'((?<=^>)\d{1,}\s*)', message, maxsplit=1)[-1]
    # сообщение >[text] -> [abonent_id]
    elif re.match(r'^>', message):
        message = re.split(r'^>\s*', message, maxsplit=1)[-1]
    # сообщение [text] -x->
    else:
        return 1, 1
    # сообщение начинается с ! -> повторяем
    if re.match(r'^!', message):
        repeat = 1
        message = re.split(r'^!\s*', message, maxsplit=1)[-1]
    else:
        repeat = 0
    now = date_time_now()
    print(f'{now} HFpager send to ID: {abonent_id} repeat:{repeat} '
          f'message: {message}')
    proc = subprocess.Popen(
        f'am start --user 0 '
        f'-n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity '
        f'-a "android.intent.action.SEND" '
        f'--es "android.intent.extra.TEXT" "{message}" -t "text/plain" '
        f'--ei "android.intent.extra.INDEX" "{abonent_id}" '
        f'--es "android.intent.extra.SUBJECT" "Flags:1,{repeat}"',
        stdout=subprocess.PIPE, shell=True)
    out = proc.stdout.read()


bot = telebot.TeleBot(token)


@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message, f"""Привет, я HFpager Bot.
Я отправляю сообщения с шлюза UB9WMS через HFpager ID:{my_id}\n
Как меня использовать:\n
`>blah blah blah` - отправит _blah blah blah_ на ID:{abonent_id}\n
`>123 blah blah blah` - отправит _blah blah blah_ на ID:_123_\n
`! blah blah blah` - ! в сообщении раносилен опции "Повторять до подтв."\n
`>123! blahblah` - отправка на ID:123 будет повторятся до подтверждения
""", parse_mode='markdown')


@bot.message_handler(func=lambda message: True)
def echo_message(message):
    now = date_time_now()
    print(f'{now} Bot receive message: {message.text}')
    send_pager(message.text, abonent_id)


if __name__ == "__main__":
    name = "WEB->HFpager"
    to_radio = Thread(target=bot_polling)
    to_web = Thread(target=hfpager_bot)
    to_radio.start()
    to_web.start()
    to_radio.join()
    to_web.join()
