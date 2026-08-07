<template>
  <div class="remediation-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>自愈管理</h1>
          <p>告警自动处置 · AI 智能修复</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'ai' }" @click="tab = 'ai'">🤖 AI 自愈工作台</button>
      <button class="tab" :class="{ active: tab === 'rules' }" @click="tab = 'rules'">📋 简单规则</button>
      <button class="tab" :class="{ active: tab === 'logs' }" @click="tab = 'logs'">📝 执行记录</button>
    </div>

    <!-- ═══ AI 自愈工作台 ═══ -->
    <template v-if="tab === 'ai'">
      <div class="stats-bar">
        <div class="stat-box"><span class="stat-num">{{ groupedTriggeredAlerts.length }}</span> 待处理告警</div>
        <div class="stat-box"><span class="stat-num">{{ pendingActions.length }}</span> 待审批动作</div>
        <div class="stat-box"><span class="stat-num">{{ actionTotal }}</span> 已执行</div>
      </div>

      <div class="panel">
        <div class="panel-header"><h3>待处理告警</h3><button class="btn btn-sm" @click="loadTriggeredAlerts">刷新</button></div>
        <div class="panel-body">
          <div v-if="alertLoading" class="loading-state">加载中...</div>
          <div v-else-if="groupedTriggeredAlerts.length" class="alert-groups">
            <div v-for="g in groupedTriggeredAlerts" :key="g.key" class="alert-group">
              <div class="alert-group-header" @click="alertGroupOpen[g.key] = !alertGroupOpen[g.key]">
                <span class="group-expand-icon">{{ alertGroupOpen[g.key] ? '▼' : '▶' }}</span>
                <span class="badge" :class="severityClass(g.severity)">{{ severityLabel(g.severity) }}</span>
                <span class="group-metric">{{ g.metric_name || '未知指标' }}</span>
                <span class="group-asset">· {{ g.asset_name || '未知资产' }}</span>
                <span v-if="g.items.length > 1" class="group-count">共 {{ g.items.length }} 条同类告警</span>
                <div class="group-actions" @click.stop>
                  <!-- 诊断按钮：idle / loading / done 三态 -->
                  <button v-if="groupDiagState[g.key] === 'done'"
                    class="btn btn-sm btn-done" @click="openDiagModal(g.key)">
                    📋 诊断报告
                  </button>
                  <button v-else class="btn btn-sm"
                    @click="runDiagnoseGroup(g)"
                    :disabled="groupDiagState[g.key] === 'loading'">
                    {{ groupDiagState[g.key] === 'loading' ? '诊断中...' : '🔬 诊断' }}
                  </button>
                  <!-- 重新诊断：始终可见，强制重新执行诊断命令 -->
                  <button class="btn btn-sm btn-rediagnose"
                    :disabled="groupDiagState[g.key] === 'loading'"
                    @click="runDiagnoseGroup(g, true)">
                    {{ groupDiagState[g.key] === 'loading' ? '诊断中...' : '🔄 重新诊断' }}
                  </button>
                  <!-- AI分析按钮：idle / loading / done 三态 -->
                  <button v-if="groupAiState[g.key] === 'done'"
                    class="btn btn-sm btn-done-ai" @click="openAiModal(g.key)">
                    📊 AI 方案
                  </button>
                  <button v-else class="btn btn-sm btn-primary"
                    @click="aiAnalyzeGroup(g)"
                    :disabled="groupAiState[g.key] === 'loading'">
                    {{ groupAiState[g.key] === 'loading' ? '分析中...' : '🤖 AI 分析' }}
                  </button>
                  <!-- 重新分析：始终可见，无 PA 时也可触发生成 -->
                  <button class="btn btn-sm btn-reanalyze"
                    :disabled="groupReanalyzing === g.key"
                    @click="reanalyzeGroup(g)">
                    {{ groupReanalyzing === g.key ? '分析中...' : '🔄 重新分析' }}
                  </button>
                </div>
              </div>
              <div v-if="alertGroupOpen[g.key]" class="alert-group-body">
                <table class="table table-compact">
                  <thead><tr><th>ID</th><th>告警消息</th><th>实际值</th><th>阈值</th><th>时间</th></tr></thead>
                  <tbody>
                    <tr v-for="a in g.items" :key="a.id">
                      <td>{{ a.id }}</td>
                      <td class="text-sm" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ a.message }}</td>
                      <td>{{ a.actual_value ?? '-' }}</td>
                      <td>{{ a.threshold ?? '-' }}</td>
                      <td class="text-sm">{{ a.created_at }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">✅</div><div>暂无待处理告警</div></div>
        </div>
      </div>

      <!-- ═══ 诊断报告弹窗 ═══ -->
      <div v-if="diagModal.visible" class="modal-overlay" @click.self="diagModal.visible = false">
        <div class="modal-box modal-wide">
          <div class="modal-header">
            <h3>📋 诊断报告 · {{ diagModal.groupLabel }}</h3>
            <button class="modal-close" @click="diagModal.visible = false">×</button>
          </div>
          <div class="modal-body diag-modal-body">
            <div v-if="diagModal.cached" class="diag-cache-tip">使用缓存结果（本次未重新连接）</div>
            <div v-for="(cmd, i) in diagModal.commands" :key="i" class="diag-result-item">
              <div class="diag-result-header">
                <span class="diag-cmd-idx">{{ i + 1 }}.</span>
                <code class="diag-cmd-text">{{ cmd.cmd }}</code>
                <span class="diag-cmd-status" :class="cmd.exit_code === 0 ? 'diag-ok' : 'diag-fail'">
                  {{ cmd.exit_code === 0 ? '✅' : '❌' }}
                </span>
                <span class="diag-cmd-time">{{ cmd.duration_ms }}ms</span>
              </div>
              <div v-if="cmd.desc" class="diag-cmd-desc">{{ cmd.desc }}</div>
              <pre v-if="cmd.output" class="diag-cmd-output">{{ cmd.output }}</pre>
              <div v-else class="diag-cmd-desc" style="color:#94a3b8;">(无输出)</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ AI方案弹窗（只读查看，审批在下方） ═══ -->
      <div v-if="aiModal.visible" class="modal-overlay" @click.self="aiModal.visible = false">
        <div class="modal-box modal-wide">
          <div class="modal-header">
            <h3>📊 AI 方案预览 · {{ aiModal.groupLabel }}</h3>
            <button class="modal-close" @click="aiModal.visible = false">×</button>
          </div>
          <div class="modal-body">
            <div v-if="aiModal.dedup" class="diag-cache-tip">已复用当天已有方案（未重新调用 AI）</div>
            <div class="analysis-grid">
              <div class="analysis-item"><span class="kv-key">根因分析</span><p class="kv-val">{{ aiModal.root_cause || '-' }}</p></div>
              <div class="analysis-item"><span class="kv-key">影响评估</span><p class="kv-val">{{ aiModal.impact || '-' }}</p></div>
              <div v-if="aiModal.action_type === 'workflow'" class="analysis-item" style="grid-column:1/-1">
                <span class="kv-key">推荐工作流</span>
                <p class="kv-val"><span class="badge action">工作流 #{{ aiModal.recommended_workflow_id }}</span> {{ aiModal.recommended_workflow_name }}</p>
              </div>
              <div v-else class="analysis-item" style="grid-column:1/-1">
                <span class="kv-key">修复命令</span>
                <code class="cmd-block">{{ aiModal.command || '-' }}</code>
              </div>
              <div class="analysis-item"><span class="kv-key">方案说明</span><p class="kv-val">{{ aiModal.command_description || '执行推荐的多步骤自愈工作流' }}</p></div>
              <div class="analysis-item">
                <span class="kv-key">风险等级</span>
                <span class="badge" :class="severityClass(aiModal.risk_level)">{{ aiModal.risk_level }}</span>
              </div>
            </div>
            <div class="modal-tip">✅ 审批与执行操作请在下方「待审批动作」中进行</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3>待审批动作 · 共 {{ actionTotal }} 条</h3>
          <div class="header-actions">
            <select v-model="pendingFilter" class="filter-select" @change="loadPendingActions">
              <option value="all">全部</option>
              <option value="pending">待确认</option>
              <option value="executed">已执行</option>
              <option value="failed">失败</option>
              <option value="canceled">已取消</option>
            </select>
            <button class="btn btn-sm" @click="loadPendingActions">刷新</button>
          </div>
        </div>
        <div class="panel-body">
          <div v-if="pendingLoading" class="loading-state">加载中...</div>
          <div v-else-if="groupedPendingActions.length" class="pending-groups">
            <div v-for="g in groupedPendingActions" :key="g.alert_id" class="pending-group">
              <div class="group-alert-header">
                <span class="badge critical">告警 #{{ g.alert_id }}</span>
                <span class="alert-msg">{{ g.alert_message || '-' }}</span>
              </div>
              <div class="group-cards">
                <div v-for="pa in g.items" :key="pa.id" class="plan-card" :class="sourceClass(pa.source)">
                  <div class="plan-card-header">
                    <span class="plan-source" :class="sourceClass(pa.source)">{{ sourceLabel(pa.source) }}</span>
                    <span class="badge" :class="pendingStatusClass(pa.status)">{{ pendingStatusLabel(pa.status) }}</span>
                  </div>
                  <div class="plan-title">{{ pa.title }}</div>
                  <div class="plan-meta">
                    <span class="badge action">{{ actionLabel(pa.action_type) }}</span>
                    <span class="badge" :class="severityClass(pa.risk_level)">{{ pa.risk_level }}</span>
                  </div>
                  <div class="plan-cmd">
                    <template v-if="pa.action_type === 'workflow'">
                      <div class="wf-label">工作流 #{{ pa.workflow_id }}{{ pa.workflow_name ? ' ' + pa.workflow_name : '' }}</div>
                      <ol v-if="pa.workflow_steps && pa.workflow_steps.length" class="wf-steps">
                        <li v-for="(s, i) in pa.workflow_steps" :key="i"><code>{{ s }}</code></li>
                      </ol>
                      <code v-else>（无步骤）</code>
                    </template>
                    <code v-else>{{ pa.command || '-' }}</code>
                  </div>
                  <div v-if="pa.command_explanation" class="cmd-explanation">
                    <span class="cmd-explanation-icon">📖</span>
                    <span class="cmd-explanation-text">{{ pa.command_explanation }}</span>
                  </div>
                  <div v-if="pa.source !== 'ai'" class="plan-reason">{{ pa.reason || '-' }}</div>
                  <!-- ═══ 诊断过程折叠面板 ═══ -->
                  <div v-if="pa.diagnosis_commands && pa.diagnosis_commands.length" class="diagnosis-section">
                    <button class="diagnosis-toggle" @click="toggleDiagnosis(pa.id)">
                      <span class="diagnosis-icon">{{ diagnosisOpen[pa.id] ? '▼' : '▶' }}</span>
                      📋 查看诊断过程 ({{ pa.diagnosis_commands.length }}条命令{{ diagnosisRounds(pa.diagnosis_commands) > 1 ? '，' + diagnosisRounds(pa.diagnosis_commands) + '轮' : '' }})
                      <span class="diagnosis-time">{{ diagnosisDuration(pa.diagnosis_commands) }}</span>
                    </button>
                    <div v-if="diagnosisOpen[pa.id]" class="diagnosis-commands">
                      <template v-for="(group, gi) in groupedByRound(pa.diagnosis_commands)" :key="gi">
                        <div v-if="groupedByRound(pa.diagnosis_commands).length > 1" class="diag-round-label">{{ group.label }}</div>
                        <div v-for="(cmd, ci) in group.commands" :key="gi + '-' + ci" class="diag-cmd-item">
                          <div class="diag-cmd-header">
                            <span class="diag-cmd-idx">{{ ci + 1 }}.</span>
                            <code class="diag-cmd-text">{{ cmd.cmd }}</code>
                            <span class="diag-cmd-status" :class="cmd.exit_code === 0 ? 'diag-ok' : 'diag-fail'">
                              {{ cmd.exit_code === 0 ? '✅' : '❌' }}
                            </span>
                            <span class="diag-cmd-time">{{ cmd.duration_ms }}ms</span>
                          </div>
                          <div class="diag-cmd-desc">{{ cmd.desc }}</div>
                          <pre v-if="cmd.output" class="diag-cmd-output">{{ cmd.output }}</pre>
                        </div>
                      </template>
                    </div>
                  </div>
                  <!-- ═══ 根因 + 推理链 ═══ -->
                  <div v-if="pa.root_cause || pa.diagnosis_reasoning" class="reasoning-section">
                    <div v-if="pa.root_cause" class="reasoning-block">
                      <div class="reasoning-label">🔍 根因定位</div>
                      <div class="reasoning-text">{{ pa.root_cause }}</div>
                    </div>
                    <div v-if="pa.diagnosis_reasoning" class="reasoning-block">
                      <div class="reasoning-label">💡 推理依据</div>
                      <div class="reasoning-text">{{ pa.diagnosis_reasoning }}</div>
                    </div>
                  </div>
                  <div class="plan-time">{{ pa.created_at }}</div>
                  <div class="plan-actions">
                    <template v-if="pa.status === 'pending'">
                      <button class="btn btn-sm btn-primary" @click="confirmAction(pa.id)">确认执行</button>
                      <button class="btn btn-sm btn-danger" @click="cancelAction(pa.id)">取消</button>
                      <button class="btn btn-sm btn-warning" :disabled="reanalyzingId === pa.id" @click="reanalyzeAlert(pa)">
                        {{ reanalyzingId === pa.id ? '分析中...' : '🔄 重新分析' }}
                      </button>
                      <button class="btn btn-sm btn-transfer" @click="transferToAgent(pa)">🔄 转交智能助手</button>
                    </template>
                    <template v-else-if="pa.status === 'failed'">
                      <button class="btn btn-sm btn-warning" :disabled="reanalyzingId === pa.id" @click="reanalyze(pa)">
                        {{ reanalyzingId === pa.id ? '分析中...' : '🔄 换个思路' }}
                      </button>
                      <button class="btn btn-sm btn-transfer" @click="transferToAgent(pa)">🔄 转交智能助手</button>
                    </template>
                    <template v-else-if="pa.status === 'executed'">
                      <button class="btn btn-sm btn-transfer" @click="transferToAgent(pa)">🔄 转交智能助手</button>
                    </template>
                    <span v-else class="text-sm">—</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">暂无待审批动作</div>
        </div>
      </div>
    </template>

    <!-- ═══ 简单规则 ═══ -->
    <template v-if="tab === 'rules'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openCreate">+ 新增规则</button>
        <button class="btn" @click="loadData">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-header"><h3>响应规则</h3></div>
        <div class="panel-body">
          <div v-if="loading" class="loading-state">加载中...</div>
          <table v-else-if="remediations.length" class="table">
            <thead><tr><th>名称</th><th>触发规则</th><th>动作</th><th>目标</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="r in remediations" :key="r.id">
                <td>{{ r.name }}</td>
                <td>{{ ruleName(r.rule_id) }}</td>
                <td><span class="badge action">{{ actionLabel(r.action_type) }}</span></td>
                <td class="text-sm">{{ r.params?.target || '-' }}</td>
                <td><span class="badge" :class="r.enabled ? 'resolved' : 'info'">{{ r.enabled ? '启用' : '停用' }}</span></td>
                <td><button class="btn btn-sm btn-danger" @click="deleteRule(r)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🔧</div><div>暂无规则</div></div>
        </div>
      </div>
    </template>

    <!-- ═══ 执行记录 ═══ -->
    <template v-if="tab === 'logs'">
      <div class="panel">
        <div class="panel-header"><h3>执行记录 · 共 {{ logTotal }} 条</h3></div>
        <div class="panel-body">
          <table v-if="logs.length" class="table">
            <thead><tr><th>时间</th><th>动作</th><th>目标</th><th>结果</th><th>输出</th></tr></thead>
            <tbody>
              <tr v-for="lg in logs" :key="lg.id" class="log-row" @click="openLogDetail(lg)">
                <td class="text-sm">{{ formatTime(lg.created_at) }}</td>
                <td>{{ actionLabel(lg.action_type) }}</td>
                <td class="text-sm">{{ lg.target }}</td>
                <td><span class="badge" :class="lg.is_success ? 'resolved' : 'critical'">{{ lg.is_success ? '成功' : '失败' }}</span></td>
                <td class="output-cell">{{ lg.output }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无执行记录</div>
          <div v-if="totalPages > 1" class="pagination">
            <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
            <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
            <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
            <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
            <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
            <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
            <span class="page-info">共 {{ logTotal }} 条 / {{ totalPages }} 页</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 执行记录详情弹窗 -->
    <div v-if="logDetail" class="modal-overlay" @click.self="logDetail = null">
      <div class="modal-box log-detail-modal">
        <div class="modal-header">
          <h3>执行记录详情</h3>
          <button class="modal-close" @click="logDetail = null">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-row"><label>时间</label><span>{{ formatTime(logDetail.created_at) }}</span></div>
          <div class="detail-row"><label>动作</label><span>{{ actionLabel(logDetail.action_type) }}</span></div>
          <div class="detail-row"><label>目标</label><span>{{ logDetail.target }}</span></div>
          <div class="detail-row"><label>结果</label><span :style="{ color: logDetail.is_success ? '#10b981' : '#ef4444', fontWeight: 600 }">{{ logDetail.is_success ? '成功' : '失败' }}</span></div>
          <div class="detail-row"><label>完整输出</label></div>
          <pre class="log-output-full">{{ logDetail.output }}</pre>
        </div>
      </div>
    </div>

    <!-- 新增规则弹窗 -->
    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header"><h3>新增自愈规则</h3><button class="modal-close" @click="createVisible = false">×</button></div>
        <div class="modal-body">
          <div class="form-group"><label>名称</label><input v-model="form.name" placeholder="如：CPU 高自动重启" /></div>
          <div class="form-group">
            <label>触发规则</label>
            <select v-model.number="form.rule_id">
              <option :value="0">任何告警</option>
              <option v-for="r in rules" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>动作类型</label>
            <select v-model="form.action_type" @change="onActionChange">
              <option v-for="(label, key) in actions" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="form-group"><label>目标</label><input v-model="form.params_target" placeholder="如：nginx（服务名）/tmp（路径）/bash 命令" /></div>
          <div v-if="form.action_type === 'scale'" class="form-group"><label>实例数</label><input v-model.number="form.params_count" type="number" /></div>
          <div v-if="form.action_type === 'script'" class="form-group"><label>脚本路径</label><input v-model="form.params_script" placeholder="/opt/scripts/fix.sh" /></div>
          <div v-if="form.action_type === 'run_command'" class="form-group"><label>执行命令</label><input v-model="form.params_command" placeholder="如：hostname 或 uptime（危险命令会被拦截）" /></div>
          <div class="form-actions"><button class="btn" @click="createVisible = false">取消</button><button class="btn btn-primary" @click="createRule" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button></div>
        </div>
      </div>
    </div>

    <GuideDrawer v-model="showGuide" title="📖 自愈管理 · 操作说明">
      <section class="guide-section">
        <h4>1. AI 自愈工作台</h4>
        <p><strong>诊断先行</strong>：点击「🔬 诊断」按钮自动执行只读诊断命令（ps/df/free 等），收集故障现场数据，无需人工审核。</p>
        <p><strong>AI 分析</strong>：点击「🤖 AI 分析」，AI 基于诊断结果分析根因，生成修复命令。审批时可展开「查看诊断过程」回溯排查证据链。</p>
        <p>你审核后点击「确认执行」才会真正执行，形成<strong>自动诊断 → AI 分析 → 人工审批 → 执行</strong>的安全闭环。</p>
      </section>
      <section class="guide-section">
        <h4>2. 简单规则模式</h4>
        <p>配置"告警触发 → 自动执行"的固定规则，适用于已知的、安全的修复场景（如清理临时文件、重启已知服务）。</p>
      </section>
      <section class="guide-section">
        <h4>3. 支持的动作类型</h4>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key">重启服务</span><span class="kv-val">通过 SSH 执行 systemctl restart</span></div>
          <div class="kv-row"><span class="kv-key">清理磁盘</span><span class="kv-val">删除指定目录下 7 天前的旧文件（仅允许 /tmp /var/log /var/cache /opt /home）</span></div>
          <div class="kv-row"><span class="kv-key">扩缩容</span><span class="kv-val">扩缩容 K8s Deployment（需指定实例数）</span></div>
          <div class="kv-row"><span class="kv-key">执行脚本</span><span class="kv-val">在目标主机执行自定义脚本路径</span></div>
          <div class="kv-row"><span class="kv-key">执行命令</span><span class="kv-val">在目标主机执行任意 Shell 命令（危险命令会被拦截）</span></div>
          <div class="kv-row"><span class="kv-key">发送通知</span><span class="kv-val">发送告警通知到指定渠道</span></div>
        </div>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GuideDrawer from '@/components/GuideDrawer.vue'
import request from '@/api/request'

const showGuide = ref(false)
const tab = ref('ai')

// ── AI 自愈工作台 ──
const triggeredAlerts = ref([])
const alertLoading = ref(false)
const reanalyzingId = ref(0)
const pendingActions = ref([])
const pendingLoading = ref(false)
const pendingFilter = ref('pending')
const actionTotal = ref(0)
const diagnosisOpen = ref({})   // { [paId]: true/false } 折叠状态
const alertGroupOpen = ref({})  // { [groupKey]: true/false } 告警聚合组展开状态

// 按钮状态：idle / loading / done（分组粒度）
const groupDiagState = ref({})  // { [groupKey]: 'idle'|'loading'|'done' }
const groupAiState  = ref({})   // { [groupKey]: 'idle'|'loading'|'done' }
const groupReanalyzing = ref('')  // groupKey currently re-analyzing
// 各分组缓存的数据，用于弹窗展示
const groupDiagData = ref({})   // { [groupKey]: { groupLabel, commands, cached } }
const groupAiData   = ref({})   // { [groupKey]: { groupLabel, ...analysisFields, dedup } }

// 弹窗状态
const diagModal = reactive({ visible: false, groupLabel: '', commands: [], cached: false })
const aiModal   = reactive({ visible: false, groupLabel: '', dedup: false,
                              root_cause: '', impact: '', action_type: '', command: '',
                              command_description: '', risk_level: '', recommended_workflow_id: null,
                              recommended_workflow_name: '' })

function openDiagModal(key) {
  const d = groupDiagData.value[key]
  if (!d) return
  Object.assign(diagModal, { visible: true, ...d })
}
function openAiModal(key) {
  const d = groupAiData.value[key]
  if (!d) return
  Object.assign(aiModal, { visible: true, ...d })
}

function severityClass(s) {
  if (!s) return 'info'
  const m = { critical: 'critical', high: 'critical', warning: 'warning', info: 'info', low: 'info', medium: 'warning' }
  return m[s.toLowerCase()] || 'info'
}
function severityLabel(s) {
  if (!s) return '未知'
  const m = { critical: '严重', high: '高', warning: '警告', info: '信息', low: '低', medium: '中' }
  return m[s.toLowerCase()] || s
}
function pendingStatusClass(s) {
  const m = { pending: 'warning', confirmed: 'info', executing: 'info', executed: 'resolved', failed: 'critical', canceled: 'info' }
  return m[s] || 'info'
}
function pendingStatusLabel(s) {
  const m = { pending: '待确认', confirmed: '已确认', executing: '执行中', executed: '已执行', failed: '失败', canceled: '已取消' }
  return m[s] || s
}
function actionLabel(type) {
  const m = {
    restart: '重启服务', restart_service: '重启服务', restart_pod: '重启 Pod',
    clean: '清理磁盘', clean_disk: '清理磁盘',
    scale: '扩缩容', scale_up: '扩缩容',
    script: '执行脚本', run_command: '执行命令',
    notify: '发送通知', notify_owner: '通知负责人',
    workflow: '执行工作流',
  }
  return m[type] || type
}

async function loadTriggeredAlerts() {
  alertLoading.value = true
  try {
    const data = await request.get('/remediation/api/triggered-alerts')
    triggeredAlerts.value = data.alerts || []
    // 加载完成后异步恢复各分组的诊断报告状态（cached 立刻返回，不阻塞渲染）
    await restoreDiagnosisState()
  } catch (e) { ElMessage.error('加载告警失败: ' + e.message) }
  finally { alertLoading.value = false }
}

// 恢复诊断状态：对每个分组的代表告警调一次诊断接口（no force，有缓存立刻返回）
async function restoreDiagnosisState() {
  const groups = groupedTriggeredAlerts.value
  await Promise.allSettled(groups.map(async (g) => {
    const rep = g.items[0]
    if (!rep) return
    try {
      const data = await request.post(`/remediation/api/diagnose/${rep.id}`, {}, { timeout: 130000 })
      if (data.ok && data.commands && data.commands.length) {
        const label = `${g.metric_name || '未知指标'} · ${g.asset_name || '未知资产'}`
        groupDiagData.value = { ...groupDiagData.value, [g.key]: { groupLabel: label, commands: data.commands, cached: true } }
        groupDiagState.value = { ...groupDiagState.value, [g.key]: 'done' }
      }
    } catch (_) { /* 静默失败，不影响页面 */ }
  }))
}

// 按 metric_name + asset_name 聚合告警，降噪
const groupedTriggeredAlerts = computed(() => {
  const map = new Map()
  for (const a of triggeredAlerts.value) {
    const key = `${a.metric_name || ''}|${a.asset_name || ''}`
    if (!map.has(key)) {
      map.set(key, { key, metric_name: a.metric_name, asset_name: a.asset_name, severity: a.severity, items: [] })
    }
    map.get(key).items.push(a)
  }
  return Array.from(map.values()).sort((a, b) => {
    const severityOrder = { critical: 0, high: 1, warning: 2, medium: 3, info: 4, low: 5 }
    return (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9)
  })
})

// 以分组为粒度：取最新一条告警作为代表执行诊断/AI分析
async function runDiagnoseGroup(group, force = false) {
  const rep = group.items[0]
  groupDiagState.value = { ...groupDiagState.value, [group.key]: 'loading' }
  try {
    const data = await request.post(`/remediation/api/diagnose/${rep.id}?force=${force}`, {}, { timeout: 130000 })
    if (data.ok) {
      const cmds = data.commands || []
      const label = `${group.metric_name || '未知指标'} · ${group.asset_name || '未知资产'}`
      groupDiagData.value = { ...groupDiagData.value, [group.key]: { groupLabel: label, commands: cmds, cached: data.cached || false } }
      groupDiagState.value = { ...groupDiagState.value, [group.key]: 'done' }
      ElMessage.success(data.cached ? '使用缓存诊断结果，点击「诊断报告」查看' : `诊断完成 ${cmds.length} 条命令，点击「诊断报告」查看`)
      loadPendingActions()
    } else {
      groupDiagState.value = { ...groupDiagState.value, [group.key]: 'idle' }
      ElMessage.error('诊断失败: ' + (data.error || '未知错误'))
    }
  } catch (e) {
    groupDiagState.value = { ...groupDiagState.value, [group.key]: 'idle' }
    ElMessage.error('诊断请求失败: ' + e.message)
  }
}

async function aiAnalyzeGroup(group) {
  const rep = group.items[0]
  groupAiState.value = { ...groupAiState.value, [group.key]: 'loading' }
  try {
    await request.post(`/remediation/api/diagnose/${rep.id}`, {}, { timeout: 130000 })
    const data = await request.post(`/remediation/api/ai-analyze/${rep.id}`, {}, { timeout: 130000 })
    if (data.ok) {
      const a = data.analysis || {}
      const label = `${group.metric_name || '未知指标'} · ${group.asset_name || '未知资产'}`
      groupAiData.value = { ...groupAiData.value, [group.key]: {
        groupLabel: label, dedup: data.dedup || false,
        root_cause: a.root_cause || '', impact: a.impact || '',
        action_type: a.action_type || '', command: a.command || '',
        command_description: a.command_description || '',
        risk_level: a.risk_level || 'medium',
        recommended_workflow_id: a.recommended_workflow_id || null,
        recommended_workflow_name: a.recommended_workflow_name || '',
      }}
      groupAiState.value = { ...groupAiState.value, [group.key]: 'done' }
      ElMessage.success(data.dedup ? 'AI 方案已存在，点击「AI 方案」查看，在下方审批执行' : 'AI 分析完成，点击「AI 方案」查看，在下方审批执行')
      loadPendingActions()
    } else {
      groupAiState.value = { ...groupAiState.value, [group.key]: 'idle' }
      ElMessage.error('AI 分析失败: ' + (data.error || '未知错误'))
    }
  } catch (e) {
    groupAiState.value = { ...groupAiState.value, [group.key]: 'idle' }
    ElMessage.error('AI 分析请求失败: ' + e.message)
  }
}

// 重新分析：取消旧 PA + 重新 AI 分析，始终可用（无 PA 时也可触发）
async function reanalyzeGroup(group) {
  const rep = group.items[0]
  groupReanalyzing.value = group.key
  try {
    const data = await request.post(`/remediation/api/ai-reanalyze-alert/${rep.id}`, {}, { timeout: 130000 })
    if (data.ok) {
      const a = data.analysis || {}
      const label = `${group.metric_name || '未知指标'} · ${group.asset_name || '未知资产'}`
      groupAiData.value = { ...groupAiData.value, [group.key]: {
        groupLabel: label, dedup: false,
        root_cause: a.root_cause || '', impact: a.impact || '',
        action_type: a.action_type || '', command: a.command || '',
        command_description: a.command_description || '',
        risk_level: a.risk_level || 'medium',
        recommended_workflow_id: a.recommended_workflow_id || null,
        recommended_workflow_name: a.recommended_workflow_name || '',
      }}
      groupAiState.value = { ...groupAiState.value, [group.key]: 'done' }
      ElMessage.success('AI 已重新分析，请审核新方案')
      loadPendingActions()
    } else {
      ElMessage.error('重新分析失败: ' + (data.error || '未知错误'))
    }
  } catch (e) { ElMessage.error('重新分析请求失败: ' + e.message) }
  finally { groupReanalyzing.value = '' }
}

async function loadPendingActions() {
  pendingLoading.value = true
  try {
    const data = await request.get('/remediation/api/ai-pending', { params: { status: pendingFilter.value } })
    pendingActions.value = data.items || []
    actionTotal.value = data.total || 0
  } catch (e) { ElMessage.error('加载待审批动作失败: ' + e.message) }
  finally { pendingLoading.value = false }
}

// 恢复 AI 方案状态：独立加载全状态 pending actions 与告警分组匹配，不受当前筛选影响
async function restoreAiState() {
  if (!triggeredAlerts.value.length) return
  // 构建 alert_id -> groupKey 映射
  const alertToGroup = new Map()
  for (const a of triggeredAlerts.value) {
    const key = `${a.metric_name || ''}|${a.asset_name || ''}`
    alertToGroup.set(a.id, key)
  }
  // 独立请求全状态 PA，避免被 pendingFilter 过滤掉已执行/已取消的方案
  try {
    const allPa = await request.get('/remediation/api/ai-pending', { params: { status: 'all', limit: 100 } })
    for (const pa of (allPa.items || [])) {
      if (pa.source !== 'ai') continue
      const groupKey = alertToGroup.get(pa.alert_id)
      if (!groupKey) continue
      if (groupAiState.value[groupKey] === 'done') continue
      const parts = groupKey.split('|')
      const label = `${parts[0] || '未知指标'} · ${parts[1] || '未知资产'}`
      groupAiData.value = { ...groupAiData.value, [groupKey]: {
        groupLabel: label, dedup: true,
        root_cause: pa.root_cause || '',
        impact: pa.impact || '',
        action_type: pa.action_type || '',
        command: pa.command || '',
        command_description: pa.reason || '',
        risk_level: pa.risk_level || 'medium',
        recommended_workflow_id: pa.workflow_id || null,
        recommended_workflow_name: pa.workflow_name || '',
      }}
      groupAiState.value = { ...groupAiState.value, [groupKey]: 'done' }
    }
  } catch (_) { /* 静默失败 */ }
}

// 按 alert_id 分组：同告警下并排展示规则方案与 AI 方案，供人工择优
const groupedPendingActions = computed(() => {
  const map = new Map()
  for (const pa of pendingActions.value) {
    const key = pa.alert_id || `no-alert-${pa.id}`
    if (!map.has(key)) {
      map.set(key, { alert_id: key, alert_message: pa.alert_message, items: [] })
    }
    map.get(key).items.push(pa)
  }
  return Array.from(map.values())
})
function sourceLabel(s) { return s === 'rule' ? '规则方案' : 'AI 方案' }
function sourceClass(s) { return s === 'rule' ? 'src-rule' : 'src-ai' }

// 转交智能助手深度分析：注入告警+诊断+AI方案上下文，创建 Agent 会话
async function transferToAgent(pa) {
  try {
    const data = await request.post('/agent/transfer-from-remediation', {
      alert_id: pa.alert_id,
      pending_action_id: pa.id,
    }, { timeout: 30000 })
    if (data.session_id) {
      // 设置待打开会话 ID，AgentChatView onMounted 会读取并自动打开
      window._pendingAgentSessionId = data.session_id
      window._navigateTo && window._navigateTo('agent-chat')
      ElMessage.success('已转交智能助手，正在跳转...')
    } else {
      ElMessage.error('转交失败: ' + (data.error || '未知错误'))
    }
  } catch (e) { ElMessage.error('转交请求失败: ' + e.message) }
}

async function confirmAction(id) {
  try {
    const data = await request.post(`/remediation/api/ai-pending/${id}/confirm`)
    if (data.success) {
      ElMessage.success('✅ 执行成功: ' + (data.output || ''))
    } else {
      ElMessage.error('❌ 执行失败: ' + (data.output || data.error || '未知错误'))
    }
    pendingFilter.value = 'all'
    loadPendingActions()
    loadTriggeredAlerts()
  } catch (e) { ElMessage.error('确认失败: ' + e.message) }
}

async function cancelAction(id) {
  if (!await ElMessageBox.confirm('确认取消此动作？', '取消确认', { type: 'info' }).catch(() => false)) return
  try {
    await request.post(`/remediation/api/ai-pending/${id}/cancel`)
    ElMessage.success('已取消')
    pendingFilter.value = 'all'
    loadPendingActions()
  } catch (e) { ElMessage.error('取消失败: ' + e.message) }
}

async function reanalyze(pa) {
  reanalyzingId.value = pa.id
  try {
    const data = await request.post(`/remediation/api/ai-reanalyze/${pa.id}`, {}, { timeout: 130000 })
    if (data.ok) {
      ElMessage.success('AI 换了新思路，请审核新方案')
      pendingFilter.value = 'all'
      loadPendingActions()
    } else {
      ElMessage.error('重新分析失败: ' + (data.error || '未知错误'))
    }
  } catch (e) { ElMessage.error('重新分析请求失败: ' + e.message) }
  finally { reanalyzingId.value = 0 }
}

async function reanalyzeAlert(pa) {
  reanalyzingId.value = pa.id
  try {
    const data = await request.post(`/remediation/api/ai-reanalyze-alert/${pa.alert_id}`, {}, { timeout: 130000 })
    if (data.ok) {
      ElMessage.success('AI 已重新分析，请审核新方案')
      pendingFilter.value = 'all'
      loadPendingActions()
    } else {
      ElMessage.error('重新分析失败: ' + (data.error || '未知错误'))
    }
  } catch (e) { ElMessage.error('重新分析请求失败: ' + e.message) }
  finally { reanalyzingId.value = 0 }
}

function toggleDiagnosis(paId) {
  diagnosisOpen.value = { ...diagnosisOpen.value, [paId]: !diagnosisOpen.value[paId] }
}

function diagnosisDuration(commands) {
  if (!commands || !commands.length) return ''
  const total = commands.reduce((sum, c) => sum + (c.duration_ms || 0), 0)
  return total >= 1000 ? `共 ${(total / 1000).toFixed(1)}s` : `共 ${total}ms`
}

function diagnosisRounds(commands) {
  if (!commands || !commands.length) return 1
  const rounds = new Set(commands.map(c => c.round_num ?? 0))
  return rounds.size
}

function groupedByRound(commands) {
  if (!commands || !commands.length) return []
  const map = new Map()
  for (const c of commands) {
    const rn = c.round_num ?? 0
    if (!map.has(rn)) map.set(rn, [])
    map.get(rn).push(c)
  }
  return Array.from(map.entries()).map(([rn, cmds]) => ({
    round: rn,
    label: rn === 0 ? '静态初诊' : `第${rn}轮 AI 补诊`,
    commands: cmds,
  }))
}

// ── 简单规则 ──
const loading = ref(false)
const remediations = ref([])
const rules = ref([])
const actions = ref({})
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', rule_id: 0, action_type: 'restart', params_target: '', params_count: 2, params_script: '', params_command: '' })

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/remediation/api/list')
    remediations.value = data.remediations || []
    rules.value = data.rules || []
    actions.value = data.actions || {}
    total.value = data.total || 0
  } catch (e) { ElMessage.error('加载失败: ' + e.message) }
  finally { loading.value = false }
}

function ruleName(id) { if (!id) return '任何告警'; const r = rules.value.find(x => x.id === id); return r ? r.name : `规则#${id}` }

function openCreate() {
  Object.assign(form, { name: '', rule_id: 0, action_type: 'restart', params_target: '', params_count: 2, params_script: '', params_command: '' })
  createVisible.value = true
}
function onActionChange() {}

async function createRule() {
  if (!form.name || !form.action_type) { ElMessage.warning('请填写名称和动作'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('rule_id', form.rule_id)
    fd.append('action_type', form.action_type)
    fd.append('params_target', form.params_target)
    fd.append('params_count', form.params_count)
    fd.append('params_script', form.params_script)
    fd.append('params_command', form.params_command)
    await request.post('/remediation/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadData()
  } catch (e) { ElMessage.error('创建失败: ' + e.message) }
  finally { creating.value = false }
}

async function deleteRule(r) {
  try {
    await ElMessageBox.confirm(`确认删除规则"${r.name}"？`, '删除确认')
    await request.post(`/remediation/api/${r.id}/delete`)
    ElMessage.success('已删除')
    loadData()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

// ── 执行记录 ──
const logs = ref([])
const logDetail = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const logTotal = ref(0)
const totalPages = ref(1)
const jumpPage = ref(1)
const pageNumbers = computed(() => {
  const pages = []; const cur = currentPage.value; const tp = totalPages.value
  if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i) }
  else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 1); const end = Math.min(tp - 1, cur + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < tp - 3) pages.push('...')
    pages.push(tp)
  }
  return pages
})
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === currentPage.value) return
  currentPage.value = p; loadLogs()
}
async function loadLogs() {
  try {
    const data = await request.get('/remediation/api/logs', { params: { page: currentPage.value, per_page: pageSize.value } })
    logs.value = data.items || []; logTotal.value = data.total || 0; totalPages.value = data.total_pages || 1
  } catch (e) { ElMessage.error('加载执行记录失败: ' + e.message) }
}
function openLogDetail(lg) { logDetail.value = lg }
function formatTime(s) { return s ? s.substring(0, 19) : '-' }

onMounted(async () => {
  await loadTriggeredAlerts()   // 先加载告警（内部会恢复诊断状态）
  await loadPendingActions()    // 加载待审批列表（按筛选）
  restoreAiState()              // 独立恢复 AI 方案按钮状态（全状态 PA）
  loadData()
  loadLogs()
})
</script>

<style scoped>
.remediation-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.title-row { display: flex; align-items: center; gap: 16px; }
.tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 2px solid var(--border, rgba(0,0,0,0.07)); }
.tab { padding: 8px 18px; border: none; background: none; cursor: pointer; font-size: 0.85rem; color: var(--text-secondary, #64748b); border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
.tab:hover { color: var(--accent, #6366f1); }
.tab.active { color: var(--accent, #6366f1); border-bottom-color: var(--accent, #6366f1); font-weight: 600; }
.stats-bar { display: flex; gap: 12px; margin-bottom: 16px; }
.stat-box { flex: 1; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 18px; text-align: center; font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.stat-num { display: block; font-size: 1.6rem; font-weight: 700; color: var(--accent, #6366f1); margin-bottom: 2px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.btn-warning { color: #d97706; border-color: rgba(217,119,6,0.3); background: rgba(217,119,6,0.06); }
.btn-warning:hover { background: rgba(217,119,6,0.12); }
.btn-warning:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-transfer { color: #8b5cf6; border-color: rgba(139,92,246,0.3); background: rgba(139,92,246,0.06); }
.btn-transfer:hover { background: rgba(139,92,246,0.14); }
.btn-reanalyze { color: #f59e0b; border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.06); }
.btn-reanalyze:hover { background: rgba(245,158,11,0.14); }
.btn-rediagnose { color: #0ea5e9; border-color: rgba(14,165,233,0.3); background: rgba(14,165,233,0.06); }
.btn-rediagnose:hover { background: rgba(14,165,233,0.14); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.filter-select { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; font-size: 0.78rem; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.analyzing-row td { background: rgba(99,102,241,0.04); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.output-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.action { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.analysis-panel { border-color: var(--accent, #6366f1); }
.analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.analysis-item { padding: 8px 12px; background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 8px; }
.analysis-item:nth-child(3) { grid-column: 1 / -1; }
.analysis-item:nth-child(4) { grid-column: 1 / -1; }
.kv-key { display: block; font-size: 0.7rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600; }
.kv-val { margin: 0; font-size: 0.85rem; color: var(--text, #1e293b); line-height: 1.5; }
.cmd-block { display: block; padding: 10px 14px; background: #1e293b; color: #e2e8f0; border-radius: 8px; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.82rem; white-space: pre-wrap; word-break: break-all; margin: 0; }
.cmd-inline { padding: 1px 6px; background: #f1f5f9; color: #1e293b; border-radius: 4px; font-family: monospace; font-size: 0.78rem; }
.analysis-actions { display: flex; gap: 10px; margin-top: 16px; justify-content: center; }
.action-result { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 0.82rem; }
.action-result.success { background: rgba(34,197,94,0.1); color: #16a34a; }
.action-result.fail { background: rgba(239,68,68,0.1); color: #dc2626; }
.modal-close { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; padding: 0; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 520px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* ── 待审批动作分组并排展示 ── */
.pending-groups { display: flex; flex-direction: column; gap: 16px; }
.pending-group { border: 1px solid var(--border, rgba(0,0,0,0.08)); border-radius: 10px; overflow: hidden; }
.group-alert-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  background: rgba(239,68,68,0.06);
  border-bottom: 1px solid var(--border, rgba(0,0,0,0.08));
}
.alert-msg { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.group-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; padding: 12px; }
.plan-card {
  border: 1px solid var(--border, rgba(0,0,0,0.08));
  border-radius: 8px; padding: 12px;
  background: var(--bg-card-solid, #fff);
  display: flex; flex-direction: column; gap: 6px;
}
.plan-card.src-rule { border-left: 3px solid #3b82f6; }
.plan-card.src-ai { border-left: 3px solid #8b5cf6; }
.plan-card-header { display: flex; justify-content: space-between; align-items: center; }
.plan-source { font-size: 0.78rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; }
.plan-source.src-rule { background: rgba(59,130,246,0.1); color: #3b82f6; }
.plan-source.src-ai { background: rgba(139,92,246,0.1); color: #8b5cf6; }
.plan-title { font-size: 0.9rem; font-weight: 600; color: var(--text, #1e293b); }
.plan-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.plan-cmd { background: rgba(0,0,0,0.04); padding: 6px 8px; border-radius: 4px; font-family: 'SF Mono', Consolas, monospace; font-size: 0.78rem; word-break: break-all; }
.plan-cmd code { background: none; color: var(--text, #1e293b); }
.plan-cmd .wf-label { font-weight: 600; color: var(--text, #1e293b); margin-bottom: 4px; }
.plan-cmd .wf-steps { margin: 0; padding-left: 16px; }
.plan-cmd .wf-steps li { margin: 2px 0; }
.plan-cmd .wf-steps code { font-size: 0.72rem; }
.plan-reason { font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }

/* ── 命令解释 ── */
.cmd-explanation {
  display: flex; gap: 6px; align-items: flex-start;
  background: rgba(34,197,94,0.06); border: 1px solid rgba(34,197,94,0.15);
  border-radius: 6px; padding: 8px 10px;
}
.cmd-explanation-icon { font-size: 0.85rem; flex-shrink: 0; margin-top: 1px; }
.cmd-explanation-text {
  font-size: 0.78rem; color: var(--text, #1e293b);
  line-height: 1.6;
}
.plan-time { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); }
.plan-actions { display: flex; gap: 8px; margin-top: 4px; }

/* ── 诊断过程折叠面板 ── */
.diagnosis-section { margin-top: 6px; border-top: 1px dashed var(--border, rgba(0,0,0,0.1)); padding-top: 6px; }
.diagnosis-toggle {
  display: flex; align-items: center; gap: 6px; width: 100%;
  background: none; border: none; cursor: pointer; font-size: 0.78rem;
  color: var(--accent, #6366f1); font-weight: 500; padding: 4px 0;
  transition: opacity 0.2s;
}
.diagnosis-toggle:hover { opacity: 0.8; }
.diagnosis-icon { font-size: 0.65rem; transition: transform 0.2s; }
.diagnosis-time { margin-left: auto; font-size: 0.7rem; color: var(--text-secondary, #64748b); font-weight: 400; }
.diagnosis-commands {
  margin-top: 6px; display: flex; flex-direction: column; gap: 6px;
  max-height: 400px; overflow-y: auto; padding-right: 4px;
}
.diag-round-label {
  font-size: 0.7rem; font-weight: 600; color: var(--text-secondary, #64748b);
  padding: 4px 0 2px; border-bottom: 1px dashed var(--border, rgba(0,0,0,0.06));
  margin-top: 4px;
}
.diag-round-label:first-child { margin-top: 0; }
.diag-cmd-item {
  background: var(--bg-hover, rgba(0,0,0,0.02));
  border: 1px solid var(--border, rgba(0,0,0,0.06));
  border-radius: 6px; padding: 8px 10px;
}
.diag-cmd-header {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.diag-cmd-idx { font-weight: 600; color: var(--text-secondary, #64748b); font-size: 0.72rem; min-width: 18px; }
.diag-cmd-text {
  font-family: 'SF Mono', Consolas, monospace; font-size: 0.75rem;
  color: var(--text, #1e293b); background: rgba(0,0,0,0.04);
  padding: 1px 6px; border-radius: 3px; word-break: break-all;
}
.diag-cmd-status { font-size: 0.72rem; margin-left: auto; }
.diag-cmd-time { font-size: 0.68rem; color: var(--text-tertiary, #94a3b8); }
.diag-cmd-desc { font-size: 0.72rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.diag-cmd-output {
  margin: 4px 0 0; padding: 6px 8px;
  background: #1e293b; color: #e2e8f0;
  border-radius: 4px; font-family: 'SF Mono', Consolas, monospace;
  font-size: 0.7rem; line-height: 1.4;
  max-height: 150px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-all;
}
.diag-ok { color: #22c55e; }
.diag-fail { color: #ef4444; }

/* ── 根因 + 推理链 ── */
.reasoning-section {
  margin-top: 8px; border-top: 1px dashed var(--border, rgba(0,0,0,0.1));
  padding-top: 8px; display: flex; flex-direction: column; gap: 8px;
}
.reasoning-block {
  background: linear-gradient(135deg, rgba(99,102,241,0.04), rgba(139,92,246,0.06));
  border: 1px solid rgba(139,92,246,0.12);
  border-radius: 6px; padding: 8px 10px;
}
.reasoning-label {
  font-size: 0.75rem; font-weight: 600; color: var(--accent, #6366f1);
  margin-bottom: 4px;
}
.reasoning-text {
  font-size: 0.78rem; color: var(--text, #1e293b);
  line-height: 1.6; white-space: pre-wrap;
}

/* ── 告警聚合降噪 ── */
.alert-groups { display: flex; flex-direction: column; gap: 6px; }
.alert-group { border: 1px solid var(--border, rgba(0,0,0,0.08)); border-radius: 8px; overflow: hidden; }
.alert-group-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer; user-select: none;
  background: var(--bg-hover, rgba(0,0,0,0.02));
  transition: background 0.15s;
}
.alert-group-header:hover { background: rgba(99,102,241,0.04); }
.group-actions { margin-left: auto; display: flex; gap: 6px; flex-shrink: 0; }

/* ── 诊断/AI 按钮完成态 ── */
.btn-done {
  background: rgba(16,185,129,0.1); color: #10b981;
  border-color: rgba(16,185,129,0.3); font-weight: 600;
}
.btn-done:hover { background: rgba(16,185,129,0.18); }
.btn-done-ai {
  background: rgba(139,92,246,0.1); color: #8b5cf6;
  border-color: rgba(139,92,246,0.3); font-weight: 600;
}
.btn-done-ai:hover { background: rgba(139,92,246,0.18); }

/* ── 弹窗宽版（诊断报告 / AI方案）── */
.modal-wide { max-width: 720px; width: 95%; }
.diag-modal-body {
  display: flex; flex-direction: column; gap: 10px;
  max-height: 65vh; overflow-y: auto;
  padding: 20px;
}
.diag-result-item {
  background: var(--bg-hover, rgba(0,0,0,0.02));
  border: 1px solid var(--border, rgba(0,0,0,0.07));
  border-radius: 8px; padding: 10px 12px;
}
.diag-result-header {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px;
}
.diag-cache-tip {
  font-size: 0.78rem; color: #f59e0b;
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2);
  border-radius: 6px; padding: 6px 10px; margin-bottom: 8px;
}
.modal-tip {
  margin-top: 16px; text-align: center;
  font-size: 0.78rem; color: var(--text-secondary, #64748b);
  background: var(--bg-hover, rgba(0,0,0,0.02));
  border-radius: 6px; padding: 8px 12px;
}

.group-expand-icon { font-size: 0.6rem; color: var(--text-secondary, #64748b); min-width: 14px; }
.group-metric { font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); }
.group-asset { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.group-count {
  font-size: 0.7rem; padding: 2px 8px;
  background: rgba(99,102,241,0.08); color: var(--accent, #6366f1);
  border-radius: 8px; font-weight: 500;
}
.alert-group-body { border-top: 1px solid var(--border, rgba(0,0,0,0.08)); }
.table-compact th { padding: 6px 10px; font-size: 0.7rem; }
.table-compact td { padding: 6px 10px; font-size: 0.8rem; }
.log-row { cursor: pointer; }
.log-row:hover { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.log-detail-modal { max-width: 700px; }
.log-detail-modal .detail-row { display: flex; gap: 12px; margin-bottom: 10px; align-items: flex-start; }
.log-detail-modal .detail-row label { width: 80px; flex-shrink: 0; font-size: 0.82rem; color: var(--text-secondary, #64748b); padding-top: 2px; }
.log-detail-modal .detail-row span { font-size: 0.85rem; color: var(--text, #1e293b); }
.log-output-full {
  background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 8px;
  font-size: 0.8rem; line-height: 1.5; max-height: 400px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-all; font-family: 'JetBrains Mono', monospace;
}
</style>