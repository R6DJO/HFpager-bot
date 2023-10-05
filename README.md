# HFpager-bot

This is Telegram-bot for HFpagerNG  
  
Register bot on BotFather
Install ```termux``` app from F-Droid or Google Play  
Download ```bot4```
Create ```config.py``` from ```config.py.sample```file to you smartphone and edit:
```
token = 'ТОКЕН'
chat_id = ИД_ЧАТА
beacon_chat_id = ИД_ЧАТА_МАЯКОВ
my_id = ИД_МОЕГО_ПЕЙДЖЕРА
abonent_id = ИД_ПЕЙДЖЕРА_КОРРЕСПОНДЕНТА_ПО_УМОЛЧАНИЮ
owm_api_key = 'АПИ_КЕЙ_ОВМ'
callsign = 'ПОЗЫВНОЙ_ШЛЮЗА'
log_level = 'DEBUG'
system = 'LINUX' # ANDROID | LINUX
hfpager_path = 'ГДЕ_ЛЕЖИТ_КВПЕЙДЖЕР'
msg_end = 'ЧТО_ДОБАВЛЯЕМ_В_КОНЦЕ_СООБЩЕНИЯ'
<<<<<<< HEAD
=======
geo_delta = СМЕЩЕНИЕ_КООРДИНАТ
>>>>>>> fb38d8a9720fe96d198a8de958be05d3d46942a0
```


After install python and modules and run Bot
On Android:
```bash
cd ~/
pkg upgrade
pkg install python
pkg install git
termux-setup-storage
termux-wake-lock
```
On Android or Linux:
```
git clone https://github.com/R6DJO/HFpager-bot.git
cd HFpager-bot
pip install -r requirements.txt
nohup python bot4.py &
tail -f bot.log
```

Send a message ```blah blah blah``` to the chat and the bot will pass it with HFpager to ID: ИД_ПО_УМОЛЧАНИЮ  
Send ```>123 blah blah blah``` and the bot will pass it with HFpager to ID: 123  
Send ```! blah blah blah``` and the HFpager repeat send until ACK
Received by HFpagerNG messages are forwarded to the chat.

To use with HFpager Demo change ```'am start --user 0 -n ru.radial.nogg.hfpager/ru.radial.full.hfpager.MainActivity -a '``` to  
```'am start --user 0 -n ru.radial.demo.hfpager/ru.radial.full.hfpager.MainActivity -a '``` in 74 line of bot4
