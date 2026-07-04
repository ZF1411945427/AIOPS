<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">菜单配置</span>
        <span class="toolbar-desc">自定义侧边栏菜单结构，保存后实时生效 · <a href="/api/menu" target="_blank" style="color:var(--primary)">查看当前配置</a></span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="resetToDefault" type="warning" plain>重置默认</el-button>
        <el-button size="small" @click="loadMenu" plain>重新加载</el-button>
        <el-button size="small" type="primary" @click="saveMenu" :loading="saving">保存配置</el-button>
      </div>
    </div>

    <div class="workbench-card" style="flex:1;display:flex;flex-direction:column">
      <div class="workbench-toolbar">
        <div class="workbench-toolbar-left">
          <span style="font-size:12px;color:var(--text-secondary)">
            共 {{ menuData.length }} 个分组 · {{ totalItems }} 个菜单项
          </span>
        </div>
        <div class="workbench-toolbar-right">
          <el-input v-model="search" size="small" placeholder="搜索菜单项..." style="width:180px" clearable />
        </div>
      </div>

      <div style="flex:1;overflow:auto">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'items' }"
          default-expand-all
          node-key="key"
          style="background:transparent"
          v-if="treeData.length"
        >
          <template #default="{ node, data }">
            <span style="display:flex;align-items:center;gap:8px;font-size:13px;flex:1">
              <el-icon><component :is="getIcon(data.icon)" /></el-icon>
              <span style="font-weight:600;color:var(--text-primary)">{{ data.label }}</span>
              <el-tag size="small" type="info">{{ data.type === 'group' ? '分组' : data.path }}</el-tag>
              <span v-if="data.items && data.items.length" style="color:var(--text-muted);font-size:11px">{{ data.items.length }} 项</span>
              <el-button
                size="small"
                type="danger"
                text
                style="margin-left:auto;padding:2px 6px"
                @click.stop="removeNode(data)"
              >删除</el-button>
            </span>
          </template>
        </el-tree>

        <div v-if="!treeData.length" style="text-align:center;padding:40px;color:var(--text-muted)">
          暂无菜单数据
        </div>
      </div>

      <div style="margin-top:12px">
        <el-button size="small" @click="addGroup" type="primary" plain>+ 添加分组</el-button>
        <el-button size="small" @click="addItem" type="primary" plain>+ 添加菜单项</el-button>
        <span style="font-size:11px;color:var(--text-muted);margin-left:12px">
          直接编辑下方 JSON，保存后生效：
        </span>
      </div>

      <div style="flex:1;margin-top:8px;min-height:200px">
        <el-input
          v-model="jsonText"
          type="textarea"
          :rows="12"
          placeholder="菜单 JSON 配置..."
          style="font-family:monospace;font-size:12px"
          @change="validateJson"
        />
        <div v-if="jsonError" style="color:var(--danger);font-size:11px;margin-top:4px">{{ jsonError }}</div>
      </div>
    </div>

    <!-- 添加菜单项对话框 -->
    <el-dialog v-model="addDialogVisible" title="添加菜单项" width="440px">
      <el-form :model="addForm" label-width="80px" size="default">
        <el-form-item label="所属分组">
          <el-select v-model="addForm.groupIndex" placeholder="选择分组" style="width:100%">
            <el-option
              v-for="(g, idx) in menuData"
              :key="g.key"
              :label="g.label"
              :value="idx"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="addForm.label" placeholder="如：告警中心" />
        </el-form-item>
        <el-form-item label="Key">
          <el-input v-model="addForm.key" placeholder="如：alert-center" />
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="addForm.path" placeholder="如：/alerts" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="addForm.type">
            <el-radio value="iframe">iframe（Jinja2页面）</el-radio>
            <el-radio value="vue">vue（Vue页面）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddItem">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search, Lightning
} from '@element-plus/icons-vue'
import request from '@/api/request'

const saving = ref(false)
const menuData = ref([])
const search = ref('')
const jsonText = ref('')
const jsonError = ref('')
const addDialogVisible = ref(false)
const addForm = reactive({ groupIndex: 0, key: '', label: '', path: '', type: 'iframe' })

const ICON_MAP = {
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search, Lightning
}

function getIcon(name) {
  return ICON_MAP[name] || Monitor
}

const totalItems = computed(() => {
  return menuData.value.reduce((sum, g) => sum + (g.items ? g.items.length : 0), 0)
})

const treeData = computed(() => {
  return menuData.value.map(g => ({
    label: g.label,
    key: g.key,
    icon: g.icon,
    type: 'group',
    items: (g.items || []).map(i => ({
      label: i.label,
      key: i.key,
      path: i.path,
      type: i.type
    }))
  }))
})

function validateJson() {
  try {
    JSON.parse(jsonText.value)
    jsonError.value = ''
    return true
  } catch (e) {
    jsonError.value = 'JSON 格式错误: ' + e.message
    return false
  }
}

async function loadMenu() {
  try {
    const data = await request.get('/api/menu')
    menuData.value = Array.isArray(data) ? data : (data.menu || [])
    jsonText.value = JSON.stringify(menuData.value, null, 2)
    jsonError.value = ''
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  }
}

async function saveMenu() {
  if (!validateJson()) {
    ElMessage.error('请先修正 JSON 格式')
    return
  }
  try {
    const parsed = JSON.parse(jsonText.value)
    saving.value = true
    await request.put('/api/menu', { menu: parsed })
    menuData.value = parsed
    ElMessage.success('保存成功，刷新页面后生效')
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

async function resetToDefault() {
  try {
    await request.post('/api/menu/reset')
    await loadMenu()
    ElMessage.success('已重置为默认配置')
  } catch (e) {
    ElMessage.error('重置失败: ' + e.message)
  }
}

function addGroup() {
  const key = 'group_' + Date.now()
  menuData.value.push({ key, label: '新分组', icon: 'Setting', items: [] })
  jsonText.value = JSON.stringify(menuData.value, null, 2)
}

function addItem() {
  if (!menuData.value.length) {
    ElMessage.warning('请先添加分组')
    return
  }
  // 重置表单，默认选第一个分组
  addForm.groupIndex = 0
  addForm.key = 'item_' + Date.now()
  addForm.label = ''
  addForm.path = '/'
  addForm.type = 'iframe'
  addDialogVisible.value = true
}

function confirmAddItem() {
  if (!addForm.label.trim()) {
    ElMessage.warning('请输入菜单项名称')
    return
  }
  if (!addForm.key.trim()) {
    ElMessage.warning('请输入菜单项 key')
    return
  }
  if (!addForm.path.trim()) {
    ElMessage.warning('请输入路径')
    return
  }
  const group = menuData.value[addForm.groupIndex]
  if (!group) {
    ElMessage.error('所选分组不存在')
    return
  }
  if (!group.items) group.items = []
  // 检查 key 重复
  const allKeys = []
  menuData.value.forEach(g => {
    allKeys.push(g.key)
    if (g.items) g.items.forEach(i => allKeys.push(i.key))
  })
  if (allKeys.includes(addForm.key)) {
    ElMessage.error('key 已存在，请换一个')
    return
  }
  group.items.push({
    key: addForm.key.trim(),
    label: addForm.label.trim(),
    path: addForm.path.trim(),
    type: addForm.type,
  })
  jsonText.value = JSON.stringify(menuData.value, null, 2)
  addDialogVisible.value = false
  ElMessage.success('已添加，记得点击"保存配置"生效')
}

function removeNode(data) {
  ElMessageBox.confirm(
    `确定删除"${data.label}"吗？${data.items && data.items.length ? `该节点下有 ${data.items.length} 个子项，将一并删除。` : ''}`,
    '删除确认',
    { type: 'warning' }
  ).then(() => {
    // 先尝试作为顶层分组删除
    const gIdx = menuData.value.findIndex(g => g.key === data.key)
    if (gIdx >= 0) {
      menuData.value.splice(gIdx, 1)
    } else {
      // 作为子项删除
      for (const g of menuData.value) {
        if (g.items) {
          const iIdx = g.items.findIndex(i => i.key === data.key)
          if (iIdx >= 0) {
            g.items.splice(iIdx, 1)
            break
          }
        }
      }
    }
    jsonText.value = JSON.stringify(menuData.value, null, 2)
    ElMessage.success('已删除，记得点击"保存配置"生效')
  }).catch(() => {})
}

onMounted(loadMenu)
</script>
