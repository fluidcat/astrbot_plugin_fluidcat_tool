import json
import os
import traceback
import uuid
from datetime import datetime

import aiohttp
from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core import logger
from astrbot.core.message.components import Plain, Record
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav

from .stt import STT
from .oil_tool import OilTool
from .weather_tool import WeatherTool


@register(
    "astrbot_plugin_fluidcat_tool",
    "fluidcat",
    "fluidcat 工具",
    "1.0.0",
    "",
)
class FluidCatToolPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        self.context = context
        self.config = config
        self.weather_tool = WeatherTool(context, config, self)
        self.oil_tool = OilTool(context, config, self)
        self.stt = STT(context, config, self)
        self.config = config
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.llm_tool("get_weather")
    async def get_weather_tool(self, event, location: str):
        """当用户对某个城市或地区的天气情况感兴趣时，用于获取实时天气信息。
        Args:
            location(string): 省市区县的拼音
        """
        resp, *_ = await self.weather_tool.get_weather_from_api(location)
        return event.plain_result(
            resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
        )

    @filter.command("weather")
    async def get_weather_command(self, event: AstrMessageEvent, location: str):
        """当用户对某个城市或地区的天气情况感兴趣时，用于获取实时天气信息。
        Args:
            location(string): 省市区县的拼音
        """
        api_json, country, adm1, adm2 = await self.weather_tool.get_weather_from_api(location)
        if country:
            format_weather = self.compose_weather_message(api_json, country, adm1, adm2)
        else:
            format_weather = api_json

        yield event.plain_result(format_weather)

    @filter.llm_tool("current_oil_price_and_forecast")
    async def get_weather_tool(self, event):
        """查询当前92号汽油、95号汽油、98号汽油、柴油的油价信息和下轮油价调整预测信息。
        """
        return json.dumps(await self.oil_tool.get_oil_json(), ensure_ascii=False)

    @filter.command("oil")
    async def oil_command(self, event: AstrMessageEvent, province: str = None):
        """查询当前92号汽油、95号汽油、98号汽油、柴油的油价信息和下轮油价调整预测信息。
        Args:
            province(string): 省份
        """
        report = await self.oil_tool.get_daily_oil_report([x.strip() for x in province.split(",")] if province else [])

        yield event.plain_result(report)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def voice_to_text(self, event: AstrMessageEvent):
        """收到语音消息时，将语音转为文本
        """
        message_chain = event.get_messages()

        for idx, component in enumerate(message_chain):
            if isinstance(component, Record) and component.url:
                try:
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    output_path = os.path.join(temp_dir, str(uuid.uuid4()) + ".wav")
                    path = component.url.removeprefix("file://")

                    await tencent_silk_to_wav(path, output_path)
                    result = await self.stt.audio_acr(output_path, event.get_sender_id())
                    message_chain[idx] = Plain(result)
                    event.message_str += result
                    event.message_obj.message_str += result

                    event.set_extra("is_record_req", True)
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"语音转文本失败: {e}")
    
    @filter.on_decorating_result()
    async def text_to_vioce():
        """使用语音回复语音消息"""

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
