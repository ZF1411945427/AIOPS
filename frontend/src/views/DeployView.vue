<template>
  <div class="deploy-page">
    <div class="toolbar">
      <h2>AI 自动部署</h2>
      <div class="toolbar-right">
        <el-select v-model="filterStatus" clearable placeholder="筛选状态" style="width:140px" @change="loadPlans">
          <el-option label="草稿" value="draft" />
          <el-option label="已规划" value="planned" />
          <el-option label="执行中" value="running" />
          <el-option label="成功" value="succeeded" />
          <el-option label="失败" value="failed" />
          <el-option label="已回滚" value="rolled_back" />
        </el-select>
        <button class="btn btn-primary" @click="showCreate = true">+ 新建部署计划</button>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="plans.length === 0" class="empty">
      <p>暂无部署计划，点击上方按钮创建</p>
    </div>

    <div v-else class="plan-grid">
      <div v-for="p in plans" :key="p.id" class="plan-card" :class="'status-' + p.status">
        <div class="card-clickable" @click="openPlan(p.id)">
          <div class="card-header">
            <span class="plan-name">{{ p.name }}</span>
            <span class="status-badge" :class="p.status">{{ statusLabel(p.status) }}</span>
          </div>
          <div class="card-body">
            <div class="card-meta" v-if="p.asset_ids && p.asset_ids.length">资产: {{ p.asset_ids.join(', ') }}</div>
            <div class="card-meta" v-if="p.artifact_path">{{ p.artifact_path }}</div>
            <div class="card-meta">{{ p.created_at }}</div>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-sm btn-delete" @click.stop="deletePlan(p.id, p.name)">删除</button>
        </div>
      </div>
    </div>

    <div v-if="total > perPage" class="pagination">
      <button :disabled="page <= 1" @click="page--; loadPlans()">上一页</button>
      <span>{{ page }} / {{ Math.ceil(total / perPage) }}</span>
      <button :disabled="page >= Math.ceil(total / perPage)" @click="page++; loadPlans()">下一页</button>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建部署计划</h3>
        <div class="form-row"><label>计划名称</label><input v-model="form.name" class="input" placeholder="如：生产环境 v1.0 发布" /></div>
        <div class="form-row"><label>描述</label><textarea v-model="form.description" class="input" rows="2" placeholder="可选"></textarea></div>
        <div class="form-row"><label>目标资产（可多选）</label>
          <el-select v-model="form.asset_ids" multiple filterable placeholder="选择目标资产" style="width:100%">
            <el-option v-for="a in allAssets" :key="a.id" :label="`${a.name} (${a.ip})`" :value="a.id" />
          </el-select>
        </div>
        <div class="form-row"><label>代码包路径 (artifact_path)</label><input v-model="form.artifact_path" class="input" placeholder="支持 Git 仓库(GitHub/Gitee)或 HTTP 下载地址，如 https://github.com/xxx/yyy 或 /opt/app" />
          <div class="hint">Git/HTTP 地址会在探查前自动下载到目标机；留空或填本地路径则不下载。离线部署填 <code>offline://</code> 前缀。</div>
        </div>
        <div class="form-row"><label>源码下载目标路径 (可选)</label><input v-model="form.artifact_download_path" class="input" placeholder="留空默认 /data/aiops-deploy/<计划名>" /></div>
        <div class="form-row"><label class="row-label">探查前自动下载源码</label>
          <el-switch v-model="form.artifact_auto_download" active-text="开启" inactive-text="关闭" />
        </div>
        <div class="form-row"><label>部署手册</label>
          <div class="doc-upload-area">
            <input ref="fileInput" type="file" accept=".md,.txt,.yaml,.yml" style="display:none" @change="onFileSelect" />
            <button class="btn btn-upload" @click="$refs.fileInput.click()">上传手册文件</button>
            <span v-if="form.doc_file_name" class="file-name">{{ form.doc_file_name }}</span>
          </div>
          <textarea v-model="form.doc_raw" class="input" rows="6" placeholder="或直接粘贴部署手册 Markdown 内容，可用 ${ENV_xxx} 标记环境敏感值"></textarea>
        </div>
        <div class="form-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="doCreate">创建</button>
        </div>
      </div>
    </div>

    <div v-if="detailPlan" class="modal-overlay" @click.self="closeDetail">
      <div class="modal wide">
        <div class="detail-header">
          <h3>{{ detailPlan.name }}</h3>
          <span class="status-badge" :class="detailPlan.status">{{ statusLabel(detailPlan.status) }}</span>
          <button class="btn btn-sm btn-delete" @click="deletePlan(detailPlan.id, detailPlan.name)" style="margin-left:auto">删除</button>
          <button class="btn-close" @click="closeDetail">✕</button>
        </div>

        <div class="plan-info">
          <div class="plan-info-row" v-if="detailPlan.artifact_path"><span class="info-label">源码地址</span><span class="info-value mono">{{ detailPlan.artifact_path }}</span></div>
          <div class="plan-info-row" v-if="detailPlan.artifact_download_path"><span class="info-label">下载目标</span><span class="info-value mono">{{ detailPlan.artifact_download_path }}</span></div>
          <div class="plan-info-row" v-if="'artifact_auto_download' in detailPlan"><span class="info-label">自动下载</span><span class="info-value">{{ detailPlan.artifact_auto_download ? '开启' : '关闭' }}</span></div>
          <div class="plan-info-row" v-if="detailPlan._asset_names && detailPlan._asset_names.length"><span class="info-label">目标资产</span><span class="info-value">{{ detailPlan._asset_names.join('、') }}</span></div>
          <div class="plan-info-row" v-if="detailPlan.created_at"><span class="info-label">创建时间</span><span class="info-value">{{ detailPlan.created_at }}</span></div>
        </div>

        <div class="detail-tabs">
          <button :class="{ active: detailTab === 'sop' }" @click="detailTab = 'sop'">SOP 步骤</button>
          <button :class="{ active: detailTab === 'env' }" @click="detailTab = 'env'">环境映射</button>
          <button :class="{ active: detailTab === 'preflight' }" @click="detailTab = 'preflight'">预检</button>
          <button :class="{ active: detailTab === 'execute' }" @click="detailTab = 'execute'">执行</button>
          <button :class="{ active: detailTab === 'report' }" @click="detailTab = 'report'">📄 报告</button>
        </div>

        <div class="detail-body">
          <div v-if="detailTab === 'sop'">
            <div class="action-bar">
              <div class="doc-upload-area">
                <input ref="detailFileInput" type="file" accept=".md,.txt,.yaml,.yml" style="display:none" @change="onDetailFileSelect" />
                <button class="btn btn-upload" @click="$refs.detailFileInput.click()">上传手册文件</button>
                <span v-if="detailPlan.doc_file_name" class="file-name">{{ detailPlan.doc_file_name }}</span>
              </div>
              <button class="btn btn-primary" :disabled="!detailPlan.doc_raw || detailPlan.status !== 'draft'" @click="aiParse">AI 解析手册</button>
              <span v-if="detailPlan.sop_json && detailPlan.sop_json.steps">共 {{ detailPlan.sop_json.steps.length }} 步</span>
            </div>
            <div v-if="parsing" class="loading">AI 正在解析手册...</div>
            <div v-if="parseError" class="error-msg">{{ parseError }}</div>
            <div v-if="envVars.length" class="env-vars">
              <h4>AI 识别到的环境参数</h4>
              <table class="table">
                <tr><th>参数名</th><th>说明</th><th>示例值</th><th>来源</th></tr>
                <tr v-for="ev in envVars" :key="ev.name">
                  <td><code>{{ '${' + ev.name + '}' }}</code></td>
                  <td>{{ ev.description }}</td>
                  <td>{{ ev.example }}</td>
                  <td>{{ ev.source }}</td>
                </tr>
              </table>
            </div>
            <div v-if="detailPlan.sop_json && detailPlan.sop_json.steps" class="step-list">
              <div v-for="s in detailPlan.sop_json.steps" :key="s.order" class="step-item">
                <div class="step-header">
                  <span class="step-order">步骤 {{ s.order }}</span>
                  <span class="risk-badge" :class="s.risk">{{ s.risk }}</span>
                </div>
                <div class="step-desc">{{ s.description }}</div>
                <div class="step-cmd" v-if="s.command"><code>{{ s.command }}</code></div>
                <div class="step-verify" v-if="s.verify">校验: <code>{{ s.verify }}</code></div>
                <div class="step-rollback" v-if="s.rollback">回滚: <code>{{ s.rollback }}</code></div>
              </div>
            </div>
          </div>

          <div v-if="detailTab === 'env'">
            <div class="action-bar">
              <button class="btn" :disabled="detailPlan.status === 'draft'" @click="downloadArtifact">📦 下载源码</button>
              <button class="btn" :disabled="detailPlan.status === 'draft'" @click="probeEnv">🔍 环境探查</button>
              <button class="btn btn-primary" :disabled="!detailPlan.environment_probe_json || Object.keys(detailPlan.environment_probe_json).length === 0" @click="autoEnv">⚙️ AI 自动分析</button>
              <button class="btn" :disabled="detailPlan.status === 'draft'" @click="resolveEnv">解析环境映射</button>
            </div>
            <div v-if="probing" class="loading">正在 SSH 探查目标机环境...</div>
            <div v-if="probeError" class="error-msg">{{ probeError }}</div>

            <!-- AI 自适应建议 -->
            <div v-if="envAnalysis && envAnalysis.adaptations && envAnalysis.adaptations.length" class="env-analysis">
              <h4>🤖 AI 环境自适应建议</h4>
              <div v-for="(ad, ai) in envAnalysis.adaptations" :key="ai" class="adapt-item">
                <div class="adapt-type"><span class="risk-badge medium">{{ ad.type }}</span> 步骤 {{ ad.step }}</div>
                <div class="adapt-reason">📌 {{ ad.reason }}</div>
                <div class="adapt-action" v-if="ad.action">💡 {{ ad.action }}</div>
              </div>
            </div>
            <div v-if="envAnalysis && envAnalysis.service_topology" class="env-analysis">
              <h4>🧭 服务拓扑分析</h4>
              <pre class="topology">{{ envAnalysis.service_topology }}</pre>
            </div>

            <!-- 源码下载结果 -->
            <div v-if="sourceLog" class="probe-result">
              <h4>📦 源码下载结果</h4>
              <div class="probe-item"><label>来源</label><code>{{ sourceLog.source || '—' }}</code></div>
              <div class="probe-item"><label>方式</label><code>{{ sourceLog.method || sourceLog.note || '—' }}</code></div>
              <div class="probe-item" v-if="sourceLog.dest"><label>目标路径</label><code>{{ sourceLog.dest }}</code></div>
              <div class="probe-sub" v-if="sourceLog.log && sourceLog.log.length">
                <label>下载日志</label><code>{{ sourceLog.log.join('\n') }}</code>
              </div>
              <div class="probe-sub" v-if="sourceLog.reason"><label>说明</label><code>{{ sourceLog.reason }}</code></div>
            </div>

            <!-- 环境探查结果 -->
            <div v-if="environmentProbe && Object.keys(environmentProbe).length" class="probe-result">
              <h4>🔍 环境探查结果</h4>
              <div class="probe-grid">
                <div class="probe-item"><label>OS</label><code>{{ environmentProbe.os || '—' }}</code></div>
                <div class="probe-item"><label>Docker</label><code>{{ environmentProbe.docker || '—' }}</code></div>
                <div class="probe-item"><label>磁盘</label><code>{{ environmentProbe.disk || '—' }}</code></div>
              </div>
              <div class="probe-sub" v-if="environmentProbe.images">
                <label>本地镜像</label><code>{{ environmentProbe.images }}</code>
              </div>
              <div class="probe-sub" v-if="environmentProbe.port_scan && Object.keys(environmentProbe.port_scan).length">
                <label>端口扫描</label><code>{{ Object.entries(environmentProbe.port_scan).map(([p,s]) => p + ':' + s).join('  ') }}</code>
              </div>
              <div class="probe-sub" v-if="environmentProbe.dirs && Object.keys(environmentProbe.dirs).length">
                <label>目录/文件</label>
                <div v-for="(v, d) in environmentProbe.dirs" :key="d" class="probe-file">
                  <code class="dir-key">{{ d }}</code>
                  <pre>{{ v }}</pre>
                </div>
              </div>
            </div>

            <div class="env-mapping-table" v-if="Object.keys(detailPlan.env_mapping).length">
              <table class="table">
                <tr><th>占位符</th><th>实际值</th></tr>
                <tr v-for="(v, k) in detailPlan.env_mapping" :key="k">
                  <td><code>{{ '${' + k + '}' }}</code></td>
                  <td>
                    <input v-model="detailPlan.env_mapping[k]" class="input" style="width:100%" />
                  </td>
                </tr>
              </table>
              <div class="action-bar">
                <button class="btn btn-primary" @click="saveEnvMapping">保存映射</button>
              </div>
            </div>
            <div v-else class="empty">暂无环境映射，请先 AI 解析手册后再设置</div>
          </div>

          <div v-if="detailTab === 'preflight'">
            <div class="action-bar">
              <button class="btn btn-primary" :disabled="detailPlan.status === 'draft'" @click="runPreflight">执行预检</button>
            </div>
            <div v-if="preflightLoading" class="loading">预检执行中...</div>
            <div v-if="preflightError" class="error-msg">{{ preflightError }}</div>
            <div v-if="preflightResults.length" class="preflight-results">
              <div v-for="r in preflightResults" :key="r.check + r.asset" class="preflight-item" :class="{ pass: r.passed, fail: !r.passed }">
                <span class="preflight-icon">{{ r.passed ? '✓' : '✗' }}</span>
                <div class="preflight-info">
                  <div class="preflight-check">{{ r.check }} <span class="asset-tag" v-if="r.asset">{{ r.asset }}</span></div>
                  <div class="preflight-cmd"><code>{{ r.command }}</code></div>
                  <div class="preflight-output" v-if="r.output">{{ r.output }}</div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="detailTab === 'execute'">
            <div class="action-bar">
              <button class="btn btn-primary" :disabled="detailPlan.status !== 'planned' || wsConnected || cleaning" @click="startDeployLive">开始部署（AI 执行引擎）</button>
              <button class="btn" :disabled="detailPlan.status !== 'running'" @click="stopDeployLive">停止</button>
              <button class="btn btn-danger" :disabled="['planned','draft','running'].includes(detailPlan.status) || wsConnected || cleaning" @click="rollbackCleanup">🧹 回滚清理</button>
              <span v-if="deploying && !wsConnected" class="loading">部署执行中...</span>
              <span v-if="wsConnected" class="live-tag" :class="cleaning ? 'clean-tag' : ''">● {{ cleaning ? '清理中' : 'AI 执行中' }}</span>
            </div>
            <div v-if="executeError" class="error-msg">{{ executeError }}</div>
            <div class="term-section" v-show="!cleaning && (wsConnected || wsHasOutput)">
              <div class="term-header">
                <span class="term-title">🚀 部署执行终端</span>
              </div>
              <div class="live-terminal" ref="deployTermEl"></div>
            </div>
            <div class="term-section" v-show="cleaning || cleanFinished">
              <div class="term-header">
                <span class="term-title clean-title">🧹 回滚清理终端</span>
              </div>
              <div class="live-terminal" ref="cleanTermEl"></div>
            </div>
            <div v-if="riskConfirmInfo" class="risk-confirm-bar">
              <span class="risk-confirm-icon">🔴</span>
              <span class="risk-confirm-text">{{ riskConfirmInfo.description || '高危操作' }}</span>
              <code class="risk-confirm-cmd">{{ riskConfirmInfo.command || '' }}</code>
              <span class="risk-confirm-label">需要您的确认</span>
              <button class="btn btn-sm btn-danger" @click="confirmRisk(true)">✅ 确认执行</button>
              <button class="btn btn-sm" @click="confirmRisk(false)">⛔ 拒绝</button>
            </div>
            <div v-if="dagPlan && dagPlan.length" class="dag-plan">
              <h4>🧠 AI 执行计划（DAG）</h4>
              <div v-for="g in dagPlan" :key="g.group_order" class="dag-group">
                <span class="dag-group-label">组 {{ g.group_order }} {{ g.parallel ? '⚡并行' : '→串行' }}</span>
                <span class="dag-group-reason">{{ g.reason }}</span>
                <span class="dag-steps">步骤 {{ g.step_orders.join(', ') }}</span>
              </div>
            </div>
            <div v-if="detailPlan.steps && detailPlan.steps.length" class="step-list">
              <div v-for="s in detailPlan.steps" :key="s.id" class="step-item" :class="'step-' + s.status">
                <div class="step-header">
                  <span class="step-order">步骤 {{ s.step_order }}</span>
                  <span class="risk-badge" :class="s.risk_level">{{ s.risk_level }}</span>
                  <span class="status-badge" :class="s.status">{{ statusLabel(s.status) }}</span>
                </div>
                <div class="step-desc">{{ s.description }}</div>
                <div class="step-cmd" v-if="s.command"><code>{{ s.command }}</code></div>
                <div class="step-output" v-if="s.output"><pre>{{ s.output }}</pre></div>
              </div>
            </div>
            <div v-else class="empty">请先 AI 解析手册生成部署步骤</div>

            <div v-if="cleanupHistory && cleanupHistory.length" class="report-section">
              <h4>🧹 回滚清理历史（共 {{ cleanupHistory.length }} 次）</h4>
              <div v-for="(c, ci) in cleanupHistory.slice().reverse()" :key="ci" class="cleanup-hist-item">
                <div class="cleanup-hist-head" @click="toggleCleanup(ci)">
                  <span class="cleanup-time">{{ c.cleaned_at }}</span>
                  <span class="cleanup-appdir" v-if="c.app_dir"><code>{{ c.app_dir }}</code></span>
                  <span class="cleanup-assets">资产 {{ (c.assets || []).length }} 台</span>
                  <span class="cleanup-toggle">{{ openCleanup[ci] === ci ? '▾' : '▸' }}</span>
                </div>
                <div v-if="openCleanup[ci] === ci" class="cleanup-log">
                  <template v-for="(a, ai) in (c.assets || [])" :key="ai">
                    <div class="cleanup-asset-title">═══ [{{ a.asset }}] {{ a.ip || '' }} ═══</div>
                    <pre v-for="(ln, li) in (a.lines || [])" :key="li">{{ ln }}</pre>
                  </template>
                </div>
              </div>
            </div>
          </div>

          <div v-if="detailTab === 'report'">
            <div class="action-bar">
              <button class="btn" :disabled="!detailPlan.status || detailPlan.status === 'draft' || detailPlan.status === 'planned'" @click="runPostVerify">🔍 部署后验证</button>
              <button class="btn btn-primary" :disabled="!detailPlan.status || detailPlan.status === 'draft' || detailPlan.status === 'planned'" @click="runGenerateReport">📝 生成报告</button>
              <template v-if="detailPlan.deploy_report_json && detailPlan.deploy_report_json.executive_summary">
                <a :href="`/deploy/api/plans/${detailPlan.id}/report/download?fmt=docx`" class="btn btn-download" target="_blank">📄 下载 Word</a>
                <a :href="`/deploy/api/plans/${detailPlan.id}/report/download?fmt=html`" class="btn btn-download-print" target="_blank">🌐 下载 HTML</a>
              </template>
              <span v-if="reportLoading" class="loading">生成中...</span>
            </div>
            <div v-if="detailPlan.deploy_report_json && detailPlan.deploy_report_json.executive_summary" class="report-full">
              <div class="report-header">
                <h3>{{ detailPlan.deploy_report_json.title || '部署报告' }}</h3>
                <span v-if="detailPlan.deploy_report_json.status" class="report-status-badge" :class="detailPlan.deploy_report_json.status">{{ statusLabel(detailPlan.deploy_report_json.status) }}</span>
              </div>
              <div class="report-meta-bar">
                <span>计划: {{ detailPlan.name }}</span>
                <span>部署次数: 第 {{ detailPlan.deploy_report_json.deploy_count || detailPlan.deploy_count || 0 }} 次</span>
                <span>时间: {{ detailPlan.deploy_report_json.deployed_at || '-' }}</span>
              </div>

              <!-- 执行摘要 -->
              <div class="report-section-card">
                <h4>📋 执行摘要</h4>
                <p class="report-summary-text">{{ detailPlan.deploy_report_json.executive_summary }}</p>
                <div class="kpi-grid">
                  <div class="kpi-item"><span class="kpi-label">总步骤</span><span class="kpi-value">{{ detailPlan.deploy_report_json.total_steps || 0 }}</span></div>
                  <div class="kpi-item success"><span class="kpi-label">成功</span><span class="kpi-value">{{ detailPlan.deploy_report_json.succeeded_steps || 0 }}</span></div>
                  <div class="kpi-item" v-if="detailPlan.deploy_report_json.failed_steps"><span class="kpi-label">失败</span><span class="kpi-value" style="color:#ef4444">{{ detailPlan.deploy_report_json.failed_steps }}</span></div>
                  <div class="kpi-item" v-if="detailPlan.deploy_report_json.skipped_steps"><span class="kpi-label">跳过</span><span class="kpi-value" style="color:#f59e0b">{{ detailPlan.deploy_report_json.skipped_steps }}</span></div>
                  <div class="kpi-item"><span class="kpi-label">资产</span><span class="kpi-value">{{ detailPlan.deploy_report_json.total_assets || 0 }}</span></div>
                  <div class="kpi-item" :class="detailPlan.deploy_report_json.preflight_passed ? 'success' : ''"><span class="kpi-label">预检</span><span class="kpi-value">{{ detailPlan.deploy_report_json.preflight_passed ? '✅' : '❌' }}</span></div>
                  <div class="kpi-item" :class="detailPlan.deploy_report_json.verification_passed ? 'success' : ''"><span class="kpi-label">验证</span><span class="kpi-value">{{ detailPlan.deploy_report_json.verification_passed ? '✅' : '❌' }}</span></div>
                  <div class="kpi-item"><span class="kpi-label">AI决策</span><span class="kpi-value">{{ detailPlan.deploy_report_json.ai_decisions || 0 }}</span></div>
                </div>
              </div>

              <!-- 部署架构 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.deployment_architecture">
                <h4>🏗️ 部署架构</h4>
                <p>{{ detailPlan.deploy_report_json.deployment_architecture }}</p>
              </div>

              <!-- 启停服务命令 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.start_stop_commands">
                <h4>🔌 启停服务命令</h4>
                <pre class="command-block">{{ detailPlan.deploy_report_json.start_stop_commands }}</pre>
              </div>

              <!-- 部署路径 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.deploy_paths">
                <h4>📂 部署路径</h4>
                <pre class="command-block">{{ detailPlan.deploy_report_json.deploy_paths }}</pre>
              </div>

              <!-- 服务端口 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.service_ports">
                <h4>🔌 服务端口</h4>
                <pre class="command-block">{{ detailPlan.deploy_report_json.service_ports }}</pre>
              </div>

              <!-- 访问方式 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.access_methods">
                <h4>🌐 访问方式</h4>
                <pre class="command-block">{{ detailPlan.deploy_report_json.access_methods }}</pre>
              </div>

              <!-- 登录信息 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.login_info">
                <h4>🔑 登录信息</h4>
                <pre class="command-block">{{ detailPlan.deploy_report_json.login_info }}</pre>
              </div>

              <!-- 环境信息 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.environment">
                <h4>🖥️ 环境信息</h4>
                <table class="report-table">
                  <tr v-for="(v, k) in detailPlan.deploy_report_json.environment" :key="k"><td class="env-key">{{ k }}</td><td>{{ typeof v === 'string' ? v : JSON.stringify(v) }}</td></tr>
                </table>
              </div>

              <!-- 时间线 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.timeline">
                <h4>⏱️ 时间线</h4>
                <p>{{ detailPlan.deploy_report_json.timeline }}</p>
              </div>

              <!-- 步骤执行 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.steps_table">
                <h4>📊 步骤执行结果</h4>
                <div class="report-steps-markdown" v-html="renderMarkdown(detailPlan.deploy_report_json.steps_table)"></div>
              </div>

              <!-- 关键观察 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.key_observations && detailPlan.deploy_report_json.key_observations.length">
                <h4>🔍 关键观察</h4>
                <ul><li v-for="(obs, oi) in detailPlan.deploy_report_json.key_observations" :key="oi">{{ obs }}</li></ul>
              </div>

              <!-- 验证结果 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.verification">
                <h4>✅ 部署验证</h4>
                <p>{{ detailPlan.deploy_report_json.verification }}</p>
              </div>

              <!-- 测试记录 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.test_results">
                <h4>🧪 测试记录</h4>
                <p>{{ detailPlan.deploy_report_json.test_results }}</p>
              </div>

              <!-- 问题 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.issues && detailPlan.deploy_report_json.issues.length">
                <h4>🐛 问题与处理</h4>
                <div v-for="(issue, ii) in detailPlan.deploy_report_json.issues" :key="ii" class="issue-item" :class="'severity-' + (issue.severity || 'low')">
                  <span class="issue-severity">[{{ issue.severity }}]</span>
                  <span class="issue-desc">{{ issue.description }}</span>
                  <span class="issue-resolve" v-if="issue.resolution">→ {{ issue.resolution }}</span>
                  <span class="issue-status" :class="issue.status">{{ issue.status }}</span>
                </div>
              </div>

              <!-- 风险评估 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.risk_assessment">
                <h4>⚠️ 风险评估</h4>
                <p>{{ detailPlan.deploy_report_json.risk_assessment }}</p>
              </div>

              <!-- 建议 -->
              <div class="report-section-card" v-if="detailPlan.deploy_report_json.recommendations && detailPlan.deploy_report_json.recommendations.length">
                <h4>💡 改进建议</h4>
                <ol><li v-for="(rec, ri) in detailPlan.deploy_report_json.recommendations" :key="ri">{{ rec }}</li></ol>
              </div>

              <!-- 总体评估 -->
              <div class="report-section-card overall" :class="detailPlan.deploy_report_json.overall_assessment ? detailPlan.deploy_report_json.overall_assessment.toLowerCase().includes('success') ? 'success' : detailPlan.deploy_report_json.overall_assessment.toLowerCase().includes('fail') ? 'fail' : '' : ''">
                <h4>📝 总体评估</h4>
                <p class="overall-text">{{ detailPlan.deploy_report_json.overall_assessment }}</p>
              </div>
            </div>
            <div v-else-if="detailPlan.status === 'succeeded' || detailPlan.status === 'failed' || detailPlan.status === 'rolled_back'" class="empty">
              点击「生成报告」按钮生成专业部署报告
            </div>

            <div v-if="testResults && testResults.tests && testResults.tests.length" class="report-section">
              <h4>🧪 测试记录</h4>
              <div class="test-summary">
                <span>总体: </span>
                <span :class="testResults.all_passed ? 'pass-text' : 'fail-text'">{{ testResults.all_passed ? '✅ 全部通过' : '❌ 有失败项' }}</span>
              </div>
              <div v-for="(t, ti) in testResults.tests" :key="ti" class="test-asset">
                <h5>{{ t.asset }} ({{ t.ip }})</h5>
                <table class="table">
                  <tr><th>检查项</th><th>结果</th><th>详情</th></tr>
                  <tr v-for="(test, tti) in t.tests" :key="tti" :class="test.passed ? 'pass-row' : 'fail-row'">
                    <td><code>{{ test.name }}</code></td>
                    <td><span :class="test.passed ? 'pass-text' : 'fail-text'">{{ test.passed ? '✓' : '✗' }}</span></td>
                    <td class="test-detail">{{ test.detail || '-' }}</td>
                  </tr>
                </table>
              </div>
            </div>

            <div v-if="executionHistory && executionHistory.length" class="report-section">
              <h4>📜 执行历史（共 {{ detailPlan.deploy_count || 0 }} 次）</h4>
              <table class="table">
                <tr><th>#</th><th>时间</th><th>状态</th><th>资产</th></tr>
                <tr v-for="(h, hi) in executionHistory.slice().reverse()" :key="hi">
                  <td>{{ hi + 1 }}</td>
                  <td>{{ h.executed_at }}</td>
                  <td><span class="status-badge" :class="h.status">{{ statusLabel(h.status) }}</span></td>
                  <td>{{ h.succeeded_assets }}/{{ h.total_assets }}</td>
                </tr>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import request from '@/api/request'

function renderMarkdown(text) {
  if (!text) return ''
  const md = String(text)
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- (.*)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.*)$/gm, '<li>$2</li>')
    .replace(/^\|(.+)\|$/gm, (m) => {
      const cells = m.split('|').filter(c => c.trim() !== '').map(c => `<td>${c.trim()}</td>`).join('')
      return `<tr>${cells}</tr>`
    })
    .replace(/(<tr>.*<\/tr>)/gs, '<table>$1</table>')
    .replace(/\n\n/g, '<br/>')
}

const loading = ref(false)
const plans = ref([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const filterStatus = ref('')
const showCreate = ref(false)
const allAssets = ref([])
const fileInput = ref(null)
const detailFileInput = ref(null)
const form = ref({ name: '', description: '', asset_ids: [], artifact_path: '', artifact_download_path: '', artifact_auto_download: true, doc_raw: '', doc_file_name: '' })

const detailPlan = ref(null)
const detailTab = ref('sop')
const parsing = ref(false)
const parseError = ref('')
const envVars = ref([])
const preflightLoading = ref(false)
const preflightError = ref('')
const preflightResults = ref([])
const deploying = ref(false)
const executeError = ref('')
const deployTermEl = ref(null)
const cleanTermEl = ref(null)
const wsConnected = ref(false)
const wsFinished = ref(false)
const wsHasOutput = ref(false)
const deployTerm = ref(null)
const cleanTerm = ref(null)
const probing = ref(false)
const probeError = ref('')
const environmentProbe = ref(null)
const sourceLog = ref(null)
const envAnalysis = ref(null)
const needDecision = ref(false)
const riskConfirmInfo = ref(null)
const dagPlan = ref([])
const reportLoading = ref(false)
const testResults = ref(null)
const executionHistory = ref([])
const cleanupHistory = ref([])
const openCleanup = ref({})
const cleaning = ref(false)
const cleanFinished = ref(false)
let deployWs = null

const statusLabel = (s) => ({
  draft: '草稿', planned: '已规划', running: '执行中',
  succeeded: '成功', failed: '失败', rolled_back: '已回滚',
  pending: '待执行', skipped: '已跳过',
}[s] || s)

function onFileSelect(e) {
  const f = e.target.files?.[0]
  if (!f) return
  form.value.doc_file_name = f.name
  const reader = new FileReader()
  reader.onload = (ev) => { form.value.doc_raw = ev.target.result }
  reader.readAsText(f)
}

function onDetailFileSelect(e) {
  const f = e.target.files?.[0]
  if (!f) return
  uploadDocFile(f)
}

async function uploadDocFile(f) {
  const fd = new FormData()
  fd.append('file', f)
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/upload-doc`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    if (res.plan) {
      detailPlan.value.doc_raw = res.plan.doc_raw || ''
      detailPlan.value.doc_file_name = res.file_name || f.name
      ElMessage.success(`手册已上传: ${res.file_name} (${(res.size / 1024).toFixed(1)} KB)`)
    }
  } catch (e) {
    ElMessage.error('上传失败')
  }
}

async function loadPlans() {
  loading.value = true
  try {
    const res = await request.get('/deploy/api/plans', { params: { status: filterStatus.value || undefined, page: page.value, per_page: perPage.value } })
    plans.value = (res.items || []).map(p => ({
      ...p,
      env_mapping: typeof p.env_mapping === 'object' ? p.env_mapping : {},
      sop_json: typeof p.sop_json === 'object' ? p.sop_json : {},
      asset_ids: Array.isArray(p.asset_ids) ? p.asset_ids : [],
    }))
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载计划列表失败')
  } finally {
    loading.value = false
  }
}

async function loadAssets() {
  try {
    const res = await request.get('/assets/api/list', { params: { page_size: 500 } })
    allAssets.value = res.items || []
  } catch (_) {}
}

async function deletePlan(id, name) {
  if (!confirm(`确定删除部署计划「${name}」？此操作不可恢复`)) return
  try {
    const res = await request.post(`/deploy/api/plans/${id}/delete`)
    if (res.ok) {
      ElMessage.success('已删除')
      loadPlans()
      if (detailPlan.value && detailPlan.value.id === id) closeDetail()
    } else {
      ElMessage.error(res.error || '删除失败')
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function doCreate() {
  if (!form.value.name) return ElMessage.warning('请填写计划名称')
  try {
    const res = await request.post('/deploy/api/plans/create', form.value)
    if (res.plan) {
      const planObj = res.plan || {}
      showCreate.value = false
      form.value = { name: '', description: '', asset_ids: [], artifact_path: '', artifact_download_path: '', artifact_auto_download: true, doc_raw: '', doc_file_name: '' }
      loadPlans()
      const pw = planObj.path_warning || res.path_warning
      if (pw) {
        ElMessageBox.confirm(pw, '路径非空提示', {
          confirmButtonText: '我知道，继续创建',
          cancelButtonText: '知道了',
          type: 'warning'
        }).catch(() => {})
      } else {
        ElMessage.success('创建成功')
      }
    }
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

async function openPlan(id) {
  try {
    const res = await request.get(`/deploy/api/plans/${id}`)
    res.env_mapping = typeof res.env_mapping === 'object' ? res.env_mapping : {}
    res.sop_json = typeof res.sop_json === 'object' ? res.sop_json : {}
    res.asset_ids = Array.isArray(res.asset_ids) ? res.asset_ids : []
    res._asset_names = (res.asset_ids || []).map(id => {
      const a = allAssets.value.find(x => x.id === id)
      return a ? `${a.name} (${a.ip})` : String(id)
    })
    detailPlan.value = res
    detailTab.value = 'sop'
    envVars.value = []
    preflightResults.value = []
    preflightError.value = ''
    executeError.value = ''
    testResults.value = res.test_results_json || null
    executionHistory.value = Array.isArray(res.execution_history_json) ? res.execution_history_json : []
    cleanupHistory.value = Array.isArray(res.cleanup_history_json) ? res.cleanup_history_json : []
  } catch (e) {
    ElMessage.error('加载计划详情失败')
  }
}

function closeDetail() {
  detailPlan.value = null
  loadPlans()
}

async function aiParse() {
  if (!detailPlan.value) return
  parsing.value = true
  parseError.value = ''
  envVars.value = []
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/parse`)
    if (res.error) {
      parseError.value = res.error
    } else {
      detailPlan.value.sop_json = res.sop || {}
      envVars.value = res.env_vars || []
      detailPlan.value.status = 'planned'
      ElMessage.success(`解析完成，共 ${res.step_count || 0} 步`)
    }
  } catch (e) {
    parseError.value = 'AI 解析请求失败'
  } finally {
    parsing.value = false
  }
}

async function resolveEnv() {
  if (!detailPlan.value) return
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/resolve-env`, { env_mapping: detailPlan.value.env_mapping || {} })
    if (res.env_mapping) {
      detailPlan.value.env_mapping = res.env_mapping
      ElMessage.success('环境映射已解析')
    }
  } catch (e) {
    ElMessage.error('环境映射解析失败')
  }
}

async function saveEnvMapping() {
  if (!detailPlan.value) return
  try {
    await request.post(`/deploy/api/plans/${detailPlan.value.id}/update`, { env_mapping: detailPlan.value.env_mapping })
    ElMessage.success('环境映射已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

async function downloadArtifact() {
  if (!detailPlan.value) return
  probing.value = true
  probeError.value = ''
  sourceLog.value = null
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/artifact-download`)
    if (res.error) {
      probeError.value = res.error
    } else {
      sourceLog.value = res
      ElMessage.success(res.skipped ? '源码已存在，跳过下载' : '源码下载完成')
    }
  } catch (e) {
    probeError.value = '源码下载请求失败'
  } finally {
    probing.value = false
  }
}

async function probeEnv() {
  if (!detailPlan.value) return
  probing.value = true
  probeError.value = ''
  environmentProbe.value = null
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/probe`)
    if (res.error) {
      probeError.value = res.error
    } else {
      environmentProbe.value = res.probe || {}
      ElMessage.success('环境探查完成')
    }
  } catch (e) {
    probeError.value = '环境探查请求失败'
  } finally {
    probing.value = false
  }
}

async function autoEnv() {
  if (!detailPlan.value) return
  probing.value = true
  probeError.value = ''
  envAnalysis.value = null
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/auto-env`)
    if (res.error) {
      probeError.value = res.error
    } else {
      if (res.env_mapping) detailPlan.value.env_mapping = res.env_mapping
      envAnalysis.value = res.analysis || {}
      ElMessage.success('AI 环境分析完成')
    }
  } catch (e) {
    probeError.value = 'AI 分析请求失败'
  } finally {
    probing.value = false
  }
}

async function sendDecision(action) {
  if (deployWs && deployWs.readyState === WebSocket.OPEN) {
    deployWs.send(JSON.stringify({ type: 'decision', action }))
  }
  needDecision.value = false
}

function confirmRisk(approved) {
  if (deployWs && deployWs.readyState === WebSocket.OPEN) {
    deployWs.send(JSON.stringify({ type: 'decision', action: approved ? 'confirm' : 'reject' }))
  }
  riskConfirmInfo.value = null
}

async function runPreflight() {
  preflightLoading.value = true
  preflightError.value = ''
  preflightResults.value = []
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/preflight`)
    if (res.error) {
      preflightError.value = res.error
    } else {
      preflightResults.value = res.results || []
    }
  } catch (e) {
    preflightError.value = '预检请求失败'
  } finally {
    preflightLoading.value = false
  }
}

async function startDeploy() {
  deploying.value = true
  executeError.value = ''
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/execute`)
    if (res.error) {
      executeError.value = res.error
    } else {
      ElMessage.success(`部署完成: ${res.status}, 成功 ${res.succeeded_assets || 0}/${res.total_assets || 0} 台`)
      const reload = await request.get(`/deploy/api/plans/${detailPlan.value.id}`)
      reload.env_mapping = typeof reload.env_mapping === 'object' ? reload.env_mapping : {}
      reload.sop_json = typeof reload.sop_json === 'object' ? reload.sop_json : {}
      reload.asset_ids = Array.isArray(reload.asset_ids) ? reload.asset_ids : []
      detailPlan.value = reload
    }
  } catch (e) {
    executeError.value = '部署执行请求失败'
  } finally {
    deploying.value = false
  }
}

function startDeployLive() {
  if (!detailPlan.value) return
  wsHasOutput.value = false
  wsFinished.value = false
  executeError.value = ''
  dagPlan.value = []
  riskConfirmInfo.value = null

  const wsUrl = `ws://${location.host}/deploy/ws/plans/${detailPlan.value.id}/execute`
  deployWs = new WebSocket(wsUrl)
  deployWs.onopen = () => {
    wsConnected.value = true
    detailPlan.value.status = 'running'
    nextTick(() => {
      if (!deployTermEl.value) return
      const fitAddon = new FitAddon()
      deployTerm.value = new Terminal({ cursorBlink: true, fontSize: 13, theme: { background: '#1e293b', foreground: '#e2e8f0' } })
      deployTerm.value.loadAddon(fitAddon)
      deployTerm.value.open(deployTermEl.value)
      fitAddon.fit()
      deployTerm.value.write('\x1b[36m⏳ 部署开始，等待实时输出...\x1b[0m\r\n')
      deployTerm.value.onData((data) => {
        if (deployWs && deployWs.readyState === WebSocket.OPEN) {
          deployWs.send(JSON.stringify({ type: 'input', data }))
        }
      })
    })
  }
  deployWs.onmessage = (e) => {
    wsHasOutput.value = true
    let event
    try { event = JSON.parse(e.data) } catch { return }
    if (deployTerm.value) {
      switch (event.type) {
        case 'status':
          break
        case 'resource_check':
          const rcPassed = event.passed
          deployTerm.value.write(`\r\n\x1b[${rcPassed ? '32' : '31'}m🔧 前置资源检查: ${rcPassed ? '✅ 通过' : '❌ 有风险'} [${event.recommendation || ''}] ${event.summary || ''}\x1b[0m\r\n`)
          if (event.checks && event.checks.length) {
            event.checks.forEach(c => {
              deployTerm.value.write(`\x1b[90m  ${c.passed ? '✓' : '✗'} ${c.name}: ${c.detail || ''}\x1b[0m\r\n`)
            })
          }
          break
        case 'strategy_selected':
          deployTerm.value.write(`\r\n\x1b[35m🧠 AI 策略选择: ${event.strategy || 'auto'} | 风险评分: ${event.risk_score || '?'}/100\x1b[0m\r\n`)
          if (event.reason) deployTerm.value.write(`\x1b[90m  ${event.reason}\x1b[0m\r\n`)
          break
        case 'risk_warning':
          deployTerm.value.write(`\r\n\x1b[31m⚠️ AI 历史模式预警 [${event.risk || ''}]: ${event.pattern || ''}\x1b[0m\r\n`)
          if (event.suggestion) deployTerm.value.write(`\x1b[33m  💡 建议: ${event.suggestion}\x1b[0m\r\n`)
          break
        case 'ai_plan':
          deployTerm.value.write(`\r\n\x1b[35m🧠 AI 理解意图: ${event.intent || ''}\x1b[0m\r\n`)
          if (event.adjustments && event.adjustments.length) {
            event.adjustments.forEach(a => deployTerm.value.write(`\x1b[90m  🔧 ${a}\x1b[0m\r\n`))
          }
          break
        case 'risk_confirm':
          riskConfirmInfo.value = {
            step: event.step,
            description: event.description || '',
            command: event.command || '',
            risk: event.risk || 'high',
            reason: event.reason || ''
          }
          deployTerm.value.write(`\r\n\x1b[31m🔴 高危操作需确认: ${event.description || ''}\x1b[0m\r\n`)
          deployTerm.value.write(`\x1b[90m  $ ${(event.command || '').slice(0, 120)}\x1b[0m\r\n`)
          break
        case 'health_gate':
          const hgIcon = event.passed ? '✅' : '❌'
          deployTerm.value.write(`\r\n\x1b[33m🔍 健康门控 步骤${event.step}: ${hgIcon} ${event.recommendation || ''}\x1b[0m\r\n`)
          if (event.checks && event.checks.length) {
            event.checks.forEach(c => {
              deployTerm.value.write(`\x1b[90m  ${c.passed ? '✓' : '✗'} ${c.name}: ${c.detail || ''}\x1b[0m\r\n`)
            })
          }
          break
        case 'dag_plan':
          dagPlan.value = event.groups || []
          deployTerm.value.write(`\r\n\x1b[36m🧠 AI 执行计划(DAG): ${(event.groups || []).map(g => `[组${g.group_order}${g.parallel ? '⚡并行' : '→串行'} 步骤${(g.step_orders || []).join(',')}]`).join(' ')}\x1b[0m\r\n`)
          break
        case 'parallel_group':
          deployTerm.value.write(`\r\n\x1b[35m📦 组 ${event.group}: ${event.parallel ? '⚡ 并行执行' : '→ 串行执行'} 步骤 [${(event.steps || []).join(', ')}]\x1b[0m\r\n`)
          break
        case 'ai_precheck':
          deployTerm.value.write(`\r\n\x1b[33m🤖 AI 预检 步骤${event.step}: 风险[${event.risk || ''}] ${event.reason || ''}\x1b[0m\r\n`)
          if (event.precheck) deployTerm.value.write(`\x1b[90m  前置检查: ${event.precheck}\x1b[0m\r\n`)
          break
        case 'ai_decision':
          deployTerm.value.write(`\r\n\x1b[36m🤖 AI 自主决策 步骤${event.step}: ${event.decision} — ${event.reason || ''}\x1b[0m\r\n`)
          if (event.fix_commands && event.fix_commands.length) {
            deployTerm.value.write(`\x1b[90m  🔧 修复: ${event.fix_commands.join('; ')}\x1b[0m\r\n`)
          }
          break
        case 'asset_start':
          deployTerm.value.write(`\r\n\x1b[33m═══ [${event.asset}] ${event.ip || ''} ═══\x1b[0m\r\n`)
          break
        case 'step_start':
          deployTerm.value.write(`\r\n\x1b[36m→ 步骤 ${event.step}: ${event.description}${event.ai_risk ? ` [AI风险:${event.ai_risk}]` : ''}${event.ai_intent ? ` | ${event.ai_intent}` : ''}\x1b[0m\r\n`)
          break
        case 'cmd':
          deployTerm.value.write(`\x1b[90m$ ${event.command}\x1b[0m\r\n`)
          break
        case 'output':
          deployTerm.value.write(event.line + '\r\n')
          break
        case 'step_end':
          if (event.status === 'succeeded') {
            deployTerm.value.write(`\x1b[32m✔ 步骤 ${event.step} 成功\x1b[0m\r\n`)
          } else {
            deployTerm.value.write(`\x1b[31m✘ 步骤 ${event.step} 失败 (exit=${event.exit_code || '?'})\x1b[0m\r\n`)
          }
          break
        case 'asset_end':
          deployTerm.value.write(`\x1b[33m═══ ${event.asset} ${event.status === 'succeeded' ? '成功' : '失败'} ═══\x1b[0m\r\n`)
          break
        case 'complete':
          deployTerm.value.write(`\r\n\x1b[1m${event.status === 'succeeded' ? '\x1b[32m' : '\x1b[31m'}部署完成: ${event.status}, 成功 ${event.succeeded_assets || 0}/${event.total_assets || 0} 台\x1b[0m\r\n`)
          deployTerm.value.write(`\r\n\x1b[36m📄 正在生成部署报告和验证...\x1b[0m\r\n`)
          setTimeout(() => {
            runPostVerify()
            runGenerateReport()
          }, 500)
          break
        case 'error':
          deployTerm.value.write(`\r\n\x1b[31m❌ ${event.message}\x1b[0m\r\n`)
          break
      }
    }
  }
  deployWs.onclose = () => {
    wsConnected.value = false
    wsFinished.value = true
    loadDetailPlan()
  }
  deployWs.onerror = () => {
    wsConnected.value = false
    executeError.value = 'WebSocket 连接失败'
  }
}

function stopDeployLive() {
  if (deployWs && deployWs.readyState === WebSocket.OPEN) {
    deployWs.close(); deployWs = null
  }
  wsConnected.value = false
  wsFinished.value = true
  // 强制停止：断开前端连接 + 后端自动执行回滚清理(停容器/清产物/重置 planned)
  request.post(`/deploy/api/plans/${detailPlan.value.id}/stop`, {})
    .then((res) => {
      if (res && res.error) ElMessage.warning(res.error)
      else if (res && res.message) ElMessage.success(res.message)
      loadDetailPlan()
    })
    .catch(() => { loadDetailPlan() })
}

function rollbackCleanup() {
  if (!detailPlan.value) return
  if (!confirm(`确定要回滚清理「${detailPlan.value.name}」？这将删除已部署的服务和文件，重置为可重新部署状态`)) return
  cleaning.value = true
  cleanFinished.value = false
  wsHasOutput.value = false
  wsFinished.value = false
  executeError.value = ''

  const wsUrl = `ws://${location.host}/deploy/ws/plans/${detailPlan.value.id}/rollback-cleanup`
  deployWs = new WebSocket(wsUrl)
  deployWs.onopen = () => {
    wsConnected.value = true
    nextTick(() => {
      if (!cleanTermEl.value) return
      const fitAddon = new FitAddon()
      cleanTerm.value = new Terminal({ cursorBlink: true, fontSize: 13, theme: { background: '#1e293b', foreground: '#e2e8f0' } })
      cleanTerm.value.loadAddon(fitAddon)
      cleanTerm.value.open(cleanTermEl.value)
      fitAddon.fit()
      cleanTerm.value.write('\x1b[33m🧹 开始清理回滚...\x1b[0m\r\n')
    })
  }
  deployWs.onmessage = (e) => {
    wsHasOutput.value = true
    let event
    try { event = JSON.parse(e.data) } catch { return }
    if (cleanTerm.value) {
      switch (event.type) {
        case 'output': cleanTerm.value.write(event.line + '\r\n'); break
        case 'asset_start': cleanTerm.value.write(`\r\n\x1b[33m═══ [${event.asset}] ${event.ip || ''} ═══\x1b[0m\r\n`); break
        case 'asset_end': cleanTerm.value.write(`\x1b[32m✔ ${event.asset} 清理完成\x1b[0m\r\n`); break
        case 'complete': cleanTerm.value.write(`\r\n\x1b[32m✔ 清理完成，状态已重置为 planned，可重新部署\x1b[0m\r\n`); break
        case 'error': cleanTerm.value.write(`\r\n\x1b[31m❌ ${event.message}\x1b[0m\r\n`); break
      }
    }
  }
  deployWs.onclose = () => {
    wsConnected.value = false
    cleaning.value = false
    cleanFinished.value = true
    loadDetailPlan()
  }
  deployWs.onerror = () => {
    wsConnected.value = false
    cleaning.value = false
    cleanFinished.value = true
    executeError.value = '清理回滚 WebSocket 连接失败'
  }
}

async function loadDetailPlan() {
  try {
    const res = await request.get(`/deploy/api/plans/${detailPlan.value.id}`)
    res.env_mapping = typeof res.env_mapping === 'object' ? res.env_mapping : {}
    res.sop_json = typeof res.sop_json === 'object' ? res.sop_json : {}
    res.asset_ids = Array.isArray(res.asset_ids) ? res.asset_ids : []
    detailPlan.value = res
    environmentProbe.value = res.environment_probe_json || null
    envAnalysis.value = res.env_analysis_json || null
    testResults.value = res.test_results_json || null
    executionHistory.value = Array.isArray(res.execution_history_json) ? res.execution_history_json : []
    cleanupHistory.value = Array.isArray(res.cleanup_history_json) ? res.cleanup_history_json : []
  } catch (_) {}
}

function toggleCleanup(idx) {
  openCleanup.value[idx] = openCleanup.value[idx] === idx ? null : idx
}

async function runPostVerify() {
  if (!detailPlan.value) return
  reportLoading.value = true
  try {
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/post-verify`)
    if (res.error) {
      ElMessage.error(res.error)
    } else {
      testResults.value = res.result || null
      ElMessage.success('部署后验证完成')
    }
  } catch (e) {
    ElMessage.error('验证失败')
  } finally {
    reportLoading.value = false
  }
}

async function runGenerateReport() {
  if (!detailPlan.value) return
  reportLoading.value = true
  try {
    // 生成报告前自动刷新最新预检与部署后验证，确保报告中"预检/验证"KPI 反映真实最新状态
    if (['succeeded', 'failed', 'rolled_back'].includes(detailPlan.value.status)) {
      try {
        await request.post(`/deploy/api/plans/${detailPlan.value.id}/preflight`)
      } catch (_) {}
      try {
        const vres = await request.post(`/deploy/api/plans/${detailPlan.value.id}/post-verify`)
        if (vres && vres.result) {
          testResults.value = vres.result
        }
      } catch (_) {}
    }
    const res = await request.post(`/deploy/api/plans/${detailPlan.value.id}/generate-report`)
    if (res.error) {
      ElMessage.error(res.error)
    } else {
      detailPlan.value.deploy_report_json = res.report || {}
      ElMessage.success('部署报告已生成')
    }
  } catch (e) {
    ElMessage.error('报告生成失败')
  } finally {
    reportLoading.value = false
  }
}

onMounted(() => {
  loadPlans()
  loadAssets()
})
</script>

<style scoped>
.deploy-page { padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.toolbar-right { display: flex; gap: 10px; align-items: center; }
.loading { text-align: center; padding: 40px; color: #888; }
.empty { text-align: center; padding: 60px; color: #888; }
.error-msg { background: #fef2f2; color: #dc2626; padding: 10px; border-radius: 6px; margin: 10px 0; }
.plan-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.plan-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; transition: box-shadow .2s; }
.plan-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.card-clickable { padding: 16px; cursor: pointer; }
.card-actions { padding: 0 16px 10px; display: flex; justify-content: flex-end; }
.btn-delete { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.btn-delete:hover { background: #fecaca; }
.plan-card.status-running { border-left: 3px solid #3b82f6; }
.plan-card.status-succeeded { border-left: 3px solid #22c55e; }
.plan-card.status-failed { border-left: 3px solid #ef4444; }
.plan-card.status-rolled_back { border-left: 3px solid #f59e0b; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.plan-name { font-weight: 600; font-size: 15px; }
.card-body { font-size: 13px; color: #666; }
.card-meta { margin-top: 4px; }
.plan-info { display: flex; flex-wrap: wrap; gap: 6px 20px; padding: 10px 16px; margin: 0 16px 12px; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 12px; }
.plan-info-row { display: flex; align-items: center; gap: 6px; min-width: 200px; }
.plan-info-row .info-label { color: #6b7280; white-space: nowrap; }
.plan-info-row .info-value { color: #111827; word-break: break-all; }
.plan-info-row .info-value.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.status-badge.draft { background: #f3f4f6; color: #6b7280; }
.status-badge.planned { background: #dbeafe; color: #2563eb; }
.status-badge.running { background: #e0f2fe; color: #0284c7; }
.status-badge.succeeded { background: #dcfce7; color: #16a34a; }
.status-badge.failed { background: #fef2f2; color: #dc2626; }
.status-badge.rolled_back { background: #fef3c7; color: #d97706; }
.status-badge.pending { background: #f3f4f6; color: #6b7280; }
.status-badge.skipped { background: #f3f4f6; color: #9ca3af; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 20px; }
.pagination button { padding: 6px 14px; border: 1px solid #d1d5db; background: #fff; border-radius: 4px; cursor: pointer; }
.pagination button:disabled { opacity: .5; cursor: default; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal { background: #fff; border-radius: 12px; padding: 24px; width: 90%; max-width: 500px; max-height: 80vh; overflow-y: auto; }
.modal.wide { max-width: 800px; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; color: #374151; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn { padding: 8px 16px; border: 1px solid #d1d5db; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-primary { background: #6366f1; color: #fff; border-color: #6366f1; }
.btn-primary:disabled { opacity: .5; cursor: default; }
.btn-close { background: none; border: none; font-size: 18px; cursor: pointer; padding: 4px; color: #666; }
.btn-upload { background: #e0e7ff; color: #4338ca; border-color: #c7d2fe; }
.btn-upload:hover { background: #c7d2fe; }
.doc-upload-area { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.file-name { font-size: 12px; color: #6366f1; }
.input { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
textarea.input { font-family: inherit; }
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.detail-header h3 { margin: 0; flex: 1; }
.detail-tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 2px solid #e5e7eb; }
.detail-tabs button { padding: 8px 16px; border: none; background: none; cursor: pointer; font-size: 14px; color: #6b7280; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.detail-tabs button.active { color: #6366f1; border-bottom-color: #6366f1; font-weight: 600; }
.action-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.step-list { display: flex; flex-direction: column; gap: 8px; }
.step-item { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
.step-item.step-succeeded { border-left: 3px solid #22c55e; }
.step-item.step-failed { border-left: 3px solid #ef4444; }
.step-item.step-running { border-left: 3px solid #3b82f6; }
.step-item.step-rolled_back { border-left: 3px solid #f59e0b; }
.step-item.step-skipped { opacity: .6; }
.step-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.step-order { font-weight: 600; font-size: 14px; }
.step-desc { font-size: 13px; color: #374151; margin-bottom: 4px; }
.step-cmd, .step-verify, .step-rollback { font-size: 12px; margin-top: 4px; }
.step-cmd code, .step-verify code, .step-rollback code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 12px; word-break: break-all; }
.step-output pre { background: #1f2937; color: #e5e7eb; padding: 8px; border-radius: 4px; font-size: 12px; overflow-x: auto; max-height: 200px; margin: 4px 0 0; }
.risk-badge { padding: 1px 6px; border-radius: 8px; font-size: 10px; font-weight: 600; }
.risk-badge.low { background: #dcfce7; color: #16a34a; }
.risk-badge.medium { background: #fef3c7; color: #d97706; }
.risk-badge.high { background: #fef2f2; color: #dc2626; }
.env-vars { margin: 12px 0; }
.env-vars h4 { margin: 0 0 8px; font-size: 14px; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 8px; border: 1px solid #e5e7eb; text-align: left; }
.table th { background: #f9fafb; font-weight: 600; }
.env-mapping-table { margin: 12px 0; }
.env-mapping-table td input { border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 6px; font-size: 13px; }
.preflight-results { display: flex; flex-direction: column; gap: 8px; }
.preflight-item { display: flex; gap: 10px; padding: 10px; border-radius: 8px; border: 1px solid #e5e7eb; }
.preflight-item.pass { border-left: 3px solid #22c55e; }
.preflight-item.fail { border-left: 3px solid #ef4444; }
.preflight-icon { font-size: 18px; font-weight: bold; flex-shrink: 0; }
.preflight-item.pass .preflight-icon { color: #22c55e; }
.preflight-item.fail .preflight-icon { color: #ef4444; }
.preflight-info { flex: 1; }
.preflight-check { font-weight: 600; font-size: 14px; }
.asset-tag { display: inline-block; background: #e0e7ff; color: #4338ca; padding: 0 6px; border-radius: 4px; font-size: 11px; margin-left: 4px; }
.preflight-cmd { margin-top: 4px; }
.preflight-cmd code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.preflight-output { margin-top: 4px; font-size: 12px; color: #666; white-space: pre-wrap; }
.live-terminal { background: #1e293b; border-radius: 0 0 8px 8px; padding: 8px; min-height: 200px; }
.term-section { margin-bottom: 16px; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }
.term-header { background: #0f172a; padding: 6px 12px; }
.term-title { font-size: 12px; font-weight: 600; color: #38bdf8; }
.term-title.clean-title { color: #fbbf24; }
.live-tag { display: inline-block; background: #dcfce7; color: #16a34a; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; animation: pulse 1.5s infinite; }
.clean-tag { background: #fef3c7; color: #d97706; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.terminal-fallback { color: #94a3b8; font-size: 13px; padding: 20px; text-align: center; }
.env-analysis { margin: 12px 0; padding: 12px; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; }
.env-analysis h4 { margin: 0 0 8px; font-size: 14px; }
.adapt-item { padding: 8px; border-bottom: 1px dashed #e5e7eb; }
.adapt-item:last-child { border-bottom: none; }
.adapt-type { font-weight: 600; font-size: 13px; }
.adapt-reason { font-size: 13px; color: #444; margin-top: 2px; }
.adapt-action { font-size: 12px; color: #2563eb; margin-top: 2px; }
.topology { background: #f1f5f9; padding: 8px; border-radius: 6px; font-size: 12px; white-space: pre-wrap; }
.probe-result { margin: 12px 0; }
.probe-result h4 { margin: 0 0 8px; font-size: 14px; }
.probe-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.probe-item { background: #f8fafc; padding: 6px 10px; border-radius: 6px; font-size: 12px; }
.probe-item label, .probe-sub label { display: block; font-weight: 600; color: #666; font-size: 11px; margin-bottom: 2px; }
.probe-sub { margin-bottom: 8px; font-size: 12px; }
.probe-sub code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }
.probe-file { margin-bottom: 6px; }
.probe-file .dir-key { display: block; background: #eef2ff; color: #4338ca; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-bottom: 2px; }
.probe-file pre { background: #f8fafc; padding: 6px; border-radius: 4px; font-size: 11px; max-height: 150px; overflow: auto; margin: 0; white-space: pre-wrap; }
.decision-bar { display: flex; align-items: center; gap: 8px; padding: 10px; background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px; margin-top: 8px; flex-wrap: wrap; }
.decision-label { font-weight: 600; color: #92400e; font-size: 13px; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
.btn-danger:hover { background: #fecaca; }
.report-section { margin: 16px 0; }
.report-section h4 { margin: 0 0 10px; font-size: 14px; }
.report-card { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; font-size: 13px; }
.report-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.report-label { font-weight: 600; color: #6b7280; font-size: 12px; }
.report-summary { font-size: 14px; color: #1f2937; margin-bottom: 10px; padding: 8px; background: #fff; border-radius: 6px; }
.report-field { margin-top: 8px; }
.report-field .report-label { display: block; margin-bottom: 4px; }
.report-pre { background: #fff; border: 1px solid #e5e7eb; padding: 8px; border-radius: 4px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; }
.report-field ul { margin: 4px 0; padding-left: 18px; }
.report-field li { font-size: 13px; color: #374151; margin-bottom: 2px; }
.assessment { font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.assessment.succeeded { background: #dcfce7; color: #16a34a; }
.assessment.failed { background: #fef2f2; color: #dc2626; }
.assessment.partial { background: #fef3c7; color: #d97706; }
.cleanup-hist-item { border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 8px; background: #f8fafc; }
.cleanup-hist-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; cursor: pointer; font-size: 13px; }
.cleanup-hist-head:hover { background: #f1f5f9; }
.cleanup-time { font-weight: 600; color: #0f172a; }
.cleanup-appdir code { background: #e2e8f0; padding: 1px 6px; border-radius: 4px; font-size: 12px; }
.cleanup-assets { color: #6b7280; font-size: 12px; }
.cleanup-toggle { margin-left: auto; color: #64748b; }
.cleanup-log { padding: 4px 12px 12px; border-top: 1px dashed #e2e8f0; }
.cleanup-asset-title { font-weight: 600; color: #b45309; font-size: 12px; margin: 8px 0 4px; }
.cleanup-log pre { background: #0f172a; color: #e2e8f0; border-radius: 4px; padding: 6px 8px; font-size: 12px; margin: 2px 0; white-space: pre-wrap; word-break: break-all; }
.test-summary { font-size: 14px; margin-bottom: 10px; }
.pass-text { color: #16a34a; font-weight: 600; }
.fail-text { color: #dc2626; font-weight: 600; }
.test-asset { margin-bottom: 12px; }
.test-asset h5 { margin: 0 0 6px; font-size: 13px; color: #374151; }
.test-detail { font-size: 12px; font-family: monospace; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pass-row td { background: #f0fdf4; }
.fail-row td { background: #fef2f2; }
.dag-plan { margin: 12px 0; padding: 12px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; }
.dag-plan h4 { margin: 0 0 8px; font-size: 14px; color: #0369a1; }
.dag-group { display: flex; gap: 12px; align-items: center; padding: 4px 0; font-size: 13px; }
.dag-group-label { background: #0ea5e9; color: #fff; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.dag-group-reason { color: #475569; font-size: 12px; flex: 1; }
.dag-steps { color: #0369a1; font-weight: 600; font-size: 12px; }
.report-full { padding: 0; }
.report-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.report-header h3 { margin: 0; font-size: 20px; color: #0f172a; }
.report-status-badge { padding: 3px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; color: #fff; }
.report-status-badge.succeeded { background: #22c55e; }
.report-status-badge.failed { background: #ef4444; }
.report-status-badge.rolled_back { background: #f59e0b; }
.report-status-badge.planned { background: #3b82f6; }
.report-meta-bar { display: flex; gap: 20px; font-size: 12px; color: #64748b; margin-bottom: 20px; padding: 8px 12px; background: #f8fafc; border-radius: 6px; }
.report-section-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; }
.report-section-card h4 { margin: 0 0 12px; font-size: 15px; color: #0f172a; }
.report-summary-text { font-size: 14px; line-height: 1.8; color: #334155; }
.kpi-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.kpi-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 16px; text-align: center; min-width: 80px; }
.kpi-item.success { border-color: #22c55e; background: #f0fdf4; }
.kpi-label { display: block; font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
.kpi-value { font-size: 22px; font-weight: 700; color: #0f172a; }
.report-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.report-table td { padding: 6px 10px; border: 1px solid #e2e8f0; }
.report-table .env-key { font-weight: 600; color: #475569; width: 120px; background: #f8fafc; }
.report-steps-markdown table { width: 100%; border-collapse: collapse; font-size: 13px; }
.report-steps-markdown td, .report-steps-markdown th { padding: 8px 10px; border: 1px solid #e2e8f0; }
.report-steps-markdown th { background: #f1f5f9; font-weight: 600; }
.issue-item { padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; border: 1px solid #e2e8f0; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; }
.issue-item.severity-high { border-left: 3px solid #ef4444; background: #fef2f2; }
.issue-item.severity-medium { border-left: 3px solid #f59e0b; background: #fffbeb; }
.issue-item.severity-low { border-left: 3px solid #22c55e; background: #f0fdf4; }
.issue-severity { font-weight: 600; font-size: 11px; color: #64748b; }
.issue-desc { flex: 1; }
.issue-resolve { color: #6366f1; font-size: 12px; }
.issue-status { padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.issue-status.resolved { background: #dcfce7; color: #16a34a; }
.issue-status.unresolved { background: #fef2f2; color: #dc2626; }
.overall-text { font-size: 15px; line-height: 1.8; padding: 12px; background: #f8fafc; border-radius: 8px; }
.report-section-card.overall.success { border-color: #22c55e; }
.report-section-card.overall.fail { border-color: #ef4444; }
.btn-download { padding: 8px 16px; border: 1px solid #6366f1; background: #eef2ff; color: #4338ca; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }
.btn-download:hover { background: #e0e7ff; }
.btn-download-print { padding: 8px 16px; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }
.btn-download-print:hover { background: #f3f4f6; }
.command-block { background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 8px; font-size: 13px; font-family: 'JetBrains Mono', 'Fira Code', monospace; white-space: pre-wrap; line-height: 1.6; margin: 0; }
.risk-confirm-bar { display: flex; align-items: center; gap: 8px; padding: 12px; background: #fef2f2; border: 2px solid #ef4444; border-radius: 8px; margin: 12px 0; flex-wrap: wrap; }
.risk-confirm-icon { font-size: 18px; }
.risk-confirm-text { font-weight: 600; color: #b91c1c; font-size: 14px; }
.risk-confirm-cmd { background: #fef2f2; color: #b91c1c; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-family: monospace; border: 1px solid #fecaca; }
.risk-confirm-label { font-size: 12px; color: #92400e; background: #fef3c7; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
</style>