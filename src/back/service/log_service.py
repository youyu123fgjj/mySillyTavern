from src.back.SQLiteConnectionPool import pool


async def build_date_filter(start_date, end_date):
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


async def usage(request, user_id):
    async with pool.connection() as conn:
        date_sql, date_args = build_date_filter(request.start_date, request.end_date)
        args = [user_id] + date_args

        total = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0) FROM request_logs "
            "WHERE user_id = (?)" + date_sql, args).fetchone()

        rows = conn.execute(
            "SELECT date(created_at), COUNT(*), COALESCE(SUM(total_tokens), 0) FROM request_logs "
            "WHERE user_id = (?)" + date_sql + " GROUP BY date(created_at) ORDER BY date(created_at)",
            args).fetchall()

        return {
            "total_requests": total[0],
            "total_tokens": total[1],
            "daily_breakdown": [{"date": i[0], "requests": i[1], "tokens": i[2]} for i in rows],
        }


async def log_list(request, user_id):
    async with pool.connection() as conn:
        page = request.page if request.page > 0 else 1
        limit = request.limit if 0 < request.limit <= 100 else 20

        total = conn.execute("SELECT COUNT(*) FROM request_logs WHERE user_id = (?)", (user_id,)).fetchone()[0]
        rows = conn.execute(
            "SELECT id, endpoint, session_id, prompt_tokens, completion_tokens, total_tokens, "
            "duration_ms, status, error_message, created_at FROM request_logs "
            "WHERE user_id = (?) ORDER BY id DESC LIMIT (?) OFFSET (?)",
            (user_id, limit, (page - 1) * limit)).fetchall()

        return {
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
        }