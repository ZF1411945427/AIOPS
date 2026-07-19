<template>
  <div class="ta-page">
    <div class="page-header">
      <h1>Trace 异常检测配置</h1>
      <p>链路追踪异常阈值 · 服务级别延迟/错误率检测</p>
    </div>
    <div class="toolbar">
      <input v-model="searchSvc" class="input" placeholder="服务名搜索" @keyup.enter="loadConfigs" />
      <button class="btn btn-primary" @click="openCreate">+ 新建配置</button>
      <button class="btn" @click="loadConfigs">刷新</button>
      <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
    </div>
    <div class="panel">
      <div class="panel-head">检测规则</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!items.length" class="empty-state">暂无配置</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th>服务</th><th>延迟阈值(ms)</th><th>错误率阈值</th><th>检测窗口</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="c in items" :key="c.id">
                <td>{{ c.name }}</td>
                <td><code>{{ c.service_name || '*' }}</code></td>
                <td>{{ c.latency_threshold_ms }}</td>
                <td>{{ (c.error_rate_threshold * 100).toFixed(1) }}%</td>
                <td>{{ c.check_window_minutes || 30 }} min</td>
                <td><span class="badge" :class="c.enabled ? 'resolved' : 'info'">{{ c.enabled ? '运行中' : '已暂停' }}</span></td>
                <td>
                  <button class="btn btn-sm" @click="openEdit(c)">编辑</button>
                  <button class="btn btn-sm" :class="c.enabled ? 'btn-warning' : 'btn-primary'" @click="toggleConfig(c)">{{ c.enabled ? '暂停' : '启用' }}</button>
                  <button class="btn btn-sm btn-danger" @click="deleteConfig(c)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
      <div class="modal-box">
        <h3>{{ editing ? '编辑配置' : '新建配置' }}</h3>
        <div class="form-group"><label class="form-label">名称</label><input v-model="form.name" class="input" /></div>
        <div class="form-group"><label class="form-label">服务名（留空=全部）</label><input v-model="form.service_name" class="input" placeholder="service-a" /></div>
        <div class="form-group"><label class="form-label">延迟阈值 (ms)</label><input v-model.number="form.latency_threshold_ms" type="number" class="input" /></div>
        <div class="form-group"><label class="form-label">错误率阈值 (0~1)</label><input v-model.number="form.error_rate_threshold" type="number" step="0.01" min="0" max="1" class="input" /></div>
        <div class="form-group"><label class="form-label">检测窗口 (分钟，默认 30)</label><input v-model.number="form.check_window_minutes" type="number" min="1" max="1440" class="input" /><div class="form-hint">检测最近 N 分钟的 spans 数据，过小会因数据滞后漏报，过大可能错过实时异常</div></div>
        <div class="modal-actions">
          <button class="btn" @click="showForm = false">取消</button>
          <button class="btn btn-primary" @click="submitForm">保存</button>
        </div>
      </div>
    </div>
    <GuideDrawer v-model="showGuide" title="📖 Trace 异常检测配置 · 操作说明">
      <section class="guide-section">
        <h4>1. 这个页面是干嘛的？</h4>
        <p>简单说：<strong>给"链路追踪"设阈值，超了就报警</strong>。</p>
        <p>系统从链路追踪（Trace）数据里实时统计每个服务的<strong>错误率</strong>和<strong>延迟</strong>，一旦超过你设的阈值，就自动创建告警，让你及时发现线上问题。</p>
        <div class="tip-box">💡 没有这个功能，你只能等用户投诉"服务慢/报错"才知道出问题；有了它，系统能在用户感知之前就报警。</div>
      </section>
      <section class="guide-section">
        <h4>2. 什么是 Trace？</h4>
        <p><strong>Trace（链路追踪）</strong>记录了一个请求从入口到出口经过的所有服务调用。每次调用叫一个 <strong>Span</strong>，包含：</p>
        <ul>
          <li><code>service_name</code> — 调用了哪个服务</li>
          <li><code>duration_ms</code> — 调用耗时（毫秒）</li>
          <li><code>status</code> — 调用结果（OK / WARN / ERROR）</li>
        </ul>
        <p>比如用户下单：gateway → order-service → payment-service → inventory-service，每个环节都是一个 Span，串成一条 Trace。哪个环节慢、哪个环节报错，一目了然。</p>
      </section>
      <section class="guide-section">
        <h4>3. 检测逻辑（系统怎么判断异常？）</h4>
        <p>系统每 60 秒在后台跑一次检测，对每条启用的配置：</p>
        <ul>
          <li>查询<strong>最近 N 分钟</strong>（N = 检测窗口，默认 30 分钟）的 Span 数据</li>
          <li>按 <code>service_name</code> 过滤（留空 = 查全部服务）</li>
          <li>计算两个指标：<strong>错误率</strong> = ERROR 数 / 总数；<strong>平均延迟</strong> = 所有 duration_ms 的平均值</li>
          <li>错误率 &gt; 阈值 → 创建"错误率告警"</li>
          <li>平均延迟 &gt; 阈值 → 创建"延迟告警"</li>
          <li>同一个配置的同类型告警不重复创建（避免刷屏）</li>
        </ul>
        <div class="formula">告警 = 真实指标 超过 你设的阈值</div>
      </section>
      <section class="guide-section">
        <h4>4. 表单字段含义</h4>
        <div class="key-value-list">
          <div class="kv-row">
            <span class="kv-key">名称</span>
            <span class="kv-val">给这条规则起个名，便于识别。例：<code>支付服务监控</code></span>
          </div>
          <div class="kv-row">
            <span class="kv-key">服务名</span>
            <span class="kv-val">要监控的服务名。<strong>留空 = 监控所有服务</strong>。例：<code>payment-service</code></span>
          </div>
          <div class="kv-row">
            <span class="kv-key">延迟阈值 (ms)</span>
            <span class="kv-val">平均延迟超过多少毫秒就告警。例：<code>1000</code> 表示平均响应超过 1 秒就告警</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">错误率阈值 (0~1)</span>
            <span class="kv-val">错误率超过多少就告警。<code>0.05</code> = 5% 的请求报错就告警</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">检测窗口 (分钟)</span>
            <span class="kv-val">检测最近 N 分钟的 Span 数据。默认 30。<br>⚠️ <strong>关键参数</strong>：过小会因数据滞后漏报，过大可能错过实时异常</span>
          </div>
        </div>
      </section>
      <section class="guide-section">
        <h4>5. 怎么操作？</h4>
        <h5>场景：监控支付服务，错误率超 5% 或平均延迟超 800ms 就告警</h5>
        <ul>
          <li>① 点 <code>+ 新建配置</code></li>
          <li>② 名称填：<code>支付服务监控</code></li>
          <li>③ 服务名填：<code>payment-service</code></li>
          <li>④ 延迟阈值填：<code>800</code></li>
          <li>⑤ 错误率阈值填：<code>0.05</code></li>
          <li>⑥ 检测窗口填：<code>30</code>（默认即可）</li>
          <li>⑦ 点"保存" → 状态自动变为 <span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">运行中</span></li>
        </ul>
        <p>配置启用后，系统每 60 秒检测一次。一旦触发阈值，告警会出现在「告警中心」页面。</p>
      </section>
      <section class="guide-section">
        <h4>6. 状态含义</h4>
        <ul>
          <li><span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">运行中</span> — 配置已启用，后台每 60 秒自动检测</li>
          <li><span class="tag-demo" style="background:rgba(148,163,184,0.12);color:#64748b;">已暂停</span> — 配置存在但不检测，可点"启用"恢复</li>
        </ul>
        <div class="tip-box">💡 配置"运行中"但没告警 ≠ 功能坏了：可能是最近窗口内数据正常（错误率/延迟都没超阈值），这正是我们希望的状态——有问题才报警，没问题就不打扰。</div>
      </section>
      <section class="guide-section">
        <h4>7. 常见疑问</h4>
        <h5>Q: 我建了配置，一直"运行中"但没告警？</h5>
        <p>A: 两种可能：</p>
        <ul>
          <li><strong>数据正常</strong> — 最近窗口内的错误率/延迟都没超阈值，没异常可报（这是好事）</li>
          <li><strong>窗口内无数据</strong> — 检测窗口设得太小（如 5min），但最近没有新的 Span 数据。可适当调大窗口（如 30~60min）</li>
        </ul>
        <h5>Q: 怎么验证检测真的在跑？</h5>
        <p>A: 临时建一条低阈值配置（比如延迟阈值设 10ms），保存后等 1-2 分钟，去「告警中心」看是否有新告警。验证完记得删除测试配置。</p>
      </section>
    </GuideDrawer>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const items = ref([])
const loading = ref(false)
const showForm = ref(false)
const showGuide = ref(false)
const editing = ref(false)
const searchSvc = ref('')
const form = ref({ name: '', service_name: '', latency_threshold_ms: 1000, error_rate_threshold: 0.05, check_window_minutes: 30 })
async function loadConfigs() {
  loading.value = true
  try {
    const params = {}
    if (searchSvc.value) params.service_name = searchSvc.value
    const res = await request.get('/trace-anomaly/api/configs', { params })
    items.value = res.items || []
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
function openCreate() {
  editing.value = false
  form.value = { name: '', service_name: '', latency_threshold_ms: 1000, error_rate_threshold: 0.05, check_window_minutes: 30 }
  showForm.value = true
}
function openEdit(c) {
  editing.value = true
  form.value = { ...c }
  showForm.value = true
}
async function submitForm() {
  try {
    if (editing.value) {
      await request.put(`/trace-anomaly/api/configs/${form.value.id}`, form.value)
      ElMessage.success('已更新')
    } else {
      await request.post('/trace-anomaly/api/configs', form.value)
      ElMessage.success('已创建')
    }
    showForm.value = false
    loadConfigs()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function toggleConfig(c) {
  try {
    await request.post(`/trace-anomaly/api/configs/${c.id}/toggle`)
    ElMessage.success(c.enabled ? '已暂停' : '已启用')
    loadConfigs()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function deleteConfig(c) {
  if (!confirm(`确认删除「${c.name}」？`)) return
  try {
    await request.delete(`/trace-anomaly/api/configs/${c.id}`)
    ElMessage.success('已删除')
    loadConfigs()
  } catch (e) { ElMessage.error('删除失败: ' + (e.message || e)) }
}
onMounted(loadConfigs)
</script>
<style scoped>
.ta-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-warning { background: #d97706; color: #fff; border-color: #d97706; }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-sm { padding: 3px 8px; font-size: 0.75rem; }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; outline: none; }
.input:focus { border-color: var(--accent,#6366f1); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
code { background: rgba(99,102,241,0.08); padding: 1px 5px; border-radius: 4px; font-size: 0.78rem; }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.resolved { background: rgba(34,197,94,0.12); color: #22c55e; }
.info { background: rgba(148,163,184,0.12); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.form-hint { font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); margin-top: 3px; line-height: 1.5; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
