from fastapi import APIRouter, Depends

from src.back.request_entity import UsageQuery, LogQuery
from src.back.tools.tools import ok_response, get_connection, authentication

lr = APIRouter(prefix="/log")


def build_date_filter(start_date, end_date):
    """把可选的起止日期拼成 SQL 条件片段与参数，created_at 为 UTC 的 'YYYY-MM-DD HH:MM:SS'"""
    sql = ""
    args = []
    if start_date:
        sql += " AND date(created_at) >= (?)"
        args.append(start_date)
    if end_date:
        sql += " AND date(created_at) <= (?)"
        args.append(end_date)
    return sql, args


@lr.post("/usage")
def usage(request: UsageQuery, conn=Depends(get_connection), user_id=Depends(authentication)):
    """用量统计。total_requests 已可用，token 相关字段待 dsh 集成后才有数据"""
    date_sql, date_args = build_date_filter(request.start_date, request.end_date)
    args = [user_id] + date_args

    total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0) FROM request_logs "
        "WHERE user_id = (?)" + date_sql, args).fetchone()

    rows = conn.execute(
        "SELECT date(created_at), COUNT(*), COALESCE(SUM(total_tokens), 0) FROM request_logs "
        "WHERE user_id = (?)" + date_sql + " GROUP BY date(created_at) ORDER BY date(created_at)",
        args).fetchall()

    return ok_response(data={
        "total_requests": total[0],
        "total_tokens": total[1],
        "daily_breakdown": [{"date": i[0], "requests": i[1], "tokens": i[2]} for i in rows],
    })


@lr.post("/list")
def log_list(request: LogQuery, conn=Depends(get_connection), user_id=Depends(authentication)):
    """分页查询自己的调用日志，按时间倒序"""
    page = request.page if request.page > 0 else 1
    limit = request.limit if 0 < request.limit <= 100 else 20

    total = conn.execute("SELECT COUNT(*) FROM request_logs WHERE user_id = (?)", (user_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT id, endpoint, session_id, prompt_tokens, completion_tokens, total_tokens, "
        "duration_ms, status, error_message, created_at FROM request_logs "
        "WHERE user_id = (?) ORDER BY id DESC LIMIT (?) OFFSET (?)",
        (user_id, limit, (page - 1) * limit)).fetchall()

    return ok_response(data={
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [{
            "id": i[0],
            "endpoint": i[1],
            "session_id": i[2],
            "prompt_tokens": i[3],
            "completion_tokens": i[4],
            "total_tokens": i[5],
            "duration_ms": i[6],
            "status": i[7],
            "error_message": i[8],
            "created_at": i[9],
        } for i in rows],
    })
