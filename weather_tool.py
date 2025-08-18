from datetime import datetime

import aiohttp
from astrbot.core import AstrBotConfig
from astrbot.core.star import Context


class WeatherTool:

    def __init__(self, context: Context, config: AstrBotConfig, astrbotTool):
        self.context = context
        self.config = config
        self.astrbotTool = astrbotTool

        self.qweather_api_key = config.get("qweather_api_key", "")
    async def get_weather_from_api(self, request_loc):
        if not self.qweather_api_key:
            return self.weather_result('需要先设置天气接口api_key')

        session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
        async with session:

            geo_api_url = f'https://geoapi.qweather.com/v2/city/lookup?key={self.qweather_api_key}&number=1&location={request_loc}'
            async with session.get(geo_api_url) as response:
                geoapi_json = await response.json()

            if geoapi_json.get('error') and geoapi_json.get('error').get('status') == 400:
                return self.weather_result(f"{request_loc} 这个地点不存在，请检查后重试")
            elif geoapi_json.get('code') != '200':
                return self.weather_result("天气接口不可用")

            country = geoapi_json["location"][0]["country"]
            adm1 = geoapi_json["location"][0]["adm1"]
            adm2 = geoapi_json["location"][0]["adm2"]
            city_id = geoapi_json["location"][0]["id"]

            weather_json = {}
            # 请求现在天气api
            weather_base = 'https://devapi.qweather.com/v7/weather'

            now_weather_api_url = f'{weather_base}/now?key={self.qweather_api_key}&location={city_id}'
            async with session.get(now_weather_api_url) as response:
                weather_json['now'] = (await response.json()).get('now')

            # 请求预报天气api
            weather_forecast_api_url = f'{weather_base}/7d?key={self.qweather_api_key}&location={city_id}'
            async with session.get(weather_forecast_api_url) as response:
                weather_json['daily'] = (await response.json()).get('daily')
        return self.weather_result(weather_json, country, adm1, adm2)

    @staticmethod
    def weather_result(weather_json, country='', adm1='', adm2=''):
        return weather_json, country, adm1, adm2
    @staticmethod
    def compose_weather_message(weather_json, country, adm1, adm2):
        update_time = weather_json['now']['obsTime']
        try:
            update_time = datetime.fromisoformat(update_time).strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            update_time = weather_json['now']['obsTime']

        now_temperature = weather_json['now']['temp']
        now_feels_like = weather_json['now']['feelsLike']
        now_weather = weather_json['now']['text']
        now_wind_direction = weather_json['now']['windDir']
        now_wind_scale = weather_json['now']['windScale']
        now_humidity = weather_json['now']['humidity']
        now_precip = weather_json['now']['precip']
        now_visibility = weather_json['now']['vis']
        now_uvindex = weather_json['daily'][0]['uvIndex']
        max_len = 6

        message = (
            f"☁️{country}{adm1}{adm2} 实时天气☁️\n"
            f"⏰更新时间：{update_time}\n\n"
            f"🌡️{'当前温度：':　<{max_len}}{now_temperature}℃\n"
            f"🌡️{'体感温度：':　<{max_len}}{now_feels_like}℃\n"
            f"☁️{'天气：':　<{max_len}}{now_weather}\n"
            f"☀️{'紫外线指数：':　<{max_len}}{now_uvindex}\n"
            f"🌬️{'风向：':　<{max_len}}{now_wind_direction}\n"
            f"🌬️{'风力：':　<{max_len}}{now_wind_scale}级\n"
            f"💦{'湿度：':　<{max_len}}{now_humidity}%\n"
            f"🌧️{'降水量：':　<{max_len}}{now_precip}mm/h\n"
            f"👀{'能见度：':　<{max_len}}{now_visibility}km\n\n"
            f"☁️未来3天 {adm2} 天气：\n"
        )
        for day in weather_json['daily'][1:4]:
            date = '.'.join([i.lstrip('0') for i in day['fxDate'].split('-')[1:]])
            weather = day['textDay']
            max_temp = day['tempMax']
            min_temp = day['tempMin']
            uv_index = day['uvIndex']
            message += f'{date} {weather} 最高🌡️{max_temp}℃ 最低🌡️{min_temp}℃ ☀️紫外线:{uv_index}\n'

        return message.rstrip()
