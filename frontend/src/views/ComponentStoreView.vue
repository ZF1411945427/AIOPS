<template>
  <div class="store-page">
    <div class="page-header">
      <h1>📦 组件应用商店</h1>
      <p>官方组件一键部署 · 支持传统 / Docker / K8S(Helm) / 高可用 四种方式 · 配置优化 / 高可用 / 漏洞 / AI 分析</p>
    </div>

    <!-- 统计 -->
    <div class="stat-grid">
      <div class="stat-card"><div class="val blue">{{ stats.total_components }}</div><div class="lbl">可用组件</div></div>
      <div class="stat-card"><div class="val">{{ stats.total_installs }}</div><div class="lbl">安装记录</div></div>
      <div class="stat-card"><div class="val ok">{{ stats.running_installs }}</div><div class="lbl">运行中</div></div>
      <div class="stat-card"><div class="val warn">{{ stats.by_category ? Object.keys(stats.by_category).length : 0 }}</div><div class="lbl">组件分类</div></div>
    </div>

    <div class="tab-bar">
      <div class="tab-item" :class="{active: tab==='catalog'}" @click="tab='catalog'">组件目录</div>
      <div class="tab-item" :class="{active: tab==='installs'}" @click="tab='installs'; loadInstalls()">安装记录</div>
    </div>

    <!-- ═══ 组件目录 Tab ═══ -->
    <div v-show="tab==='catalog'" class="pane">
      <div class="filter-bar">
        <select v-model="filterCat" @change="loadCatalog">
          <option value="">全部分类</option>
          <option value="database">数据库</option>
          <option value="cache">缓存</option>
          <option value="message">消息</option>
          <option value="web">Web</option>
          <option value="observability">可观测</option>
        </select>
        <input v-model="keyword" placeholder="搜索组件..." @input="loadCatalog" />
      </div>
      <div v-if="!loading && comps.length===0" class="empty">暂无组件</div>
      <div v-else class="comp-grid">
        <div v-for="c in comps" :key="c.id" class="comp-card">
          <div class="comp-head">
            <span class="icon">{{ c.icon }}</span>
            <div class="title-box">
              <div class="name">{{ c.display_name }}</div>
              <div class="ver">{{ c.name }} · v{{ c.version }}</div>
            </div>
          </div>
          <div class="desc">{{ c.description }}</div>
          <div class="deploy-tags">
            <span v-for="d in c.deploy_types" :key="d" class="dt-tag">{{ deployLabel(d) }}</span>
          </div>
          <div class="foot">
            <span class="complexity">{{ c.complexity }}</span>
            <button class="btn btn-primary btn-sm" @click="openDeploy(c)">一键部署</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 安装记录 Tab(K8S 式部署计划列表) ═══ -->
    <div v-show="tab==='installs'" class="pane">
      <div class="inst-toolbar">
        <div class="status-filter">
          <button class="sf-btn" :class="{active: statusFilter===''}" @click="setStatus('')">全部</button>
          <button class="sf-btn" :class="{active: statusFilter==='running'}" @click="setStatus('running')">运行中</button>
          <button class="sf-btn" :class="{active: statusFilter==='deploying'}" @click="setStatus('deploying')">部署中</button>
          <button class="sf-btn" :class="{active: statusFilter==='failed'}" @click="setStatus('failed')">失败</button>
          <button class="sf-btn" :class="{active: statusFilter==='stopped'}" @click="setStatus('stopped')">已停止</button>
        </div>
        <button class="btn btn-primary btn-sm" @click="runBatchFullCheck">🔍 一键批量体检</button>
      </div>

      <div v-if="!filteredInstalls.length" class="empty">暂无安装记录，去「组件目录」一键部署吧</div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>组件</th>
              <th>目标机</th>
              <th>方式</th>
              <th>端口</th>
              <th>状态</th>
              <th>更新时间</th>
              <th style="width: 240px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in filteredInstalls" :key="it.id">
              <td class="pname">{{ iconOf(it.component_name) }} {{ it.component_name }}</td>
              <td>{{ it.asset_name || ('资产#'+it.asset_id) }}</td>
              <td>{{ deployLabel(it.deploy_type) }}</td>
              <td>{{ it.port || '-' }}</td>
              <td><span class="status-badge" :class="it.status">{{ ut(it.status) }}</span></td>
              <td class="muted">{{ (it.updated_at || '').slice(0,16) }}</td>
              <td class="row-actions">
                <button class="btn sm" @click="viewInstall(it)">📖 详情</button>
                <button class="btn sm" @click="openReport(it)">📄 部署报告</button>
                <button class="btn sm" v-if="it.status==='running'" @click="openAddAsset(it)">➕ 添加到资产</button>
                <button class="btn sm" @click="runHealthCheck(it)">🤖 AI 体检</button>
                <button class="btn sm danger" @click="delInstall(it)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══ 部署弹窗(优化: 组件摘要 + 两栏布局 + 分区卡片) ═══ -->
    <div v-if="deployComp" class="modal-overlay" @click.self="closeDeploy">
      <div class="modal-box wide deploy-dialog">
        <!-- 深色头部: 组件摘要 -->
        <div class="deploy-hero">
          <div class="hero-icon">{{ deployComp.icon }}</div>
          <div class="hero-info">
            <div class="hero-title">
              {{ deployComp.display_name }}
              <span class="hero-ver">{{ deployComp.name }} · v{{ deployComp.version }}</span>
            </div>
            <div class="hero-sub">{{ deployComp.description }}</div>
            <div class="hero-tags">
              <span v-for="d in deployComp.deploy_types" :key="d" class="hero-tag">{{ deployLabel(d) }}</span>
              <span v-if="deployComp.default_port" class="hero-tag port">端口 {{ deployComp.default_port }}</span>
            </div>
          </div>
          <div class="hero-badge">
            <span class="status-badge lg" :class="deployStatusClass">{{ deployStatusText }}</span>
          </div>
          <button class="hero-close" @click="closeDeploy">×</button>
        </div>

        <!-- 两栏主体 -->
        <div class="deploy-body">
          <!-- 左栏: 配置(Tab: 基础配置 / 部署方案, 便于后续扩展更多配置) -->
          <div class="deploy-col config-col">
            <div class="cfg-tabs-head">
              <button class="config-tab" :class="{active: cfgTab==='base'}" @click="cfgTab='base'">基础配置</button>
              <button class="config-tab" :class="{active: cfgTab==='plan'}" @click="cfgTab='plan'"><span v-if="deployPlan.ai_generated" class="plan-ai" style="margin-left:0">AI</span>部署方案</button>
            </div>

            <!-- Tab: 基础配置 -->
            <div v-show="cfgTab==='base'" class="cfg-tab-pane">
              <div class="cfg-field">
                <label>目标机 <span class="req">*</span></label>
                <select v-model="deployForm.asset_id" :disabled="deploying" @change="renderRecipe">
                  <option :value="0">请选择目标机</option>
                  <option v-for="a in assets" :key="a.id" :value="a.id"
                    :class="{ 'opt-offline': (a.status||'online')!=='online' }">
                    {{ a.name }} <i>({{ a.ip }})</i>{{ (a.status||'online')!=='online' ? ' — offline' : '' }}
                  </option>
                </select>
              </div>

              <div class="cfg-field">
                <label>部署方式 <span class="req">*</span></label>
                <div class="mode-grid">
                  <button v-for="d in deployComp.deploy_types" :key="d" class="mode-btn"
                    :class="{ active: deployForm.deploy_type === d }" :disabled="deploying" @click="selectDeployType(d)">
                    {{ deployLabel(d) }}
                  </button>
                </div>
              </div>

              <div class="cfg-row" v-if="deployForm.asset_id">
                <div class="cfg-field">
                  <label>部署路径</label>
                  <input v-model="deployForm.deploy_path" :disabled="deploying" placeholder="留空自动生成" />
                </div>
              </div>

              <!-- ═══ 组件定制参数(按 param_schema 动态渲染, 真实注入 compose/脚本) ═══ -->
              <div v-if="deployComp.param_schema && deployComp.param_schema.length" class="param-block">
                <div class="param-title">⚙️ 组件定制参数</div>
                <div class="param-grid">
                  <div v-for="p in deployComp.param_schema" :key="p.key" class="cfg-field">
                    <label>{{ p.label }} <span v-if="p.required" class="req">*</span></label>
                    <select v-if="p.type==='select'" v-model="deployParams[p.key]" :disabled="deploying" @change="renderRecipe">
                      <option value="">请选择</option>
                      <option v-for="o in (p.options||[])" :key="o" :value="o">{{ o }}</option>
                    </select>
                    <input v-else-if="p.type==='number'" v-model.number="deployParams[p.key]" type="number" :disabled="deploying" :placeholder="p.placeholder || p.default || ''" @change="renderRecipe" />
                    <input v-else-if="p.type==='bool'" type="checkbox" v-model="deployParams[p.key]" :disabled="deploying" @change="renderRecipe" style="width:auto" />
                    <input v-else :type="p.type==='password' ? 'password' : 'text'" v-model="deployParams[p.key]" :disabled="deploying" :placeholder="p.placeholder || p.default || ''" @change="renderRecipe" />
                    <div v-if="p.hint" class="hint">{{ p.hint }}</div>
                  </div>
                </div>
              </div>

              <div class="offline-toggle" v-if="deployForm.deploy_type==='docker'">
                <label class="checkbox-row">
                  <input type="checkbox" v-model="deployForm.use_offline" :disabled="deploying" @change="renderRecipe" />
                  <span>📦 使用离线私有仓库(可选)</span>
                </label>
                <div class="hint" style="margin-left:2px">开启后 docker 镜像改从离线私有 Registry 拉取(需已默认配置仓库并已 load 离线包), 不对接则联网拉取。</div>
              </div>

              <template v-if="deployForm.deploy_type==='helm'">
                <div class="cfg-row">
                  <div class="cfg-field">
                    <label>命名空间</label>
                    <input v-model="deployForm.namespace" :disabled="deploying" placeholder="default" />
                  </div>
                  <div class="cfg-field">
                    <label>Release 名</label>
                    <input v-model="deployForm.release" :disabled="deploying" placeholder="release 名" />
                  </div>
                </div>
              </template>

              <details class="proxy-block" :disabled="deploying">
                <summary>网络代理 (可选)</summary>
                <div class="proxy-select-row">
                  <label>快速选用</label>
                  <select class="proxy-select" @change="applyProxy($event.target.value)">
                    <option value="">— 选择离线仓库已存代理 / 留空手填 —</option>
                    <option v-for="px in proxyList" :key="px.id" :value="px.id">{{ px.name }}{{ px.is_default ? ' (默认)' : '' }}</option>
                  </select>
                  <button class="btn sm" type="button" @click="refreshProxyList">刷新</button>
                </div>
                <div class="proxy-grid">
                  <div class="cfg-field">
                    <label>HTTP 代理</label>
                    <input v-model="deployForm.http_proxy" :disabled="deploying" placeholder="如 http://11.0.1.1:7897" />
                  </div>
                  <div class="cfg-field">
                    <label>HTTPS 代理</label>
                    <input v-model="deployForm.https_proxy" :disabled="deploying" placeholder="留空=用 HTTP 代理" />
                  </div>
                  <div class="cfg-field">
                    <label>NO_PROXY</label>
                    <input v-model="deployForm.no_proxy" :disabled="deploying" placeholder="127.0.0.1,localhost,.local" />
                  </div>
                </div>
                <div class="hint">Docker 部署时写入目标机 docker daemon, 使 docker pull 走代理拉取镜像</div>
              </details>
            </div>

            <!-- Tab: 部署方案 -->
            <div v-show="cfgTab==='plan'" class="cfg-tab-pane">
              <div class="plan-toolbar">
                <button class="btn sm primary" :disabled="!deployForm.asset_id || generatingPlan" @click="genPlan">
                  {{ generatingPlan ? '生成中...' : (deployPlan.plan ? '🔄 重新生成' : '🤖 AI 生成方案') }}
                </button>
                <span class="hint" v-if="precheckSystem">系统: {{ precheckSystem }}</span>
              </div>
              <div class="plan-meta" v-if="deployPlan.system">
                <span class="plan-system">{{ deployPlan.system }}</span>
                <span v-if="deployPlan.ai_generated" class="plan-ai">AI 生成</span>
              </div>
              <pre class="recipe" v-if="deployPlan.plan">{{ deployPlan.plan }}</pre>
              <div v-else class="plan-empty">先选目标机, 点上方「AI 生成方案」按系统类型生成可执行部署方案</div>
            </div>
          </div>

          <!-- 右栏: 部署执行 -->
          <div class="deploy-col exec-col">
            <div class="panel-title">
              部署执行
              <span v-if="deploying" class="exec-live"><i class="dot"></i>实时</span>
            </div>

            <!-- AI 决策门控卡片 -->
            <div v-if="decisionPending" class="decision-card">
              <div class="decision-head"><span class="decision-icon">🤖</span> AI 需你决策</div>
              <div class="decision-q">{{ decisionPending.question }}</div>
              <div class="decision-opts">
                <button v-for="(o,i) in decisionPending.options" :key="i" class="decision-opt"
                  @click="pickDecision(o.title)">
                  <span class="decision-opt-key">{{ ['A','B','C'][i] || (i+1) }}</span>
                  <span class="decision-opt-title">{{ o.title }}</span>
                  <span class="decision-opt-detail">{{ o.detail }}</span>
                </button>
              </div>
              <div class="decision-free" v-if="decisionPending.free">
                <input v-model="decisionPending.custom" placeholder="或输入自定义命令/方案..." @keyup.enter="submitDecision()" />
                <button class="btn primary sm" @click="submitDecision()">执行自定义</button>
              </div>
            </div>

            <!-- 阶段条 -->
            <div class="phase-bar" v-if="deploying">
              <div v-for="(s,i) in phases" :key="i" class="phase" :class="phaseState(i)">{{ s }}</div>
            </div>

            <!-- 执行区 Tab(避免一屏堆满) -->
            <div class="exec-tabs">
              <div class="exec-tabs-head">
                <button class="exec-tab" :class="{active: execTab==='check'}" @click="execTab='check'">🩺 预检</button>
                <button class="exec-tab" :class="{active: execTab==='log'}" @click="execTab='log'">🖥 日志</button>
                <button class="exec-tab" :class="{active: execTab==='ai'}" @click="execTab='ai'">🤖 AI 建议<span v-if="aiTips.length" class="tab-badge">{{ aiTips.length }}</span></button>
              </div>
            </div>

            <!-- Tab: 终端日志 -->
            <div v-show="execTab==='log'" class="terminal">
              <div class="term-head"><span>实时部署日志</span><span class="term-info" v-if="deploying">● 已连接</span></div>
              <div class="term-body term-body-lg" ref="termBodyRef">
                <div v-if="!logs.length" class="term-empty">等待部署日志...</div>
                <div v-for="(l,i) in logs" :key="i" class="tline" :class="l.type">
                  <span class="tts">{{ l.ts }}</span><span class="tmsg">{{ l.message }}</span>
                </div>
              </div>
            </div>

            <!-- Tab: AI 建议 -->
            <div v-show="execTab==='ai'" class="ai-panel ai-panel-lg">
              <div v-if="!aiTips.length" class="ai-empty">AI 将在各阶段实时生成建议...</div>
              <div v-for="(t,i) in aiTips" :key="i" class="ai-tip" :class="{ diagnostic: t.stage === 'diagnosis' }">
                <div class="ai-stage" v-if="t.stage !== 'diagnosis'">{{ stageLabel(t.stage) }}</div>
                <template v-if="t.stage === 'diagnosis'">
                  <div class="diag-head"><span class="diag-icon">⚠︎</span> AI 失败诊断</div>
                  <div class="diag-cause" v-if="t.root_cause">{{ t.root_cause }}</div>
                  <div class="ai-advice" v-if="t.advice">{{ t.advice }}</div>
                  <div class="diag-steps" v-if="t.steps && t.steps.length">
                    <div v-for="(s,si) in t.steps" :key="si" class="diag-step"><span class="diag-n">{{ si+1 }}</span>{{ s }}</div>
                  </div>
                  <div class="ai-risk" v-if="t.risk" :class="'risk-'+t.risk">风险: {{ t.risk }}</div>
                </template>
                <template v-else>
                  <div class="ai-summary">{{ t.summary }}</div>
                  <div class="ai-advice" v-if="t.advice">{{ t.advice }}</div>
                </template>
              </div>
            </div>

            <!-- Tab: 预检 / 报告 -->
            <div v-show="execTab==='check'" class="check-tab">
              <div class="precheck-panel" v-if="precheckChecks.length">
                <div class="precheck-title">预检明细 <span :class="precheckOk ? 'ok' : 'fail'">{{ precheckOk ? '通过' : precheckIssues.length + ' 项问题' }}</span></div>
                <div v-for="(c,i) in precheckChecks" :key="i" class="precheck-item">
                  <span class="precheck-mark" :class="c.ok ? 'ok' : 'fail'">{{ c.ok ? '✓' : '✗' }}</span>
                  <span class="precheck-name">{{ c.name }}</span>
                  <span class="precheck-msg" :class="c.ok ? 'ok' : 'fail'">{{ c.message }}</span>
                </div>
              </div>

              <div v-if="deployReport">
                <div v-if="deployReport.deliverable" class="report-box deliv">
                  <div class="report-title">AI 部署报告
                    <span class="report-overall" :class="'ov-'+deployReport.overview">{{ deployReport.overview }}</span>
                  </div>
                  <div class="report-conclusion">{{ deployReport.conclusion }}</div>
                  <template v-if="deployReport.root_cause"><div class="report-field"><span class="rf-label">根因</span>{{ deployReport.root_cause }}</div></template>
                  <template v-if="deployReport.executed"><div class="report-field"><span class="rf-label">已执行</span>{{ deployReport.executed }}</div></template>
                  <template v-if="deployReport.impact"><div class="report-field"><span class="rf-label">影响</span>{{ deployReport.impact }}</div></template>
                  <template v-if="deployReport.next_steps && deployReport.next_steps.length">
                    <div class="report-field"><span class="rf-label">下一步</span><div v-for="(ns,ni) in deployReport.next_steps" :key="ni" class="rf-item">· {{ ns }}</div></div>
                  </template>
                  <template v-if="deployReport.risks && deployReport.risks.length">
                    <div class="report-field"><span class="rf-label">风险</span><div v-for="(rk,ri) in deployReport.risks" :key="ri" class="rf-item risk-item">· {{ rk }}</div></div>
                  </template>
                  <button class="btn sm" style="margin-top:6px" @click="openReportRaw">查看完整报告</button>
                </div>
                <div v-else class="report-box">
                  <div class="report-title">四合一体检
                    <span class="report-overall" :class="'ov-'+deployReport.overall_status">{{ deployReport.overall_status }}</span>
                  </div>
                  <div class="report-summary" v-if="deployReport.summary">{{ deployReport.summary }}</div>
                  <button class="btn sm" style="margin-top:6px" @click="openReportRaw">查看完整报告</button>
                </div>
              </div>
              <div v-else-if="!deploying && resultText" class="result-box" :class="resultOk ? 'ok' : 'fail'">{{ resultText }}</div>
            </div>
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="modal-foot">
          <button class="btn" :disabled="deploying || prechecking || !deployForm.asset_id" @click="runPrecheck">
            {{ prechecking ? '预检中...' : '逻辑预检' }}
          </button>
          <button class="btn danger" v-if="deploying" @click="stopDeploy">■ 停止</button>
          <button class="btn primary" v-else :disabled="!deployForm.asset_id || !deployRecipe || prechecking" @click="startDeploy">▶ 开始部署</button>
          <button class="btn" v-if="!deploying" @click="closeDeploy">完成</button>
        </div>
      </div>
    </div>

    <!-- ═══ 检查结果抽屉 ═══ -->
    <div v-if="resultView" class="mask">
      <div class="modal wide">
        <div class="mhead">
          <h3>{{ resultView.title }}</h3>
          <button class="mclose" @click="resultView=null">✕</button>
        </div>
        <div class="mbody">
          <pre class="result">{{ resultView.body }}</pre>
        </div>
        <div class="mfoot"><button class="btn" @click="resultView=null">关闭</button></div>
      </div>
    </div>

    <!-- ═══ 可直接交付的完整部署报告弹窗(对标 AI 自动部署页报告版式) ═══ -->
    <div v-if="reportOpen" class="modal-overlay" @click.self="closeReport">
      <div class="modal-box wide report-dialog">
        <div class="report-dialog-head">
          <div class="rdh-left">
            <span class="rdh-icon">{{ reportMode === 'health' ? '🏥' : '📄' }}</span>
            <div>
              <div class="rdh-title">{{ reportMode === 'health' ? 'AI 全面体检报告' : '部署交付报告' }}</div>
              <div class="rdh-sub" v-if="reportItem">{{ reportItem.component_name }} @ {{ reportItem.asset_name }} <span class="rdh-tag">{{ deployLabel(reportItem.deploy_type) }}</span></div>
            </div>
          </div>
          <button class="hero-close" @click="closeReport">×</button>
        </div>

        <div class="report-dialog-body">
          <div v-if="reportLoading" class="report-loading"><span class="spinner"></span> {{ reportMode === 'health' ? 'AI 正在生成全面体检报告...' : 'AI 正在生成部署报告...' }}</div>

          <template v-else-if="reportData">
            <div class="report-full">
              <div class="report-header">
                <h3>{{ reportData.title || '部署报告' }}</h3>
                <span v-if="reportData.status" class="report-status-badge" :class="reportData.status">{{ ut(reportData.status) }}</span>
              </div>
              <div class="report-meta-bar">
                <span>组件: {{ reportItem?.component_name }}</span>
                <span>方式: {{ deployLabel(reportItem?.deploy_type) }}</span>
                <span v-if="reportData.deployed_at">时间: {{ (reportData.deployed_at||'').slice(0,16) }}</span>
                <span v-if="reportData.kpi && reportData.kpi.checked_at">体检时间: {{ reportData.kpi.checked_at }}</span>
              </div>

              <!-- ═══ AI 体检报告(可读版) ═══ -->
              <template v-if="reportData.type === 'ai_health'">
                <div class="report-section-card">
                  <h4>🏥 总体评估</h4>
                  <p class="report-summary-text">{{ reportData.overall_assessment || reportData.executive_summary }}</p>
                  <div class="kpi-grid" v-if="reportData.kpi">
                    <div class="kpi-item" :class="reportData.kpi.overall_status==='healthy' ? 'success' : ''"><span class="kpi-label">总体</span><span class="kpi-value">{{ ut(reportData.kpi.overall_status) }}</span></div>
                    <div class="kpi-item"><span class="kpi-label">健康</span><span class="kpi-value">{{ reportData.kpi.health_passed || 0 }}/{{ reportData.kpi.health_total || 0 }}</span></div>
                    <div class="kpi-item"><span class="kpi-label">配置</span><span class="kpi-value">{{ reportData.kpi.config_passed || 0 }}/{{ reportData.kpi.config_total || 0 }}</span></div>
                    <div class="kpi-item" :class="(reportData.kpi.vuln_critical||reportData.kpi.vuln_high) ? '' : 'success'"><span class="kpi-label">漏洞</span><span class="kpi-value">{{ reportData.kpi.vuln_count || 0 }}</span></div>
                    <div class="kpi-item"><span class="kpi-label">AI问题</span><span class="kpi-value">{{ reportData.kpi.ai_issues || 0 }}</span></div>
                    <div class="kpi-item"><span class="kpi-label">AI建议</span><span class="kpi-value">{{ reportData.kpi.ai_recs || 0 }}</span></div>
                    <div class="kpi-item"><span class="kpi-label">AI模式</span><span class="kpi-value" style="font-size:12px">{{ reportData.kpi.ai_generated ? 'AI' : '规则' }}</span></div>
                  </div>
                </div>

                <div class="report-section-card"><h4>📋 执行摘要</h4><p class="report-summary-text">{{ reportData.executive_summary }}</p></div>

                <div class="report-section-card" v-if="reportData.health_section">
                  <h4>🧭 {{ reportData.health_section.title }}</h4>
                  <span v-if="reportData.health_section.status" class="report-status-badge" :class="reportData.health_section.status">{{ ut(reportData.health_section.status) }}</span>
                  <div v-for="(row, hi) in reportData.health_section.rows" :key="'h'+hi" class="report-line">{{ row }}</div>
                </div>

                <div class="report-section-card" v-if="reportData.config_section">
                  <h4>⚙️ {{ reportData.config_section.title }}</h4>
                  <span v-if="reportData.config_section.status" class="report-status-badge" :class="reportData.config_section.status">{{ ut(reportData.config_section.status) }}</span>
                  <div v-for="(row, ci) in reportData.config_section.rows" :key="'c'+ci" class="report-line">{{ row }}</div>
                </div>

                <div class="report-section-card" v-if="reportData.vuln_section">
                  <h4>🔒 {{ reportData.vuln_section.title }}</h4>
                  <span v-if="reportData.vuln_section.status" class="report-status-badge" :class="reportData.vuln_section.safe ? 'success' : 'error'">{{ reportData.vuln_section.status }}</span>
                  <div v-for="(row, vi) in reportData.vuln_section.rows" :key="'v'+vi" class="report-line">{{ row }}</div>
                </div>

                <div class="report-section-card" v-if="reportData.issues && reportData.issues.length">
                  <h4>🐛 问题清单</h4>
                  <div v-for="(issue, ii) in reportData.issues" :key="'i'+ii" class="issue-item" :class="'severity-' + (issue.severity || 'low')">
                    <span class="issue-severity">[{{ issue.severity }}]</span>
                    <span class="issue-desc">{{ issue.description }}</span>
                    <span class="issue-resolve" v-if="issue.resolution">→ {{ issue.resolution }}</span>
                  </div>
                  <div v-if="!reportData.issues.length" class="report-line">未发现问题</div>
                </div>

                <div class="report-section-card" v-if="reportData.recommendations && reportData.recommendations.length">
                  <h4>💡 改进建议</h4>
                  <ul><li v-for="(r, ri) in reportData.recommendations" :key="'r'+ri">{{ r }}</li></ul>
                </div>

                <div class="report-section-card" v-if="reportData.risk_assessment"><h4>⚠️ 风险评估</h4><p>{{ reportData.risk_assessment }}</p></div>
              </template>

              <!-- ═══ 部署交付报告 ═══ -->
              <template v-else>
              <!-- 执行摘要 -->
              <div class="report-section-card">
                <h4>📋 执行摘要</h4>
                <p class="report-summary-text">{{ reportData.executive_summary }}</p>
                <div class="kpi-grid" v-if="reportData.kpi">
                  <div class="kpi-item"><span class="kpi-label">阶段</span><span class="kpi-value">{{ reportData.kpi.total_steps || 0 }}</span></div>
                  <div class="kpi-item success"><span class="kpi-label">成功</span><span class="kpi-value">{{ reportData.kpi.succeeded_steps || 0 }}</span></div>
                  <div class="kpi-item" v-if="reportData.kpi.failed_steps"><span class="kpi-label">失败</span><span class="kpi-value" style="color:#ef4444">{{ reportData.kpi.failed_steps }}</span></div>
                  <div class="kpi-item" :class="reportData.kpi.preflight_passed ? 'success' : ''"><span class="kpi-label">预检</span><span class="kpi-value">{{ reportData.kpi.preflight_passed ? '✅' : '❌' }}</span></div>
                  <div class="kpi-item" :class="reportData.kpi.verification_passed ? 'success' : ''"><span class="kpi-label">验证</span><span class="kpi-value">{{ reportData.kpi.verification_passed ? '✅' : '❌' }}</span></div>
                  <div class="kpi-item"><span class="kpi-label">AI决策</span><span class="kpi-value">{{ reportData.kpi.ai_decisions || 0 }}</span></div>
                </div>
              </div>

              <div class="report-section-card" v-if="reportData.deployment_architecture"><h4>🏗️ 部署架构</h4><p>{{ reportData.deployment_architecture }}</p></div>
              <div class="report-section-card" v-if="reportData.start_stop_commands && reportData.start_stop_commands.length">
                <h4>🔌 启停服务命令</h4>
                <pre class="command-block">{{ Array.isArray(reportData.start_stop_commands) ? reportData.start_stop_commands.join('\n') : reportData.start_stop_commands }}</pre>
              </div>
              <div class="report-section-card" v-if="reportData.deploy_paths && reportData.deploy_paths.length">
                <h4>📂 部署路径</h4>
                <pre class="command-block">{{ reportData.deploy_paths.join('\n') }}</pre>
              </div>
              <div class="report-section-card" v-if="reportData.service_ports && reportData.service_ports.length">
                <h4>🔌 服务端口</h4>
                <pre class="command-block">{{ reportData.service_ports.join('\n') }}</pre>
              </div>
              <div class="report-section-card" v-if="reportData.access_methods && reportData.access_methods.length">
                <h4>🌐 访问方式</h4>
                <pre class="command-block">{{ reportData.access_methods.join('\n') }}</pre>
              </div>
              <div class="report-section-card" v-if="reportData.login_info && reportData.login_info.length">
                <h4>🔑 登录信息</h4>
                <div v-for="(li, liI) in reportData.login_info" :key="liI" class="login-line"><span class="login-user">{{ li.user }}</span> <span class="login-via">{{ li.via }}</span></div>
              </div>
              <div class="report-section-card" v-if="reportData.environment && Object.keys(reportData.environment).length">
                <h4>🖥️ 环境信息</h4>
                <table class="report-table">
                  <tr v-for="(v, k) in reportData.environment" :key="k"><td class="env-key">{{ k }}</td><td>{{ typeof v === 'string' ? v : JSON.stringify(v) }}</td></tr>
                </table>
              </div>
              <div class="report-section-card" v-if="reportData.timeline"><h4>⏱️ 时间线</h4><p>{{ reportData.timeline }}</p></div>
              <div class="report-section-card" v-if="reportData.verification"><h4>✅ 部署验证</h4><p>{{ reportData.verification }}</p></div>
              <div class="report-section-card" v-if="reportData.risk_assessment"><h4>⚠️ 风险评估</h4><p>{{ reportData.risk_assessment }}</p></div>
              <div class="report-section-card" v-if="reportData.recommendations && reportData.recommendations.length"><h4>💡 改进建议</h4><ul><li v-for="(r, ri) in reportData.recommendations" :key="ri">{{ r }}</li></ul></div>
              <div class="report-section-card" v-if="reportData.issues && reportData.issues.length"><h4>🐛 问题与处理</h4><div v-for="(issue, ii) in reportData.issues" :key="ii" class="issue-item" :class="'severity-' + (issue.severity || 'low')"><span class="issue-severity">[{{ issue.severity }}]</span><span class="issue-desc">{{ issue.description }}</span><span class="issue-resolve" v-if="issue.resolution">→ {{ issue.resolution }}</span><span class="issue-status" :class="issue.status">{{ issue.status }}</span></div></div>
              </template>
              </div>
          </template>

          <div v-else class="report-loading">暂无报告, 点击「生成报告」</div>
        </div>

        <div class="report-dialog-foot">
          <button v-if="reportData && reportData.type === 'ai_health'" class="btn" :disabled="reportLoading" @click="generateHealthReport">🔄 重新体检</button>
          <button v-else class="btn" :disabled="reportLoading" @click="generateReport">🔄 {{ reportData ? '重新生成' : '📝 生成报告' }}</button>
          <button class="btn primary" @click="closeReport">关闭</button>
        </div>
      </div>
    </div>

    <!-- ═══ 添加资产弹窗(从安装记录登记为子资产, 自动填充+补全) ═══ -->
    <div v-if="assetFormOpen" class="modal-overlay" @click.self="closeAssetForm">
      <div class="modal-box asset-dialog">
        <div class="asset-dialog-head">
          <div class="adh-left">
            <span class="adh-icon">➕</span>
            <div>
              <div class="adh-title">添加到资产</div>
              <div class="adh-sub" v-if="assetFormItem">{{ assetFormItem.component_name }} @ {{ assetFormItem.asset_name }} · 端口 {{ assetFormItem.port || '-' }}</div>
            </div>
          </div>
          <button class="hero-close" @click="closeAssetForm">×</button>
        </div>

        <div class="asset-dialog-body">
          <div class="asset-readonly-tip">以下信息已自动填充, 可直接使用</div>

          <div class="asset-form-grid">
            <div class="af-field">
              <label>资产名称 <span class="req">*</span></label>
              <input v-model="assetForm.name" placeholder="组件名称" />
            </div>
            <div class="af-field">
              <label>IP 地址</label>
              <input :value="assetForm.ip" disabled />
            </div>
            <div class="af-field">
              <label>CI 类型</label>
              <input :value="assetForm.ci_type" disabled />
            </div>
            <div class="af-field">
              <label>实例端口</label>
              <input :value="assetForm.port" disabled />
            </div>
            <div class="af-field">
              <label>挂载于(目标机)</label>
              <input :value="assetForm.parent_name" disabled />
            </div>
            <div class="af-field">
              <label>状态</label>
              <input :value="assetForm.status" disabled />
            </div>
          </div>

          <div class="asset-form-sep">可补全信息(选填)</div>

          <div class="asset-form-grid">
            <div class="af-field">
              <label>SSH 用户</label>
              <input v-model="assetForm.ssh_user" placeholder="默认 root" />
            </div>
            <div class="af-field">
              <label>SSH 密码</label>
              <input v-model="assetForm.ssh_password" type="password" placeholder="继承目标机, 可修改" />
            </div>
            <div class="af-field">
              <label>SSH 端口</label>
              <input v-model.number="assetForm.ssh_port" type="number" placeholder="22" />
            </div>
            <div class="af-field">
              <label>描述</label>
              <input v-model="assetForm.description" placeholder="资产备注说明" />
            </div>
            <div class="af-field af-wide">
              <label>标签(逗号分隔)</label>
              <input v-model="assetForm.tags" placeholder="如 component:redis,prod" />
            </div>
          </div>
        </div>

        <div class="asset-dialog-foot">
          <button class="btn" :disabled="assetSaving" @click="closeAssetForm">取消</button>
          <button class="btn primary" :disabled="assetSaving" @click="saveAssetFromInstall">
            {{ assetSaving ? '保存中...' : '✅ 确认添加' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ 查看执行: 部署详情(与「一键部署」弹窗完全一致的布局) ═══ -->
    <div v-if="replayOpen && replayInstall" class="modal-overlay" @click.self="closeReplay">
      <div class="modal-box wide deploy-dialog">
        <div class="deploy-hero">
          <div class="hero-icon">{{ iconOf(replayInstall.component_name) }}</div>
          <div class="hero-info">
            <div class="hero-title">
              {{ replayInstall.component_name }}
              <span class="hero-ver">{{ replayInstall.deploy_type }}<template v-if="replayInstall.name_space || replayInstall.release_name"> · {{ replayInstall.release_name || '' }}{{ replayInstall.name_space ? '/'+replayInstall.name_space : '' }}</template><template v-if="replayInstall.port"> · 端口 {{ replayInstall.port }}</template></span>
            </div>
            <div class="hero-sub">{{ replayInstall.asset_name }}<template v-if="replayInstall.deploy_path"> · {{ replayInstall.deploy_path }}</template></div>
            <div class="hero-tags">
              <span v-if="replayConnecting" class="hero-tag">回放中...</span>
              <span v-if="replayDone && !replayConnecting" class="hero-tag port">已回放</span>
            </div>
          </div>
          <div class="hero-badge">
            <span class="status-badge lg" :class="detailStatusClass(replayInstall.status)">{{ ut(replayInstall.status) }}</span>
          </div>
          <button class="hero-close" @click="closeReplay">×</button>
        </div>

        <div class="deploy-body">
          <!-- 左栏: 配置(只读回填已部署信息) -->
          <div class="deploy-col config-col">
            <div class="cfg-tabs-head">
              <button class="config-tab" :class="{active: cfgTab==='base'}" @click="cfgTab='base'">部署信息</button>
              <button class="config-tab" :class="{active: cfgTab==='plan'}" @click="cfgTab='plan'"><span v-if="deployRecipe" class="plan-ai" style="margin-left:0">部署方案</span></button>
            </div>

            <!-- Tab: 部署信息 -->
            <div v-show="cfgTab==='base'" class="cfg-tab-pane">
              <div class="cfg-field">
                <label>目标机</label>
                <input :value="replayInstall.asset_name" disabled />
              </div>
              <div class="cfg-field">
                <label>部署方式</label>
                <input :value="deployLabel(replayInstall.deploy_type)" disabled />
              </div>
              <div class="cfg-row">
                <div class="cfg-field">
                  <label>部署路径</label>
                  <input :value="replayInstall.deploy_path || '-'" disabled />
                </div>
                <div class="cfg-field">
                  <label>端口</label>
                  <input :value="replayInstall.port || '-'" disabled />
                </div>
              </div>
              <template v-if="replayInstall.deploy_type==='helm'">
                <div class="cfg-row">
                  <div class="cfg-field">
                    <label>命名空间</label>
                    <input :value="replayInstall.name_space || 'default'" disabled />
                  </div>
                  <div class="cfg-field">
                    <label>Release 名</label>
                    <input :value="replayInstall.release_name || '-'" disabled />
                  </div>
                </div>
              </template>
              <div class="cfg-row">
                <div class="cfg-field">
                  <label>组件 ID</label>
                  <input :value="replayInstall.component_id || '-'" disabled />
                </div>
                <div class="cfg-field">
                  <label>创建时间</label>
                  <input :value="(replayInstall.created_at || '').slice(0,16)" disabled />
                </div>
              </div>
              <div class="cfg-field">
                <label>更新时间</label>
                <input :value="(replayInstall.updated_at || '').slice(0,16)" disabled />
              </div>
            </div>

            <!-- Tab: 部署方案 -->
            <div v-show="cfgTab==='plan'" class="cfg-tab-pane">
              <div class="plan-toolbar">
                <button class="btn sm primary" :disabled="generatingPlan" @click="genPlan">
                  {{ generatingPlan ? '生成中...' : (deployPlan.plan ? '🔄 重新生成' : '🤖 AI 生成方案') }}
                </button>
                <span class="hint" v-if="precheckSystem">系统: {{ precheckSystem }}</span>
              </div>
              <div class="plan-meta" v-if="deployPlan.system">
                <span class="plan-system">{{ deployPlan.system }}</span>
                <span v-if="deployPlan.ai_generated" class="plan-ai">AI 生成</span>
              </div>
              <pre class="recipe" v-if="deployPlan.plan">{{ deployPlan.plan }}</pre>
              <pre class="recipe" v-else-if="deployRecipe">{{ deployRecipe }}</pre>
              <div v-else class="plan-empty">点上方「AI 生成方案」按系统类型生成可执行部署方案</div>
            </div>
          </div>

          <!-- 右栏: 部署执行(与一键部署一致) -->
          <div class="deploy-col exec-col">
            <div class="panel-title">
              部署执行
              <span v-if="replayConnecting" class="exec-live"><i class="dot"></i>回放中</span>
            </div>

            <!-- AI 决策门控卡片(续对话) -->
            <div v-if="decisionPending" class="decision-card">
              <div class="decision-head"><span class="decision-icon">🤖</span> AI 需你决策(续)</div>
              <div class="decision-q">{{ decisionPending.question }}</div>
              <div class="decision-opts">
                <button v-for="(o,i) in decisionPending.options" :key="i" class="decision-opt" @click="submitReplayDecision(o.title)">
                  <span class="decision-opt-key">{{ ['A','B','C'][i]||(i+1) }}</span>
                  <span class="decision-opt-title">{{ o.title }}</span>
                  <span class="decision-opt-detail">{{ o.detail }}</span>
                </button>
              </div>
              <div class="decision-free" v-if="decisionPending.free">
                <input v-model="decisionPending.custom" placeholder="或输入自定义命令/方案..." @keyup.enter="submitReplayDecision()" />
                <button class="btn primary sm" @click="submitReplayDecision()">执行</button>
              </div>
            </div>

            <!-- 阶段条 -->
            <div class="phase-bar" v-if="currentStep >= 0">
              <div v-for="(s,i) in phases" :key="i" class="phase" :class="i===currentStep?'cur':(i<currentStep?'done':'')">{{ s }}</div>
            </div>

            <!-- 执行区 Tab -->
            <div class="exec-tabs">
              <div class="exec-tabs-head">
                <button class="exec-tab" :class="{active: execTab==='check'}" @click="execTab='check'">🩺 预检</button>
                <button class="exec-tab" :class="{active: execTab==='log'}" @click="execTab='log'">🖥 日志</button>
                <button class="exec-tab" :class="{active: execTab==='ai'}" @click="execTab='ai'">🤖 AI 建议<span v-if="aiTips.length" class="tab-badge">{{ aiTips.length }}</span></button>
              </div>
            </div>

            <!-- Tab: 终端日志 -->
            <div v-show="execTab==='log'" class="terminal">
              <div class="term-head"><span>实时部署日志</span><span class="term-info" v-if="replayConnecting">● 回放中</span></div>
              <div class="term-body term-body-lg" ref="termBodyRef">
                <div v-if="!logs.length" class="term-empty">等待部署日志...</div>
                <div v-for="(l,i) in logs" :key="i" class="tline" :class="l.type"><span class="tts">{{ l.ts }}</span><span class="tmsg">{{ l.message }}</span></div>
              </div>
            </div>

            <!-- Tab: AI 建议 -->
            <div v-show="execTab==='ai'" class="ai-panel ai-panel-lg">
              <div v-if="!aiTips.length" class="ai-empty">无 AI 建议</div>
              <div v-for="(t,i) in aiTips" :key="i" class="ai-tip" :class="{diagnostic:t.stage==='diagnosis'}">
                <div class="ai-stage" v-if="t.stage!=='diagnosis'">{{ stageLabel(t.stage) }}</div>
                <template v-if="t.stage==='diagnosis'">
                  <div class="diag-head"><span class="diag-icon">⚠︎</span> AI 失败诊断</div>
                  <div class="diag-cause" v-if="t.root_cause">{{ t.root_cause }}</div>
                  <div class="ai-advice" v-if="t.advice">{{ t.advice }}</div>
                  <div class="diag-steps" v-if="t.steps && t.steps.length"><div v-for="(s,si) in t.steps" :key="si" class="diag-step"><span class="diag-n">{{ si+1 }}</span>{{ s }}</div></div>
                  <div class="ai-risk" v-if="t.risk" :class="'risk-'+t.risk">风险: {{ t.risk }}</div>
                </template>
                <template v-else>
                  <div class="ai-summary">{{ t.summary }}</div><div class="ai-advice" v-if="t.advice">{{ t.advice }}</div>
                </template>
              </div>
            </div>

            <!-- Tab: 预检 / 报告 -->
            <div v-show="execTab==='check'" class="check-tab">
              <div class="precheck-panel" v-if="precheckChecks.length">
                <div class="precheck-title">预检明细 <span :class="precheckOk?'ok':'fail'">{{ precheckOk?'通过':'存在问题' }}</span></div>
                <div v-for="(c,i) in precheckChecks" :key="i" class="precheck-item">
                  <span class="precheck-mark" :class="c.ok?'ok':'fail'">{{ c.ok?'✓':'✗' }}</span>
                  <span class="precheck-name">{{ c.name }}</span><span class="precheck-msg" :class="c.ok?'ok':'fail'">{{ c.message }}</span>
                </div>
              </div>
              <div v-if="deployReport">
                <div v-if="deployReport.deliverable" class="report-box deliv">
                  <div class="report-title">AI 部署报告<span class="report-overall" :class="'ov-'+deployReport.overview">{{ deployReport.overview }}</span></div>
                  <div class="report-conclusion">{{ deployReport.conclusion }}</div>
                  <template v-if="deployReport.root_cause"><div class="report-field"><span class="rf-label">根因</span>{{ deployReport.root_cause }}</div></template>
                  <template v-if="deployReport.executed"><div class="report-field"><span class="rf-label">已执行</span>{{ deployReport.executed }}</div></template>
                  <template v-if="deployReport.impact"><div class="report-field"><span class="rf-label">影响</span>{{ deployReport.impact }}</div></template>
                  <template v-if="deployReport.next_steps && deployReport.next_steps.length">
                    <div class="report-field"><span class="rf-label">下一步</span><div v-for="(ns,ni) in deployReport.next_steps" :key="ni" class="rf-item">· {{ ns }}</div></div>
                  </template>
                  <template v-if="deployReport.risks && deployReport.risks.length">
                    <div class="report-field"><span class="rf-label">风险</span><div v-for="(rk,ri) in deployReport.risks" :key="ri" class="rf-item risk-item">· {{ rk }}</div></div>
                  </template>
                </div>
                <div v-else class="report-box">
                  <div class="report-title">四合一体检<span class="report-overall" :class="'ov-'+deployReport.overall_status">{{ deployReport.overall_status }}</span></div>
                  <div class="report-summary" v-if="deployReport.summary">{{ deployReport.summary }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-foot">
          <button class="btn primary" @click="closeReplay">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const API = '/component-market/api'
const ASSET_API = '/assets/api'

const tab = ref('catalog')
const comps = ref([])
const stats = ref({ total_components:0, total_installs:0, running_installs:0, by_category:{} })
const installs = ref([])
const statusFilter = ref('')
const assets = ref([])
const filterCat = ref('')
const keyword = ref('')
const loading = ref(false)
const deployComp = ref(null)
const deployForm = ref({ asset_id:0, deploy_type:'', namespace:'default', release:'', deploy_path:'', http_proxy:'', https_proxy:'', no_proxy:'127.0.0.1,localhost,.local', use_offline:false })
const deployParams = ref({})
const proxyList = ref([])
async function refreshProxyList() {
  try { const r = await axios.get(`${API}/proxies`); proxyList.value = r.data.items || [] } catch (e) { /* ignore */ }
}
function applyProxy(id) {
  const px = proxyList.value.find(p => p.id === Number(id))
  if (!px) return
  deployForm.value.http_proxy = px.http_proxy || ''
  deployForm.value.https_proxy = px.https_proxy || ''
  deployForm.value.no_proxy = px.no_proxy || '127.0.0.1,localhost,.local'
  renderRecipe()
}
const deployRecipe = ref('')
const resultView = ref(null)
const installDetail = ref(null)
const replayOpen = ref(false)
const replayInstall = ref(null)
const replayDone = ref(false)
const replayConnecting = ref(false)
let replayWs = null
// ── 部署实时视图状态 ──
const deploying = ref(false)
const logs = ref([])
const aiTips = ref([])
const currentStep = ref(0)
const currentInstallId = ref(null)
const decisionPending = ref(null)  // {id, install_id, question, options, free, custom}
const execTab = ref('log')
const cfgTab = ref('base')
const resultText = ref('')
const resultOk = ref(false)
const precheckChecks = ref([])
const precheckOk = ref(true)
const precheckIssues = ref([])
const prechecking = ref(false)
const deployReport = ref(null)
const deployPlan = ref({ ai_generated: false, system: '', title: '', plan: '' })
const precheckSystem = ref('')
const generatingPlan = ref(false)
const reportOpen = ref(false)
const reportItem = ref(null)
const reportData = ref(null)
const reportMode = ref('deploy')
const reportLoading = ref(false)
const assetFormOpen = ref(false)
const assetFormItem = ref(null)
const assetForm = ref({ name:'', ip:'', ci_type:'', port:0, parent_id:0, parent_name:'', status:'online', ssh_user:'root', ssh_password:'', ssh_port:22, description:'', tags:'' })
const assetSaving = ref(false)
let deployWs = null
const phases = ['预检环境','代理/网络','生成配方','执行部署','部署验证']
const stageNames = { preflight:'预检', proxy:'代理', deploy:'部署', verify:'验证', done:'完成', fail:'失败', helm:'Helm', stop:'已停止' }
function stageLabel(s) { return stageNames[s] || s || '' }
const termBodyRef = ref(null)
const currentAssetName = computed(() => {
  const a = assets.value.find(x => x.id === deployForm.value.asset_id)
  return a ? (a.name + (a.ip ? `(${a.ip})` : '')) : ''
})
const currentAssetNameShort = computed(() => {
  const a = assets.value.find(x => x.id === deployForm.value.asset_id)
  return a ? a.name : ''
})
const deployStatusText = computed(() => {
  if (deploying.value) return '部署中'
  if (deployReport.value) return '已体检'
  if (resultText.value) return resultOk.value ? '成功' : '失败'
  return '待部署'
})
const deployStatusClass = computed(() => {
  if (deploying.value) return 'running'
  if (resultText.value) return resultOk.value ? 'succeeded' : 'failed'
  return 'draft'
})

const deployLabels = { native:'🐧 传统', docker:'🐳 Docker', helm:'☸️ K8S/Helm', ha:'🛡️ 高可用' }
function deployLabel(d) { return deployLabels[d] || d }
const iconBy = { mysql:'🐬', redis:'🔴', kafka:'📨', rabbitmq:'🐇', nginx:'🌐', elasticsearch:'🔎', mongodb:'🍃', postgresql:'🐘' }
function iconOf(n) { return iconBy[n] || '📦' }
const statusText = { deploying:'部署中', running:'运行中', failed:'失败', stopped:'已停止', healthy:'健康', degraded:'亚健康', unhealthy:'不健康', pending:'待评估', pass:'通过', safe:'安全', drift:'有漂移', error:'检查失败' }
function ut(s) { return statusText[s] || s }
function detailStatusClass(s) {
  if (s === 'running') return 'succeeded'
  if (s === 'failed') return 'failed'
  if (s === 'deploying') return 'running'
  return 'draft'
}

async function loadStats() { try { const {data}=await axios.get(`${API}/stats`); stats.value=data } catch(e){} }
async function loadCatalog() {
  loading.value=true
  try {
    const {data}=await axios.get(`${API}/catalog`, { params:{ category:filterCat.value, keyword:keyword.value } })
    comps.value=data.items||[]
  } finally { loading.value=false }
}
const filteredInstalls = computed(() =>
  statusFilter.value
    ? (installs.value || []).filter(i => i.status === statusFilter.value)
    : (installs.value || [])
)
function setStatus(s) {
  statusFilter.value = s
  loadInstalls()
}
async function loadInstalls() {
  try { const {data}=await axios.get(`${API}/installs`); installs.value=data.items||[] } catch(e){}
}
async function viewInstall(it) {
  try {
    const { data } = await axios.get(`${API}/installs/${it.id}`)
    if (!data.ok) { ElMessage.error(data.error || '获取详情失败'); return }
    installDetail.value = data.item
    // 打开部署详情(与「一键部署」同布局): 用详情数据填充部署信息 & 连 resume ws 回放历史/续 AI 对话
    const item = data.item
    replayInstall.value = item
    currentInstallId.value = item.id
    cfgTab.value = 'base'
    execTab.value = 'log'
    // 构造组件/表单, 使「部署方案」tab 的 AI 生成方案功能可复用
    const comp = comps.value.find(c => c.id === item.component_id) ||
      { id: item.component_id, name: item.component_name, display_name: item.component_name,
        description: '', deploy_types: [item.deploy_type], default_port: item.port }
    deployComp.value = comp
    deployForm.value = {
      asset_id: item.asset_id || 0, deploy_type: item.deploy_type || comp.deploy_types[0],
      namespace: item.name_space || 'default', release: item.release_name || '',
      deploy_path: item.deploy_path || '', http_proxy: '', https_proxy: '', no_proxy: '',
    }
    deployRecipe.value = ''
    deployPlan.value = { ai_generated: false, system: '', title: '', plan: '' }
    generatingPlan.value = false
    // 渲染部署方案配方(供「部署方案」tab 展示)
    replayRecipe(item)
    replayOpen.value = true
    startReplay(item)
  } catch(e) { ElMessage.error('查看失败: ' + e.message) }
}
async function replayRecipe(inst) {
  deployRecipe.value = ''
  try {
    const { data } = await axios.get(`${API}/render`, { params:{
      component_id: inst.component_id, deploy_type: inst.deploy_type,
      host: '', namespace: inst.name_space || 'default', release: inst.release_name || '' } })
    deployRecipe.value = data.content || data.error || ''
  } catch(e){ deployRecipe.value = '' }
}
function replayWsUrl(iid) {
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://'
  return `${proto}${location.host}/component-market/ws/deploy?resume=1&install_id=${iid}`
}
function startReplay(inst) {
  if (replayWs) { try { replayWs.close() } catch(e){} replayWs = null }
  // 重置回放工作台状态(复用执行视图状态)
  logs.value = []; aiTips.value = []; currentStep.value = -1
  decisionPending.value = null; precheckChecks.value = []; precheckOk.value = true
  deployReport.value = null; replayDone.value = false
  replayConnecting.value = true
  replayWs = new WebSocket(replayWsUrl(inst.id))
  replayWs.onopen = () => { replayConnecting.value = false }
  replayWs.onmessage = (ev) => {
    let e; try { e = JSON.parse(ev.data) } catch(err) { return }
    if (e && e.install_id) currentInstallId.value = e.install_id
    if (e.type === 'phase') { currentStep.value = e.step; pushLog('phase', `▶ ${e.title || ('阶段'+e.step)}`) }
    else if (e.type === 'log' || e.type === 'output') pushLog(e.type, e.message !== undefined ? e.message : (e.line||''))
    else if (e.type === 'ai') aiTips.value.push({ stage: e.stage||'done', summary:e.summary||'', advice:e.advice||'', risk:e.risk||'', root_cause:e.root_cause||'', steps:e.steps||[] })
    else if (e.type === 'precheck') { precheckChecks.value.push({ name:e.name||'', ok:!!e.ok, message:e.message||'' }); if (!e.ok) precheckOk.value = false }
    else if (e.type === 'decide') decisionPending.value = { id:e.id, install_id:e.install_id, question:e.question||'', options:e.options||[], free:!!e.free, custom:'' }
    else if (e.type === 'report') { deployReport.value = e.conclusion ? { deliverable:true, overview:e.overview||'', conclusion:e.conclusion||'', root_cause:e.root_cause||'', executed:e.executed||'', impact:e.impact||'', next_steps:e.next_steps||[], risks:e.risks||[], raw:e } : { deliverable:false, overall_status:e.overall_status||'', summary:e.summary||'', report:e.report||{} } }
    else if (e.type === 'complete') { replayDone.value = true; pushLog('ok', e.status==='succeeded' ? '✓ 部署成功' : `结束:${e.status||''}`) }
    else if (e.type === 'resume_done') { replayDone.value = true; pushLog('ok', '已加载执行记录(无待决策)') }
  }
  replayWs.onerror = () => { replayConnecting.value = false; replayDone.value = true }
  replayWs.onclose = () => { replayConnecting.value = false; replayWs = null }
}
function submitReplayDecision(choice) {
  const d = decisionPending.value
  if (!d || !replayWs) return
  const payload = choice || (d.custom || '')
  if (!payload) { ElMessage.warning('请选择或输入'); return }
  try { replayWs.send(JSON.stringify({ type:'decision', install_id:d.install_id, id:d.id, choice:payload })) } catch(e){}
  decisionPending.value = null
}
function closeReplay() { replayOpen.value = false; if (replayWs) { try{replayWs.close()}catch(e){} replayWs=null } }
async function loadAssets() {
  try {
    const {data}=await axios.get(`${ASSET_API}/list`, { params:{ page_size:500 } })
    const all=(data.items||data.assets||data.list||[])
    // 目标机只保留可 SSH 部署的资产(排除 k8s 集群/database/http 等, 及 k8s 命名空间/服务杂项)
    assets.value = all.filter(a =>
      (a.connection_type || 'ssh').toLowerCase() === 'ssh' &&
      a.id && a.ip && !/\//.test(a.name || '')
    )
  } catch(e){}
}
async function loadAll() { loadStats(); loadCatalog(); loadAssets() }

function openDeploy(c) {
  deployComp.value=c
  deployForm.value={ asset_id:0, deploy_type:(c.deploy_types||[])[0]||'docker', namespace:'default', release:'', deploy_path:'', http_proxy:'', https_proxy:'', no_proxy:'127.0.0.1,localhost,.local', use_offline:false }
  initDeployParams()
  deployRecipe.value=''
  deploying.value=false
  logs.value=[]
  aiTips.value=[]
  currentStep.value=0
  currentInstallId.value=null
  resultText.value=''
  precheckChecks.value=[]
  precheckOk.value=true
  precheckIssues.value=[]
  prechecking.value=false
  deployReport.value=null
  deployPlan.value={ ai_generated:false, system:'', title:'', plan:'' }
  precheckSystem.value=''
  generatingPlan.value=false
  execTab.value='log'
  if (deployWs) { try { deployWs.close() } catch(e){} deployWs = null }
  renderRecipe()
}
async function selectDeployType(d) {
  deployForm.value.deploy_type=d
  await renderRecipe()
}
function initDeployParams() {
  const p = {}
  ;(deployComp.value?.param_schema || []).forEach(item => {
    p[item.key] = item.default !== undefined && item.default !== null ? item.default : (item.type === 'bool' ? false : '')
  })
  deployParams.value = p
}
async function renderRecipe() {
  const c=deployComp.value; const a=assets.value.find(x=>x.id===deployForm.value.asset_id)
  const collectParams = {}
  ;(c.param_schema || []).forEach(item => { collectParams[item.key] = deployParams.value[item.key] })
  try {
    const {data}=await axios.get(`${API}/render`, { params:{
      component_id:c.id, deploy_type:deployForm.value.deploy_type,
      host:a?`${a.ip}`:'', namespace:deployForm.value.namespace, release:deployForm.value.release,
      use_offline: deployForm.value.use_offline ? 'true' : '',
      params: JSON.stringify(collectParams),
    } })
    deployRecipe.value=data.content || data.error || ''
  } catch(e){ deployRecipe.value='渲染失败' }
}
async function doDeploy() {
  try {
    const {data}=await axios.post(`${API}/deploy`, {
      component_id:deployComp.value.id, asset_id:deployForm.value.asset_id,
      deploy_type:deployForm.value.deploy_type, namespace:deployForm.value.namespace,
      release:deployForm.value.release, deploy_path:deployForm.value.deploy_path,
      http_proxy:deployForm.value.http_proxy, https_proxy:deployForm.value.https_proxy,
      no_proxy:deployForm.value.no_proxy,
    })
    if(data.ok){
      ElMessage.success(data.component && data.deploy_log && String(data.deploy_log).includes('Up')
        ? `${data.component} 部署成功` : `已创建 ${data.component} ${data.deploy_type} 部署记录`)
      deployComp.value=null
      tab.value='installs'; loadInstalls()
      if(data.deploy_log) resultView.value={ title:`🚀 部署结果 · ${data.component}`, body: data.deploy_log }
    } else ElMessage.error(data.error||'部署失败')
  } catch(e){ ElMessage.error('部署失败') }
}

// ── 实时部署(WebSocket + AI 辅助) ──
function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://'
  const collectParams = {}
  ;(deployComp.value.param_schema || []).forEach(item => { collectParams[item.key] = deployParams.value[item.key] })
  const q = new URLSearchParams({
    component_id: deployComp.value.id,
    asset_id: deployForm.value.asset_id,
    deploy_type: deployForm.value.deploy_type,
    namespace: deployForm.value.namespace,
    release: deployForm.value.release,
    deploy_path: deployForm.value.deploy_path || '',
    http_proxy: deployForm.value.http_proxy || '',
    https_proxy: deployForm.value.https_proxy || '',
    no_proxy: deployForm.value.no_proxy || '',
  })
  if (deployForm.value.use_offline) q.set('use_offline', 'true')
  if (Object.keys(collectParams).length) q.set('params', JSON.stringify(collectParams))
  return `${proto}${location.host}/component-market/ws/deploy?${q.toString()}`
}
function phaseState(i) {
  if (i < currentStep.value) return 'done'
  if (i === currentStep.value && deploying.value) return 'cur'
  return ''
}
function pushLog(type, message) {
  logs.value.push({ type, message, ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }) })
  const el = termBodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}
async function runPrecheck() {
  if (!deployForm.value.asset_id) { ElMessage.warning('请先选择目标机'); return }
  prechecking.value = true
  precheckChecks.value = []
  precheckOk.value = true
  precheckIssues.value = []
  try {
    const { data } = await axios.post(`${API}/precheck`, {
      component_id: deployComp.value.id,
      asset_id: deployForm.value.asset_id,
      deploy_type: deployForm.value.deploy_type,
      deploy_path: deployForm.value.deploy_path || '',
      http_proxy: deployForm.value.http_proxy,
      https_proxy: deployForm.value.https_proxy,
      no_proxy: deployForm.value.no_proxy,
    })
    precheckChecks.value = data.checks || []
    precheckOk.value = !!data.ok
    precheckIssues.value = data.issues || []
    precheckSystem.value = data.system || ''
    if (data.ok) ElMessage.success(`预检通过 (${(data.checks || []).length} 项)`)
    else ElMessage.warning('预检存在问题: ' + ((data.issues || []).join('; ') || '请查看明细'))
  } catch (e) {
    ElMessage.error('预检失败: ' + e.message)
  } finally {
    prechecking.value = false
  }
}
async function genPlan() {
  if (!deployForm.value.asset_id) { ElMessage.warning('请先选择目标机'); return }
  generatingPlan.value = true
  try {
    const { data } = await axios.post(`${API}/plan`, {
      component_id: deployComp.value.id,
      asset_id: deployForm.value.asset_id,
      deploy_type: deployForm.value.deploy_type,
      deploy_path: deployForm.value.deploy_path || '',
    })
    if (!data.ok) { ElMessage.error(data.error || '生成方案失败'); return }
    deployPlan.value = { ai_generated: !!data.ai_generated, system: data.system || '', title: data.title || '', plan: data.plan || '' }
    if (data.system) precheckSystem.value = data.system
    ElMessage.success('部署方案已生成')
  } catch (e) {
    ElMessage.error('生成方案失败: ' + e.message)
  } finally {
    generatingPlan.value = false
  }
}
function openReport(it) {
  reportItem.value = it
  reportMode.value = 'deploy'
  reportOpen.value = true
  // 已落库的直接展示, 不重复调 AI; 否则首次生成并自动保存
  if (it.report_json) {
    try { reportData.value = JSON.parse(it.report_json) } catch(e) { reportData.value = null }
  }
  if (!reportData.value) generateReport()
}
async function generateReport() {
  if (!reportItem.value) return
  reportLoading.value = true
  try {
    const { data } = await axios.post(`${API}/installs/${reportItem.value.id}/report`)
    if (!data.ok) { ElMessage.error(data.error || '生成报告失败'); return }
    reportData.value = data.report
    reportItem.value.report_json = JSON.stringify(data.report)
  } catch (e) {
    ElMessage.error('生成报告失败: ' + e.message)
  } finally {
    reportLoading.value = false
  }
}
function closeReport() {
  reportOpen.value = false
  reportItem.value = null
  reportData.value = null
  reportMode.value = 'deploy'
}
// ── AI 体检(可读报告, 对标部署报告版式) ──
function runHealthCheck(it) {
  reportItem.value = it
  reportData.value = null
  reportMode.value = 'health'
  reportOpen.value = true
  generateHealthReport()
}
async function generateHealthReport() {
  if (!reportItem.value) return
  reportLoading.value = true
  try {
    const { data } = await axios.post(`${API}/installs/${reportItem.value.id}/health-report`)
    if (!data.ok) { ElMessage.error(data.error || 'AI 体检失败'); return }
    reportData.value = data.report
    loadInstalls()
  } catch (e) {
    ElMessage.error('AI 体检失败: ' + e.message)
  } finally {
    reportLoading.value = false
  }
}
function openReportRaw() {
  if (!deployReport.value) return
  const src = deployReport.value.raw || deployReport.value.report || deployReport.value
  resultView.value = {
    title: deployReport.value.deliverable ? `AI 部署报告 · ${deployReport.value.overview}` : `四合一体检报告 · overall=${deployReport.value.overall_status}`,
    body: JSON.stringify(src, null, 2),
  }
}
// ── 添加到资产: 从安装记录登记为子资产(自动填充 + 补全) ──
const DB_CATS = ['mysql','redis','mongodb','postgresql','elasticsearch','mariadb','tidb','clickhouse','influxdb','cassandra','neo4j','hbase','tdengine','dameng','kingbase','opengauss','oceanbase','doris','starrocks','memcached','valkey']
function openAddAsset(it) {
  assetFormItem.value = it
  const parent = assets.value.find(a => a.id === it.asset_id) || {}
  const ci_type = DB_CATS.includes(it.component_name) ? 'database' : 'middleware'
  const pc = parent.connection_config
  let ssh = { ssh_user:'root', ssh_password:'', ssh_port:22 }
  if (pc) { try { const o = typeof pc==='string' ? JSON.parse(pc) : pc; ssh = { ssh_user: o.ssh_user || 'root', ssh_password: o.ssh_password || '', ssh_port: o.ssh_port || 22 } } catch(e){} }
  assetForm.value = {
    name: it.component_name,
    ip: parent.ip || it.asset_name || '',
    ci_type,
    port: it.port || 0,
    parent_id: it.asset_id,
    parent_name: it.asset_name || '',
    status: 'online',
    ssh_user: ssh.ssh_user,
    ssh_password: ssh.ssh_password,
    ssh_port: ssh.ssh_port,
    description: `由组件商店「${it.component_name}」部署实例登记(${it.deploy_type} 方式, 端口 ${it.port || '-'})`,
    tags: `component:${it.component_name}`,
  }
  assetFormOpen.value = true
}
function closeAssetForm() {
  assetFormOpen.value = false
  assetFormItem.value = null
}
async function saveAssetFromInstall() {
  if (!assetForm.value.name.trim()) { ElMessage.warning('资产名称不能为空'); return }
  const it = assetFormItem.value
  const parent = assets.value.find(a => a.id === it.asset_id) || {}
  const cname = `aiops-${it.component_name}`
  const payload = {
    name: assetForm.value.name.trim(),
    ci_type: assetForm.value.ci_type,
    ip: assetForm.value.ip,
    status: assetForm.value.status,
    tags: assetForm.value.tags || '',
    connection_type: 'ssh',
    ssh_user: assetForm.value.ssh_user || 'root',
    ssh_password: assetForm.value.ssh_password || '',
    ssh_port: assetForm.value.ssh_port || 22,
    parent_id: assetForm.value.parent_id,
    connection_config: {
      ssh_user: assetForm.value.ssh_user || 'root',
      ssh_password: assetForm.value.ssh_password || '',
      ssh_port: assetForm.value.ssh_port || 22,
      container_name: cname,
      component: it.component_name,
      deploy_type: it.deploy_type,
      app_port: it.port,
    },
    ci_attributes: {
      source: 'component-store',
      component: it.component_name,
      install_id: it.id,
      deploy_type: it.deploy_type,
      container: cname,
    },
  }
  if (assetForm.value.description) payload.description = assetForm.value.description
  assetSaving.value = true
  try {
    await axios.post(`${ASSET_API}/create`, payload)
    ElMessage.success(`已添加资产: ${assetForm.value.name}`)
    closeAssetForm()
    loadAssets()
  } catch (e) {
    ElMessage.error('添加资产失败: ' + (e.response?.data?.message || e.message))
  } finally {
    assetSaving.value = false
  }
}
function startDeploy() {
  deploying.value = true
  logs.value = []
  aiTips.value = []
  currentStep.value = 0
  resultText.value = ''
  resultOk.value = false
  precheckChecks.value = []
  precheckOk.value = true
  precheckIssues.value = []
  deployReport.value = null
  decisionPending.value = null
  if (deployWs) { try { deployWs.close() } catch(e){} deployWs = null }
  deployWs = new WebSocket(wsUrl())
  deployWs.onopen = () => {}  // 参数已在 query string 中传递
  deployWs.onmessage = (ev) => {
    let e
    try { e = JSON.parse(ev.data) } catch(err) { return }
    if (e && e.install_id) currentInstallId.value = e.install_id
    if (e.type === 'decide') {
      decisionPending.value = { id: e.id, install_id: e.install_id, question: e.question || '', options: e.options || [], free: !!e.free, custom: '' }
      pushLog('ai', `🤖 等待你的决策: ${(e.question || '')}`)
    } else if (e.type === 'plan') {
      deployPlan.value = { ai_generated: !!e.ai_generated, system: e.system || '', title: e.title || '', plan: e.plan || '' }
    } else if (e.type === 'phase') {
      currentStep.value = e.step
      pushLog('phase', `▶ ${e.title || ('阶段 ' + e.step)}`)
    } else if (e.type === 'log' || e.type === 'output') {
      pushLog(e.type, e.message !== undefined && e.message !== null ? e.message : (e.line || ''))
    } else if (e.type === 'ai') {
      aiTips.value.push({ stage: e.stage || 'done', summary: e.summary || '', advice: e.advice || '', risk: e.risk || '', root_cause: e.root_cause || '', steps: e.steps || [] })
    } else if (e.type === 'precheck') {
      precheckChecks.value.push({ name: e.name || '', ok: !!e.ok, message: e.message || '' })
      if (!e.ok) precheckOk.value = false
    } else if (e.type === 'report') {
      // final_report(交付版, 含 conclusion) 或 四合一体检(report 数据)
      if (e.conclusion) {
        deployReport.value = {
          deliverable: true, overview: e.overview || 'unknown',
          conclusion: e.conclusion || '', root_cause: e.root_cause || '',
          executed: e.executed || '', impact: e.impact || '',
          next_steps: e.next_steps || [], risks: e.risks || [],
          raw: e,
        }
        pushLog('ok', `📋 AI 部署报告已生成`)
      } else {
        deployReport.value = { deliverable: false, overall_status: e.overall_status || 'unknown', summary: e.summary || '', report: e.report || {} }
        pushLog('ok', `📋 四合一体检完成: overall=${e.overall_status || 'unknown'}`)
      }
      loadInstalls()
    } else if (e.type === 'status') {
      pushLog('phase', e.message || e.status)
    } else if (e.type === 'error') {
      pushLog('error', '✗ ' + (e.message || '部署错误'))
    } else if (e.type === 'complete') {
      deploying.value = false
      const ok = e.status === 'succeeded'
      resultOk.value = ok
      resultText.value = e.message || (ok ? '部署成功' : '部署失败')
      if (ok) ElMessage.success(e.message || '部署成功')
      else if (e.status === 'failed') ElMessage.error(e.message || '部署失败')
      pushLog(ok ? 'ok' : 'error', ok ? '✓ 部署完成' : '✗ 部署失败')
      if (deployWs) { try { deployWs.close() } catch(err){} deployWs = null }
      loadInstalls()
      nextTick(() => { if (termBodyRef.value) termBodyRef.value.scrollTop = termBodyRef.value.scrollHeight })
    }
  }
  deployWs.onerror = () => {
    deploying.value = false
    resultOk.value = false
    resultText.value = 'WebSocket 连接失败'
    ElMessage.error('WebSocket 连接失败')
  }
  deployWs.onclose = () => {
    if (deploying.value) {
      deploying.value = false
      if (!resultText.value) { resultText.value = '连接已断开'; resultOk.value = false }
    }
    deployWs = null
  }
}
function stopDeploy() {
  if (currentInstallId.value) {
    try { axios.post(`${API}/deploys/${currentInstallId.value}/stop`) } catch(e){}  }
  if (deployWs) {
    try { deployWs.send(JSON.stringify({ type: 'stop', install_id: currentInstallId.value })) } catch(e){}
  }
  if (deployWs) { try { deployWs.close() } catch(e){} deployWs = null }
  deploying.value = false
  decisionPending.value = null
  resultText.value = '已发送停止指令'
  resultOk.value = false
}
function closeDeploy() {
  if (deploying.value) stopDeploy()
  if (deployWs) { try { deployWs.close() } catch(e){} deployWs = null }
  deployComp.value = null
}
function pickDecision(optTitle) {
  submitDecision(optTitle)
}
function submitDecision(choice) {
  const d = decisionPending.value
  if (!d || !deployWs) return
  const payload = choice || (d.custom || '')
  if (!payload) { ElMessage.warning('请选择方案或输入命令'); return }
  try {
    deployWs.send(JSON.stringify({ type: 'decision', install_id: d.install_id, id: d.id, choice: payload }))
  } catch(e) { ElMessage.error('回传决策失败') }
  decisionPending.value = null
}
async function runBatchFullCheck() {
  if(!confirm('对所有运行中的组件实例执行批量全面体检？')) return
  try {
    const {data}=await axios.post(`${API}/batch-full-check`)
    if(!data.ok){ ElMessage.error(data.error||'批量体检失败'); return }
    const r=data.result
    const lines = []
    lines.push(`共体检 ${r.total} 个实例 | 健康 ${r.healthy} | 亚健康 ${r.degraded} | 不健康 ${r.unhealthy}`)
    lines.push('')
    ;(r.results||[]).forEach(it=>{
      const st={healthy:'✅ 健康',degraded:'⚠️ 亚健康',unhealthy:'❌ 不健康'}[it.overall_status]||it.overall_status||'?'
      lines.push(`${st}  ${it.component} (ID:${it.install_id})`)
      if(it.health_status) lines.push(`   · 健康: ${it.health_status}`)
      if(it.config_check_status) lines.push(`   · 配置: ${it.config_check_status}`)
      if(it.vuln_safe!==undefined) lines.push(`   · 漏洞: ${it.vuln_safe?'安全':'有风险'}`)
      if(it.error) lines.push(`   · 错误: ${it.error}`)
    })
    resultView.value={ title:`🔍 批量体检摘要 (共 ${r.total} 实例)`, body: lines.join('\n') }
    loadInstalls()
  } catch(e){ ElMessage.error('批量体检失败') }
}
async function runFullCheck(it) {
  try {
    const {data}=await axios.post(`${API}/installs/${it.id}/full-check`)
    if(!data.ok){ ElMessage.error(data.error||'体检失败'); return }
    resultView.value={ title:`🔍 全面体检报告 · ${it.component_name}`, body: JSON.stringify(data.result,null,2) }
    loadInstalls()
  } catch(e){ ElMessage.error('体检失败') }
}
async function runCheck(it, kind) {
  try {
    const {data}=await axios.post(`${API}/installs/${it.id}/${kind}`)
    if(!data.ok){ ElMessage.error(data.error||'检查失败'); return }
    const r=data.result
    resultView.value={ title: resultTitle(kind, it.component_name), body: JSON.stringify(r,null,2) }
    loadInstalls()
  } catch(e){ ElMessage.error('检查失败') }
}
function resultTitle(kind, name){
  return { health:`🧭 高可用检查 · ${name}`, config:`⚙️ 配置优化 · ${name}`, vuln:`⚠️ 漏洞检查 · ${name}`, analyze:`🤖 AI 健康分析 · ${name}` }[kind]||'检查结果'
}
async function delInstall(it){
  if(!confirm(`删除安装记录 ${it.component_name}@${it.asset_name}?`)) return
  try{ await axios.delete(`${API}/installs/${it.id}`); loadInstalls() }catch(e){}
}
async function toAsset(it){
  try {
    const {data}=await axios.post(`${API}/installs/${it.id}/to-asset`)
    if(data.ok){
      if(data.already) ElMessage.warning(`资产「${it.component_name}」已存在(asset #${data.asset_id}), 未重复创建`)
      else {
        ElMessage.success(`已登记为资产「${it.component_name}」(#${data.asset_id})`)
        resultView.value={ title:`📌 资产登记成功 · ${it.component_name}`, body: JSON.stringify(data.asset,null,2) }
      }
    } else ElMessage.error(data.error||'登记失败')
  } catch(e){ ElMessage.error('登记失败') }
}

onMounted(()=>{ loadAll(); refreshProxyList() })
</script>

<style scoped>
.store-page{padding:20px;color:#1f2937}
.page-header h1{margin:0 0 4px;font-size:20px}
.page-header p{margin:0 0 16px;color:#6b7280;font-size:13px}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px;text-align:center}
.val{font-size:24px;font-weight:700}.val.blue{color:#3b82f6}.val.ok{color:#10b981}.val.warn{color:#f59e0b}
.lbl{font-size:12px;color:#6b7280}
.tab-bar{display:flex;gap:0;border-bottom:2px solid #e5e7eb;margin-bottom:16px}
.tab-item{padding:10px 18px;cursor:pointer;color:#6b7280;border-bottom:2px solid transparent;margin-bottom:-2px}
.tab-item.active{color:#3b82f6;border-bottom-color:#3b82f6;font-weight:600}
.filter-bar{display:flex;gap:10px;margin-bottom:16px}
.filter-bar select,.filter-bar input{padding:7px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px}
.filter-bar select{width:140px}
.comp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.comp-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px}
.comp-head{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.icon{font-size:26px}.title-box .name{font-weight:600;font-size:15px}.ver{font-size:11px;color:#9ca3af}
.desc{font-size:12px;color:#4b5563;min-height:32px;margin-bottom:10px}
.deploy-tags{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.dt-tag{font-size:11px;background:#eff6ff;color:#1e40af;padding:2px 8px;border-radius:10px}
.foot{display:flex;justify-content:space-between;align-items:center}
.complexity{font-size:11px;color:#9ca3af}
.inst-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.inst-tip{font-size:12px;color:#9ca3af}
.inst-list{display:flex;flex-direction:column;gap:12px}.inst-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;display:flex;justify-content:space-between;align-items:center;gap:12px}
.inst-head{display:flex;gap:12px;align-items:center}
.ic{font-size:24px}.iname{font-weight:600}.imeta{font-size:12px;color:#6b7280}
.status-group{display:flex;gap:6px}
.st{padding:2px 8px;border-radius:10px;font-size:11px;background:#e5e7eb;color:#374151}
.st-st{color:#1e40af}
.st2{padding:2px 8px;border-radius:10px;font-size:11px}
.st2-healthy{background:#d1fae5;color:#065f46}.st2-unhealthy{background:#fee2e2;color:#991b1b}.st2-unknown{background:#f3f4f6;color:#6b7280}
.ops{display:flex;gap:6px;flex-wrap:wrap}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:1100}
.modal{background:#fff;border-radius:12px;width:620px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column}
.modal.wide{width:760px}
.mhead{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid #e5e7eb}
.mhead h3{margin:0;font-size:16px}.mclose{background:none;border:none;font-size:18px;cursor:pointer}
.mbody{padding:18px 20px;overflow-y:auto}
.mfoot{display:flex;justify-content:flex-end;gap:10px;padding:14px 20px;border-top:1px solid #e5e7eb}
.field{margin-bottom:14px}.field label{display:block;font-size:13px;font-weight:600;margin-bottom:6px}
.field select,.field input{width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:6px;box-sizing:border-box;font-size:13px}
.dt-select{display:flex;gap:8px}.dt-btn{padding:8px 14px;border:1px solid #d1d5db;background:#fff;border-radius:8px;cursor:pointer;font-size:13px}
.dt-btn.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.row2{display:flex;gap:10px}
.proxy-block{border:1px dashed #dcdfe6;border-radius:8px;padding:10px 12px;margin-bottom:14px;background:#fafbfc}
.proxy-block summary{cursor:pointer;font-size:13px;color:#3b82f6;font-weight:600;user-select:none}
.proxy-grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
.proxy-select-row{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.proxy-select-row label{font-size:13px;color:#475569;font-weight:600}
.proxy-select{flex:1;border:1px solid #d7dee8;border-radius:8px;padding:8px 10px;font-size:13px;background:#fff}
.proxy-hint{font-size:12px;color:#9ca3af;margin-top:4px}
.param-block{border:1px solid #dbeafe;background:#f8fbff;border-radius:8px;padding:12px 14px;margin-bottom:14px}
.param-title{font-size:13px;font-weight:700;color:#1d4ed8;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.param-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:640px){.param-grid{grid-template-columns:1fr}}
.param-block .cfg-field label{font-size:12px}
.offline-toggle{border:1px solid #e2e8f0;background:#f8fafc;border-radius:8px;padding:10px 14px;margin-bottom:14px}
.offline-toggle .checkbox-row{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#0f172a}
.offline-toggle input[type=checkbox]{width:16px;height:16px}
.recipe{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:12px;font-size:12px;max-height:260px;overflow:auto;white-space:pre-wrap}
.result{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:14px;font-size:12px;max-height:60vh;overflow:auto;white-space:pre-wrap}
.empty{text-align:center;padding:50px;color:#6b7280}
.btn{padding:8px 14px;border:1px solid #d1d5db;background:#fff;border-radius:6px;cursor:pointer;font-size:13px}
.btn-primary{background:#3b82f6;color:#fff;border-color:#3b82f6}
.btn-danger{color:#ef4444;border-color:#fecaca}
.btn-asset{color:#7c3aed;border-color:#ddd6fe}
.btn-asset:disabled{opacity:.5;cursor:not-allowed}
.btn-sm{padding:5px 10px;font-size:12px}
.btn:disabled{opacity:.5;cursor:not-allowed}
.deploy-modal{width:880px}
.deploy-status{font-size:12px;color:#10b981;margin-left:10px;display:inline-flex;align-items:center;gap:6px}
.spinner{width:12px;height:12px;border:2px solid #10b981;border-top-color:transparent;border-radius:50%;display:inline-block;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.phase-bar{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.phase{padding:4px 10px;font-size:12px;border-radius:6px;background:#eef2f7;color:#94a3b8}
.phase.done{background:#d1fae5;color:#065f46}
.phase.cur{background:#3b82f6;color:#fff}
.deploy-workspace{display:grid;grid-template-columns:1.6fr 1fr;gap:12px}
.terminal{background:#0f172a;border-radius:8px;overflow:hidden;display:flex;flex-direction:column;min-height:320px}
.term-head{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#1e293b;color:#e2e8f0;font-size:12px;border-bottom:1px solid #334155}
.term-info{color:#10b981}
.term-body{flex:1;padding:10px 12px;overflow:auto;max-height:360px;font-family:Consolas,Menlo,monospace;font-size:12px}
.term-empty{color:#64748b;text-align:center;padding:40px 0}
.tline{white-space:pre-wrap;word-break:break-all;margin-bottom:2px;color:#cbd5e1}
.tline .tts{color:#64748b;margin-right:8px;font-size:11px}
.tline.phase{background:none;padding:0;color:#93c5fd;border-radius:0}
.tline.error{color:#f87171}
.tline.ok{color:#34d399}
.tline .tmsg{vertical-align:baseline}
.ai-panel{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;min-height:320px;display:flex;flex-direction:column;gap:8px;overflow:auto;max-height:400px}
.ai-head{font-weight:600;font-size:13px;color:#7c3aed;display:flex;align-items:center;gap:6px}
.ai-empty{color:#94a3b8;font-size:12px;text-align:center;padding:30px 0}
.ai-tip{background:#fff;border:1px solid #ede9fe;border-left:3px solid #7c3aed;border-radius:6px;padding:8px 10px}
.ai-stage{font-size:11px;color:#7c3aed;font-weight:600;margin-bottom:4px}
.ai-summary{font-size:12px;color:#1f2937;margin-bottom:4px}
.ai-advice{font-size:12px;color:#6b7280;line-height:1.5}
.ai-risk{font-size:11px;margin-top:4px;font-weight:600}
.ai-risk.risk-low{color:#10b981}.ai-risk.risk-medium{color:#f59e0b}.ai-risk.risk-high{color:#ef4444}
.ai-foot{margin-top:auto}
.result-box{padding:10px;border-radius:6px;font-size:13px;font-weight:600;text-align:center}
.result-box.ok{background:#d1fae5;color:#065f46}
.result-box.fail{background:#fee2e2;color:#991b1b}
.precheck-panel{background:#f6f8fa;border:1px solid #e1e4e8;border-radius:8px;padding:10px 12px;max-height:180px;overflow:auto}
.precheck-title{font-weight:600;font-size:12px;color:#1f2937;margin-bottom:6px}
.precheck-item{display:flex;align-items:center;gap:8px;padding:2px 0;font-size:12px}
.precheck-mark{font-weight:700}
.precheck-mark.ok{color:#10b981}
.precheck-mark.fail{color:#ef4444}
.precheck-name{min-width:110px;color:#374151}
.precheck-msg.ok{color:#059669}
.precheck-msg.fail{color:#dc2626}
.report-box{background:#fff;border:1px solid #ddd6fe;border-left:3px solid #7c3aed;border-radius:8px;padding:10px}
.report-title{font-weight:600;font-size:13px;color:#5b21b6;display:flex;align-items:center;gap:8px}
.report-overall{padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}
.report-overall.ov-healthy{background:#d1fae5;color:#065f46}
.report-overall.ov-degraded{background:#fef3c7;color:#92400e}
.report-overall.ov-unhealthy{background:#fee2e2;color:#991b1b}
.report-summary{font-size:12px;color:#6b7280;margin-top:6px;line-height:1.5}

/* ── K8s 详情/部署式弹窗样式 ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:1050}
.modal-box{background:#fff;border-radius:8px;max-width:92vw;width:960px;max-height:90vh;overflow:auto}
.modal-head{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid #e4e7ed;position:sticky;top:0;background:#fff;z-index:2}
.modal-head h3{margin:0;font-size:16px;display:flex;align-items:center;gap:8px}
.modal-close{border:none;background:none;font-size:22px;cursor:pointer;color:#909399;line-height:1}
.modal-close:hover{color:#f56c6c}
.modal-body{padding:16px 18px}
.modal-foot{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid #e4e7ed;position:sticky;bottom:0;background:#fff}
.form-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.form-row{margin-bottom:8px}
.form-row label{display:block;font-size:13px;color:#606266;margin-bottom:4px}
.form-row select,.form-row input{width:100%;border:1px solid #dcdfe6;border-radius:4px;padding:6px 8px;font-size:13px;box-sizing:border-box;background:#fff}
.form-row select:disabled,.form-row input:disabled{background:#f5f7fa;color:#a8abb2}
.req{color:#f56c6c}
.hint{color:#909399;font-size:12px;margin-top:6px}
.deploy-actions{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.deploy-actions .kv{background:#f0f2f5;border-radius:4px;padding:2px 8px;font-size:12px;color:#606266}
.deploy-actions .kv.run{background:#ecf5ff;color:#409eff}
.status-badge{border-radius:4px;padding:1px 8px;font-size:12px}
.status-badge.draft,.status-badge.pending{background:#f4f4f5;color:#909399}
.status-badge.running{background:#ecf5ff;color:#409eff}
.status-badge.succeeded,.status-badge.ok{background:#f0f9eb;color:#67c23a}
.status-badge.failed{background:#fef0f0;color:#f56c6c}
.terminal{background:#1e1e1e;color:#d4d4d4;border-radius:4px;overflow:hidden;min-height:300px;display:flex;flex-direction:column}
.term-head{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#2b2b2b;color:#e2e8f0;font-size:12px;border-bottom:1px solid #333}
.term-info{color:#89d185}
.term-body{flex:1;padding:10px 12px;overflow:auto;max-height:340px;font-family:Consolas,Menlo,monospace;font-size:12px}
.phase-bar{display:flex;gap:4px;margin:12px 0;flex-wrap:wrap}
.phase{padding:3px 8px;font-size:11px;border-radius:3px;background:#f4f4f5;color:#909399}
.phase.done{background:#f0f9eb;color:#67c23a}
.phase.cur{background:#409eff;color:#fff}

/* ══ 优化版部署弹窗: 深色摘要头 + 两栏分区卡片 ══ */
.deploy-dialog{width:1020px;max-width:96vw;max-height:92vh;overflow:hidden;display:flex;flex-direction:column;border-radius:14px;box-shadow:0 24px 60px -12px rgba(2,6,23,.4)}
.deploy-hero{display:flex;align-items:center;gap:16px;padding:18px 22px;color:#fff;
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 60%,#312e81 100%);position:relative}
.hero-icon{width:52px;height:52px;border-radius:14px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0;backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.15)}
.hero-info{flex:1;min-width:0}
.hero-title{font-size:20px;font-weight:700;display:flex;align-items:baseline;gap:10px;letter-spacing:.3px;color:#fff}
.hero-ver{font-size:12px;color:#a5b4fc;font-weight:500}
.hero-sub{font-size:12.5px;color:#cbd5e1;margin-top:2px;opacity:.9}
.hero-tags{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.hero-tag{font-size:11px;padding:2px 9px;border-radius:20px;background:rgba(255,255,255,.12);color:#e2e8f0;border:1px solid rgba(255,255,255,.14)}
.hero-tag.port{background:rgba(129,140,248,.25);border-color:rgba(129,140,248,.35);color:#c7d2fe}
.hero-badge{flex-shrink:0}
.status-badge.lg{padding:3px 12px;font-size:12.5px;border-radius:20px;font-weight:600}
.hero-close{position:absolute;top:14px;right:16px;background:none;border:none;color:#94a3b8;font-size:24px;cursor:pointer;line-height:1}
.hero-close:hover{color:#fff}

.deploy-body{display:grid;grid-template-columns:minmax(320px,36%) 1fr;gap:0;flex:1;overflow:hidden;background:#f1f5f9}
.deploy-col{padding:18px 20px;overflow-y:auto}
.config-col{background:#fff;border-right:1px solid #e2e8f0}
.exec-col{padding-left:22px;display:flex;flex-direction:column;gap:14px}
.panel-title{font-size:13px;font-weight:700;color:#0f172a;letter-spacing:.5px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}
.config-col .panel-title::after{content:'';flex:1;height:1px;background:#e2e8f0;margin-left:12px}
.exec-live{font-size:11px;color:#10b981;font-weight:600;display:inline-flex;align-items:center;gap:5px;background:#ecfdf5;padding:2px 8px;border-radius:20px}
.exec-live .dot{width:6px;height:6px;border-radius:50%;background:#10b981;animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.cfg-field{margin-bottom:14px}
.cfg-field label{display:block;font-size:12.5px;font-weight:600;color:#334155;margin-bottom:6px}
.cfg-field select,.cfg-field input{width:100%;padding:8px 11px;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;background:#f8fafc;box-sizing:border-box;transition:border-color .15s,box-shadow .15s,background .15s}
.cfg-field select:focus,.cfg-field input:focus{outline:none;border-color:#6366f1;background:#fff;box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.cfg-field select:disabled,.cfg-field input:disabled{background:#f1f5f9;color:#94a3b8}
.cfg-field select i{font-style:normal;color:#94a3b8}
.cfg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}

.mode-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.mode-btn{padding:9px 6px;border:1px solid #e2e8f0;border-radius:9px;background:#fff;cursor:pointer;font-size:12.5px;color:#475569;transition:all .15s;display:flex;align-items:center;justify-content:center;gap:5px}
.mode-btn:hover{border-color:#c7d2fe;background:#f5f6ff}
.mode-btn.active{background:linear-gradient(135deg,#6366f1,#4f46e5);border-color:#4f46e5;color:#fff;font-weight:600;box-shadow:0 4px 12px -3px rgba(79,70,229,.5)}
.mode-btn:disabled{opacity:.5;cursor:not-allowed}

.proxy-block,.recipe-block{border:1px dashed #e2e8f0;border-radius:10px;padding:10px 13px;margin-bottom:0;background:#f8fafc}
.proxy-block summary,.recipe-block summary{cursor:pointer;font-size:12.5px;color:#4f46e5;font-weight:600;user-select:none;list-style:none;display:flex;align-items:center;gap:6px}
.proxy-block summary::before,.recipe-block summary::before{content:'\25B8';transition:transform .15s;font-size:11px}
.proxy-block[open] summary::before,.recipe-block[open] summary::before{transform:rotate(90deg)}
.proxy-grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
.recipe-block{margin-top:12px}
.recipe-block pre{background:#0f172a;color:#a5f3fc;border-radius:8px;padding:12px;font-size:12px;max-height:180px;overflow:auto;white-space:pre-wrap;margin-top:10px;font-family:Consolas,Menlo,monospace;line-height:1.5}

.exec-col .terminal{flex:none;background:#0b1220;border:1px solid #1e293b;border-radius:10px;overflow:hidden}
.exec-col .term-head{background:#111c33;border-bottom:1px solid #1e293b}
.exec-col .term-body{max-height:220px;font-size:12px}
.exec-col .precheck-panel{border-radius:10px;border:1px solid #e2e8f0}
.exec-col .ai-panel{min-height:0;max-height:220px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px}
.exec-col .ai-tip{background:#fff;border-left:3px solid #6366f1}
.exec-col .report-box,.exec-col .result-box{border-radius:10px}

/* ── AI 失败诊断卡 ── */
.ai-tip.diagnostic{border-left:3px solid #ef4444;border-color:#fecaca;background:#fff5f5}
.diag-head{font-size:12px;font-weight:700;color:#dc2626;display:flex;align-items:center;gap:6px;margin-bottom:4px}
.diag-icon{font-size:13px}
.diag-cause{font-size:12.5px;color:#7f1d1d;font-weight:600;margin-bottom:6px;line-height:1.5}
.diag-steps{display:flex;flex-direction:column;gap:4px;margin-top:4px}
.diag-step{display:flex;align-items:flex-start;gap:6px;font-size:12px;color:#374151;line-height:1.4}
.diag-n{flex-shrink:0;width:16px;height:16px;border-radius:50%;background:#ef4444;color:#fff;font-size:10px;display:flex;align-items:center;justify-content:center;margin-top:1px;font-weight:600}

/* ── AI 交付报告 ── */
.report-box.deliv{background:#faf9ff;border:1px solid #ddd6fe;border-left:3px solid #7c3aed;border-radius:10px;padding:12px}
.report-conclusion{font-size:13px;font-weight:600;color:#1f2937;margin:6px 0 8px;line-height:1.5}
.report-field{font-size:12px;color:#374151;margin-bottom:6px;line-height:1.5}
.rf-label{display:inline-block;font-size:11px;font-weight:700;color:#7c3aed;background:#ede9fe;border-radius:4px;padding:1px 6px;margin-right:6px;vertical-align:top}
.rf-item{margin:2px 0 2px 12px;color:#4b5563}
.rf-item.risk-item{color:#b91c1c}

/* ── AI 决策门控卡片 ── */
.decision-card{background:linear-gradient(135deg,#eef2ff,#f5f3ff);border:1.5px solid #6366f1;border-radius:12px;padding:12px 14px;margin-bottom:12px;box-shadow:0 6px 18px -8px rgba(99,102,241,.4)}
.decision-head{font-size:13px;font-weight:700;color:#4338ca;display:flex;align-items:center;gap:6px;margin-bottom:6px}
.decision-icon{font-size:15px}
.decision-q{font-size:12.5px;color:#3730a3;margin-bottom:10px;line-height:1.5}
.decision-opts{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
.decision-opt{display:flex;align-items:flex-start;gap:8px;text-align:left;padding:9px 11px;border:1px solid #c7d2fe;border-radius:9px;background:#fff;cursor:pointer;transition:all .15s}
.decision-opt:hover{border-color:#6366f1;background:#eef2ff;transform:translateY(-1px);box-shadow:0 4px 12px -6px rgba(99,102,241,.5)}
.decision-opt-key{flex-shrink:0;width:20px;height:20px;border-radius:6px;background:#6366f1;color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
.decision-opt-title{font-size:12.5px;font-weight:600;color:#1e1b4b;margin-bottom:2px}
.decision-opt-detail{font-size:11.5px;color:#6d28d9;line-height:1.4;display:block}
.decision-free{display:flex;gap:8px;align-items:center}
.decision-free input{flex:1;border:1px solid #c7d2fe;border-radius:8px;padding:8px 10px;font-size:12.5px;background:#fff}
.decision-free input:focus{outline:none;border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.12)}

/* ── 部署方案(AI 生成) ── */
.plan-system{display:inline-block;background:#e0e7ff;color:#3730a3;border-radius:10px;padding:1px 8px;font-size:11px;margin-left:6px;font-weight:600}
.plan-ai{display:inline-block;background:#dcfce7;color:#15803d;border-radius:10px;padding:1px 8px;font-size:11px;margin-left:6px;font-weight:600}
.plan-toolbar{display:flex;align-items:center;gap:10px;margin-top:10px;flex-wrap:wrap}
.plan-empty{color:#94a3b8;font-size:12px;padding:14px 4px}
.recipe-block pre{max-height:220px}
.opt-offline{color:#c0c4cc}
.detail-dialog{border-radius:14px;overflow:hidden;box-shadow:0 24px 60px -12px rgba(2,6,23,.4)}
.detail-body{padding:18px 22px;max-height:66vh;overflow:auto;background:#f8fafc}
.detail-log{background:#0b1220;color:#a5f3fc;border-radius:10px;padding:14px;font-size:12.5px;min-height:200px;white-space:pre-wrap;line-height:1.6;font-family:Consolas,Menlo,monospace;border:1px solid #1e293b}
.detail-ai{background:#fff;border-left:3px solid #7c3aed;border-radius:8px;padding:12px;font-size:13px;color:#1f2937;white-space:pre-wrap;line-height:1.5}

/* ── 执行区 Tab(减挤) ── */
.exec-tabs-head{display:flex;gap:6px;margin-bottom:10px;border-bottom:1px solid #e2e8f0;padding-bottom:8px}
.exec-tab{border:none;background:none;padding:6px 14px;font-size:13px;color:#64748b;cursor:pointer;border-radius:8px;display:inline-flex;align-items:center;gap:6px;transition:all .15s}
.exec-tab:hover{background:#f1f5f9}
.exec-tab.active{background:#eef2ff;color:#4f46e5;font-weight:600}
.tab-badge{background:#4f46e5;color:#fff;font-size:11px;border-radius:10px;padding:0 6px;min-width:16px;text-align:center}
.term-body-lg{max-height:380px;height:340px}
.ai-panel-lg{min-height:200px;max-height:380px}
.check-tab{display:flex;flex-direction:column;gap:12px;max-height:380px;overflow:auto}
.check-tab .precheck-panel{border-radius:10px}
.exec-col .check-tab .report-box{border-radius:10px}

/* ── 配置区 Tab(左栏) ── */
.cfg-tabs-head{display:flex;gap:6px;margin-bottom:14px;border-bottom:1px solid #e2e8f0;padding-bottom:8px}
.config-tab{border:none;background:none;padding:6px 12px;font-size:13px;color:#64748b;cursor:pointer;border-radius:8px;display:inline-flex;align-items:center;gap:5px;transition:all .15s}
.config-tab:hover{background:#f1f5f9}
.config-tab.active{background:#eef2ff;color:#4f46e5;font-weight:600}
.cfg-tab-pane{display:flex;flex-direction:column;gap:2px}
.plan-meta{display:flex;gap:6px;align-items:center;margin:6px 0 8px}

/* ── K8S 式安装记录表格 ── */
.status-filter{display:flex;gap:6px;flex-wrap:wrap}
.sf-btn{border:1px solid #e2e8f0;background:#fff;padding:5px 14px;font-size:13px;color:#64748b;border-radius:8px;cursor:pointer;transition:all .15s}
.sf-btn:hover{border-color:#c7d2fe}
.sf-btn.active{background:#4f46e5;color:#fff;border-color:#4f46e5;font-weight:600}
.table-wrap{background:#fff;border:1px solid #e4e7ed;border-radius:10px;overflow:auto}
.table{width:100%;border-collapse:collapse;font-size:13px}
.table thead th{background:#f8fafc;color:#64748b;font-weight:600;text-align:left;padding:10px 14px;border-bottom:1px solid #e4e7ed;white-space:nowrap}
.table tbody td{padding:10px 14px;border-bottom:1px solid #f1f5f9}
.table tbody tr:hover{background:#f8faff}
.table .pname{font-weight:600;color:#1e293b}
.table .muted{color:#94a3b8}
.row-actions{white-space:nowrap}
.row-actions .btn{margin-right:4px}

/* ── 可直接交付部署报告弹窗(对标 AI 自动部署页报告版式) ── */
.report-dialog{max-width:880px;display:flex;flex-direction:column;max-height:90vh}
.report-dialog-head{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;background:#0f172a;border-radius:14px 14px 0 0;color:#fff}
.rdh-left{display:flex;align-items:center;gap:12px}
.rdh-icon{font-size:26px}
.rdh-title{font-size:17px;font-weight:700}
.rdh-sub{font-size:12px;opacity:.8;margin-top:2px}
.rdh-tag{margin-left:6px;background:#1e293b;padding:2px 8px;border-radius:10px;font-size:11px}
.report-dialog-head .hero-close{color:#94a3b8}
.report-dialog-body{overflow:auto;padding:20px 22px;flex:1}
.report-loading{display:flex;align-items:center;gap:10px;color:#64748b;padding:40px;justify-content:center}
.report-loading .spinner{width:18px;height:18px;border:2px solid #cbd5e1;border-top-color:#3b82f6;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.report-dialog-foot{display:flex;justify-content:flex-end;gap:10px;padding:14px 22px;border-top:1px solid #eef2f7;background:#fff;border-radius:0 0 14px 14px}
.report-full{padding:0}
.report-header{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.report-header h3{margin:0;font-size:20px;color:#0f172a}
.report-meta-bar{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:#64748b;margin-bottom:16px;padding:8px 14px;background:#f8fafc;border-radius:8px}
.report-status-badge{font-size:12px;padding:3px 10px;border-radius:12px;font-weight:600}
.report-status-badge.succeeded,.report-status-badge.success,.report-status-badge.healthy,.report-status-badge.pass,.report-status-badge.safe{background:#dcfce7;color:#16a34a}
.report-status-badge.failed,.report-status-badge.error,.report-status-badge.unhealthy{background:#fee2e2;color:#dc2626}
.report-status-badge.running,.report-status-badge.pending{background:#dbeafe;color:#2563eb}
.report-status-badge.degraded,.report-status-badge.drift{background:#fef3c7;color:#d97706}
.report-status-badge.error{background:#fee2e2;color:#dc2626}
.report-line{margin:5px 0;font-size:13px;color:#334155;line-height:1.6}
.report-section-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;margin-bottom:16px}
.report-section-card h4{margin:0 0 12px;font-size:15px;color:#0f172a}
.report-summary-text{color:#334155;line-height:1.7;margin:0}
.kpi-grid{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.kpi-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 14px;min-width:64px;text-align:center}
.kpi-item.success{border-color:#bbf7d0;background:#f0fdf4}
.kpi-label{display:block;font-size:11px;color:#64748b;margin-bottom:2px}
.kpi-value{font-size:18px;font-weight:700;color:#0f172a}
.command-block{background:#1e293b;color:#e2e8f0;padding:12px;border-radius:8px;font-size:13px;font-family:'JetBrains Mono','Fira Code',monospace;white-space:pre-wrap;line-height:1.6;margin:0}
.report-table{width:100%;border-collapse:collapse;font-size:13px}
.report-table td{padding:8px 10px;border-bottom:1px solid #f1f5f9}
.report-table td.env-key{width:140px;font-weight:600;color:#0f172a;background:#f8fafc}
.login-line{margin:4px 0;font-size:13px}
.login-user{font-weight:600;color:#0f172a}
.login-via{color:#64748b;margin-left:8px;font-family:'JetBrains Mono',monospace;font-size:12px}
.issue-item{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;padding:6px 0;border-bottom:1px solid #f1f5f9}
.issue-severity{font-weight:600;text-transform:uppercase;font-size:11px}
.severity-high .issue-severity{color:#dc2626}.severity-medium .issue-severity{color:#d97706}.severity-low .issue-severity{color:#16a34a}
.issue-desc{flex:1}
.issue-resolve{color:#64748b}
.issue-status{font-size:11px;padding:2px 8px;border-radius:10px;background:#f1f5f9;color:#475569}
.issue-status.resolved{background:#dcfce7;color:#16a34a}
.issue-status.pending{background:#fee2e2;color:#dc2626}
.asset-dialog{max-width:640px;display:flex;flex-direction:column;max-height:92vh}
.asset-dialog-head{display:flex;align-items:center;justify-content:space-between;padding:16px 22px;background:#0f172a;border-radius:14px 14px 0 0;color:#fff}
.adh-left{display:flex;align-items:center;gap:12px}
.adh-icon{font-size:24px}
.adh-title{font-size:17px;font-weight:700}
.adh-sub{font-size:12px;opacity:.8;margin-top:2px}
.asset-dialog-head .hero-close{color:#94a3b8}
.asset-dialog-body{overflow:auto;padding:20px 22px;flex:1}
.asset-readonly-tip{background:#eff6ff;color:#1d4ed8;font-size:12px;padding:8px 12px;border-radius:8px;margin-bottom:16px}
.asset-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.af-field{display:flex;flex-direction:column;gap:6px}
.af-field.af-wide{grid-column:1 / -1}
.af-field label{font-size:13px;color:#475569;font-weight:600}
.af-field label .req{color:#ef4444}
.af-field input{border:1px solid #d7dee8;border-radius:8px;padding:9px 12px;font-size:13px;outline:none;background:#fff}
.af-field input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.12)}
.af-field input:disabled{background:#f1f5f9;color:#64748b;cursor:not-allowed}
.asset-form-sep{font-size:13px;font-weight:700;color:#0f172a;margin:20px 0 12px;padding-top:16px;border-top:1px dashed #e2e8f0}
.asset-dialog-foot{display:flex;justify-content:flex-end;gap:10px;padding:14px 22px;border-top:1px solid #eef2f7;background:#fff;border-radius:0 0 14px 14px}
</style>
