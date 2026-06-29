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
            <span style="display:flex;align-items:center;gap:8px;font-size:13px">
              <el-icon><component :is="getIcon(data.icon)" /></el-icon>
              <span style="font-weight:600;color:var(--text-primary)">{{ data.label }}</span>
              <el-tag size="small" type="info">{{ data.type === 'group' ? '分组' : data.path }}</el-tag>
              <span v-if="data.items && data.items.length" style="color:var(--text-muted);font-size:11px">{{ data.items.length }} 项</span>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
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
  ElMessage.info('请直接在下方 JSON 中添加菜单项，保存后生效')
}

onMounted(loadMenu)
</script>
