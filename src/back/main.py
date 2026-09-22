import os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlite3 import IntegrityError
from time import perf_counter

from src.back.nodes.SystemSqlite import init_system_sqlite
from src.back.tools.tools import error_response, ok_response, admin_authentication
from src.back.tools.request_log import resolve_user_id, write_log, SELF_LOGGED
from src.back.routers.user_router import ur
from src.back.routers.chat_router import cu
from src.back.routers.session_router import su
from src.back.routers.message_router import mu
from src.back.routers.knowledge_router import kr
from src.back.routers.review_router import rr
from src.back.routers.log_router import lr


app = FastAPI()
app.include_router(ur)
app.include_router(cu)
app.include_router(su)
app.include_router(mu)
app.include_router(kr)
app.include_router(rr)
app.include_router(lr)


# ---- 前端静态托管（生产）----
# 前端构建产物目录：src/frontend/dist（请先 npm run build 生成）
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
ASSETS_DIR = os.path.join(FRONTEND_DIST, "assets")

# vite 构建的 JS/CSS/图片等静态资源挂载到 /assets
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    """记录每个请求的耗时与结果。流式端点自行记录，见 SELF_LOGGED"""
    if request.url.path in SELF_LOGGED:
        return await call_next(request)
    start_time = perf_counter()
    user_id = resolve_user_id(request.headers.get("authorization"))
    try:
        response = await call_next(request)
    except BaseException as e:
        # 异常还没被全局处理器转成响应，这里先记一笔再抛出去
        write_log(user_id, request.url.path, start_time, "500", str(e))
        raise
    write_log(user_id, request.url.path, start_time, str(response.status_code), None)
    return response


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """
    仅捕获IntegrityError异常的全局异常处理器
    :param request: Request类对象，fastapi自动传入
    :param exc: 异常对象
    :return: error_response，fastapi自动传入
    """
    s = str(exc)
    if s.split()[0] == "UNIQUE":
        return error_response(500, {}, "操作的目标名称重复！")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    捕获所有类型的异常。必须返回一个fastapi内置的Response
    :param request: Request类对象，fastapi自动传入
    :param exc: 异常对象
    :return: error_response
    """
    s = str(exc)
    print(f"捕获异常：{s}")
    return error_response(500, {}, s)


@app.get("/")
async def root():
    """返回用户前端页面（SPA，见 src/frontend）"""
    return FileResponse(FRONTEND_INDEX)


@app.get("/admin")
async def admin_page(client_host=Depends(admin_authentication)):
    """返回管理员专用前端页面，仅允许本机访问"""
    return FileResponse(FRONTEND_INDEX)


@app.get("/dbInit")
async def db_init():
    """初始化数据库"""
    await init_system_sqlite()
    return ok_response(msg="数据库初始化完成")


# 后端接口前缀：SPA 回退一律跳过，避免吞掉 API / 误回退到 index.html
_API_ROUTES = {"user", "chat", "knowledge", "session", "message", "review", "log", "dbInit"}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """
    前端使用 createWebHistory（无 # 的历史路由），刷新/深链接需回退到 index.html。
    仅当请求是「接口前缀下的更深子路径」时才判定为未知接口并返回 404；
    恰好命中前缀本身（如 /chat、/knowledge）的是 SPA 页面，仍需回退到 index.html。
    :param full_path: 路由
    :return: 前端页面
    """
    cleaned = full_path.rstrip("/")
    root_segment = cleaned.split("/")[0]
    has_subpath = len(cleaned.split("/")) > 1
    if root_segment in _API_ROUTES and has_subpath:
        return error_response(404, {}, "接口不存在!")
    return FileResponse(FRONTEND_INDEX)

if __name__ == "__main__":
    import uvicorn

    # 启动FastAPI服务器
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        log_level="info"
    )
