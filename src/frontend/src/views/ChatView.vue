<script setup>
import { onMounted, ref, computed, nextTick } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { api } from '@/api'

const message = useMessage()
const dialog = useDialog()

const sessions = ref([]) // [{id, characterId, title, characterName}]
const characters = ref([]) // [{id, name}] 供新建会话
const activeId = ref(null)
const loading = ref(false)

const currentSession = computed(() => sessions.value.find((s) => s.id === activeId.value))

// 会话内容与对话状态
const head = ref(null)
const messages = ref([]) // [{id?, user, assistant, opening?}]
const lastMsgId = ref(0)
const draft = ref('')
const streaming = ref(false)
const branchList = ref([])

const messageListEl = ref(null)
// 左侧会话列表：小屏默认收起，避免占满移动端
const sideCollapsed = ref(false)
if (typeof window !== 'undefined') sideCollapsed.value = window.innerWidth < 768

function parseSessionRowPage(r) {
  // sessions 列序: id,user_id,character_id,title,system_prompt,opening_remarks,
  //                current_branch_id,next_branch_id,created_at,updated_at
  return { id: r[0], characterId: r[2], title: r[3] || '新会话' }
}

async function loadCharacters() {
  try {
    const res = await api.chatList()
    characters.value = Object.values(res.data || {}).map((c) => ({ id: c.id, name: c.chat_name }))
  } catch (e) {
    message.error(e.message)
  }
}

async function loadSessions() {
  loading.value = true
  try {
    const res = await api.sessionList()
    const rows = Array.isArray(res.data) ? res.data : []
    const nameById = Object.fromEntries(characters.value.map((c) => [c.id, c.name]))
    sessions.value = rows.map((r) => {
      const s = parseSessionRowPage(r)
      return { ...s, characterName: nameById[s.characterId] || '未知角色' }
    })
  } catch (e) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function renderMessages(info) {
  lastMsgId.value = info.head?.last_msg_id ?? 0
  const list = []
  if (info.head?.opening_remarks) {
    list.push({ user: null, assistant: info.head.opening_remarks, opening: true })
  }
  for (const m of info.body || []) {
    list.push({ id: m.id, previous_id: m.previous_id, user: m.content[0] || '', assistant: m.content[1] || '' })
  }
  return list
}

async function openSession(id) {
  activeId.value = id
  loadBranchList()
  await loadConversation()
}

async function loadConversation() {
  if (!activeId.value) return
  try {
    const res = await api.sessionInfo(activeId.value, 200)
    head.value = res.data.head
    messages.value = renderMessages(res.data)
    await scrollBottom(true)
  } catch (e) {
    message.error(e.message)
  }
}

const createModal = ref(false)
const createCharId = ref(null)
const creating = ref(false)
const renameModal = ref(false)
const renameValue = ref('')

async function createSession() {
  if (!characters.value.length) {
    message.info('请先在「角色卡」页创建角色')
    return
  }
  createModal.value = true
}

async function confirmCreate() {
  if (!createCharId.value) return message.warning('请选择角色卡')
  creating.value = true
  try {
    const res = await api.sessionCreate(createCharId.value)
    message.success('会话已创建')
    createModal.value = false
    createCharId.value = null
    await loadSessions()
    const created = sessions.value.find((s) => s.id === res.data.session_id)
    if (created) openSession(created.id)
  } catch (e) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

function renameSession() {
  if (!currentSession.value) return
  renameValue.value = currentSession.value.title
  renameModal.value = true
}

async function confirmRename() {
  const s = currentSession.value
  if (!s) return
  try {
    await api.sessionUpdate(s.id, renameValue.value.trim())
    s.title = renameValue.value.trim()
    message.success('已重命名')
    renameModal.value = false
  } catch (e) {
    message.error(e.message)
  }
}

async function scrollBottom(force = false) {
  await nextTick()
  const el = messageListEl.value
  if (el) el.scrollTop = el.scrollHeight
}

/** 核心发送：把 text 拼成新一轮发出并流式渲染 assistant（用户文本由调用方先行本地渲染） */
async function doSend(text) {
  const userText = (text || '').trim()
  if (!userText || !activeId.value) return false
  if (streaming.value) {
    message.warning('正在生成中...')
    return false
  }

  // previous_id 记录本轮挂链的分叉点（= 请求的 last_msg_id），供重新生成/编辑时定位
  messages.value.push({ user: userText, assistant: '', pending: true, previous_id: lastMsgId.value })
  streaming.value = true
  editingIndex.value = null
  await scrollBottom()
  const lastMsg = messages.value[messages.value.length - 1]

  try {
    const resp = await fetch('/message/dialogue', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: localStorage.getItem('api_key') || ''
      },
      body: JSON.stringify({ last_msg_id: lastMsgId.value, session_id: activeId.value, message: userText })
    })
    if (!resp.ok) {
      let msg = '请求失败'
      try {
        const j = (await resp.json()) || {}
        msg = j.msg || msg
      } catch {}
      throw new Error(msg)
    }
    if (!resp.body) throw new Error('无响应流')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let errorText = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const evt = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const dataLine = evt
          .split('\n')
          .find((l) => l.startsWith('data:'))
        if (!dataLine) continue
        const data = dataLine.slice(5).trim()
        if (data === '[DONE]') continue
        try {
          const parsed = JSON.parse(data)
          // 后端在响应末尾送出的 {last_msg_id} 帧：保存新消息 id，下次发送接着挂链
          if (parsed.last_msg_id) {
            lastMsgId.value = parsed.last_msg_id
            lastMsg.id = parsed.last_msg_id
          }
          if (parsed.content) lastMsg.assistant += parsed.content
          else if (parsed.error) errorText = parsed.error
          await scrollBottom()
        } catch {}
      }
    }
    if (errorText) {
      message.error(errorText)
      lastMsg.error = errorText
    }
  } catch (e) {
    message.error(e.message)
    lastMsg.error = e.message
  } finally {
    lastMsg.pending = false
    streaming.value = false
    // 用户文本已在请求前本地渲染；新 last_msg_id 已随 SSE 带回。不再整表回读 /session/info。
  }
  return true
}

function sendMessage() {
  if (!draft.value.trim()) return
  const text = draft.value.trim()
  draft.value = ''
  doSend(text)
}

// ---- DeepSeek 式分支：编辑 / 重新生成某一轮时，自动在上一轮处分叉并重发 ----
const editingIndex = ref(null)
const editText = ref('')

function startEdit(index) {
  if (streaming.value) return
  editingIndex.value = index
  editText.value = messages.value[index]?.user || ''
}

function cancelEdit() {
  editingIndex.value = null
  editText.value = ''
}

function regenerate(index) {
  const turn = messages.value[index]
  if (!turn || turn.opening) return
  forkTurn(index, turn.user)
}

async function submitEdit() {
  const index = editingIndex.value
  if (index == null) return
  const text = editText.value.trim()
  if (!text) return message.warning('内容不能为空')
  await forkTurn(index, text)
}

function onEditKey(e) {
  if (e.key !== 'Enter') return
  if (e.isComposing) return
  if (e.shiftKey) return
  e.preventDefault()
  submitEdit()
}

/**
 * 编辑 / 重新生成某轮：先以「该轮的上一条消息」为分叉点新建分支并切过去，
 * 再裁剪掉该轮及之后的内容，把新文本作为新一轮发出（自动落在新分支上）。
 */
async function forkTurn(index, text) {
  const turn = messages.value[index]
  if (!turn || turn.opening || streaming.value) return
  const fromMsgId = typeof turn.previous_id === 'number' ? turn.previous_id : 0
  try {
    const res = await api.branchCreate(activeId.value, fromMsgId, '')
    lastMsgId.value = res.data.last_msg_id
    if (head.value) head.value.current_branch_id = res.data.branch_id
    // 新分支只保留分叉点之前的前缀；当前轮及之后留在原分支，从列表里裁掉
    messages.value = messages.value.slice(0, index)
    await loadBranchList()
    await doSend(text)
  } catch (e) {
    message.error(e.message)
  }
}

function deleteSession() {
  const s = currentSession.value
  if (!s) return
  dialog.warning({
    title: '删除会话',
    content: `确定删除「${s.title}」？此操作不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.sessionDelete(s.id)
        message.success('已删除')
        sessions.value = sessions.value.filter((x) => x.id !== s.id)
        if (activeId.value === s.id) {
          activeId.value = null
          head.value = null
          messages.value = []
        }
      } catch (e) {
        message.error(e.message)
      }
    }
  })
}

async function loadBranchList() {
  if (!activeId.value) return
  try {
    const res = await api.branchList(activeId.value)
    branchList.value = res.data || []
  } catch (e) {
    message.error(e.message)
  }
}

async function switchBranch(branchId) {
  try {
    await api.branchSwitch(activeId.value, branchId)
    message.success('已切换分支')
    await loadBranchList()
    await loadConversation()
  } catch (e) {
    message.error(e.message)
  }
}

function onEnter(e) {
  // 仅在按下 Enter 时才发送；其他按键（含组合输入）不拦截、不发送
  if (e.key !== 'Enter') return
  if (e.isComposing) return
  if (e.shiftKey) return
  e.preventDefault()
  sendMessage()
}

onMounted(async () => {
  await loadCharacters()
  await loadSessions()
})
</script>

<template>
  <div class="chat">
    <!-- 左侧会话列表 -->
    <div class="side" :class="{ collapsed: sideCollapsed }">
      <div class="side-head">
        <div class="side-head-main">
          <n-button type="primary" size="small" block @click="createSession">新建会话</n-button>
        </div>
        <n-button quaternary size="small" class="side-close" @click="sideCollapsed = true">
          ✕
        </n-button>
      </div>
      <n-scrollbar class="side-list">
        <n-empty v-if="!sessions.length && !loading" description="暂无会话" size="small"
          style="margin-top: 40px" />
        <div v-for="s in sessions" :key="s.id" class="session-item" :class="{ active: s.id === activeId }"
          @click="openSession(s.id)">
          <div class="session-title">{{ s.title }}</div>
          <div class="session-sub">{{ s.characterName }}</div>
        </div>
      </n-scrollbar>
    </div>
    <div v-if="!sideCollapsed" class="side-mask" @click="sideCollapsed = true"></div>

    <!-- 右侧对话 -->
    <div v-if="currentSession" class="main-pane">
      <div class="chat-head">
        <div class="chat-title">
          <n-button quaternary size="small" class="side-toggle" @click="sideCollapsed = !sideCollapsed">
            <template #icon>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"
                stroke-linecap="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </template>
          </n-button>
          <div class="title-text">{{ currentSession.title }}</div>
          <n-tag size="small" type="info" round>{{ currentSession.characterName }}</n-tag>
        </div>
        <div class="chat-ops">
          <n-popover trigger="click">
            <template #trigger>
              <n-button size="small" secondary>分支 ({{ branchList.length }})</n-button>
            </template>
            <div class="branch-panel">
              <div v-for="b in branchList" :key="b.branch_id" class="branch-item"
                :class="{ active: b.branch_id === head?.current_branch_id }">
                <div class="branch-info" @click="switchBranch(b.branch_id)">
                  <div>{{ b.branch_name }} <n-tag size="tiny">{{ b.message_count }}</n-tag></div>
                  <n-text depth="3" class="branch-preview">{{ b.preview || '（无消息）' }}</n-text>
                </div>
              </div>
            </div>
          </n-popover>
          <n-button size="small" secondary @click="renameSession">重命名</n-button>
          <n-button size="small" secondary type="error" @click="deleteSession">删除</n-button>
        </div>
      </div>

      <div ref="messageListEl" class="message-list">
        <n-scrollbar>
          <div class="messages">
            <n-empty v-if="!messages.length" description="开始对话吧" style="margin-top: 60px" />
            <div v-for="(m, i) in messages" :key="i" class="turn">
              <template v-if="m.opening">
                <div class="bubble assistant opening">
                  <div class="role">开场白</div>
                  <div class="text" v-text="m.assistant"></div>
                </div>
              </template>
              <template v-else>
                <!-- 编辑态：输入框替换该轮用户气泡，保存后自动分叉重发 -->
                <template v-if="editingIndex === i">
                  <div class="bubble user editable">
                    <n-input
                      v-model:value="editText"
                      type="textarea"
                      :autosize="{ minRows: 2, maxRows: 6 }"
                      placeholder="修改后发送将开启新分支"
                      @keydown="onEditKey"
                    />
                    <div class="edit-ops">
                      <n-button size="tiny" type="primary" :disabled="!editText.trim() || streaming" @click="submitEdit">
                        保存并发送
                      </n-button>
                      <n-button size="tiny" @click="cancelEdit">取消</n-button>
                    </div>
                  </div>
                </template>
                <div v-else class="bubble user">
                  <div class="text" v-text="m.user"></div>
                </div>
                <div class="bubble assistant" :class="{ pending: m.pending }">
                  <div class="role">助手</div>
                  <div class="text">
                    <span v-text="m.assistant"></span>
                    <span v-if="m.pending" class="cursor">▌</span>
                    <n-text v-if="m.error" type="error" depth="3" class="err">（{{ m.error }}）</n-text>
                  </div>
                  <div v-if="!m.pending && !m.error" class="actions">
                    <n-button size="tiny" text @click="startEdit(i)">编辑</n-button>
                    <n-button size="tiny" text @click="regenerate(i)">重新生成</n-button>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </n-scrollbar>
      </div>

      <div class="input-bar">
        <n-input
          v-model:value="draft"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 6 }"
          :disabled="streaming"
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          @keydown="onEnter"
        />
        <n-button type="primary" :loading="streaming" :disabled="!draft.trim()" @click="sendMessage">
          发送
        </n-button>
      </div>
    </div>

    <div v-else class="main-pane empty">
      <div class="chat-head">
        <n-button quaternary size="small" class="side-toggle" @click="sideCollapsed = !sideCollapsed">
          <template #icon>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </template>
        </n-button>
      </div>
      <div class="empty-state">
        <n-button type="primary" @click="createSession">新建会话</n-button>
        <n-text depth="3">从左侧选择会话，或新建一个会话开始对话</n-text>
      </div>
    </div>

    <!-- 新建会话弹窗 -->
    <n-modal v-model:show="createModal" preset="card" title="新建会话" style="width: 420px" :bordered="false">
      <n-form label-placement="top">
        <n-form-item label="选择角色卡">
          <n-select v-model:value="createCharId" :options="characters" label-field="name" value-field="id"
            placeholder="选择角色卡" filterable />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="createModal = false">取消</n-button>
          <n-button type="primary" :loading="creating" @click="confirmCreate">创建</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 重命名弹窗 -->
    <n-modal v-model:show="renameModal" preset="card" title="重命名会话" style="width: 420px" :bordered="false">
      <n-input v-model:value="renameValue" placeholder="会话标题" @keyup.enter="confirmRename" />
      <template #footer>
        <n-space justify="end">
          <n-button @click="renameModal = false">取消</n-button>
          <n-button type="primary" @click="confirmRename">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100%;
}
.side {
  width: 260px;
  border-right: 1px solid var(--n-border-color, #eee);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  margin-left: 0;
  transition: margin-left 0.2s ease;
}
.side.collapsed {
  margin-left: -260px;
}
.side-toggle {
  flex-shrink: 0;
}
@media (max-width: 767.98px) {
  .side {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    background: var(--n-color, #fff);
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.12);
  }
  /* 抽屉打开时露出关闭按钮与点外关闭遮罩 */
  .side-close {
    display: inline-flex;
  }
  .side-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 99;
    background: rgba(0, 0, 0, 0.35);
  }
}
.side-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px;
  border-bottom: 1px solid var(--n-border-color, #eee);
}
.side-head-main {
  flex: 1;
  min-width: 0;
}
@media (min-width: 768px) {
  .side-close {
    display: none;
  }
  .side-mask {
    display: none;
  }
}
.side-list {
  flex: 1;
}
.session-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--n-border-color, #f0f0f0);
}
.session-item:hover {
  background: var(--n-color-hover, #f5f5f5);
}
.session-item.active {
  background: var(--n-primary-color, #2080f0) 33;
  border-left: 3px solid var(--n-primary-color, #2080f0);
}
.session-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-sub {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}
.main-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.main-pane.empty {
  align-items: stretch;
  justify-content: flex-start;
}
.main-pane.empty .empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
}
.chat-head {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--n-border-color, #eee);
  flex-shrink: 0;
}
.chat-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title-text {
  font-weight: 600;
}
.chat-ops {
  display: flex;
  gap: 6px;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.messages {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.turn {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bubble.user {
  align-self: flex-end;
  background: var(--n-primary-color, #2080f0);
  color: #fff;
  padding: 8px 12px;
  border-radius: 12px 12px 2px 12px;
  max-width: 80%;
  white-space: pre-wrap;
}
.bubble.assistant {
  align-self: flex-start;
  background: var(--n-color-2, #f2f3f5);
  padding: 10px 12px;
  border-radius: 2px 12px 12px 12px;
  max-width: 80%;
}
.bubble.assistant .role {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
  margin-bottom: 4px;
}
.bubble .text {
  white-space: pre-wrap;
  word-break: break-word;
}
.cursor {
  animation: blink 1s infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.bubble.user.editable {
  align-self: flex-end;
  background: var(--n-color-2, #f2f3f5);
  color: var(--n-text-color, #333);
  padding: 8px;
  border-radius: 12px 12px 2px 12px;
  max-width: 90%;
  width: 100%;
}
.bubble .edit-ops {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  justify-content: flex-end;
}
.actions {
  display: flex;
  gap: 14px;
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}
.actions :deep(.n-button__content) {
  color: var(--n-text-color-3, #999);
}
.bubble.assistant:hover .actions {
  opacity: 1;
}
.bubble.user:hover .actions {
  opacity: 1;
}
.err {
  margin-left: 4px;
}
.input-bar {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--n-border-color, #eee);
  align-items: flex-end;
  flex-shrink: 0;
}
.input-bar .n-input {
  flex: 1;
}
.branch-panel {
  width: 260px;
}
.branch-item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.branch-item:hover {
  background: var(--n-color-hover, #f5f5f5);
}
.branch-item.active {
  background: var(--n-primary-color, #2080f0) 20;
}
.branch-preview {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>