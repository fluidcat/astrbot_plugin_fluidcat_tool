import json
import mimetypes
from pathlib import Path

import aiohttp
from astrbot.core import AstrBotConfig
from astrbot.core.star import Context


class STT:

    def __init__(self, context: Context, config: AstrBotConfig, astrbotTool):
        self.context = context
        self.config = config
        self.astrbotTool = astrbotTool

    async def audio_acr(self, file_path: str, session_id: str) -> str:
        upload_file_id = await self.upload_file(file_path, session_id)

        url = 'https://api.dify.ai/v1/workflows/run'
        headers = {"Authorization": f"Bearer app-WOBX22g8QogVRSfjOZnqAaLa", "Content-Type": "application/json"}
        payload = json.dumps({
            "inputs": {"audio": {"type": "audio", "transfer_method": "local_file", "upload_file_id": upload_file_id}},
            "user": session_id,
            "response_mode": "blocking",
            "files": [],
        })
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, headers=headers, data=payload) as resp:
                if resp.status == 200:
                    ocr_ret = await resp.json()
                else:
                    return ''
        return ocr_ret.get('data', {}).get('outputs', {}).get('text', '')

    async def upload_file(self, file_path: str, session_id: str):
        headers = {"Authorization": f"Bearer app-WOBX22g8QogVRSfjOZnqAaLa"}

        file_name = Path(file_path).name
        if file_path and (mime_types := mimetypes.guess_type(file_name)):
            mime_type, _ = mime_types
            filename, content_type = file_name, mime_type
        else:
            filename, content_type = file_name, "application/octet-stream"

        with open(file_path, "rb") as f:
            file = f.read()

        form_data = aiohttp.FormData()
        form_data.add_field("user", session_id)
        form_data.add_field("file", file, filename=filename, content_type=content_type)

        url = "https://api.dify.ai/v1/files/upload"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form_data) as resp:
                resp_json = await resp.json()

        return resp_json.get("id", "")
