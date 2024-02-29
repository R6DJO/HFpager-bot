import logging
from datetime import datetime
import requests

# Function get_weather: Fetches weather information using the OpenWeatherMap API
def get_weather(OWM_API_KEY, lat, lon):
    """Function get weater from OWM servers."""
    url = ('http://api.openweathermap.org/data/2.5/onecall?'
           f'lat={lat}&lon={lon}&exclude=minutely,hourly&appid={OWM_API_KEY}'
           '&lang=ru&units=metric')
    resp = requests.get(url, timeout=10)
    data = resp.json()

    # Initialize an empty string for storing the weather information
    weather = ''

    # Check if the request was successful by checking if the 'cod' key is present
    if 'cod' in data:
        error = data['message']
        logging.error('HFpager get weather error: %s', error)
        return 'Error in weather'
    else:
        # Iterate through the first three days of weather data
        for day in data['daily'][:3]:
            # Format the date and extract the minimum and maximum temperatures
            date = datetime.fromtimestamp(day['dt']).strftime('%m/%d')
            temp_min = day['temp']['min']
            temp_max = day['temp']['max']

            # Extract the cloud coverage, precipitation probability, and wind data
            clouds = day['clouds']
            pop = day['pop']*100
            wind_speed = day['wind_speed']
            wind_gust = day['wind_gust']
            weather_cond = day['weather'][0]['description']

            # Convert the wind direction to a human-readable format
            wind_direct = get_wind_direction(day['wind_deg'])

            # Combine the extracted data into a single string
            weather += (f'{date} '
                        f'Темп:{temp_min:.0f}…{temp_max:.0f}°C '
                        f'Вет:{wind_direct} {wind_speed:.0f}…'
                        f'{wind_gust:.0f}м/с {weather_cond} '
                        f'Обл:{clouds}% Вер.ос:{pop:.0f}% ')

            # If rain or snow data is available, append it to the string
            if 'rain' in day:
                rain = day['rain']
                weather += f'Дождь:{rain:.1f}мм '
            if 'snow' in day:
                rain = day['snow']
                weather += f'Снег:{rain:.1f}мм '

            # Add a newline character to separate the entries
            weather += '\n'
        
        return weather


# Function get_wind_direction: Converts wind direction degrees to a human-readable format
def get_wind_direction(deg):
    """Function convert wind direction."""
    wind = ''
    direction = ['С ', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
    for i in range(0, 8):
        step = 45.
        minimum = i*step - 45/2.
        maximum = i*step + 45/2.

        # Convert the wind degree value to the appropriate direction index
        if i == 0 and deg > 360-45/2.:
            deg = deg - 360
        if minimum <= deg  <= maximum:
            wind = direction[i]
            break
    return wind


# Function get_speed: Converts wind speed to a user-friendly format
def get_speed(speed):
    """Function convert userfrendly speed."""
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
    return sp_data[speed] if speed in sp_data else 0
