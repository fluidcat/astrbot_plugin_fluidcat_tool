import json
from datetime import datetime

import aiohttp
from astrbot.core import AstrBotConfig
from astrbot.core.star import Context

from .daily_cache import daily_cache


class OilTool:
    def __init__(self, context: Context, config: AstrBotConfig, astrbotTool):
        self.context = context
        self.config = config
        self.astrbotTool = astrbotTool

        self.oil_report_provinces = config.get("oil_report_provinces", "")
        self.sub_provider = config.get("sub_provider_id", "")
        self.system_prompt = '总结文案，输出下次油价调整时间以及预测涨跌详细信息(元/吨和元/升)。输出非md文本：{"next_time": ' \
                             '"时间"，"forecast"："上调xxxx或者下调xxxx或者搁浅"}'

    async def get_daily_oil_report(self, provinces: list = None):
        provinces = provinces if provinces else self.oil_report_provinces

        list_json = await self.get_oil_data()
        forecast = await self.get_oil_forecast()
        oil = [[item.get(p) for p in provinces] for item in list_json]

        _92, _95, _98, _cy = oil
        width = 7
        blank = '\u2002'
        now = datetime.now()
        msg = (
            f"🛢️油价快报  {now.month}月{now.day}日🛢️\n"
            f"　　　{'92# ':{blank}<{width}}{'95# ':{blank}<{width}}{'98# ':{blank}<{width}}柴油\n"
        )
        for i, p in enumerate(provinces):
            msg += f"{p}　{_92[i]:{blank}<{width}}{_95[i]:{blank}<{width}}{_98[i]:{blank}<{width}}{_cy[i]}\n"

        if forecast.get('next_time', ''):
            msg += f"\n下次调价：{forecast.get('next_time', '')}\n"

            if forecast.get('forecast', ''):
                msg += f"目前预测：{forecast.get('forecast', '')}\n"

        return msg.strip()

    async def get_oil_json(self):
        list_json = await self.get_oil_data()
        forecast = await self.get_oil_forecast()
        return {"province_price": list_json, "forecast": forecast}

    @daily_cache
    async def get_oil_data(self):
        all_types = ['92', '95', '98', 'chaiyou']
        data = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for oil_type in all_types:
                async with session.get("https://api.guiguiya.com/api/youjia?region=" + oil_type) as resp:
                    resp = await resp.json()
                if resp.get('code', 0) == 200 and resp.get('data', None):
                    data.append(resp.get('data'))
                else:
                    data.append({})
        return data

    @daily_cache
    async def get_oil_forecast(self):
        forecast_url = "https://r.jina.ai/http://www.qiyoujiage.com/"
        headers = {
            'Accept': 'application/json',
            'X-Target-Selector': '#rightTop',
            'X-Retain-Images: ': 'none'
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(forecast_url, headers=headers) as resp:
                forecast_resp = await resp.json()
        forecast_content = ''
        if forecast_resp.get('code', 0) == 200 and forecast_resp.get('data', None):
            forecast_content = forecast_resp.get('data', {}).get('content', '')
        if not forecast_content:
            return {}

        provider = self.context.get_provider_by_id(self.sub_provider)
        llm_response = await provider.text_chat(prompt=forecast_content, system_prompt=self.system_prompt)

        try:
            return json.loads(llm_response.completion_text.strip())
        except Exception as e:
            return {}
