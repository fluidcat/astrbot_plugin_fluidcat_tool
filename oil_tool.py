import asyncio
import json
from datetime import datetime

import aiohttp
from astrbot.core import AstrBotConfig, logger
from astrbot.core.star import Context
from lxml import etree

from .daily_cache import daily_cache


class OilTool:
    def __init__(self, context: Context, config: AstrBotConfig, astrbotTool):
        self.context = context
        self.config = config
        self.astrbotTool = astrbotTool

        self.oil_report_provinces = config.get("oil_report_provinces", "")
        self.sub_provider = config.get("sub_provider_id", "")
        self.system_prompt = '重要：输出前检查——若包含```json或```，直接删除后再输出；' \
                             '总结文案，输出下次油价调整时间以及预测涨跌详细信息(元/吨和元/升)。输出非md文本：{"next_time": ' \
                             '"时间"，"forecast"："上调xxxx或者下调xxxx或者搁浅"}'

    async def get_daily_oil_report(self, provinces: list = None):
        provinces = provinces if provinces else self.oil_report_provinces

        price_json = await self.jina_oil_data()
        forecast = await self.get_oil_forecast()
        oil = [[price_json.get(item, {}).get(p) for p in provinces] for item in ["92", "95", "98", "chaiyou"]]

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
        price_json = await self.jina_oil_data()
        forecast = await self.get_oil_forecast()
        return {"province_price": price_json, "forecast": forecast}

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
    async def jina_oil_data(self):
        urls = {
            "92": "http://www.qiyoujiage.com/92.shtml",
            "95": "http://www.qiyoujiage.com/95.shtml",
            "98": "http://www.qiyoujiage.com/98.shtml",
            "chaiyou": "http://www.qiyoujiage.com/chaiyou.shtml",
        }
        data = {}
        provider = self.context.get_provider_by_id(self.sub_provider)
        system_prompt = '重要：输出前检查——若包含```json或```，直接删除后再输出；' \
                        '整理出所有城市油价数据,输出无任何markdown语法的无换行的json。' \
                        '严格按照格式输出：{"北京": 6.84,"上海": 6.81,...}'
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        header = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Host": "www.qiyoujiage.com",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1"
        }

        async def generate_json(_rating, _url):
            retry = 1
            while retry <= 3:
                try:
                    async with session.get(_url, headers=header) as resp:
                        html = await resp.text()
                    html.replace('</td>', ',</td>').replace('</tr>', ';</tr>')
                    root_elem = etree.HTML(html).xpath("//table")
                    inner_text = root_elem and root_elem[0].xpath("string(.)").replace(',;', ';')
                    logger.debug(f"解析「{_rating}」html 成功：{inner_text}")
                    llm_response = await provider.text_chat(prompt=inner_text, system_prompt=system_prompt)
                    llm_text = llm_response.completion_text.strip().removeprefix("```json").removesuffix("```").strip()
                    logger.debug(f"使用「{provider.meta().id}」生成「{_rating}」json 完成：{llm_text}")
                    data[_rating] = json.loads(llm_text)
                    break
                except Exception as ex:
                    logger.warning(f"rating「{_rating}」，retry：{retry}，generate_json error: {ex}")
                    retry += 1

        task = []
        for rating, url in urls.items():
            task.append(generate_json(rating, url))
        await asyncio.gather(*task)
        await session.close()

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
            return None

        provider = self.context.get_provider_by_id(self.sub_provider)
        llm_response = await provider.text_chat(prompt=forecast_content, system_prompt=self.system_prompt)

        try:
            llm_text = llm_response.completion_text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(llm_text)
        except Exception as e:
            return {}
