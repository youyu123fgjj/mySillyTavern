import json

from uuid import uuid4
from fastapi.responses import JSONResponse
from fastapi import Header, Depends, Request

from src.back.SQLiteConnectionPool import get_connection, transaction
from src.back.config import role_spliter


def ok_response(data=None, msg=None):
    return JSONResponse(content={"data": data, "msg": msg}, status_code=200)


def error_response(code=500, data=None, msg=None):
    return JSONResponse(content={"data": data, "msg": msg}, status_code=code)


async def authentication(authorization: str = Header(...), conn=Depends(get_connection)):
    """鉴权函数，在需要鉴权的Depends内使用"""
    if not authorization:
        raise RuntimeError("未携带token！")
    user_id = conn.execute("SELECT id FROM users WHERE api_key = ?", (authorization,)).fetchone()
    if user_id is None:
        raise RuntimeError("token无效！")
    else:
        return user_id[0]


async def admin_authentication(request: Request):
    """仅允许本机（localhost）访问的管理员鉴权函数，在需要管理员权限的Depends内使用"""
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("仅允许本机访问该接口！")
    return client_host


def resolve_name_conflict(table, name, user_id, on_conflict, conn):
    """处理导入时的重名（UNIQUE(user_id, name)）。必须在事务内调用，否则校验与写入之间存在竞态。
    返回 (实际使用的名称, 被覆盖的旧记录 id)，旧记录 id 为 None 表示无需覆盖。
    on_conflict：rename 追加 (n) 后缀 / overwrite 覆盖同名记录 / 其余情况按重复报错"""
    old = conn.execute(f"SELECT id FROM {table} WHERE user_id=(?) AND name=(?)", (user_id, name)).fetchone()
    if old is None:
        return name, None
    if on_conflict == "overwrite":
        return name, old[0]
    if on_conflict != "rename":
        raise RuntimeError("名称已存在！导入时可指定 on_conflict 为 rename（自动改名）或 overwrite（覆盖同名）")
    # 逐个后缀试探，直到找到未被占用的名称
    n = 1
    while True:
        new_name = f"{name} ({n})"
        if conn.execute(f"SELECT 1 FROM {table} WHERE user_id=(?) AND name=(?)",
                        (user_id, new_name)).fetchone() is None:
            return new_name, None
        n += 1


def get_branch_tip(session_id: str, branch_id: str, conn) -> str:
    """
    取指定会话和指定分支上末端消息的id。分支为空时返回0
    :param session_id: 会话id
    :param branch_id: 分支id
    :param conn: 数据库连接
    :return: 末端消息id
    """
    row = conn.execute("SELECT id FROM messages WHERE session_id=(?) AND branch_id=(?) ORDER BY id DESC LIMIT 1",
                       (session_id, branch_id)).fetchone()
    return row[0] if row else 0


def get_branch_chain(tip_id: str, length: int, conn) -> list:
    """
    从tip_id回溯取最近length轮，返回按时间正序的原始行
    :param tip_id: 回溯链起点对话的id
    :param length: 要获取的对话条数
    :param conn: 数据库连接
    :return: [(id, session_id, content, branch_id, previous_id, summary_id, folded, created_at), ……]
    """
    if not tip_id:
        return []
    # 分支只保存分叉点之后的消息，之前的前缀留在父分支上，所以不能按 branch_id 平铺查询，必须顺着链走。
    rows = conn.execute("""
        WITH RECURSIVE chain(id, session_id, content, branch_id, previous_id, summary_id, folded, created_at) AS (
            SELECT id, session_id, content, branch_id, previous_id, summary_id, folded, created_at FROM messages WHERE id = (?)
            UNION ALL
            SELECT m.id, m.session_id, m.content, m.branch_id, m.previous_id, m.summary_id, m.folded, m.created_at
            FROM messages m JOIN chain c ON m.id = c.previous_id
        )
        SELECT id, session_id, content, branch_id, previous_id, summary_id, folded, created_at
        FROM chain ORDER BY id DESC LIMIT (?)
    """, (tip_id, length)).fetchall()
    rows.reverse()
    return rows


def get_branch_summary(session_id: str, tip_id: str, conn) -> str:
    """
    取分支链上最新的摘要
    :param session_id: 会话id
    :param tip_id: 最新对话的id
    :param conn: 数据库连接
    :return: 摘要内容或空串
    """
    if not tip_id:
        return ""
    row = conn.execute("SELECT summary_id FROM messages WHERE id=(?) AND session_id=(?)",
                       (tip_id, session_id)).fetchone()
    if row is None or row[0] is None:
        return ""
    memory = conn.execute("SELECT memory FROM summaries WHERE id=(?)", (row[0], )).fetchone()
    return memory[0] if memory else ""


def get_messages(messages_length, session_id, conn) -> dict:
    """
    获取会话列表
    :param messages_length: 要获取的对话数量
    :param session_id: 从哪个会话获取
    :param conn: 数据库连接
    :return:
    """
    session = conn.execute("SELECT system_prompt, opening_remarks, created_at, current_branch_id, character_id "
                           "FROM sessions WHERE id = (?)", (session_id, )).fetchone()
    if session is None:
        raise RuntimeError("未查询到数据！")
    system_prompt, opening_remarks, created_at, current_branch_id, character_id = session
    tip_id = get_branch_tip(session_id, current_branch_id, conn)
    rows = get_branch_chain(tip_id, messages_length, conn)

    def make_message_list(msg):
        return {
            "id": msg[0],  # 对话本身的id
            "session_id": msg[1],  # 对话所属的会话id
            "content": msg[2].split(role_spliter),  # 对话内容，被分成user和assistant两段
            "branch_id": msg[3],  # 对话所属的分支id
            "previous_id": msg[4],  # 对话的上一条对话的id
            "summary_id": msg[5],  # 该行时刻生效的摘要快照引用
            "created_at": msg[7]  # 对话创建的时间，目前还是utc时间
        }
    messages = [make_message_list(i) for i in rows if not i[6]]  # 跳过已折叠进摘要的行
    # last_msg_id 供前端接着发消息时回传；从中途的某条消息接话即触发分叉，见 R05
    head = {
        "character_id": character_id,
        "system_prompt": system_prompt,
        "opening_remarks": opening_remarks,
        "created_at": created_at,
        "current_branch_id": current_branch_id,
        "summary": get_branch_summary(session_id, tip_id, conn),  # 前情提要
        "last_msg_id": messages[-1]["id"] if messages else 0
    }
    return {"head": head, "body": messages}
