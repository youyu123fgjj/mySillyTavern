from fastapi import Depends, APIRouter
from fastapi.responses import StreamingResponse

from src.back.tools.tools import authentication
from src.back.request_entity import Dialogue
from src.back.service.message_service import dialogue

mu = APIRouter(prefix="/message")


@mu.post("/dialogue")
async def router_dialogue(request: Dialogue, user_id=Depends(authentication)):
    """
    请求模型获取回复
    :return: 流式生成器
    """
    return StreamingResponse(await dialogue(request, user_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
