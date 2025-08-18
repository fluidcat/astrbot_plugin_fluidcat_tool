import json
import os
from pathlib import Path
import shutil
import traceback
import uuid

import aiohttp

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core import logger
from astrbot.core.message.components import Music, Plain, Record
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.tencent_record_helper import tencent_silk_to_wav
from .oil_tool import OilTool
from .stt import STT
from .tts import TTS
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
        self.tts = TTS(context, config, self)
        self.enable_tts = config.get("enable_tts", False)
        self.enable_stt = config.get("enable_stt", False)
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
        return resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)

    @filter.command("weather")
    async def get_weather_command(self, event: AstrMessageEvent, location: str):
        """当用户对某个城市或地区的天气情况感兴趣时，用于获取实时天气信息。
        Args:
            location(string): 省市区县的拼音
        """
        api_json, country, adm1, adm2 = await self.weather_tool.get_weather_from_api(location)
        if country:
            format_weather = self.weather_tool.compose_weather_message(api_json, country, adm1, adm2)
        else:
            format_weather = api_json

        yield event.plain_result(format_weather)

    @filter.llm_tool("current_oil_price_and_forecast")
    async def current_oil_price_and_forecast(self, event):
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

    @filter.command("rmmem")
    async def rm_memory(self, event: AstrMessageEvent):
        """删除当前记忆
        """
        await self.context.conversation_manager.delete_conversation(event.unified_msg_origin)

        yield event.plain_result('已删除记忆')

    @filter.command("tts1")
    async def tts_command(self, event: AstrMessageEvent, on_off:str=None):
        """控制TTS语音回复服务的开关状态
        Args: 
            on_off(string): 开关值(支持on/off, 1/0, true/false, enable/disable, 开/关等)
        """
        if on_off is not None:
            # 定义开关关键词（集合提升查询效率）
            enable = {'on', '1', 'true', 'enable', 'up', 'start', 'yes', 'y', '开'}
            disable = {'off', '0', 'false', 'disable', 'down', 'stop', 'no', 'n', '关'}
            
            # 处理数字和字符串输入
            try:
                self.enable_tts = float(on_off) > 0
            except ValueError:
                lower_val = on_off.lower()
                if lower_val in enable:
                    self.enable_tts = True
                elif lower_val in disable:
                    self.enable_tts = False
                else:
                    yield event.plain_result(f"参数错误: {on_off} (可用: on/off, 1/0等)")
                    return
            
            # 保存配置
            self.config.update(enable_tts=self.enable_tts)
            self.config.save_config()

            yield event.plain_result(f"TTS服务已{'开启' if self.enable_tts else '关闭'}")
    
    @filter.command("music")
    async def get_music(self, event: AstrMessageEvent, keyword:str):
        """点歌服务
        Args:
            keyword(string): 点歌搜索词
        """
        api = f'https://api.cenguigui.cn/api/mg_music/?msg={keyword}&n=1&type=json'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api) as resp:
                    resp.raise_for_status()
                    ret_json = await resp.json()
                    ret_json = ret_json.get('data', {})
        except BaseException:
            yield event.plain_result("点歌服务暂时不可用")
        
        if not ret_json.get("music_url"):
            yield event.plain_result(f"搜索不到音乐：{keyword}")

        title = ret_json.get("title")
        singer = ret_json.get("singer")
        url = ret_json.get("link")
        music_url = ret_json.get("music_url")
        cover_url = ret_json.get("cover")
        lyric = ret_json.get("lrc_url")

        xml = f"""<appmsg appid="wx485a97c844086dc9" sdkver="0"><title>{title}</title><des>{singer}</des>
        <action>view</action><type>3</type><showtype>0</showtype><content/><url>{url}</url><dataurl>{music_url}</dataurl>
        <lowurl>{url}</lowurl><lowdataurl>{music_url}</lowdataurl><recorditem/><thumburl>{cover_url}</thumburl>
        <messageaction/><laninfo/><extinfo/><sourceusername/><sourcedisplayname/><songlyric>{lyric}</songlyric>
        <commenturl/><appattach><totallen>0</totallen><attachid/><emoticonmd5/><fileext/><aeskey/></appattach>
        <webviewshared><publisherId/><publisherReqId>0</publisherReqId></webviewshared><weappinfo><pagepath/><username/>
        <appid/><appservicetype>0</appservicetype></weappinfo><websearch/><songalbumurl>{cover_url}</songalbumurl>
        </appmsg>"""

        music = Music()
        music.audio = music_url
        music.url = url
        music.image = cover_url
        music.title = title
        music.content = xml
        yield event.chain_result([music])
        


    @filter.command("stt1")
    async def stt_command(self, event: AstrMessageEvent, on_off:str=None):
        """控制STT语音回复服务的开关状态
        Args:
            on_off(string): 开关值(支持on/off, 1/0, true/false, enable/disable, 开/关等)
        """
        if on_off is not None:
            # 定义开关关键词（集合提升查询效率）
            enable = {'on', '1', 'true', 'enable', 'up', 'start', 'yes', 'y', '开'}
            disable = {'off', '0', 'false', 'disable', 'down', 'stop', 'no', 'n', '关'}
            
            # 处理数字和字符串输入
            try:
                self.enable_stt = float(on_off) > 0
            except ValueError:
                lower_val = on_off.lower()
                if lower_val in enable:
                    self.enable_stt = True
                elif lower_val in disable:
                    self.enable_stt = False
                else:
                    yield event.plain_result(f"参数错误: {on_off} (可用: on/off, 1/0等)")
                    return
            
            # 保存配置
            self.config.update(enable_stt=self.enable_stt)
            self.config.save_config()

            event.clear_result

            yield event.plain_result(f"STT服务已{'开启' if self.enable_stt else '关闭'}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def voice_to_text(self, event: AstrMessageEvent):
        """收到语音消息时，将语音转为文本
        """
        if not self.enable_stt:
            return
        message_chain = event.get_messages()

        for idx, component in enumerate(message_chain):
            if isinstance(component, Record) and component.url:
                try:
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    output_path = os.path.join(temp_dir, str(uuid.uuid4()) + ".wav")
                    path = component.url.removeprefix("file://")

                    await tencent_silk_to_wav(path, output_path)
                    result = await self.stt.audio_acr(output_path, event.get_sender_id())
                    logger.info(f"fluidcat voice_to_text result: {result}")
                    if not result:
                        return
                    message_chain[idx] = Plain(result)
                    event.message_str += result
                    event.message_obj.message_str += result

                    event.set_extra("is_record_req", True)
                    # 完成消息处理流程后清理临时文件
                    self.temp_file_clean(event, [path, output_path])
                except BaseException as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"语音转文本失败: {e}")
    
    @filter.on_decorating_result()
    async def text_to_vioce(self, event: AstrMessageEvent):
        """使用语音回复语音消息"""
        if not self.enable_tts:
            return
        if event.get_extra("is_record_req"):
            result = event.get_result()
            for idx, component in enumerate(result.chain):
                if isinstance(component, Plain):
                    file_path = await self.tts.textToVoice(component.text)
                    logger.debug(f"fluidcat text_to_vioce result: {file_path}")
                    result.chain.append(Record.fromFileSystem(file_path))

                    # 完成消息处理流程后清理临时文件
                    self.temp_file_clean(event, [file_path])
    
    def temp_file_clean(self, event: AstrMessageEvent, temps:list=None):
        """完成消息处理流程后清理临时文件"""
        clean_sets = event.get_extra("clean_sets") or []

        # 添加文件
        if temps:
            for t in temps:
                clean_sets.append(t)
            event.set_extra("clean_sets", clean_sets)
            return
        
        # temps没有值，则清理event中的临时文件
        if not clean_sets:
            return
        for file_path in clean_sets:
            try:
                path = Path(file_path)                
                if not path.exists():
                    continue                
                if path.is_file():
                    path.unlink()  # 删除文件
                elif path.is_dir():
                    shutil.rmtree(path)  # 递归删除目录 
            except Exception as e:
                continue
        
        

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        # 完成消息处理流程后清理临时文件
        self.temp_file_clean(event)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
