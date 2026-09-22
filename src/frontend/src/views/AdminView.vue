<script setup>
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { api } from '@/api'

const message = useMessage()
const dialog = useDialog()

const list = ref([])
const loading = ref(false)

const rejectModal = ref(false)
const rejectTarget = ref(null)
const rejectReason = ref('')
const rejecting = ref(false)

const viewModal = ref(false)
const viewTarget = ref(null)
const viewData = ref(null)
const viewLoading = ref(false)

async function openView(item) {
  viewTarget.value = item
  viewData.value = null
  viewModal.value = true
  viewLoading.value = true
  try {
    const res = await api.reviewTargetInfo(item.target_type, item.target_id)
    viewData.value = res.data
  } catch (e) {
    viewData.value = null
    message.error(e.message)
  } finally {
    viewLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const res = await api.reviewPendingList()
    list.value = res.data?.items || []
  } catch (e) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function typeName(t) {
  return t === 'character' ? '角色卡' : t === 'knowledge_base' ? '知识库' : t
}

function openReject(item) {
  rejectTarget.value = item
  rejectReason.value = ''
  rejectModal.value = true
}

async function confirmReject() {
  if (!rejectReason.value.trim()) return message.warning('驳回必须填写原因')
  const item = rejectTarget.value
  rejecting.value = true
  try {
    await api.reviewAudit(item.target_type, item.target_id, false, rejectReason.value.trim())
    message.success('已驳回')
    rejectModal.value = false
    await load()
  } catch (e) {
    message.error(e.message)
  } finally {
    rejecting.value = false
  }
}

function approveItem(item) {
  dialog.warning({
    title: '审核通过',
    content: `确认将「${typeName(item.target_type)}」(${item.target_id.slice(0, 8)}...) 转为公用？`,
    positiveText: '确认通过',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.reviewAudit(item.target_type, item.target_id, true, null)
        message.success('已通过，该内容已转为公用')
        await load()
      } catch (e) {
        message.error(e.message)
      }
    }
  })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="head">
      <h3>管理员 · 转公用审核</h3>
      <n-button size="small" secondary @click="load">刷新</n-button>
    </div>

    <n-spin :show="loading">
      <n-empty v-if="!list.length && !loading" description="暂无待审核申请" />
      <div class="items">
        <div v-for="(it, i) in list" :key="i" class="item">
          <div class="main">
            <div class="row">
              <n-tag size="small" type="info" round>{{ typeName(it.target_type) }}</n-tag>
              <span class="id">{{ it.target_id }}</span>
            </div>
            <div class="meta">{{ it.user_id.slice(0, 8) }} ... · {{ it.applied_at }}</div>
          </div>
          <div class="ops">
            <n-button size="small" secondary @click="openView(it)">查看</n-button>
            <n-button size="small" type="primary" @click="approveItem(it)">通过</n-button>
            <n-button size="small" type="error" @click="openReject(it)">驳回</n-button>
          </div>
        </div>
      </div>
    </n-spin>

    <!-- 详情预览 -->
    <n-modal v-model:show="viewModal" preset="card" title="待审内容预览" style="width: 680px; max-width: 92vw"
      :bordered="false" :footer="null">
      <n-spin :show="viewLoading">
        <template v-if="viewTarget?.target_type === 'character' && viewData">
          <div class="kv"><span class="k">名称</span><span class="v">{{ viewData.name }}</span></div>
          <div class="kv"><span class="k">可见性</span><span class="v">{{ viewData.visibility }}</span></div>
          <div class="kv"><span class="k">温度</span><span class="v">{{ viewData.temperature }}</span></div>
          <div class="kv"><span class="k">Max Tokens</span><span class="v">{{ viewData.max_tokens }}</span></div>
          <div class="block">
            <div class="k">开场白</div>
            <pre class="p">{{ viewData.opening_remarks || '（无）' }}</pre>
          </div>
          <div class="block">
            <div class="k">系统提示词</div>
            <pre class="p">{{ viewData.system_prompt || '（无）' }}</pre>
          </div>
          <div class="kv"><span class="k">关联知识库</span>
            <span class="v">{{ viewData.knowledge_bases?.length ? viewData.knowledge_bases.map((k)=>k.name).join('、') : '（无）' }}</span>
          </div>
        </template>
        <template v-else-if="viewTarget?.target_type === 'knowledge_base' && viewData">
          <div class="kv"><span class="k">名称</span><span class="v">{{ viewData.name }}</span></div>
          <div class="kv"><span class="k">可见性</span><span class="v">{{ viewData.visibility }}</span></div>
          <div class="block">
            <div class="k">描述</div>
            <pre class="p">{{ viewData.description || '（无）' }}</pre>
          </div>
          <div class="block">
            <div class="k">条目（{{ viewData.items?.length || 0 }}）</div>
            <n-empty v-if="!viewData.items || !viewData.items.length" description="无条目" size="small" style="margin-top: 8px" />
            <div v-for="(it, k) in viewData.items" :key="k" class="item-card">
              <div class="it-title">{{ it.title }}</div>
              <pre class="p">{{ it.content }}</pre>
            </div>
          </div>
        </template>
        <n-empty v-else-if="!viewLoading" description="无法加载该内容" size="small" style="margin-top: 24px" />
      </n-spin>
    </n-modal>

    <!-- 驳回弹窗 -->
    <n-modal v-model:show="rejectModal" preset="card" title="驳回申请" style="width: 440px" :bordered="false">
      <div style="margin-bottom: 12px">
        驳回「{{ typeName(rejectTarget?.target_type) }}」({{ rejectTarget?.target_id }})：
      </div>
      <n-input v-model:value="rejectReason" type="textarea" placeholder="驳回原因（必填）"
        :autosize="{ minRows: 3, maxRows: 6 }" />
      <template #footer>
        <n-space justify="end">
          <n-button @click="rejectModal = false">取消</n-button>
          <n-button type="primary" :loading="rejecting" @click="confirmReject">确认驳回</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  padding: 24px;
  overflow-y: auto;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.items {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 720px;
}
.item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--n-border-color, #eee);
  border-radius: 8px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.id {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
  word-break: break-all;
}
.meta {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}
.ops {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.kv {
  display: flex;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 8px;
}
.kv .k {
  color: var(--n-text-color-3, #999);
  flex-shrink: 0;
  width: 110px;
}
.kv .v {
  word-break: break-word;
}
.block {
  margin: 10px 0;
  font-size: 13px;
}
.block .k {
  color: var(--n-text-color-3, #999);
  margin-bottom: 4px;
}
.p {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  line-height: 1.6;
  background: var(--n-color-2, #f5f5f5);
  border-radius: 6px;
  padding: 8px 10px;
}
.item-card {
  border: 1px solid var(--n-border-color, #eee);
  border-radius: 6px;
  padding: 8px 10px;
  margin-top: 8px;
}
.it-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.item-card .p {
  background: transparent;
  padding: 0;
}
</style>