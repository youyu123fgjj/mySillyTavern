from src.back.SQLiteConnectionPool import auto_connection


@auto_connection
def init_system_sqlite(*, conn):
    # 1. 用户相关
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            default_temperature REAL DEFAULT 0.7,
            default_max_tokens INTEGER DEFAULT 2048,
            theme TEXT DEFAULT 'light',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. 角色相关
    conn.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            opening_remarks TEXT,
            sample_text TEXT,  -- 示例对话文本，无摘要时注入 system 引导风格
            visibility TEXT DEFAULT 'private',
            temperature REAL,
            max_tokens INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_user_id ON characters(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_characters_visibility ON characters(visibility)")

    # 3. 知识库相关
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            visibility TEXT DEFAULT 'private',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            title TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_items_kb_id ON knowledge_items(kb_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS character_kb_relations (
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (character_id, kb_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_char_kb_character ON character_kb_relations(character_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_char_kb_kb ON character_kb_relations(kb_id)")

    # 3.5 转公用审核表：角色卡与知识库转为公用需管理员审核
    conn.execute("""
        CREATE TABLE IF NOT EXISTS public_reviews (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,  -- 审核目标类型：character / knowledge_base
            target_id TEXT NOT NULL,    -- 角色卡id或知识库id
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- 申请人，必须是创建者
            status TEXT NOT NULL DEFAULT 'pending',  -- pending 待审核 / approved 通过 / rejected 驳回
            warning TEXT,               -- 驳回时的告警信息，仅 rejected 时非空
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 申请时间
            approved_at TIMESTAMP,      -- 审核通过时间，仅 approved 时非空
            UNIQUE(target_type, target_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_status ON public_reviews(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON public_reviews(user_id)")

    # 4. 会话相关（注意顺序：先 sessions，后 session_branches）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- 用户id
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE, -- 角色id
            title TEXT, -- 会话标题
            system_prompt TEXT,  -- 会话系统提示词，与角色卡独立，角色卡更新此处不变
            opening_remarks TEXT, -- 开场白，同样与角色卡独立
            sample_text TEXT,  -- 示例文本，与角色卡独立（二轮）
            current_branch_id INTEGER NOT NULL DEFAULT 0,   -- 现在活跃的分支的id
            next_branch_id INTEGER NOT NULL DEFAULT 1,  -- 下一个可用的分支id
            summary_id INTEGER,  -- 快照引用 summaries.id：这一行时刻生效的摘要（二轮）
            folded INTEGER DEFAULT 0,  -- 1=已折叠进摘要，读取时跳过（二轮）
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_branches (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, --分支所属的会话id
            checkpoint_id TEXT NOT NULL,    -- 分支id
            branch_name TEXT,   -- 分支名
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, checkpoint_id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_character ON sessions(character_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_branches_session ON session_branches(session_id)")
    # 7. 对话历史表
    conn.execute("""
        -- 不存角色，system存在sessions表内；user+assistant按顺序拼接在一起存在context
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),   -- 所属的会话id
            content TEXT NOT NULL, -- 聊天内容
            branch_id INTEGER NOT NULL,  -- 记录所属的分支id
            previous_id INTEGER NOT NULL REFERENCES messages(id),    -- 上一条记录的id
            summary_id INTEGER,  -- 快照引用 summaries.id：这一行时刻生效的摘要（二轮）
            folded INTEGER DEFAULT 0,  -- 1=已折叠进摘要，读取时跳过（二轮）
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS history_sessionId_branchId ON messages(session_id, branch_id, id DESC)")

    # 7.5 摘要表（二轮）：滚动摘要，每行一次压缩生成，旧行保留供分支快照引用
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,      -- 所属会话
            branch_id INTEGER NOT NULL,    -- 摘要生成时所处分支
            memory TEXT NOT NULL,          -- 滚动摘要文本
            folded_from_msg_id INTEGER,    -- 本次折叠段的最老消息 id
            folded_to_msg_id INTEGER,      -- 本次折叠段的最后一条消息 id
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_session ON summaries(session_id)")

    # 6. 日志表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id TEXT,
            endpoint TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            duration_ms INTEGER,
            status TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_id ON request_logs(user_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_created_at ON request_logs(created_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_session ON request_logs(session_id)")

    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "sample_text" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN sample_text TEXT")

    return None
