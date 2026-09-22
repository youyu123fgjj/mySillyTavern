from fastapi import APIRouter, Depends
from uuid import uuid4
from hashlib import md5

from src.back.request_entity import User, UserSettings
from src.back.tools.tools import ok_response, get_connection, transaction, authentication

ur = APIRouter(prefix="/user")

# 默认用户配置
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048
DEFAULT_THEME = "light"


@ur.post("/register")
async def register(request: User, conn=Depends(get_connection)):
    m = md5()
    m.update((request.username + request.password).encode("utf8"))
    user_id = str(uuid4())
    with transaction(conn):
        conn.execute("INSERT INTO users(id, username, api_key, password_hash) VALUES (?, ?, ?, ?)",
                     (user_id, request.username, "", str(m.hexdigest())))
        conn.execute("INSERT INTO user_settings(user_id, default_temperature, default_max_tokens, theme) "
                     "VALUES (?, ?, ?, ?)",
                     (user_id, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS, DEFAULT_THEME))
    return ok_response()


@ur.post("/login")
async def login(request: User, conn=Depends(get_connection)):
    m = md5()
    m.update((request.username + request.password).encode("utf8"))
    with transaction(conn):
        u_id = conn.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?",
                            (request.username, str(m.hexdigest()))).fetchone()
        if u_id is None:
            raise RuntimeError("用户未注册")
        u_id = u_id[0]
        api_kay = str(uuid4())
        conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (api_kay, u_id))
    return ok_response(data=api_kay)


@ur.post("/settings/get")
async def get_settings(conn=Depends(get_connection), user_id=Depends(authentication)):
    row = conn.execute(
        "SELECT default_temperature, default_max_tokens, theme FROM user_settings WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    if row is None:
        # 兜底：旧账号可能没有配置行，回落默认值
        return ok_response(data={
            "default_temperature": DEFAULT_TEMPERATURE,
            "default_max_tokens": DEFAULT_MAX_TOKENS,
            "theme": DEFAULT_THEME,
        })
    return ok_response(data={
        "default_temperature": row[0],
        "default_max_tokens": row[1],
        "theme": row[2],
    })


@ur.post("/settings/update")
async def update_settings(request: UserSettings, conn=Depends(get_connection), user_id=Depends(authentication)):
    with transaction(conn):
        rows = conn.execute(
            "UPDATE user_settings SET default_temperature = ?, default_max_tokens = ?, theme = ? "
            "WHERE user_id = ?",
            (request.default_temperature, request.default_max_tokens, request.theme, user_id)
        )
        if rows.rowcount == 0:
            # 旧账号没有配置行，补插
            conn.execute(
                "INSERT INTO user_settings(user_id, default_temperature, default_max_tokens, theme) "
                "VALUES (?, ?, ?, ?)",
                (user_id, request.default_temperature, request.default_max_tokens, request.theme)
            )
    return ok_response()
