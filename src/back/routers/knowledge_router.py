from uuid import uuid4
from fastapi import Depends, APIRouter

from src.back.request_entity import EmptyRequest, Knowledge, JastId, KnowledgeItem, TwoId
from src.back.tools.tools import authentication, ok_response, get_connection, transaction, resolve_name_conflict
from src.back.tools.knowledge_matcher import matcher

kr = APIRouter(prefix="/knowledge")


@kr.post("/create")
def knowledge_create(request: Knowledge, conn=Depends(get_connection), user_id=Depends(authentication)):
    """新建知识库。导入场景复用此接口，靠 on_conflict 指定重名策略"""
    if request.visibility == "public":
        raise RuntimeError("转为公用需通过管理员审核，请先创建再提交申请！")
    kb_id = str(uuid4())
    with transaction(conn):
        name, old_id = resolve_name_conflict("knowledge_bases", request.name if request.name else "知识库",
                                            user_id, request.on_conflict, conn)
        if old_id is not None:
            # 覆盖同名知识库。原地更新保留 id 以免角色卡关联失效，条目则整体替换
            kb_id = old_id
            conn.execute("UPDATE knowledge_bases SET description=(?), updated_at=CURRENT_TIMESTAMP WHERE id=(?)",
                         (request.description, kb_id))
            conn.execute("DELETE FROM knowledge_items WHERE kb_id=(?)", (kb_id, ))
        else:
            conn.execute("INSERT INTO knowledge_bases(id, user_id, name, description, visibility) "
                         "VALUES (?, ?, ?, ?, ?)",
                         (kb_id, user_id, name, request.description, "private"))
        if request.items:
            for i in request.items:
                conn.execute("INSERT INTO knowledge_items(id, kb_id, title, content) VALUES (?, ?, ?, ?)",
                             (str(uuid4()), kb_id, i.title, i.content))
    # 覆盖导入会整体替换条目，失效引用该知识库的全部角色卡缓存
    matcher.invalidate_for_kb(kb_id, conn)
    return ok_response(data={"kb_id": kb_id, "name": name})


@kr.post("/delete")
def delete(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        if len(conn.execute("SELECT * FROM character_kb_relations WHERE kb_id=(?)", (request.id, )).fetchall()) > 0:
            raise RuntimeError("这个知识库正在被角色卡使用，无法删除！")
        conn.execute("DELETE FROM knowledge_bases WHERE id=(?) AND user_id=(?)", (request.id, user_id))
        conn.execute("DELETE FROM knowledge_items WHERE kb_id=(?)", (request.id, ))
    return ok_response()


@kr.post("/get_info")
def info(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    """知识库详情，含全部条目。前端可直接把返回的 data 存为文件完成导出"""
    base = conn.execute("SELECT id, name, description, visibility, user_id FROM knowledge_bases WHERE id=(?)",
                        (request.id, )).fetchone()
    if base is None:
        raise RuntimeError("知识库不存在！")
    if base[4] != user_id and base[3] != "public":
        raise RuntimeError("无权访问该知识库！")
    items = conn.execute("SELECT id, title, content FROM knowledge_items WHERE kb_id=(?)", (request.id, )).fetchall()
    return ok_response(data={
        "id": base[0],
        "name": base[1],
        "description": base[2],
        "visibility": base[3],
        "items": [{"id": i[0], "title": i[1], "content": i[2]} for i in items],
    })


@kr.post("/get_list")
def get_list(request: EmptyRequest, conn=Depends(get_connection), user_id=Depends(authentication)):
    items = conn.execute("SELECT id, name, description FROM knowledge_bases WHERE user_id=(?) OR visibility='public'",
                         (user_id, )).fetchall()
    return ok_response(data={"items": items})


@kr.post("/update_base")
def update_base(request: Knowledge, conn=Depends(get_connection), user_id=Depends(authentication)):
    if request.visibility == "":
        raise RuntimeError("转为公用需通过管理员审核，请使用提交申请！")
    with transaction(conn):
        rows = conn.execute(
            "UPDATE knowledge_bases SET name=(?), description=(?), visibility=(?) WHERE id=(?) AND user_id=(?)",
            (request.name, request.description, request.visibility, request.id, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("更新失败")
    return ok_response()


@kr.post("/update_item")
def update_item(request: KnowledgeItem, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        base = conn.execute("SELECT kb_id FROM knowledge_items WHERE id=(?)", (request.id, )).fetchone()
        if base is None:
            raise RuntimeError("条目不存在！")
        rows = conn.execute("UPDATE knowledge_items SET title=(?), content=(?) WHERE id=(?)",
                            (request.title, request.content, request.id))
        if rows.rowcount == 0:
            raise RuntimeError("更新失败")
    matcher.invalidate_for_kb(base[0], conn)
    return ok_response()


@kr.post("/delete_item")
def delete_item(request: JastId, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        base_id = conn.execute("SELECT kb_id FROM knowledge_items WHERE id=(?)", (request.id, )).fetchall()[0][0]
        if conn.execute("SELECT * FROM knowledge_bases WHERE id=(?) AND user_id=(?)", (base_id, user_id)).rowcount != 0:
            # 验证删除操作是否由知识库创建者进行
            if conn.execute("DELETE FROM knowledge_items WHERE id=(?)", (request.id, )).rowcount == 0:
                # 确认删除,判断删除是否成功
                raise RuntimeError("删除失败")
        else:
            raise RuntimeError("无权删除该条目!")
    matcher.invalidate_for_kb(base_id, conn)
    return ok_response()


@kr.post("/add_item")
def add_item(request: KnowledgeItem, conn=Depends(get_connection), user_id=Depends(authentication)):
    item_id = str(uuid4())
    with transaction(conn):
        if conn.execute("SELECT * FROM knowledge_bases WHERE id=(?) AND user_id=(?)",
                        (request.id, user_id)).rowcount != 0:
            # 插入前保证目标知识库存在
            conn.execute("INSERT INTO knowledge_items(id, kb_id, title, content) VALUES (?, ?, ?, ?)",
                         (item_id, request.id, request.title, request.content))
            # 这里复用了KnowledgeItem,但其中的id是知识库(knowledge_base)的id而不是知识库条目(knowledge_item)的id
        else:
            raise RuntimeError("目标知识库不存在")
    matcher.invalidate_for_kb(request.id, conn)
    return ok_response(msg=item_id)


@kr.post("/link")
def make_link(request: TwoId, conn=Depends(get_connection), user_id=Depends(authentication)):
    """id1 为角色卡 id，id2 为知识库 id。
    只有卡作者能挂载知识库，且只能挂自己的库或已公用的库"""
    with transaction(conn):
        if conn.execute("SELECT 1 FROM characters WHERE id=(?) AND user_id=(?)",
                        (request.id1, user_id)).fetchone() is None:
            raise RuntimeError("角色卡不存在或不属于当前用户，无法关联知识库！")
        if conn.execute("SELECT 1 FROM knowledge_bases WHERE id=(?) AND (user_id=(?) OR visibility='public')",
                        (request.id2, user_id)).fetchone() is None:
            raise RuntimeError("知识库不存在或无权关联！")
        conn.execute("INSERT INTO character_kb_relations(character_id, kb_id, user_id) VALUES (?, ?, ?)",
                     (request.id1, request.id2, user_id))
    matcher.invalidate(request.id1)
    return ok_response()


@kr.post("/unlink")
def delete_link(request: TwoId, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        rows = conn.execute("DELETE FROM character_kb_relations WHERE character_id=(?) AND kb_id=(?) AND user_id=(?)",
                            (request.id1, request.id2, user_id))
        if rows.rowcount == 0:
            raise RuntimeError("解除关联失败，该关联不存在或无权操作！")
    matcher.invalidate(request.id1)
    return ok_response()
