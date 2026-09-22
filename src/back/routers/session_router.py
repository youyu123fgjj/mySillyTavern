from uuid import uuid4
from fastapi import Depends, APIRouter

from src.back.request_entity import JastId, EmptyRequest, Session, SessionInfo, BranchSwitch, BranchCreate
from src.back.tools.tools import authentication, ok_response, get_connection, get_messages, transaction
from src.back.tools.knowledge_matcher import matcher
from src.back.config import role_spliter

su = APIRouter(prefix="/session")


@su.post("/create")
async def create_session(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    session_id = str(uuid4())
    with transaction(conn):
        char_info = conn.execute(
            "SELECT system_prompt, opening_remarks, sample_text FROM characters WHERE id=?", (request.id, )
        ).fetchone()
        conn.execute("INSERT INTO "
                     "sessions (id, user_id, character_id, title, current_branch_id, "
                     "system_prompt, opening_remarks, sample_text) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (session_id, user_id, request.id, "新会话", 0,
                      char_info[0], char_info[1], char_info[2]))
    return ok_response(data={"session_id": session_id})


@su.post("/delete")
async def delete_session(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        rows = conn.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?", (request.id, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("未找到要删除的会话或会话不属于当前用户！")
    return ok_response()


@su.post("/list")
async def list_session(request: EmptyRequest, conn=Depends(get_connection), user_id=Depends(authentication)):
    rows = conn.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id, )).fetchall()
    return ok_response(rows)


@su.post("/update")
async def update_session(request: Session, conn=Depends(get_connection), user_id=Depends(authentication)):
    if len(request.title) == 0 or request.title.isspace():
        raise RuntimeError("请使用合法的标题！")
    request.title = request.title.strip()
    with transaction(conn):
        rows = conn.execute("UPDATE sessions SET title = ? WHERE id = ? AND user_id = ?",
                            (request.title, request.id, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("更新失败")
    return ok_response()


@su.post("/info")
async def get_session_info(request: SessionInfo, user_id=Depends(authentication), conn=Depends(get_connection)):
    if conn.execute("SELECT 1 FROM sessions WHERE id=(?) AND user_id=(?)",
                    (request.session_id, user_id)).fetchone() is None:
        raise RuntimeError("目标会话不存在或不属于当前用户！")
    data = get_messages(request.messages_length, request.session_id, conn)
    # 会话上下文重建后，用当前分支链上最近几轮用户输入重激活知识库条目
    user_msgs = [m["content"][0] for m in data["body"] if m["content"]]
    matcher.reactivate(request.session_id, data["head"]["character_id"], user_msgs, conn)
    print("session info:\n", data)
    return ok_response(data=data)


@su.post("/branch/list")
async def list_branch(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    """B02 列出会话的全部分支，附末条消息预览。
    branch 0 是会话创建时的主干，不在 session_branches 中登记，这里手动补上。"""
    if conn.execute("SELECT 1 FROM sessions WHERE id=(?) AND user_id=(?)",
                    (request.id, user_id)).fetchone() is None:
        raise RuntimeError("目标会话不存在或不属于当前用户！")
    named = dict(conn.execute("SELECT checkpoint_id, branch_name FROM session_branches WHERE session_id=(?)",
                              (request.id, )).fetchall())
    rows = conn.execute("""
        SELECT branch_id, MAX(id), COUNT(*) FROM messages WHERE session_id=(?) GROUP BY branch_id
    """, (request.id, )).fetchall()
    branch_ids = sorted({int(i) for i in named} | {i[0] for i in rows} | {0})
    stat = {i[0]: (i[1], i[2]) for i in rows}

    branches = []
    for branch_id in branch_ids:
        tip_id, count = stat.get(branch_id, (0, 0))
        preview = None
        if tip_id:
            content = conn.execute("SELECT content FROM messages WHERE id=(?)", (tip_id, )).fetchone()[0]
            preview = content.split(role_spliter)[-1][:50]
        branches.append({
            "branch_id": branch_id,
            "branch_name": named.get(str(branch_id)) or ("主干" if branch_id == 0 else f"分支{branch_id}"),
            "message_count": count,   # 仅该分支自己的消息数，不含分叉点之前的前缀
            "last_msg_id": tip_id,
            "preview": preview
        })
    return ok_response(data=branches)


@su.post("/branch/switch")
async def switch_branch(request: BranchSwitch, conn=Depends(get_connection), user_id=Depends(authentication)):
    """B03 切换当前活跃分支。只改 sessions.current_branch_id，消息本身不动。"""
    with transaction(conn):
        session = conn.execute("SELECT next_branch_id FROM sessions WHERE id=(?) AND user_id=(?)",
                               (request.session_id, user_id)).fetchone()
        if session is None:
            raise RuntimeError("目标会话不存在或不属于当前用户！")
        # 0 是主干，其余必须是已分配过的分支号
        if request.branch_id != 0 and not 0 < request.branch_id < session[0]:
            raise RuntimeError("目标分支不存在！")
        conn.execute("UPDATE sessions SET current_branch_id=(?), updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                     (request.branch_id, request.session_id))
    return ok_response(data={"current_branch_id": request.branch_id})


@su.post("/branch/create")
async def create_branch(request: BranchCreate, conn=Depends(get_connection), user_id=Depends(authentication)):
    """B01 + B04 回退并分叉。
    回退不删除任何消息：从 from_msg_id 处分配一个新分支号并切过去，
    后续消息以 from_msg_id 为 previous_id 挂在新分支上，原分支完整保留。
    from_msg_id 传 0 表示从会话开头重新开始。"""
    with transaction(conn):
        session = conn.execute("SELECT next_branch_id FROM sessions WHERE id=(?) AND user_id=(?)",
                               (request.session_id, user_id)).fetchone()
        if session is None:
            raise RuntimeError("目标会话不存在或不属于当前用户！")
        if request.from_msg_id and conn.execute(
                "SELECT 1 FROM messages WHERE id=(?) AND session_id=(?)",
                (request.from_msg_id, request.session_id)).fetchone() is None:
            raise RuntimeError("分叉点消息不存在！")

        branch_id = session[0]
        conn.execute("INSERT INTO session_branches (id, session_id, checkpoint_id, branch_name) VALUES (?, ?, ?, ?)",
                     (str(uuid4()), request.session_id, str(branch_id), request.branch_name))
        conn.execute("UPDATE sessions SET current_branch_id=(?), next_branch_id=(?), "
                     "updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                     (branch_id, branch_id + 1, request.session_id))
    # 新分支还没有消息，前端接着发消息时把 last_msg_id 传成分叉点
    return ok_response(data={"branch_id": branch_id, "last_msg_id": request.from_msg_id})

