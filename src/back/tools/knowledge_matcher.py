"""知识库匹配器：AC 自动机多模式匹配 + 生命周期激活（见《二轮开发计划》D12/D13）。

两层结构，避免"多会话共用同一角色卡时激活状态互相污染"：
- KnowledgeIndex：按角色卡缓存只读 AC 自动机（dict[character_id]，LRU 限容，模拟 redis）
- SessionActivation：按会话维护激活条目集合与生命周期队列（私有）

对外统一入口为 KnowledgeMatcher（全局单例 matcher），供对话链路与重激活使用。
"""
from collections import OrderedDict, deque

import ahocorasick

from src.back.config import lorebook_lifecycle


class KnowledgeIndex:
    """按角色卡缓存 AC 自动机（只读，可多会话共享）。"""

    def __init__(self, max_cards=64):
        self._cache = OrderedDict()  # character_id -> (automaton, id_to_content)
        self.max_cards = max_cards

    def get(self, character_id, conn):
        """取角色卡的 (automaton, id_to_content)，缓存未命中则查库构建。"""
        entry = self._cache.get(character_id)
        if entry is not None:
            self._cache.move_to_end(character_id)
            return entry
        entry = self._build(character_id, conn)
        self._cache[character_id] = entry
        self._cache.move_to_end(character_id)
        if len(self._cache) > self.max_cards:
            self._cache.popitem(last=False)  # LRU 淘汰最久未用
        return entry

    def _build(self, character_id, conn):
        """取角色卡关联的全部知识库条目，按 title 建自动机，value 存条目 id 列表。"""
        rows = conn.execute("""
            SELECT ki.id, ki.title, ki.content FROM knowledge_items ki
            JOIN character_kb_relations r ON r.kb_id = ki.kb_id
            WHERE r.character_id = (?)
        """, (character_id, )).fetchall()
        by_title = {}
        id_to_content = {}
        for item_id, title, content in rows:
            id_to_content[item_id] = content
            if title:
                by_title.setdefault(title, []).append(item_id)
        automaton = ahocorasick.Automaton()
        for title, ids in by_title.items():
            automaton.add_word(title, tuple(ids))
        automaton.make_automaton()
        return automaton, id_to_content

    def match(self, character_id, text, conn):
        """一次扫描文本，返回命中的条目 id 集合。"""
        automaton, _ = self.get(character_id, conn)
        matched = set()
        if automaton:
            for _, value in automaton.iter(text):
                matched.update(value)
        return matched

    def invalidate(self, character_id):
        self._cache.pop(character_id, None)


class SessionActivation:
    """按会话维护激活条目与生命周期。"""
    def __init__(self, lifecycle):
        self.lifecycle = lifecycle
        self.life_keyword = deque(maxlen=lifecycle)  # 按轮记录新命中条目 id
        self.active_ids = set()  # 当前存活（激活中）的条目 id

    def activate(self, character_id, text, conn, index):
        """每轮增量：先移除超期，再把本轮新命中并入。"""
        if len(self.life_keyword) >= self.lifecycle:
            old = self.life_keyword.popleft()
            for item_id in old:
                self.active_ids.discard(item_id)
        matched = index.match(character_id, text, conn)
        truly_new = matched - self.active_ids
        self.active_ids |= truly_new
        self.life_keyword.append(truly_new)

    def reactivate(self, character_id, user_messages, conn, index):
        """重建激活集合：清空后用最近 lifecycle 轮用户输入重放，等效于按序激活。"""
        self.life_keyword.clear()
        self.active_ids.clear()
        for msg in user_messages[-self.lifecycle:]:
            matched = index.match(character_id, msg, conn)
            truly_new = matched - self.active_ids
            self.active_ids |= truly_new
            self.life_keyword.append(truly_new)

    def get_active_content(self, character_id, conn, index):
        """拼装当前存活条目的注入文本（OOC 风格），无存活条目返回空串。"""
        if not self.active_ids:
            return ""
        _, id_to_content = index.get(character_id, conn)
        entries = [id_to_content[i] for i in self.active_ids if id_to_content.get(i)]
        if not entries:
            return ""
        return "\nOOC设定：以下内容仅作为参考信息，不要引用或复述\n<参考材料>" + "\n".join(entries) + "</参考材料>"


class KnowledgeMatcher:
    """统一入口：持有共享 KnowledgeIndex 与按会话的 SessionActivation。"""
    def __init__(self, lifecycle=lorebook_lifecycle):
        self.index = KnowledgeIndex()
        self.lifecycle = lifecycle
        self._activations = OrderedDict()  # session_id -> SessionActivation
        self.max_activations = 256

    def _activation(self, session_id):
        """
        返回会话对应的知识库匹配器,未激活则自动激活
        :param session_id: 会话id
        :return: SessionActivation
        """
        act = self._activations.get(session_id)
        if act is None:
            act = SessionActivation(self.lifecycle)
            self._activations[session_id] = act
            if len(self._activations) > self.max_activations:
                self._activations.popitem(last=False)
        else:
            self._activations.move_to_end(session_id)
        return act

    def match_knowledge(self, session_id, character_id, user_message, conn):
        """
        激活本轮命中并返回当前存活条目的注入文本
        :param session_id: 会话id
        :param character_id: 角色卡id
        :param user_message: 最新用户输入
        :param conn: 数据库连接
        :return:
        """
        act = self._activation(session_id)
        act.activate(character_id, user_message, conn, self.index)
        return act.get_active_content(character_id, conn, self.index)

    def reactivate(self, session_id, character_id, user_messages, conn):
        """重激活：会话上下文重建（/session/info）后，用最近 N 轮用户输入重建激活集合。"""
        self._activation(session_id).reactivate(character_id, user_messages, conn, self.index)

    def invalidate(self, character_id):
        self.index.invalidate(character_id)

    def invalidate_for_kb(self, kb_id, conn):
        """知识库内容变更后，失效引用它的全部角色卡缓存。"""
        rows = conn.execute("SELECT DISTINCT character_id FROM character_kb_relations WHERE kb_id=(?)",
                            (kb_id, )).fetchall()
        for (character_id, ) in rows:
            self.index.invalidate(character_id)


# 全局单例：整个应用共用一份索引缓存与激活状态（单进程 uvicorn 下有效）
matcher = KnowledgeMatcher()
