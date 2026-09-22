from pydantic import BaseModel


class EmptyRequest(BaseModel):
    pass


class User(BaseModel):
    username: str
    password: str


class UserSettings(BaseModel):
    default_temperature: float
    default_max_tokens: int
    theme: str


class Chat(BaseModel):
    id: str
    user_name: str
    chat_name: str
    system_prompt: str
    opening_remarks: str
    sample_text: str | None = None  # 示例对话文本（二轮），无摘要时注入 system 引导风格
    visibility: str | None
    temperature: float
    max_tokens: int
    on_conflict: str | None = None  # 导入时的重名策略：rename 自动改名 / overwrite 覆盖同名 / 其余报错


class Session(BaseModel):
    id: str
    title: str


class SessionInfo(BaseModel):
    messages_length: int
    session_id: str


class JastId(BaseModel):
    id: str


class TwoId(BaseModel):
    id1: str
    id2: str


class Dialogue(BaseModel):
    last_msg_id: int
    session_id: str
    message: str


class BranchSwitch(BaseModel):
    session_id: str
    branch_id: int


class BranchCreate(BaseModel):
    session_id: str
    from_msg_id: int            # 从哪条消息之后分叉，0 表示从会话开头
    branch_name: str | None = None


class KnowledgeItem(BaseModel):
    id: str | None
    title: str
    content: str


class Knowledge(BaseModel):
    id: str | None
    name: str
    description: str
    visibility: str | None
    items: list[KnowledgeItem] | None
    on_conflict: str | None = None  # 导入时的重名策略：rename 自动改名 / overwrite 覆盖同名 / 其余报错


class ReviewApply(BaseModel):
    target_type: str    # character / knowledge_base
    target_id: str


class ReviewAudit(BaseModel):
    target_type: str    # character / knowledge_base
    target_id: str
    approved: bool      # True 通过，False 驳回
    warning: str | None = None  # 驳回原因，approved 为 False 时必填


class UsageQuery(BaseModel):
    start_date: str | None = None   # YYYY-MM-DD，不传则不限
    end_date: str | None = None


class LogQuery(BaseModel):
    page: int = 1
    limit: int = 20

