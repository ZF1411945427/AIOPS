<template>
  <div class="dashboard-designer">
    <!-- 顶部工具栏 -->
    <div class="designer-toolbar">
      <div class="toolbar-left">
        <el-select v-model="currentLayoutId" placeholder="选择仪表盘" @change="loadLayout" style="width: 200px">
          <el-option v-for="l in layouts" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
        <el-button @click="showNewDialog = true" :icon="Plus" plain>新建</el-button>
        <el-button @click="saveLayout" :icon="Check" type="primary" :loading="saving">保存</el-button>
        <el-button v-if="currentLayoutId && !currentLayoutIsDefault" @click="setDefault" :icon="Star" plain>设为默认</el-button>
        <el-button v-if="currentLayoutId" @click="deleteLayout" :icon="Delete" type="danger" plain>删除</el-button>
      </div>
      <div class="toolbar-right">
        <el-button-group>
          <el-button :type="editMode ? 'primary' : ''" @click="editMode = true">编辑模式</el-button>
          <el-button :type="!editMode ? 'primary' : ''" @click="editMode = false">预览模式</el-button>
        </el-button-group>
      </div>
    </div>

    <div class="designer-body">
      <!-- 左侧卡片库 -->
      <div v-if="editMode" class="card-library">
        <div class="library-title">卡片库</div>
        <div class="library-hint">拖拽到右侧画布</div>
        <div
          v-for="ct in cardTypes"
          :key="ct.type"
          class="library-card"
          draggable="true"
          @dragstart="onDragStart($event, ct)"
        >
          <el-icon :size="16"><component :is="getIcon(ct.icon)" /></el-icon>
          <div class="lib-card-info">
            <div class="lib-card-title">{{ ct.title }}</div>
            <div class="lib-card-desc">{{ ct.desc }}</div>
          </div>
        </div>
      </div>

      <!-- 右侧画布 -->
      <div class="canvas-area">
        <div
          class="grid-canvas"
          :class="{ 'edit-mode': editMode }"
          @dragover.prevent
          @drop="onDrop"
        >
          <div v-if="cards.length === 0" class="empty-canvas">
            <el-icon :size="48"><DataBoard /></el-icon>
            <p>从左侧拖拽卡片到此处开始构建仪表盘</p>
          </div>

          <div
            v-for="card in cards"
            :key="card.id"
            class="grid-card"
            :style="cardStyle(card)"
            @mousedown.stop="editMode && startDrag($event, card)"
          >
            <div class="grid-card-header">
              <span class="grid-card-title">{{ card.title }}</span>
              <div v-if="editMode" class="grid-card-actions">
                <el-icon @click.stop="removeCard(card)" title="删除"><Close /></el-icon>
              </div>
            </div>
            <div class="grid-card-body">
              <component :is="getCardComponent(card.type)" :card="card" />
            </div>
            <div v-if="editMode" class="grid-card-resize" @mousedown.stop="startResize($event, card)">
              <el-icon :size="12"><Rank /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建布局对话框 -->
    <el-dialog v-model="showNewDialog" title="新建仪表盘布局" width="400px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newLayout.name" placeholder="如：我的看板" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newLayout.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="共享">
          <el-switch v-model="newLayout.is_shared" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewDialog = false">取消</el-button>
        <el-button type="primary" @click="createLayout">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Check, Delete, Star, Close, Rank, DataBoard,
  Box, WarningFilled, Tickets, TrendCharts, PieChart, Warning,
  DataLine, Bell, Timer, CircleCheck, Connection, Setting,
  Cpu, Message, Monitor
} from '@element-plus/icons-vue'
import request from '@/api/request'

const ICON_MAP = {
  Box, WarningFilled, Tickets, DataBoard, TrendCharts, PieChart,
  Warning, DataLine, Bell, Timer, CircleCheck, Connection,
  Setting, Cpu, Message, Monitor
}
function getIcon(name) { return ICON_MAP[name] || Monitor }

const layouts = ref([])
const currentLayoutId = ref(null)
const currentLayoutIsDefault = ref(false)
const cards = ref([])
const cardTypes = ref([])
const editMode = ref(true)
const saving = ref(false)
const showNewDialog = ref(false)
const newLayout = ref({ name: '', description: '', is_shared: false })

const draggingNew = ref(null)
const draggingCard = ref(null)
const resizingCard = ref(null)
const COLS = 12
const ROW_H = 80

const CARD_COMPONENTS = {
  'stat-asset': defineAsyncComponent(() => import('@/components/dashboard/StatAssetCard.vue')),
  'stat-alert': defineAsyncComponent(() => import('@/components/dashboard/StatAlertCard.vue')),
  'stat-incident': defineAsyncComponent(() => import('@/components/dashboard/StatIncidentCard.vue')),
  'stat-health': defineAsyncComponent(() => import('@/components/dashboard/StatHealthCard.vue')),
  'stat-datasource': defineAsyncComponent(() => import('@/components/dashboard/StatDatasourceCard.vue')),
  'stat-rule': defineAsyncComponent(() => import('@/components/dashboard/StatRuleCard.vue')),
  'chart-alert-trend': defineAsyncComponent(() => import('@/components/dashboard/ChartAlertTrendCard.vue')),
  'chart-asset-type': defineAsyncComponent(() => import('@/components/dashboard/ChartAssetTypeCard.vue')),
  'chart-severity': defineAsyncComponent(() => import('@/components/dashboard/ChartSeverityCard.vue')),
  'chart-health-trend': defineAsyncComponent(() => import('@/components/dashboard/ChartHealthTrendCard.vue')),
  'chart-mttr': defineAsyncComponent(() => import('@/components/dashboard/ChartMttrCard.vue')),
  'chart-remediation': defineAsyncComponent(() => import('@/components/dashboard/ChartRemediationCard.vue')),
  'chart-ai-tool': defineAsyncComponent(() => import('@/components/dashboard/ChartAiToolCard.vue')),
  'chart-notification': defineAsyncComponent(() => import('@/components/dashboard/ChartNotificationCard.vue')),
  'list-recent-alerts': defineAsyncComponent(() => import('@/components/dashboard/ListRecentAlertsCard.vue')),
  'list-recent-incidents': defineAsyncComponent(() => import('@/components/dashboard/ListRecentIncidentsCard.vue')),
}
function getCardComponent(type) { return CARD_COMPONENTS[type] || Monitor }

function cardStyle(card) {
  return {
    left: (card.x / COLS * 100) + '%',
    top: (card.y * ROW_H) + 'px',
    width: (card.w / COLS * 100) + '%',
    height: (card.h * ROW_H) + 'px',
  }
}

function onDragStart(e, ct) {
  draggingNew.value = ct
  e.dataTransfer.effectAllowed = 'copy'
}

function onDrop(e) {
  e.preventDefault()
  if (!draggingNew.value) return
  const canvas = e.currentTarget
  const rect = canvas.getBoundingClientRect()
  const xPct = (e.clientX - rect.left) / rect.width
  const yPx = e.clientY - rect.top
  const x = Math.round(xPct * COLS)
  const y = Math.round(yPx / ROW_H)
  const ct = draggingNew.value
  cards.value.push({
    id: 'c' + Date.now(),
    type: ct.type,
    title: ct.title,
    x: Math.min(x, COLS - ct.w),
    y: Math.max(0, y),
    w: ct.w,
    h: ct.h,
  })
  draggingNew.value = null
}

function startDrag(e, card) {
  draggingCard.value = { card, startX: e.clientX, startY: e.clientY, origX: card.x, origY: card.y }
  const onMove = (ev) => {
    const dx = Math.round((ev.clientX - draggingCard.value.startX) / (e.currentTarget.parentElement.offsetWidth / COLS))
    const dy = Math.round((ev.clientY - draggingCard.value.startY) / ROW_H)
    card.x = Math.max(0, Math.min(COLS - card.w, draggingCard.value.origX + dx))
    card.y = Math.max(0, draggingCard.value.origY + dy)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    draggingCard.value = null
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function startResize(e, card) {
  e.stopPropagation()
  resizingCard.value = { card, startX: e.clientX, startY: e.clientY, origW: card.w, origH: card.h }
  const onMove = (ev) => {
    const dw = Math.round((ev.clientX - resizingCard.value.startX) / (e.currentTarget.parentElement.offsetWidth / COLS))
    const dh = Math.round((ev.clientY - resizingCard.value.startY) / ROW_H)
    card.w = Math.max(2, Math.min(COLS - card.x, resizingCard.value.origW + dw))
    card.h = Math.max(2, resizingCard.value.origH + dh)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    resizingCard.value = null
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function removeCard(card) {
  cards.value = cards.value.filter(c => c.id !== card.id)
}

async function loadLayouts() {
  const data = await request.get('/dashboard-config/layouts')
  layouts.value = data
  if (data.length > 0 && !currentLayoutId.value) {
    const def = data.find(l => l.is_default) || data[0]
    currentLayoutId.value = def.id
    loadLayout(def.id)
  }
}

async function loadLayout(id) {
  const data = await request.get(`/dashboard-config/layouts/${id}`)
  cards.value = data.layout_config || []
  currentLayoutIsDefault.value = data.is_default
}

async function loadCardTypes() {
  const data = await request.get('/dashboard-config/card-types')
  cardTypes.value = data.types
}

async function saveLayout() {
  if (!currentLayoutId.value) {
    ElMessage.warning('请先选择或创建一个布局')
    return
  }
  saving.value = true
  try {
    const layout = layouts.value.find(l => l.id === currentLayoutId.value)
    await request.put(`/dashboard-config/layouts/${currentLayoutId.value}`, {
      name: layout.name,
      description: layout.description || '',
      layout_config: cards.value,
      is_default: layout.is_default,
      is_shared: layout.is_shared,
    })
    ElMessage.success('仪表盘布局已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

async function createLayout() {
  if (!newLayout.value.name) {
    ElMessage.warning('请输入布局名称')
    return
  }
  try {
    const data = await request.post('/dashboard-config/layouts', {
      ...newLayout.value,
      layout_config: [],
    })
    ElMessage.success('创建成功')
    showNewDialog.value = false
    newLayout.value = { name: '', description: '', is_shared: false }
    await loadLayouts()
    currentLayoutId.value = data.id
    cards.value = []
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  }
}

async function setDefault() {
  try {
    await request.post(`/dashboard-config/layouts/${currentLayoutId.value}/set-default`)
    ElMessage.success('已设为默认')
    await loadLayouts()
  } catch (e) {
    ElMessage.error('设置失败: ' + e.message)
  }
}

async function deleteLayout() {
  try {
    await ElMessageBox.confirm('确定删除此仪表盘布局？', '提示', { type: 'warning' })
    await request.delete(`/dashboard-config/layouts/${currentLayoutId.value}`)
    ElMessage.success('已删除')
    currentLayoutId.value = null
    cards.value = []
    await loadLayouts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message)
  }
}

onMounted(async () => {
  await loadCardTypes()
  await request.post('/dashboard-config/seed-presets').catch(() => {})
  await loadLayouts()
})
</script>

<style scoped>
.dashboard-designer { height: 100%; display: flex; flex-direction: column; }
.designer-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; gap: 8px; flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; }
.designer-body { display: flex; gap: 12px; flex: 1; min-height: 0; }
.card-library {
  width: 220px; flex-shrink: 0;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 8px;
  overflow-y: auto;
}
.library-title { font-size: 14px; font-weight: 600; margin-bottom: 4px; color: var(--text-primary, #1f2937); }
.library-hint { font-size: 11px; color: var(--text-tertiary, #9ca3af); margin-bottom: 8px; }
.library-card {
  display: flex; align-items: center; gap: 8px;
  padding: 8px; margin-bottom: 4px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  cursor: grab;
  transition: all 0.15s;
}
.library-card:hover { border-color: var(--primary-color, #6366f1); background: var(--bg-hover, rgba(99,102,241,0.04)); }
.library-card:active { cursor: grabbing; }
.lib-card-title { font-size: 12px; font-weight: 600; color: var(--text-primary, #1f2937); }
.lib-card-desc { font-size: 10px; color: var(--text-tertiary, #9ca3af); }
.canvas-area { flex: 1; min-width: 0; }
.grid-canvas {
  position: relative;
  min-height: 100%;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 8px;
  transition: background 0.15s;
}
.grid-canvas.edit-mode {
  background: repeating-linear-gradient(
    0deg, transparent, transparent 79px, var(--border-color, #e5e7eb) 80px
  ),
  repeating-linear-gradient(
    90deg, transparent, transparent calc(8.333% - 1px), var(--border-color, #e5e7eb) 8.333%
  );
  background-size: 100% 80px, 100% 100%;
}
.empty-canvas {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 300px; color: var(--text-tertiary, #9ca3af);
}
.empty-canvas p { margin-top: 12px; font-size: 14px; }
.grid-card {
  position: absolute;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  padding: 8px;
  display: flex; flex-direction: column;
  overflow: hidden;
  transition: box-shadow 0.15s;
}
.grid-canvas.edit-mode .grid-card { cursor: move; border-style: dashed; }
.grid-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.grid-card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 4px; flex-shrink: 0;
}
.grid-card-title { font-size: 13px; font-weight: 600; color: var(--text-primary, #1f2937); }
.grid-card-actions { display: flex; gap: 4px; cursor: pointer; color: var(--text-tertiary, #9ca3af); }
.grid-card-actions:hover { color: var(--danger-color, #ef4444); }
.grid-card-body { flex: 1; min-height: 0; overflow: auto; }
.grid-card-resize {
  position: absolute; bottom: 0; right: 0;
  width: 16px; height: 16px;
  cursor: se-resize;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-tertiary, #9ca3af);
  opacity: 0.5;
}
.grid-card-resize:hover { opacity: 1; }
</style>
