from uuid import uuid4

from src.back.SQLiteConnectionPool import transaction, pool
from src.back.config import role_spliter
from src.back.tools.knowledge_matcher import matcher
from src.back.tools.tools import get_messages


async def creat(request, user_id):
    session_id = str(uuid4())
    async with pool.connection() as conn:
        with transaction(conn):
            char_info = conn.execute(
                "SELECT system_prompt, opening_remarks, sample_text FROM characters WHERE id=?", (request.id,)
            ).fetchone()
            conn.execute("INSERT INTO "
                         "sessions (id, user_id, character_id, title, current_branch_id, "
                         "system_prompt, opening_remarks, sample_text) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (session_id, user_id, request.id, "新会话", 0,
                          char_info[0], char_info[1], char_info[2]))
    return session_id


async def delete(request, user_id):
    async with pool.connection() as conn:
        with transaction(conn):
            rows = conn.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?", (request.id, user_id))
            if rows.rowcount == 0:
                raise RuntimeError("未找到要删除的会话或会话不属于当前用户！")


async def list_session(user_id):
    async with pool.connection() as conn:
        rows = conn.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,)).fetchall()
    return rows


async def update(request, user_id):
    if len(request.title) == 0 or request.title.isspace():
        raise RuntimeError("请使用合法的标题！")
    request.title = request.title.strip()
    async with pool.connection() as conn:
        rows = conn.execute("UPDATE sessions SET title = ? WHERE id = ? AND user_id = ?",
                            (request.title, request.id, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("更新失败")


async def info(request, user_id):
    """"""
    async with pool.connection() as conn:
        if conn.execute("SELECT 1 FROM sessions WHERE id=(?) AND user_id=(?)",
                        (request.session_id, user_id)).fetchone() is None:
            raise RuntimeError("目标会话不存在或不属于当前用户！")
    data = await get_messages(request.messages_length, request.session_id)
    # 会话上下文重建后，用当前分支链上最近几轮用户输入重激活知识库条目
    user_msgs = [m["content"][0] for m in data["body"] if m["content"]]
    await matcher.reactivate(request.session_id, data["head"]["character_id"], user_msgs)
    return data


async def get_session(session_id, user_id=None):
    obj = {}
    async with pool.connection() as conn:
        data = conn.execute(
            "SELECT id, user_id, character_id, title, system_prompt, opening_remarks, current_branch_id, "
            "next_branch_id, created_at, updated_at, sample_text"
            "FROM sessions WHERE id = (?)", (session_id,)).fetchone()
        if data in None:
            raise RuntimeError("session不存在")
        if user_id is not None:
            if user_id != data[1]:
                raise RuntimeError("session不属于当前用户")
        titles = ["id", "user_id", "character_id", "title", "system_prompt", "opening_remarks", "current_branch_id",
                  "next_branch_id", "created_at", "updated_at", "sample_text"]
        for i in range(len(titles)):
            obj[titles[i]] = data[i]
    return obj


async def branch_list(request, user_id):
    async with pool.connection() as conn:
        if conn.execute("SELECT 1 FROM sessions WHERE id=(?) AND user_id=(?)",
                        (request.id, user_id)).fetchone() is None:
            raise RuntimeError("目标会话不存在或不属于当前用户！")
        named = dict(conn.execute("SELECT checkpoint_id, branch_name FROM session_branches WHERE session_id=(?)",
                                  (request.id,)).fetchall())
        rows = conn.execute("""
            SELECT branch_id, MAX(id), COUNT(*) FROM messages WHERE session_id=(?) GROUP BY branch_id
        """, (request.id,)).fetchall()
        branch_ids = sorted({int(i) for i in named} | {i[0] for i in rows} | {0})
        stat = {i[0]: (i[1], i[2]) for i in rows}

        branches = []
        for branch_id in branch_ids:
            tip_id, count = stat.get(branch_id, (0, 0))
            preview = None
            if tip_id:
                content = conn.execute("SELECT content FROM messages WHERE id=(?)", (tip_id,)).fetchone()[0]
                preview = content.split(role_spliter)[-1][:50]
            branches.append({
                "branch_id": branch_id,
                "branch_name": named.get(str(branch_id)) or ("主干" if branch_id == 0 else f"分支{branch_id}"),
                "message_count": count,  # 仅该分支自己的消息数，不含分叉点之前的前缀
                "last_msg_id": tip_id,
                "preview": preview
            })
    return branches


async def switch_branch(request, user_id):
    async with pool.connection() as conn:
        session = conn.execute("SELECT next_branch_id FROM sessions WHERE id=(?) AND user_id=(?)",
                               (request.session_id, user_id)).fetchone()
        if session is None:
            raise RuntimeError("目标会话不存在或不属于当前用户！")
        # 0 是主干，其余必须是已分配过的分支号
        if request.branch_id != 0 and not 0 < request.branch_id < session[0]:
            raise RuntimeError("目标分支不存在！")
        conn.execute("UPDATE sessions SET current_branch_id=(?), updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                     (request.branch_id, request.session_id))


async def create_branch(request, user_id):
    async with pool.connection() as conn:
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
            conn.execute(
                "INSERT INTO session_branches (id, session_id, checkpoint_id, branch_name) VALUES (?, ?, ?, ?)",
                (str(uuid4()), request.session_id, str(branch_id), request.branch_name))
            conn.execute("UPDATE sessions SET current_branch_id=(?), next_branch_id=(?), "
                         "updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                         (branch_id, branch_id + 1, request.session_id))
    return branch_id
