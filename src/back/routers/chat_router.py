from fastapi import Depends, APIRouter

from src.back.request_entity import Chat, JastId, EmptyRequest
from src.back.tools.tools import authentication, ok_response
from src.back.service import chat_service

cu = APIRouter(prefix="/chat")


@cu.post("/create")
async def create_chat(request: Chat, user_id=Depends(authentication)):
    """新建角色卡。导入场景复用此接口，靠 on_conflict 指定重名策略"""
    return ok_response(data=await chat_service.creat_user(request, user_id))


@cu.post("/get_info")
async def chat_info(request: JastId, user_id=Depends(authentication)):
    """获取指定角色卡的详情"""
    return ok_response(data=await chat_service.get_chat_info(request, user_id))


@cu.post("/list")
async def chat_list(request: EmptyRequest, user_id=Depends(authentication)):
    """获取当前用户'可见'的全部角色卡"""
    return ok_response(data=await chat_service.get_chat_list(user_id))


@cu.post("/update")
async def update_chat(request: Chat, user_id=Depends(authentication)):
    """更新角色卡.确保只有卡作者可以更新"""
    await chat_service.update_chat(request, user_id)
    return ok_response()


@cu.post("/delete")
async def delete_chat(request: JastId, user_id=Depends(authentication)):
    """删除角色卡"""
    return ok_response(data=await chat_service.delete_chat(request, user_id))
