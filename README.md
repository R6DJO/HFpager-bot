# HFpager-bot

This is Telegram-bot for HFpagerNG  
  
Register bot on BotFather
Install ```termux``` app from F-Droid or Google Play  
Download ```bot4``` file to you smartphone and edit:
```
token = 'ТОКЕН'
chat_id = ИД_ЧАТА
my_id = МОЙ_ИД
abonent_id = ИД_ПО_УМОЛЧАНИЮ
```
After install python and modules and run Bot

```bash
pkg upgrade  
pkg install python  
pip install pytelegramapi  
chmod +x bot4
nohup python -u bot4 >> bot.log 2>&1 &
tail -f bot4.log

```

Send a message to the chat and the bot will pass it with HFpager to ID: ИД_ПО_УМОЛЧАНИЮ  
Send ```>123 blah blah blah``` and the bot will pass it with HFpager to ID: 123
