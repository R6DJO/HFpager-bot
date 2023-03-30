import requests
import logging
from datetime import datetime

from config import owm_api_key


def get_weather(lat, lon):
    url = ('http://api.openweathermap.org/data/2.5/onecall?'
           f'lat={lat}&lon={lon}&exclude=minutely,hourly&appid={owm_api_key}'
           '&lang=ru&units=metric')
    resp = requests.get(url)
    data = resp.json()
    weather = ''
    if 'cod' in data:
        error = data['message']
        logging.error(f'HFpager get weather error: {error}')
        # bot.send_message(chat_id=chat_id,
        #                  text=f'HFpager get weather error: {error}')
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


def get_speed(speed):
    sp_data = {
        '1': 1,
        '1.5': 1,
        '2': 4,
        '3': 16,
        '4': 32,
        '5': 4,
        '5.9': 4,
        '6': 4,
        '23': 16,
        '46': 32,
        '47': 32
    }
    return sp_data[speed] if speed in sp_data.keys() else 0
