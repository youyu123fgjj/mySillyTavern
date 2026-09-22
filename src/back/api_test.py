from requests import post, get

baseurl = "http://localhost:9000"
user_token = "426b4054-0156-4356-8432-fb05928399a5"
head = {"authorization": user_token}


def request(url, **kwargs):
    return post(baseurl + url, headers=head, json=kwargs)


a = get(baseurl + "/dbInit")
# a = request("/user/register", username="test", password="123456")
# a = request("/user/login", username="test", password="123456")
# a = request("/user/settings/get")
# a = request("/user/settings/update", default_temperature=0.9, default_max_tokens=4096, theme="dark")


# a = request("/chat/create", id="", user_name="", chat_name="test_chat", system_prompt="test_system_prompt",
#             opening_remarks="text_opening_remarks", visibility="private", temperature=0.7, max_tokens=2048)
chat_id = "8dfbb735-050e-4639-bb40-c25ef5bfe182"
# a = request("/chat/get_info", id=chat_id)
# a = request("/chat/list")
# a = request("/chat/update", id=chat_id, user_name="", chat_name="test_chat2", system_prompt="test_text2",
#             opening_line="text_text2", visibility="private", temperature=100.7, max_tokens=2048000)
# a = request("/chat/delete", id=chat_id)
# 导入角色卡：复用 create，on_conflict 为 rename 自动改名 / overwrite 覆盖同名 / 不传则重名报错
# a = request("/chat/create", id="", user_name="", chat_name="test_chat", system_prompt="test_system_prompt",
#             opening_remarks="text_opening_remarks", visibility="private", temperature=0.7, max_tokens=2048,
#             on_conflict="rename")


# a = request("/session/create", id=chat_id)
# 可用：e8d34e15-3690-4009-b50b-622afd65564e   7a9ddd13-aa8d-4a94-a621-46ff28302e28
session_id = "2e010ca9-941f-4be7-9230-d4293ffd89e9"
# a = request("/session/delete", id=session_id)
# a = request("/session/list")
# a = request("/session/update", id=session_id, title="")
# a = request("/session/info", session_id=session_id, messages_length=20)


# last_msg_id要小心处理，新会话的last_msg_id应该为-1
# a = request("/message/dialogue", last_msg_id=-1, session_id=session_id, message="asd")


# a = request("/knowledge/create", id=None, name="测试知识库1", description="这是测试知识库1,没有条目", visibility=None, items=None)
# a = request("/knowledge/create", id=None, name="测试知识库2", description="这是测试知识库2,有条目", visibility=None,
#             items=[{"id": None, "title": "测试条目1", "content": "这是测试条目1的内容"}])
# a = request("/knowledge/create", id=None, name="测试知识库3", description="这是测试知识库3,有多条条目", visibility=None,
#             items=[{"id": None, "title": "测试条目1", "content": "这是测试条目1的内容"},
#                    {"id": None, "title": "测试条目2", "content": "这是测试条目2的内容"},
#                    {"id": None, "title": "测试条目3", "content": "这是测试条目3的内容"},
#                    {"id": None, "title": "测试条目4", "content": "这是测试条目4的内容"}])
# a = request("/knowledge/get_list")
knowledge_id = "06b44053-eee6-496e-81df-a978e40c747e"
# a = request("/knowledge/get_info", id=knowledge_id)
# a = request("/knowledge/update_base", id=knowledge_id, name="测试知识库3",
#             description="这是测试知识库3,有多条条目,且修改过一次", visibility=None,  items=None)
knowledge_item_id = "83ff2450-d654-4221-bff1-c4a86a340a61"
# a = request("/knowledge/update_item", id=knowledge_item_id, title="测试条目1(改)", content="这是测试条目1的内容,且修改过")
# a = request("/knowledge/delete_item", id=knowledge_item_id)
# a = request("/knowledge/add_item", id=knowledge_id, title="这是插入的条目", content="插入条目的内容")
# a = request("/knowledge/delete", id=knowledge_id)
# a = request("/knowledge/link", id1=chat_id, id2=knowledge_id)
# a = request("/knowledge/unlink", id1=chat_id, id2=knowledge_id)
# 导入知识库：复用 create 并带上 items，on_conflict 同角色卡；overwrite 会整体替换原有条目
# a = request("/knowledge/create", id=None, name="测试知识库1", description="导入的知识库", visibility=None,
#             items=[{"id": None, "title": "条目", "content": "内容"}], on_conflict="overwrite")


# 转公用审核，target_type 为 character 或 knowledge_base
# a = request("/review/apply", target_type="character", target_id=chat_id)
# a = request("/review/status", target_type="character", target_id=chat_id)
# 以下两个仅本机可访问
# a = request("/review/pending_list")
# a = request("/review/audit", target_type="character", target_id=chat_id, approved=True, warning=None)
# a = request("/review/audit", target_type="character", target_id=chat_id, approved=False, warning="设定不合规")


# 调用日志，token 相关字段待 dsh 集成后才有数据
# a = request("/log/usage", start_date=None, end_date=None)
# a = request("/log/usage", start_date="2026-01-01", end_date="2026-12-31")
# a = request("/log/list", page=1, limit=20)


print(a.text)
print(a.status_code)
