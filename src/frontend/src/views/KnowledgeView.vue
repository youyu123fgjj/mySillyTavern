<script setup>
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { api } from '@/api'

const message = useMessage()
const dialog = useDialog()

const kbs = ref([]) // [{id,name,description,visibility}]
const loading = ref(false)

const modalOpen = ref(false)
const isNew = ref(true)
const tab = ref('base')
const form = ref({ id: '', name: '', description: '' })
const items = ref([]) // [{id,title,content}]
const saving = ref(false)
const reviewStatus = ref(null)

const itemModal = ref(false)
const itemForm = ref({ id: null, title: '', content: '' })
const itemSaving = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await api.kbList()
    kbs.value = (res.data?.items || []).map(([id, name, description]) => ({
      id, name, description: description || '', visibility: 'private'
    }))
    await Promise.all(
      kbs.value.map(async (k) => {
        try {
          const info = await api.kbInfo(k.id)
          k.visibility = info.data.visibility
        } catch {}
      })
    )
  } catch (e) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function newKb() {
  isNew.value = true
  tab.value = 'base'
  form.value = { id: '', name: '', description: '' }
  items.value = []
  reviewStatus.value = null
  modalOpen.value = true
}

async function editKb(id) {
  try {
    const res = await api.kbInfo(id)
    const d = res.data
    isNew.value = false
    tab.value = 'base'
    form.value = { id: d.id, name: d.name, description: d.description || '' }
    items.value = d.items || []
    reviewStatus.value = null
    modalOpen.value = true
    loadReviewStatus(id)
  } catch (e) {
    message.error(e.message)
  }
}

async function loadReviewStatus(id) {
  try {
    const res = await api.reviewStatus('knowledge_base', id)
    reviewStatus.value = res.data
  } catch {}
}

async function saveKb() {
  if (!form.value.name.trim()) return message.warning('请输入知识库名称')
  saving.value = true
  try {
    if (isNew.value) {
      await api.kbCreate({
        id: '', name: form.value.name.trim(), description: form.value.description,
        visibility: 'private', items: null
      })
    } else {
      await api.kbUpdateBase({
        id: form.value.id, name: form.value.name.trim(), description: form.value.description,
        visibility: '', items: null
      })
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

function removeKb(id, name) {
  dialog.warning({
    title: '删除知识库',
    content: `确定删除「${name}」？该库被角色卡关联时会被拒绝删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.kbDelete(id)
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
    await api.reviewApply('knowledge_base', id)
    message.success('已提交转公用申请')
    await loadReviewStatus(id)
  } catch (e) {
    message.error(e.message)
  }
}

// ---- 条目管理 ----
function addItem() {
  itemForm.value = { id: null, title: '', content: '' }
  itemModal.value = true
}

function editItem(it) {
  itemForm.value = { id: it.id, title: it.title, content: it.content }
  itemModal.value = true
}

async function saveItem() {
  if (!itemForm.value.title.trim() && !itemForm.value.content.trim()) {
    return message.warning('请输入条目内容')
  }
  itemSaving.value = true
  try {
    if (itemForm.value.id == null) {
      await api.kbAddItem({
        id: form.value.id, title: itemForm.value.title.trim(), content: itemForm.value.content
      })
    } else {
      await api.kbUpdateItem({
        id: itemForm.value.id, title: itemForm.value.title.trim(), content: itemForm.value.content
      })
    }
    itemModal.value = false
    const info = await api.kbInfo(form.value.id)
    items.value = info.data.items || []
    message.success('已保存')
  } catch (e) {
    message.error(e.message)
  } finally {
    itemSaving.value = false
  }
}

function removeItem(it) {
  dialog.warning({
    title: '删除条目',
    content: `确定删除「${it.title || it.content.slice(0, 20)}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.kbDeleteItem(it.id)
        items.value = items.value.filter((x) => x.id !== it.id)
        message.success('已删除')
      } catch (e) {
        message.error(e.message)
      }
    }
  })
}

// ---- 导入导出 ----
function download(name, text) {
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

async function exportKb(id, name) {
  try {
    const res = await api.kbInfo(id)
    download(`${name}.json`, JSON.stringify(res.data, null, 2))
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
const importOptions = [
  { label: '自动改名 (rename)', value: 'rename' },
  { label: '覆盖同名 (overwrite)', value: 'overwrite' }
]

function triggerImport() {
  importRef.value?.click()
}

async function onImport(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const d = JSON.parse(await file.text())
    if (!d.name) return message.warning('无效的知识库文件')
    importData.value = d
    importStrategy.value = 'rename'
    importModal.value = true
  } catch (err) {
    message.error('文件解析失败：' + err.message)
  }
}

async function confirmImport() {
  importing.value = true
  try {
    const d = importData.value
    await api.kbCreate({
      id: '', name: d.name, description: d.description || '', visibility: 'private',
      items: (d.items || []).map((it) => ({ id: null, title: it.title || '', content: it.content || '' })),
      on_conflict: importStrategy.value
    })
    message.success('导入成功')
    importModal.value = false
    importData.value = null
    await load()
  } catch (e) {
    message.error(e.message)
  } finally {
    importing.value = false
  }
}

function visTag(v) {
  return v === 'public' ? { type: 'success', text: '公用' } : { type: 'default', text: '私有' }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <n-space align="center">
        <n-button type="primary" @click="newKb">新建知识库</n-button>
        <n-button secondary @click="triggerImport">导入</n-button>
        <input ref="importRef" type="file" accept=".json,application/json" style="display: none" @change="onImport" />
      </n-space>
    </div>

    <n-spin :show="loading">
      <n-empty v-if="!kbs.length && !loading" description="暂无知识库" />
      <div class="cards">
        <div v-for="k in kbs" :key="k.id" class="card" @click="editKb(k.id)">
          <div class="card-head">
            <span class="name">{{ k.name }}</span>
            <n-tag size="small" :type="visTag(k.visibility).type" :bordered="false">{{ visTag(k.visibility).text }}</n-tag>
          </div>
          <div class="desc">{{ k.description || '暂无描述' }}</div>
          <div class="card-ops">
            <n-button size="tiny" text @click.stop="exportKb(k.id, k.name)">导出</n-button>
            <n-button size="tiny" text @click.stop="applyPublic(k.id)">转公用</n-button>
            <n-button size="tiny" text type="error" @click.stop="removeKb(k.id, k.name)">删除</n-button>
          </div>
        </div>
      </div>
    </n-spin>

    <!-- 编辑/创建弹窗 -->
    <n-modal v-model:show="modalOpen" preset="card" :title="isNew ? '新建知识库' : '编辑知识库'" style="width: 680px"
      :bordered="false">
      <n-tabs v-model:value="tab" type="line">
        <n-tab-pane name="base" tab="基础信息">
          <n-form label-placement="top">
            <n-form-item label="名称">
              <n-input v-model:value="form.name" placeholder="知识库名称" />
            </n-form-item>
            <n-form-item label="描述">
              <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            </n-form-item>
            <div v-if="reviewStatus">
              <n-alert
                :type="reviewStatus.status === 'approved' ? 'success' : reviewStatus.status === 'rejected' ? 'error' : 'info'"
                :title="'转公用状态：' + (reviewStatus.status === 'pending' ? '待审核' : reviewStatus.status === 'approved' ? '已通过' : '已驳回')">

                <div v-if="reviewStatus.status === 'rejected'">驳回原因：{{ reviewStatus.warning }}</div>
                <div v-else-if="reviewStatus.status === 'pending'">已提交申请，等待管理员审核。</div>
              </n-alert>
            </div>
          </n-form>
        </n-tab-pane>
        <n-tab-pane v-if="!isNew" name="items" tab="条目管理">
          <n-space justify="space-between" style="margin-bottom: 12px">
            <n-text depth="3">共 {{ items.length }} 条。对话时标题出现在用户输入中即命中并注入。</n-text>
            <n-button size="small" type="primary" @click="addItem">新增条目</n-button>
          </n-space>
          <n-empty v-if="!items.length" description="暂无条目" size="small" />
          <div v-for="it in items" :key="it.id" class="item">
            <div class="item-main">
              <div class="item-title">{{ it.title || '（无标题）' }}</div>
              <div class="item-content">{{ it.content }}</div>
            </div>
            <div class="item-ops">
              <n-button size="tiny" text @click="editItem(it)">编辑</n-button>
              <n-button size="tiny" text type="error" @click="removeItem(it)">删除</n-button>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
      <template #footer>
        <n-space justify="end">
          <n-button @click="modalOpen = false">关闭</n-button>
          <n-button type="primary" :loading="saving" @click="saveKb">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 条目弹窗 -->
    <n-modal v-model:show="itemModal" preset="card" :title="itemForm.id == null ? '新增条目' : '编辑条目'"
      style="width: 560px" :bordered="false">
      <n-form label-placement="top">
        <n-form-item label="标题 (用于关键字匹配)">
          <n-input v-model:value="itemForm.title" placeholder="如：人物 A 的设定" />
        </n-form-item>
        <n-form-item label="内容 (命中标题时注入的正文)">
          <n-input v-model:value="itemForm.content" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="itemModal = false">取消</n-button>
          <n-button type="primary" :loading="itemSaving" @click="saveItem">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 导入弹窗 -->
    <n-modal v-model:show="importModal" preset="card" title="导入知识库" style="width: 460px" :bordered="false">
      <div style="margin-bottom: 12px">将导入「{{ importData?.name || '未命名' }}」（{{ importData?.items?.length || 0 }} 条）</div>
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
  padding: 16px;
  overflow-y: auto;
}
.toolbar {
  margin-bottom: 16px;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.card {
  border: 1px solid var(--n-border-color, #e5e5e5);
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.name {
  font-weight: 600;
}
.desc {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-ops {
  display: flex;
  gap: 8px;
}
.item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px;
  border: 1px solid var(--n-border-color, #eee);
  border-radius: 6px;
  margin-bottom: 8px;
}
.item-title {
  font-weight: 600;
}
.item-content {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  margin-top: 4px;
  white-space: pre-wrap;
}
.item-ops {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}
</style>