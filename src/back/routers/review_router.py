from uuid import uuid4
from fastapi import Depends, APIRouter

from src.back.SQLiteConnectionPool import get_connection, transaction
from src.back.request_entity import ReviewApply, ReviewAudit, EmptyRequest
from src.back.tools.tools import authentication, admin_authentication, ok_response

rr = APIRouter(prefix="/review")

# 审核目标类型 -> (表名, 所属人字段)
TARGET_TABLES = {
    "character": "characters",
    "knowledge_base": "knowledge_bases",
}


async def check_target(target_type, target_id, user_id, conn):
    """校验目标类型合法、目标存在且申请人为创建者，返回当前 visibility"""
    table = TARGET_TABLES.get(target_type)
    if table is None:
        raise RuntimeError("审核目标类型非法，仅支持 character 或 knowledge_base！")
    row = conn.execute(f"SELECT visibility FROM {table} WHERE id=(?) AND user_id=(?)",
                       (target_id, user_id)).fetchone()
    if row is None:
        raise RuntimeError("目标不存在，或只有创建者才能申请转为公用！")
    return row[0]


@rr.post("/apply")
async def apply_public(request: ReviewApply, conn=Depends(get_connection), user_id=Depends(authentication)):
    """创建者申请将角色卡或知识库转为公用"""
    with transaction(conn):
        if check_target(request.target_type, request.target_id, user_id, conn) == "public":
            raise RuntimeError("该目标已是公用状态，无需申请！")

        old = conn.execute("SELECT status FROM public_reviews WHERE target_type=(?) AND target_id=(?)",
                           (request.target_type, request.target_id)).fetchone()
        if old is None:
            conn.execute("INSERT INTO public_reviews(id, target_type, target_id, user_id) VALUES (?, ?, ?, ?)",
                         (str(uuid4()), request.target_type, request.target_id, user_id))
        elif old[0] == "pending":
            raise RuntimeError("该目标已在审核中，请等待审核结果！")
        else:
            # 曾被驳回，重新申请：重置状态、清空告警与申请时间
            conn.execute("UPDATE public_reviews SET status='pending', warning=NULL, approved_at=NULL, "
                         "applied_at=CURRENT_TIMESTAMP WHERE target_type=(?) AND target_id=(?)",
                         (request.target_type, request.target_id))
    return ok_response()


@rr.post("/status")
async def review_status(request: ReviewApply, conn=Depends(get_connection), user_id=Depends(authentication)):
    """创建者查询自己提交的审核状态与结果"""
    await check_target(request.target_type, request.target_id, user_id, conn)
    row = conn.execute("SELECT status, warning, applied_at, approved_at FROM public_reviews "
                       "WHERE target_type=(?) AND target_id=(?)",
                       (request.target_type, request.target_id)).fetchone()
    if row is None:
        raise RuntimeError("该目标没有审核记录！")
    return ok_response(data={
        "target_type": request.target_type,
        "target_id": request.target_id,
        "status": row[0],        # pending 待审核 / approved 通过 / rejected 驳回
        "warning": row[1],       # 驳回原因，仅 rejected 时非空
        "applied_at": row[2],
        "approved_at": row[3],   # 通过时间，仅 approved 时非空
    })


@rr.post("/target_info")
async def target_info(request: ReviewApply, conn=Depends(get_connection), admin=Depends(admin_authentication)):
    """管理员查看待审目标的完整详情（角色卡/知识库），仅本机可访问，不妨碍审核前了解内容"""
    if request.target_type == "character":
        info = conn.execute("SELECT id, user_id, name, system_prompt, opening_remarks, visibility, "
                            "temperature, max_tokens FROM characters WHERE id=(?)", (request.target_id,)).fetchone()
        if info is None:
            raise RuntimeError("角色卡不存在！")
        kbs = conn.execute("SELECT kb.id, kb.name, kb.visibility FROM knowledge_bases kb "
                           "JOIN character_kb_relations r ON r.kb_id=kb.id WHERE r.character_id=(?)",
                           (request.target_id,)).fetchall()
        return ok_response(data={
            "id": info[0], "user_id": info[1], "name": info[2], "system_prompt": info[3],
            "opening_remarks": info[4], "visibility": info[5], "temperature": info[6], "max_tokens": info[7],
            "knowledge_bases": [{"id": i[0], "name": i[1], "visibility": i[2]} for i in kbs],
        })
    if request.target_type == "knowledge_base":
        base = conn.execute("SELECT id, user_id, name, description, visibility FROM knowledge_bases WHERE id=(?)",
                            (request.target_id,)).fetchone()
        if base is None:
            raise RuntimeError("知识库不存在！")
        items = conn.execute("SELECT id, title, content FROM knowledge_items WHERE kb_id=(?)",
                             (request.target_id,)).fetchall()
        return ok_response(data={
            "id": base[0], "user_id": base[1], "name": base[2], "description": base[3], "visibility": base[4],
            "items": [{"id": i[0], "title": i[1], "content": i[2]} for i in items],
        })
    raise RuntimeError("审核目标类型非法，仅支持 character 或 knowledge_base！")


@rr.post("/pending_list")
async def pending_list(request: EmptyRequest, conn=Depends(get_connection), admin=Depends(admin_authentication)):
    """管理员获取待审核列表，仅本机可访问"""
    rows = conn.execute("SELECT target_type, target_id, user_id, applied_at FROM public_reviews "
                        "WHERE status='pending' ORDER BY applied_at").fetchall()
    return ok_response(data={"items": [
        {"target_type": i[0], "target_id": i[1], "user_id": i[2], "applied_at": i[3]} for i in rows
    ]})


@rr.post("/audit")
async def audit(request: ReviewAudit, conn=Depends(get_connection), admin=Depends(admin_authentication)):
    """管理员审核，仅本机可访问。通过则同步将目标 visibility 改为 public"""
    table = TARGET_TABLES.get(request.target_type)
    if table is None:
        raise RuntimeError("审核目标类型非法，仅支持 character 或 knowledge_base！")

    if not request.approved and (not request.warning or request.warning.isspace()):
        raise RuntimeError("驳回审核必须填写告警信息！")

    with transaction(conn):
        row = conn.execute("SELECT status FROM public_reviews WHERE target_type=(?) AND target_id=(?)",
                           (request.target_type, request.target_id)).fetchone()
        if row is None:
            raise RuntimeError("该目标没有审核记录！")
        if row[0] != "pending":
            raise RuntimeError("该审核记录已被处理过！")

        if request.approved:
            # 通过：记录通过时间、清空告警信息，并将目标转为公用
            conn.execute("UPDATE public_reviews SET status='approved', warning=NULL, "
                         "approved_at=CURRENT_TIMESTAMP WHERE target_type=(?) AND target_id=(?)",
                         (request.target_type, request.target_id))
            conn.execute(f"UPDATE {table} SET visibility='public' WHERE id=(?)", (request.target_id,))
        else:
            conn.execute("UPDATE public_reviews SET status='rejected', warning=(?), approved_at=NULL "
                         "WHERE target_type=(?) AND target_id=(?)",
                         (request.warning.strip(), request.target_type, request.target_id))
    return ok_response()
