"""TTS — edge-tts 文本转语音"""

import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"


async def synthesize(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)
