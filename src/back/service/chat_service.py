from uuid import uuid4

from src.back.SQLiteConnectionPool import transaction, pool
from src.back.request_entity import Chat
from src.back.tools.knowledge_matcher import matcher
from src.back.tools.tools import resolve_name_conflict


async def creat_user(request: Chat, user_id):
    """创建chat"""
    if request.visibility == "public":
        raise RuntimeError("转为公用需通过管理员审核，请先创建再提交申请！")
    async with pool.connection() as conn:  # 获取数据库连接
        with transaction(conn):  # 开启事务
            name, old_id = await resolve_name_conflict("characters", request.chat_name, user_id, request.on_conflict)
            if old_id is not None:
                # 用户选择覆盖同名角色卡。原地更新而非删除重建，保留id以免已有会话与知识库关联失效
                request.chat_name = name
                await update_chat(request, user_id)
                return {"chat_id": old_id, "chat_name": name}
            # old_id为None,说明用户选择顺延.插入新角色卡
            conn.execute("""
                INSERT INTO characters 
                (id, user_id, name, system_prompt, opening_remarks, sample_text, visibility, temperature, max_tokens) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid4()), user_id, name, request.system_prompt, request.opening_remarks, request.sample_text, "private",
                  request.temperature, request.max_tokens))
            return {"chat_id": old_id, "chat_name": name}


async def get_info(chat_id):
    async with pool.connection() as conn:
        info = conn.execute("""SELECT id, user_id, name, system_prompt, opening_remarks, sample_text,
                                   visibility, temperature, max_tokens FROM characters WHERE id = ? """,
                            (chat_id,)).fetchone()
        if info is None:
            raise RuntimeError("角色不存在")
        return info


async def get_chat_info(request, user_id):
    info = await get_info(request.id)
    async with pool.connection() as conn:
        if info[1] == user_id or info[6] != "private":
            username = conn.execute("SELECT username FROM users where id = ?", (user_id,)).fetchone()[0]
            # 关联的知识库。对话时这些库全部参与关键字匹配，所以这里也不按 visibility 过滤
            kbs = conn.execute("SELECT kb.id, kb.name, kb.visibility FROM knowledge_bases kb "
                               "JOIN character_kb_relations r ON r.kb_id = kb.id WHERE r.character_id = ?",
                               (request.id,)).fetchall()
            data = Chat(
                id=info[0],
                user_name=username,
                chat_name=info[2],
                system_prompt=info[3],
                opening_remarks=info[4],
                sample_text=info[5],
                visibility=info[6],
                temperature=info[7],
                max_tokens=info[8]
            ).model_dump()
            data["knowledge_bases"] = [{"id": i[0], "name": i[1], "visibility": i[2]} for i in kbs]
            return data
        else:
            raise RuntimeError("无权访问该角色！")


async def get_chat_list(user_id):
    async with pool.connection() as conn:
        chats = conn.execute("SELECT id, name FROM characters WHERE user_id = ? or visibility = 'public'",
                             (user_id,)).fetchall()
        a = {}
        for i in range(len(chats)):
            a[str(i)] = {"id": chats[i][0], "chat_name": chats[i][1]}
        return a


async def update_chat(request, user_id):
    async with pool.connection() as conn:
        if request.visibility != "":
            raise RuntimeError("转为公用需通过管理员审核，请提交申请！")
        with transaction(conn):
            rows = conn.execute(
                "UPDATE characters SET "
                "name = ?, system_prompt = ?, opening_remarks = ?, sample_text = ?, "
                "temperature = ?, max_tokens = ?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id = ? AND user_id = ?",
                (request.chat_name, request.system_prompt, request.opening_remarks, request.sample_text,
                 request.temperature, request.max_tokens, request.id, user_id)
            )
            if rows.rowcount == 0:
                raise RuntimeError("要修改的角色卡不属于修改者，无法修改！")


async def delete_chat(request, user_id):
    async with pool.connection() as conn:
        with transaction(conn):
            rows = conn.execute("DELETE FROM characters WHERE id = ? AND user_id = ?", (request.id, user_id))
            if rows.rowcount == 0:
                raise RuntimeError("内容不存在或无权删除！")
            conn.execute("DELETE FROM character_kb_relations WHERE character_id=(?)", (request.id,))
            # 同步删除所有该角色卡的知识库链接
            deleted = rows.rowcount
        matcher.invalidate(request.id)
        return "成功删除了 " + str(deleted)+" 个chat"
