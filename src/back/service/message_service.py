from json import dumps
from time import perf_counter

from src.back.SQLiteConnectionPool import pool, transaction
from src.back.config import context_window, fold_segment, role_spliter, summary_temperature, summary_max_tokens, \
    history_max_length
from src.back.nodes.deepseek import summarize_dialogue, stream_dialogue
from src.back.tools.knowledge_matcher import matcher
from src.back.tools.request_log import write_log
from src.back.tools.tools import get_branch_chain, get_branch_summary

# 取整条链用于压缩判断时的长度上限（实际链长远小于此值）
_FULL_CHAIN_LIMIT = 10 ** 6


async def build_history(session_id, character_id, last_msg_id, system_prompt, opening_remarks, sample_text,
                        user_message):
    """
    拼接送给模型的messages
    :param session_id: 会话id
    :param character_id: 角色卡id
    :param last_msg_id: 会话当前分支下最新一条对话的id
    :param system_prompt: 角色卡的系统提示词
    :param opening_remarks: 角色卡的开场白
    :param sample_text: 角色卡的示例对话文本（二轮）
    :param user_message: 用户新一轮输入
    :return: [{"role": "", "content": ""}, ……]
    """
    # 1.在当前正在运行的分支上获取原始行
    rows = await get_branch_chain(last_msg_id, history_max_length)
    # 2.拼接system prompt到上下文窗口
    history = [{"role": "system", "content": system_prompt or ""}]
    # 3.如果角色卡有开场白则拼接（这里也有问题，目前是无论如何一定拼接开场白
    if opening_remarks:
        history.append({"role": "assistant", "content": opening_remarks})  # 开场白作为首条assistant消息
    # 4.跳过已经被折叠的行（这里似乎有bug，当我回溯到比较早的对话轮数时，后面前面的行可能已经被折叠过导致这里啥也加不进去）
    for row in rows:
        if row[6]:  # 折叠进摘要的行(folded=1)
            continue
        pair = row[2].split(role_spliter)  # messages表一行存一轮(user+assistant，用role_spliter连接)。先按行取出再拆回两条
        history.append({"role": "user", "content": pair[0]})
        history.append({"role": "assistant", "content": pair[1]})
    # 5.将用户本轮输入写入上下文
    history.append({"role": "user", "content": user_message})
    # 6.前情提要（滚动摘要）注入 system 尾部；无摘要（未压缩过）时注入示例文本引导风格
    summary = await get_branch_summary(session_id, last_msg_id)
    if summary:
        history[0]["content"] = (history[0]["content"] or "") + f"\n<前情提要>{summary}</前情提要>"
    elif sample_text:
        history[0]["content"] = (history[0]["content"] or "") + f"\n<示例>{sample_text}</示例>"
    # 7.知识库命中注入到用户最新一轮输入的末尾（激活状态由匹配器维护）
    knowledge_text = await matcher.match_knowledge(session_id, character_id, user_message)
    if knowledge_text:
        history[-1]["content"] += knowledge_text
    return history


async def maybe_compress(session_id, branch_id, tip_id):
    """
    需要时自动进行窗口压缩
    :param session_id: 会话id
    :param branch_id: 分支id
    :param tip_id: 最新一条对话id
    :return: None
    """
    """（二轮 D15/D16）：链长超 context_window 时，把最老 fold_segment 轮
    折叠成滚动摘要，折叠段标记 folded，链末端 summary_id 更新为新摘要。
    模型调用期间不占用池连接；任何异常只静默降级（下次对话再触发）。"""
    try:
        # 获取需要摘要的对话
        chain = await get_branch_chain(tip_id, _FULL_CHAIN_LIMIT)
        if len(chain) <= context_window:
            return
        fold_rows = chain[:fold_segment]  # 最老 fold_segment 轮，时间正序
        old_memory = await get_branch_summary(session_id, tip_id)
        lines = []
        for row in fold_rows:
            pair = row[2].split(role_spliter)
            user_part = pair[0]
            assistant_part = pair[1] if len(pair) > 1 else ""
            lines.append(f"用户：{user_part}\n助手：{assistant_part}")
        # 获取旧摘要
        memory = await summarize_dialogue("\n".join(lines), old_memory, summary_temperature, summary_max_tokens)
        # 新摘要写入数据库
        async with pool.connection() as write_conn:
            with transaction(write_conn):
                summary_id = write_conn.execute(
                    "INSERT INTO summaries (session_id, branch_id, memory, folded_from_msg_id, folded_to_msg_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, branch_id, memory, fold_rows[0][0], fold_rows[-1][0])).lastrowid
                # 这里动态构造了sql，使其可以面对fold_rows返回了任意多行数据的情况
                placeholders = ",".join("?" * len(fold_rows))
                write_conn.execute(
                    f"UPDATE messages SET folded=1 WHERE id IN ({placeholders})",
                    [r[0] for r in fold_rows])
                write_conn.execute(
                    "UPDATE messages SET summary_id=(?) WHERE id=(?)", (summary_id, tip_id))
    except BaseException:
        # 压缩失败不影响主流程，仅留痕，下轮对话再触发
        return


async def dialogue(request, user_id):
    # 1.对request进行检查
    if not request.message or request.message.isspace():
        raise RuntimeError("消息内容不能为空！")
    async with pool.connection() as conn:
        # 2.确定session及关联的chat存在
        session = conn.execute(
            "SELECT s.current_branch_id, s.system_prompt, s.opening_remarks, s.sample_text, "
            "c.temperature, c.max_tokens, s.character_id "
            "FROM sessions s JOIN characters c ON c.id = s.character_id "
            "WHERE s.id = (?) AND s.user_id = (?)", (request.session_id, user_id)).fetchone()
        if session is None:
            raise RuntimeError("目标会话不存在")
        # 3.last_msg_id 决定新消息挂在链上的哪个位置，必须确认它属于本会话，0 表示从头开始。验证last_msg_id存在即认为请求合法允许插入
        if request.last_msg_id and conn.execute(
                "SELECT 1 FROM messages WHERE id = (?) AND session_id = (?)",
                (request.last_msg_id, request.session_id)).fetchone() is None:
            raise RuntimeError("上一条消息不存在！")
        current_branch_id, system_prompt, opening_remarks, sample_text, temperature, max_tokens, character_id = session
        history = await build_history(request.session_id, character_id, request.last_msg_id,
                                      system_prompt, opening_remarks, sample_text, request.message)
    start_time = perf_counter()
    # print(history)

    async def scq():
        reply_text = ""
        usage = {}
        error_message = None
        new_id = None
        # 1.逐步yield模型回复
        try:
            async for chunk in stream_dialogue(history, temperature, max_tokens, usage):
                reply_text += chunk
                yield f"data: {dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except BaseException as e:
            error_message = str(e)
            yield f"data: {dumps({'error': error_message}, ensure_ascii=False)}\n\n"
        else:
            # 二轮 D16：落库 → 压缩 → [DONE]，保证链路关闭前摘要已就绪
            if reply_text:
                async with pool.connection() as write_conn:
                    # 2.将模型回复落库，新消息继承上一条的summary_id（快照）
                    new_id = write_conn.execute(
                        "INSERT INTO messages (content, session_id, branch_id, previous_id, summary_id) "
                        "VALUES (?, ?, ?, ?, (SELECT summary_id FROM messages WHERE id = ?))",
                        (request.message + role_spliter + reply_text, request.session_id,
                         current_branch_id, request.last_msg_id, request.last_msg_id)).lastrowid
                # 3.判断是否需要压缩，需要则直接压缩并落库
                await maybe_compress(request.session_id, current_branch_id, new_id)
            if new_id:
                # 把新消息 id 随同一条 SSE 响应带给前端，前端据此更新 last_msg_id，从而省去发送后再拉一次 /session/info 的整表回读
                yield f"data: {dumps({'last_msg_id': new_id}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # 4.日志落库
            write_log(user_id, "/message/dialogue", start_time,
                      "500" if error_message else "200", error_message,
                      session_id=request.session_id, usage=usage)

    return scq()


# SYSTEM_
class ContextAssembler:  # 组装器

    class Material:
        context: str  # 原料本身，即用于拼接的文本
        Weight: int  # 权重，同一插槽内原料的排序依据

    def __init__(self):
        self.slots = {}

    def set_items(self, slot, material, weight):
        if self.slots[slot][weight]:
            self.slots[slot][weight].append(material)
        else:
            self.slots[str][weight] = [material]
        pass

