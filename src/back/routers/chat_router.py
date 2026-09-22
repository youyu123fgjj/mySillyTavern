from uuid import uuid4
from fastapi import Depends, APIRouter

from src.back.request_entity import Chat, JastId, EmptyRequest
from src.back.tools.tools import authentication, ok_response, get_connection, transaction, resolve_name_conflict
from src.back.tools.knowledge_matcher import matcher

cu = APIRouter(prefix="/chat")


@cu.post("/create")
async def create_chat(request: Chat, user_id=Depends(authentication), conn=Depends(get_connection)):
    """新建角色卡。导入场景复用此接口，靠 on_conflict 指定重名策略"""
    if request.visibility == "public":
        raise RuntimeError("转为公用需通过管理员审核，请先创建再提交申请！")
    chat_id = str(uuid4())
    with transaction(conn):
        name, old_id = resolve_name_conflict("characters", request.chat_name, user_id, request.on_conflict, conn)
        if old_id is not None:
            # 覆盖同名角色卡。原地更新而非删除重建，保留 id 以免已有会话与知识库关联失效
            conn.execute(
                "UPDATE characters SET system_prompt=(?), opening_remarks=(?), sample_text=(?), "
                "temperature=(?), max_tokens=(?), updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                (request.system_prompt, request.opening_remarks, request.sample_text,
                 request.temperature, request.max_tokens, old_id))
            return ok_response(data={"chat_id": old_id, "chat_name": name})
        conn.execute("""
            INSERT INTO characters 
            (id, user_id, name, system_prompt, opening_remarks, sample_text, visibility, temperature, max_tokens) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, user_id, name, request.system_prompt, request.opening_remarks, request.sample_text, "private",
              request.temperature, request.max_tokens))
    return ok_response(data={"chat_id": chat_id, "chat_name": name})


@cu.post("/get_info")
async def chat_info(request: JastId, user_id=Depends(authentication), conn=Depends(get_connection)):
    info = conn.execute("""SELECT id, user_id, name, system_prompt, opening_remarks, sample_text,
                           visibility, temperature, max_tokens FROM characters WHERE id = ? """,
                        (request.id,)).fetchone()
    if info is None:
        raise RuntimeError("角色不存在")
    if info[1] == user_id or info[6] != "private":
        username = conn.execute("SELECT username FROM users where id = ?", (user_id,)).fetchone()[0]
        # 关联的知识库。对话时这些库全部参与关键字匹配，所以这里也不按 visibility 过滤
        kbs = conn.execute("SELECT kb.id, kb.name, kb.visibility FROM knowledge_bases kb "
                           "JOIN character_kb_relations r ON r.kb_id = kb.id WHERE r.character_id = ?",
                           (request.id, )).fetchall()
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
        return ok_response(data=data)
    else:
        raise RuntimeError("无权访问该角色！")


@cu.post("/list")
async def chat_list(request: EmptyRequest, conn=Depends(get_connection), user_id=Depends(authentication)):
    chats = conn.execute("SELECT id, name FROM characters WHERE user_id = ? or visibility = 'public'",
                         (user_id,)).fetchall()
    a = {}
    for i in range(len(chats)):
        a[str(i)] = {"id": chats[i][0], "chat_name": chats[i][1]}
    return ok_response(data=a)


@cu.post("/update")
async def update_chat(request: Chat, conn=Depends(get_connection), user_id=Depends(authentication)):
    """确保只有卡作者可以更新"""
    if request.visibility != "":
        raise RuntimeError("转为公用需通过管理员审核，请提交申请！")
    with transaction(conn):
        rows = conn.execute(
            "UPDATE characters SET "
            "name = ?, system_prompt = ?, opening_remarks = ?, sample_text = ?, "
            "visibility = ?, temperature = ?, max_tokens = ? "
            "WHERE id = ? AND user_id = ?",
            (request.chat_name, request.system_prompt, request.opening_remarks, request.sample_text,
             request.visibility, request.temperature, request.max_tokens, request.id, user_id)
        )
        if rows.rowcount == 0:
            raise RuntimeError("要修改的角色卡不属于修改者，无法修改！")
    return ok_response()


@cu.post("/delete")
async def delete_chat(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        rows = conn.execute("DELETE FROM characters WHERE id = ? AND user_id = ?", (request.id, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("内容不存在或无权删除！")
        conn.execute("DELETE FROM character_kb_relations WHERE character_id=(?)", (request.id, ))
        # 同步删除所有该角色卡的知识库链接
        deleted = rows.rowcount
    matcher.invalidate(request.id)
    return ok_response(data="成功删除了 " + str(deleted)+" 行数据")
