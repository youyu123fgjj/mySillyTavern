from sqlite3 import connect
from threading import Lock
from time import perf_counter

from src.back.config import sqlite_path

# 日志专用连接，不从连接池获取。
# 中间件在 call_next 返回后写日志，此时端点持有的池连接尚未释放
# （依赖的 teardown 要等响应体发送完毕），若再从池中取连接，
# 并发数达到池上限时会互相等待造成死锁。
_conn = connect(sqlite_path, check_same_thread=False, isolation_level=None)
_lock = Lock()

# 这些端点由自己记日志，中间件跳过。
# 原因：流式端点在 call_next 返回时响应体还没开始发送，
# 此时 token 用量和真实耗时都拿不到，只能等流结束后自行写入。
SELF_LOGGED = ("/message/dialogue", )


def resolve_user_id(api_key):
    """由 api_key 反查 user_id，查不到返回 None"""
    if not api_key:
        return None
    with _lock:
        row = _conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,)).fetchone()
    return row[0] if row else None


def write_log(user_id, endpoint, start_time, status, error_message, session_id=None, usage=None):
    """写入一条调用日志。
    user_id 为 None 时直接跳过：该字段是 NOT NULL，
    注册 / 登录 / 鉴权失败的请求没有归属用户。
    日志本身失败不能影响主流程，因此吞掉异常只打印。"""
    if user_id is None:
        return
    usage = usage or {}
    try:
        with _lock:
            _conn.execute(
                "INSERT INTO request_logs"
                "(user_id, session_id, endpoint, prompt_tokens, completion_tokens, total_tokens, "
                "duration_ms, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, session_id, endpoint, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                 usage.get("total_tokens"), int((perf_counter() - start_time) * 1000), status, error_message)
            )
    except Exception as e:
        print(f"日志写入失败：{e}")
