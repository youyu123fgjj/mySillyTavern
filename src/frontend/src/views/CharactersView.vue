<script setup>
import { onMounted, ref, computed } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { api } from '@/api'

const message = useMessage()
const dialog = useDialog()

const characters = ref([]) // [{id, chat_name, visibility}]
const kbs = ref([]) // 全部分知识库，用于关联
const loading = ref(false)

const modalOpen = ref(false)
const isNew = ref(true)
const form = ref({ id: '', chat_name: '', system_prompt: '', opening_remarks: '', sample_text: '', temperature: 0.7, max_tokens: 2048 })
const saving = ref(false)
const reviewStatus = ref(null)

const selectedKbs = ref([]) // 编辑中已关联的库 id
const charInfo = ref(null) // 编辑中角色的完整信息（含已关联知识库）

async function load() {
  loading.value = true
  try {
    const res = await api.chatList()
    characters.value = Object.values(res.data || {}).map((c) => ({ id: c.id, chat_name: c.chat_name, visibility: 'private' }))
    // 逐个获取 visibility（list 接口不含该字段）
    await Promise.all(
      characters.value.map(async (c) => {
        try {
          const info = await api.chatInfo(c.id)
          c.visibility = info.data.visibility
        } catch {}
      })
    )
    const kbRes = await api.kbList()
    kbs.value = (kbRes.data?.items || []).map(([id, name]) => ({ id, name }))
  } catch (e) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function newChar() {
  isNew.value = true
  form.value = { id: '', chat_name: '', system_prompt: '', opening_remarks: '', sample_text: '', temperature: 0.7, max_tokens: 2048 }
  reviewStatus.value = null
  charInfo.value = null
  selectedKbs.value = []
  modalOpen.value = true
}

async function editChar(id) {
  try {
    const res = await api.chatInfo(id)
    const d = res.data
    isNew.value = false
    charInfo.value = d
    form.value = {
      id: d.id,
      chat_name: d.chat_name,
      system_prompt: d.system_prompt || '',
      opening_remarks: d.opening_remarks || '',
      sample_text: d.sample_text || '',
      temperature: d.temperature ?? 0.7,
      max_tokens: d.max_tokens ?? 2048
    }
    selectedKbs.value = (d.knowledge_bases || []).map((k) => k.id)
    reviewStatus.value = null
    loadReviewStatus(id)
    modalOpen.value = true
  } catch (e) {
    message.error(e.message)
  }
}

async function loadReviewStatus(id) {
  try {
    const res = await api.reviewStatus('character', id)
    reviewStatus.value = res.data
  } catch {}
}

async function save() {
  if (!form.value.chat_name.trim()) return message.warning('请输入角色名字')
  if (!form.value.system_prompt.trim()) return message.warning('请输入系统提示词')
  saving.value = true
  try {
    let id = form.value.id
    if (isNew.value) {
      const res = await api.chatCreate({
        id: '', user_name: '', chat_name: form.value.chat_name.trim(),
        system_prompt: form.value.system_prompt, opening_remarks: form.value.opening_remarks,
        sample_text: form.value.sample_text,
        visibility: 'private', temperature: Number(form.value.temperature), max_tokens: Number(form.value.max_tokens)
      })
      id = res.data.chat_id
    } else {
      await api.chatUpdate({
        id: form.value.id, user_name: '', chat_name: form.value.chat_name.trim(),
        system_prompt: form.value.system_prompt, opening_remarks: form.value.opening_remarks,
        sample_text: form.value.sample_text,
        visibility: '', temperature: Number(form.value.temperature), max_tokens: Number(form.value.max_tokens)
      })
    }
    // 同步知识库关联：先解除全部，再勾选重建
    const oldLinks = (charInfo.value?.knowledge_bases || []).map((k) => k.id)
    for (const oldId of oldLinks) {
      if (!selectedKbs.value.includes(oldId)) await api.kbUnlink(id, oldId)
    }
    for (const newId of selectedKbs.value) {
      if (!oldLinks.includes(newId)) await api.kbLink(id, newId)
    }
    message.success('保存成功')
    modalOpen.value = false
    await load()
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

function removeChar(id, name) {
  dialog.warning({
    title: '删除角色卡',
    content: `确定删除「${name}」？关联会话与知识库关联将一并删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.chatDelete(id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error(e.message)
      }
    }
  })
}

async function applyPublic(id) {
  try {
    await api.reviewApply('character', id)
    message.success('已提交转公用申请')
    await loadReviewStatus(id)
  } catch (e) {
    message.error(e.message)
  }
}

function download(filename, text) {
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportChar(id, name) {
  try {
    const res = await api.chatInfo(id)
    const d = res.data
    download(`${name}.json`, JSON.stringify(d, null, 2))
    message.success('已导出')
  } catch (e) {
    message.error(e.message)
  }
}

const importRef = ref(null)
const importModal = ref(false)
const importData = ref(null)
const importStrategy = ref('rename')
const importing = ref(false)

function triggerImport() {
  importRef.value?.click()
}

const importOptions = [
  { label: '自动改名 (rename)', value: 'rename' },
  { label: '覆盖同名 (overwrite)', value: 'overwrite' }
]

async function onImport(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const text = await file.text()
    const d = JSON.parse(text)
    if (!d.system_prompt) {
      message.warning('无效的角色卡文件：缺少 system_prompt')
      return
    }
    importData.value = d
    importStrategy.value = 'rename'
    importModal.value = true
  } catch (err) {
    message.error('文件解析失败：' + err.message)
  }
}

async function confirmImport() {
  if (!importData.value) return
  importing.value = true
  try {
    const d = importData.value
    await api.chatCreate({
      id: '', user_name: '', chat_name: d.chat_name || '导入角色',
      system_prompt: d.system_prompt || '', opening_remarks: d.opening_remarks || '',
      sample_text: d.sample_text || '',
      visibility: 'private', temperature: d.temperature ?? 0.7, max_tokens: d.max_tokens ?? 2048,
      on_conflict: importStrategy.value
    })
    message.success('导入成功')
    importModal.value = false
    importData.value = null
    await load()
  } catch (err) {
    message.error(err.message)
  } finally {
    importing.value = false
  }
}

function visibilityTag(v) {
  return v === 'public' ? { type: 'success', text: '公用' } : { type: 'default', text: '私有' }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <n-space align="center">
        <n-button type="primary" @click="newChar">新建角色卡</n-button>
        <n-button secondary @click="triggerImport">导入</n-button>
        <input ref="importRef" type="file" accept=".json,application/json" style="display: none" @change="onImport" />
      </n-space>
    </div>

    <div class="grid">
      <n-empty v-if="!loading && !characters.length" description="暂无角色卡" />
      <n-spin :show="loading">
        <div class="cards">
          <div v-for="c in characters" :key="c.id" class="card" @click="editChar(c.id)">
            <div class="card-head">
              <span class="name">{{ c.chat_name }}</span>
              <n-tag size="small" :type="visibilityTag(c.visibility).type" :bordered="false">
                {{ visibilityTag(c.visibility).text }}
              </n-tag>
            </div>
            <div class="card-ops">
              <n-button size="tiny" text @click.stop="exportChar(c.id, c.chat_name)">导出</n-button>
              <n-button size="tiny" text @click.stop="applyPublic(c.id)">转公用</n-button>
              <n-button size="tiny" text type="error" @click.stop="removeChar(c.id, c.chat_name)">删除</n-button>
            </div>
          </div>
        </div>
      </n-spin>
    </div>

    <!-- 编辑/创建弹窗 -->
    <n-modal v-model:show="modalOpen" preset="card" :title="isNew ? '新建角色卡' : '编辑角色卡'" style="width: 640px"
      :bordered="false">
      <n-form label-placement="top">
        <n-form-item label="角色名字">
          <n-input v-model:value="form.chat_name" placeholder="角色名字" />
        </n-form-item>
        <n-form-item label="系统提示词 (System Prompt)">
          <n-input v-model:value="form.system_prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
            placeholder="描述角色的人设、性格、说话风格" />
        </n-form-item>
        <n-form-item label="开场白 (助手的首个消息)">
          <n-input v-model:value="form.opening_remarks" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="新会话时助手自动发送的消息，留空则无" />
        </n-form-item>
        <n-form-item label="示例对话 (sample_text)">
          <n-input v-model:value="form.sample_text" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="一段角色示例对话，用于少量示例 (few-shot) 引导；无摘要且填写此项时自动注入" />
        </n-form-item>
        <n-space>
          <n-form-item label="温度 (temperature)">
            <n-input-number v-model:value="form.temperature" :min="0" :max="2" :step="0.1" style="width: 160px" />
          </n-form-item>
          <n-form-item label="最大输出 tokens">
            <n-input-number v-model:value="form.max_tokens" :min="1" :max="8192" :step="128" style="width: 200px" />
          </n-form-item>
        </n-space>
        <n-form-item label="关联知识库">
          <n-select v-model:value="selectedKbs" multiple :options="kbs" label-field="name" value-field="id"
            :placeholder="kbs.length ? '选择参与对话知识注入的库' : '暂无知识库，可先到「知识库」页创建'" filterable />
        </n-form-item>
        <div v-if="reviewStatus">
          <n-alert :type="reviewStatus.status === 'approved' ? 'success' : reviewStatus.status === 'rejected' ? 'error' : 'info'"
            :title="'转公用状态：' + (reviewStatus.status === 'pending' ? '待审核' : reviewStatus.status === 'approved' ? '已通过' : '已驳回')">

            <div v-if="reviewStatus.status === 'rejected'">驳回原因：{{ reviewStatus.warning }}</div>
            <div v-else-if="reviewStatus.status === 'pending'">已提交申请，等待管理员审核（仅本机管理员可操作）。</div>
          </n-alert>
        </div>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="modalOpen = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 导入弹窗 -->
    <n-modal v-model:show="importModal" preset="card" title="导入角色卡" style="width: 460px" :bordered="false">
      <div class="import-name">将导入「{{ importData?.chat_name || '未命名' }}」</div>
      <n-form-item label="重名处理策略">
        <n-select v-model:value="importStrategy" :options="importOptions" />
      </n-form-item>
      <template #footer>
        <n-space justify="end">
          <n-button @click="importModal = false">取消</n-button>
          <n-button type="primary" :loading="importing" @click="confirmImport">导入</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow-y: auto;
}
.toolbar {
  margin-bottom: 16px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.card {
  border: 1px solid var(--n-border-color, #e5e5e5);
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-ops {
  display: flex;
  gap: 8px;
}
</style>