from fastapi import Depends, APIRouter

from src.back.request_entity import JastId, EmptyRequest, Session, SessionInfo, BranchSwitch, BranchCreate
from src.back.tools.tools import authentication, ok_response
from src.back.service import session_service

su = APIRouter(prefix="/session")


@su.post("/create")
async def create_session(request: JastId, user_id=Depends(authentication)):
    return ok_response(data={"session_id": await session_service.creat(request, user_id)})


@su.post("/delete")
async def delete_session(request: JastId, user_id=Depends(authentication)):
    await session_service.delete(request, user_id)
    return ok_response()


@su.post("/list")
async def list_session(request: EmptyRequest, user_id=Depends(authentication)):
    return ok_response(await session_service.list_session(user_id))


@su.post("/update")
async def update_session(request: Session, user_id=Depends(authentication)):
    await session_service.update(request, user_id)
    return ok_response()


@su.post("/info")
async def get_session_info(request: SessionInfo, user_id=Depends(authentication)):
    return ok_response(data=await session_service.info(request, user_id))


@su.post("/branch/list")
async def list_branch(request: JastId, user_id=Depends(authentication)):
    """B02 列出会话的全部分支，附末条消息预览。
    branch 0 是会话创建时的主干，不在 session_branches 中登记，这里手动补上。"""
    b_list = await session_service.branch_list(request, user_id)
    print(b_list, "所有分支")
    return ok_response(data=b_list)


@su.post("/branch/switch")
async def switch_branch(request: BranchSwitch, user_id=Depends(authentication)):
    """B03 切换当前活跃分支。只改 sessions.current_branch_id，消息本身不动。"""
    await session_service.switch_branch(request, user_id)
    return ok_response(data={"current_branch_id": request.branch_id})


@su.post("/branch/create")
async def create_branch(request: BranchCreate, user_id=Depends(authentication)):
    """回退不删除任何消息：从 from_msg_id 处分配一个新分支号并切过去，
    后续消息以 from_msg_id 为 previous_id 挂在新分支上，原分支完整保留。
    from_msg_id 传 0 表示从会话开头重新开始。"""

    return ok_response(data={"branch_id": await session_service.create_branch(request, user_id), "last_msg_id": request.from_msg_id})

