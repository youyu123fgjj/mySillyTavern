from fastapi import APIRouter, Depends

from src.back.request_entity import UsageQuery, LogQuery
from src.back.tools.tools import ok_response, authentication
from src.back.service import log_service

lr = APIRouter(prefix="/log")


@lr.post("/usage")
async def usage(request: UsageQuery, user_id=Depends(authentication)):
    """用量统计。total_requests 已可用，token 相关字段待 dsh 集成后才有数据"""
    return ok_response(data=await log_service.usage(request, user_id))


@lr.post("/list")
async def log_list(request: LogQuery, user_id=Depends(authentication)):
    """分页查询自己的调用日志，按时间倒序"""
    return ok_response(data=await log_service.log_list(request, user_id))
