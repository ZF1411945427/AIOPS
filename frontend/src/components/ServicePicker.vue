<template>
  <div class="sp-wrapper">
    <input
      class="sp-input"
      readonly
      :value="selectedLabel"
      :placeholder="placeholder"
      @click="open"
    />
    <button v-if="modelValue" class="sp-clear" type="button" @click.stop.prevent="clear" title="清除">×</button>
    <button type="button" class="sp-btn" @click.stop.prevent="open">📋</button>

    <div v-if="visible" class="sp-overlay" @click.self="close">
      <div class="sp-dialog">
        <div class="sp-header">
          <span>选择服务</span>
          <button type="button" class="sp-close" @click="close">×</button>
        </div>
        <div class="sp-toolbar">
          <input
            v-model="keyword"
            class="sp-search"
            placeholder="搜索服务名称..."
            @input="onSearch"
            ref="searchInput"
          />
        </div>
        <div class="sp-list">
          <div v-if="loading" class="sp-loading">加载中...</div>
          <div v-else-if="items.length === 0" class="sp-empty">无匹配结果</div>
          <div
            v-for="item in items"
            :key="item.id"
            class="sp-item"
            :class="{ active: item.id === selectedId }"
            @click="pick(item)"
          >
            <span class="sp-name">{{ item.name }}</span>
            <span class="sp-meta">{{ item.ci_type }}</span>
          </div>
        </div>
        <div class="sp-footer">
          <button type="button" class="sp-page-btn" :disabled="page <= 1" @click="prevPage">上一页</button>
          <span class="sp-page-info">第 {{ page }} / {{ totalPages || 1 }} 页</span>
          <button type="button" class="sp-page-btn" :disabled="page >= totalPages" @click="nextPage">下一页</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import request from '@/api/request'

const props = defineProps({
  modelValue: { type: [Number, String], default: null },
  placeholder: { type: String, default: '点击选择服务...' },
  ciTypes: { type: Array, default: () => ['service', 'business_app', 'api_service'] },
})
const emit = defineEmits(['update:modelValue'])

const visible = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const items = ref([])
const loading = ref(false)
const total = ref(0)
const searchInput = ref(null)
const selectedId = ref(props.modelValue)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value))
)
const selectedLabel = ref('')

watch(() => props.modelValue, async (val) => {
  selectedId.value = val
  if (val) await loadLabel(val)
}, { immediate: true })

async function loadLabel(id) {
  try {
    const data = await request.get(`/assets/api/${id}`)
    selectedLabel.value = data.name || ''
  } catch { selectedLabel.value = '' }
}

let searchTimer = null
function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

async function loadData() {
  loading.value = true
  try {
    const types = props.ciTypes.join(',')
    const params = { page: page.value, page_size: pageSize.value, ci_types: types }
    if (keyword.value.trim()) params.search = keyword.value.trim()
    const data = await request.get('/assets/api/services', { params })
    items.value = data.items || []
    total.value = data.total || 0
  } catch { items.value = [] }
  finally { loading.value = false }
}

function open() {
  visible.value = true
  page.value = 1
  keyword.value = ''
  loadData()
  nextTick(() => searchInput.value?.focus())
}

function close() {
  visible.value = false
}

function clear() {
  selectedId.value = null
  selectedLabel.value = ''
  emit('update:modelValue', null)
  close()
}

async function pick(item) {
  selectedId.value = item.id
  selectedLabel.value = item.name
  emit('update:modelValue', item.id)
  close()
}

async function prevPage() {
  if (page.value > 1) { page.value--; await loadData() }
}

async function nextPage() {
  if (page.value < totalPages.value) { page.value++; await loadData() }
}
</script>

<style scoped>
.sp-wrapper { position: relative; display: flex; align-items: center; }
.sp-input {
  width: 100%; padding: 6px 60px 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12));
  border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b);
  font-size: 0.85rem; box-sizing: border-box; cursor: pointer;
}
.sp-input:focus { border-color: var(--accent, #6366f1); outline: none; }
.sp-btn {
  position: absolute; right: 28px; background: none; border: none; cursor: pointer;
  font-size: 14px; padding: 2px 4px; color: var(--text-secondary, #64748b);
}
.sp-btn:hover { color: var(--accent, #6366f1); }
.sp-clear {
  position: absolute; right: 48px; background: none; border: none; cursor: pointer;
  font-size: 14px; padding: 2px 4px; color: var(--text-secondary, #64748b); line-height: 1;
}
.sp-clear:hover { color: #ef4444; }
.sp-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center;
  justify-content: center; z-index: 2000;
}
.sp-dialog {
  width: 520px; max-width: 90vw; max-height: 70vh; background: #fff; border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2); display: flex; flex-direction: column; overflow: hidden;
}
.sp-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid rgba(0,0,0,0.07);
  font-size: 0.95rem; font-weight: 600; color: var(--text, #1e293b);
}
.sp-close { background: none; border: none; font-size: 18px; cursor: pointer; color: #94a3b8; padding: 0; line-height: 1; }
.sp-close:hover { color: var(--text, #1e293b); }
.sp-toolbar { padding: 12px 14px; border-bottom: 1px solid rgba(0,0,0,0.06); }
.sp-search {
  width: 100%; padding: 7px 10px; border: 1px solid rgba(0,0,0,0.12); border-radius: 6px;
  font-size: 0.85rem; box-sizing: border-box;
}
.sp-search:focus { border-color: var(--accent, #6366f1); outline: none; }
.sp-list { flex: 1; overflow-y: auto; min-height: 200px; max-height: 400px; }
.sp-loading, .sp-empty { text-align: center; padding: 32px; color: #94a3b8; font-size: 0.85rem; }
.sp-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; cursor: pointer; border-bottom: 1px solid rgba(0,0,0,0.04);
}
.sp-item:hover { background: rgba(99,102,241,0.06); }
.sp-item.active { background: rgba(99,102,241,0.1); }
.sp-name { font-size: 0.85rem; font-weight: 500; color: var(--text, #1e293b); }
.sp-meta { font-size: 0.72rem; color: var(--text-secondary, #64748b); background: rgba(0,0,0,0.04); padding: 1px 6px; border-radius: 4px; }
.sp-footer {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 10px 16px; border-top: 1px solid rgba(0,0,0,0.07);
}
.sp-page-btn { padding: 4px 12px; border: 1px solid rgba(0,0,0,0.12); border-radius: 6px; background: #fff; cursor: pointer; font-size: 0.78rem; }
.sp-page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.sp-page-info { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
</style>
