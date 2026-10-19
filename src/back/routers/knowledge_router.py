from fastapi import Depends, APIRouter

from src.back.request_entity import EmptyRequest, Knowledge, JastId, KnowledgeItem, TwoId
from src.back.tools.tools import authentication, ok_response
from src.back.service import knowledge_service

kr = APIRouter(prefix="/knowledge")


@kr.post("/create")
async def knowledge_create(request: Knowledge, user_id=Depends(authentication)):
    """新建知识库。导入场景复用此接口，靠 on_conflict 指定重名策略"""
    return ok_response(data=await knowledge_service.crate(request, user_id))


@kr.post("/delete")
async def delete(request: JastId, user_id=Depends(authentication)):
    await knowledge_service.delete(request, user_id)
    return ok_response()


@kr.post("/get_info")
def info(request: JastId, user_id=Depends(authentication)):
    """知识库详情，含全部条目。前端可直接把返回的 data 存为文件完成导出"""
    return ok_response(data=knowledge_service.get_info(request, user_id))


@kr.post("/get_list")
async def get_list(request: EmptyRequest, user_id=Depends(authentication)):
    return ok_response(data={"items": await knowledge_service.get_list(user_id)})


@kr.post("/update_base")
async def update_base(request: Knowledge, user_id=Depends(authentication)):
    await knowledge_service.update_base(request, user_id)
    return ok_response()


@kr.post("/update_item")
async def update_item(request: KnowledgeItem, user_id=Depends(authentication)):
    await knowledge_service.update_item(request)
    return ok_response()


@kr.post("/delete_item")
async def delete_item(request: JastId, user_id=Depends(authentication)):
    await knowledge_service.delete_item(request, user_id)
    return ok_response()


@kr.post("/add_item")
async def add_item(request: KnowledgeItem, user_id=Depends(authentication)):
    return ok_response(msg=await knowledge_service.add_item(request, user_id))


@kr.post("/link")
async def make_link(request: TwoId, user_id=Depends(authentication)):
    """id1 为角色卡 id，id2 为知识库 id。
    只有卡作者能挂载知识库，且只能挂自己的库或已公用的库"""
    await knowledge_service.make_link(request, user_id)
    return ok_response()


@kr.post("/unlink")
async def delete_link(request: TwoId, user_id=Depends(authentication)):
    await knowledge_service.delete_link(request, user_id)
    return ok_response()
