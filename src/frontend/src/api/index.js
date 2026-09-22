import { post } from './http'

// ---- user ----
export const api = {
  // 返回 res.data 为 api_key 字符串
  login: (u) => post('/user/login', u),
  register: (u) => post('/user/register', u),
  settingsGet: () => post('/user/settings/get', {}),
  settingsUpdate: (s) => post('/user/settings/update', s),

  // ---- chat（角色卡）----
  chatCreate: (chat) => post('/chat/create', chat),
  chatInfo: (id) => post('/chat/get_info', { id }),
  chatList: () => post('/chat/list', {}),
  chatUpdate: (chat) => post('/chat/update', chat),
  chatDelete: (id) => post('/chat/delete', { id }),

  // ---- knowledge（知识库）----
  kbCreate: (kb) => post('/knowledge/create', kb),
  kbDelete: (id) => post('/knowledge/delete', { id }),
  kbInfo: (id) => post('/knowledge/get_info', { id }),
  kbList: () => post('/knowledge/get_list', {}),
  kbUpdateBase: (kb) => post('/knowledge/update_base', kb),
  kbUpdateItem: (item) => post('/knowledge/update_item', item),
  kbDeleteItem: (id) => post('/knowledge/delete_item', { id }),
  kbAddItem: (payload) => post('/knowledge/add_item', payload), // 新条目 id 在 res.msg
  kbLink: (characterId, kbId) => post('/knowledge/link', { id1: characterId, id2: kbId }),
  kbUnlink: (characterId, kbId) => post('/knowledge/unlink', { id1: characterId, id2: kbId }),

  // ---- session（会话）----
  sessionCreate: (characterId) => post('/session/create', { id: characterId }),
  sessionDelete: (id) => post('/session/delete', { id }),
  sessionList: () => post('/session/list', {}),
  sessionUpdate: (id, title) => post('/session/update', { id, title }),
  sessionInfo: (sessionId, messagesLength = 100) =>
    post('/session/info', { session_id: sessionId, messages_length: messagesLength }),
  branchList: (sessionId) => post('/session/branch/list', { id: sessionId }),
  branchSwitch: (sessionId, branchId) => post('/session/branch/switch', { session_id: sessionId, branch_id: branchId }),
  branchCreate: (sessionId, fromMsgId, branchName) =>
    post('/session/branch/create', { session_id: sessionId, from_msg_id: fromMsgId, branch_name: branchName }),

  // ---- review（公用审核）----
  reviewApply: (targetType, targetId) => post('/review/apply', { target_type: targetType, target_id: targetId }),
  reviewStatus: (targetType, targetId) => post('/review/status', { target_type: targetType, target_id: targetId }),
  reviewPendingList: () => post('/review/pending_list', {}),
  reviewTargetInfo: (targetType, targetId) => post('/review/target_info', { target_type: targetType, target_id: targetId }),
  reviewAudit: (targetType, targetId, approved, warning) =>
    post('/review/audit', { target_type: targetType, target_id: targetId, approved, warning }),

  // ---- log ----
  logUsage: (query = {}) => post('/log/usage', query),
  logList: (page = 1, limit = 20) => post('/log/list', { page, limit })
}

export function notifyMessage(err, message) {
  window.dispatchEvent(new CustomEvent('toast', { detail: message || '成功' }))
}