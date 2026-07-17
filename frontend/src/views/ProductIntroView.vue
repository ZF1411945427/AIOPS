<template>
  <div class="intro-page">
    <canvas ref="bgCanvas" id="bg-canvas"></canvas>
    <div class="bg-vignette"></div>
    <div class="bg-grain"></div>
    <!-- ─── NAV ─── -->
    <nav class="intro-nav">
      <a href="/login" class="nav-logo">
        <span class="logo-mark">AI</span><span class="logo-type">Ops</span>
      </a>
      <div class="nav-links">
        <a href="#trust">数据</a>
        <a href="#capabilities">能力</a>
        <a href="#orchestration">编排</a>
        <a href="#how">原理</a>
        <a href="#highlights">亮点</a>
        <a href="/login" class="nav-cta">立即体验</a>
      </div>
    </nav>

    <!-- ─── HERO ─── -->
    <section class="hero-section" data-theme="199,81,46">
      <div class="hero-mesh" />
      <div class="hero-content">
        <div ref="heroEyebrow" class="hero-eyebrow">
          <span class="eyebrow-dot" />
          <span>MCP 协议原生 · 大模型驱动 · 双工作流引擎</span>
        </div>
        <h1 ref="heroTitle">
          <span class="title-line">让运维拥有</span>
          <span class="title-line accent">判断力</span>
        </h1>
        <p ref="heroDesc">
          不是又一个监控仪表盘。AIOps 将大语言模型、MCP 工具协议、可视化编排融为一体——让运维从"人盯着看"进化为"智能体替你想、替你做"。
        </p>
        <div ref="heroBtns" class="hero-btns">
          <a href="/login" class="btn-primary">
            立即体验
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </a>
          <a href="#capabilities" class="btn-ghost">探索能力</a>
        </div>
        <div ref="heroStats" class="hero-stats">
          <div class="hstat">
            <span class="hstat-num" data-target="13">0</span>
            <span class="hstat-unit">min</span>
            <span class="hstat-label">平均故障恢复</span>
          </div>
          <div class="hstat-div" />
          <div class="hstat">
            <span class="hstat-num" data-target="90">0</span>
            <span class="hstat-unit">%</span>
            <span class="hstat-label">告警噪声削减</span>
          </div>
          <div class="hstat-div" />
          <div class="hstat">
            <span class="hstat-num" data-target="500">0</span>
            <span class="hstat-unit">+</span>
            <span class="hstat-label">资产纳管规模</span>
          </div>
        </div>
      </div>
      <div ref="heroVisual" class="hero-visual">
        <div class="glass-card">
          <div class="glass-card-inner">
          <div class="glass-card-header">
            <div class="gc-title">智能运维体 · 核心态势</div>
            <div class="gc-badge">
              <span class="gc-dot" />
              运行中
            </div>
          </div>
          <div class="glass-metrics">
            <div class="gc-metric">
              <div class="gc-num">99.8<span style="font-size:18px">%</span></div>
              <div class="gc-label">健康分</div>
            </div>
            <div class="gc-metric">
              <div class="gc-num warn">2</div>
              <div class="gc-label">活跃告警</div>
            </div>
            <div class="gc-metric">
              <div class="gc-num muted" style="color:var(--fg3)">8</div>
              <div class="gc-label">未关闭事件</div>
            </div>
            <div class="gc-metric">
              <div class="gc-num">128</div>
              <div class="gc-label">资产总数</div>
            </div>
          </div>
          <div class="glass-chart">
            <svg viewBox="0 0 300 60" fill="none">
              <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stop-color="#4F46E5" />
                  <stop offset="100%" stop-color="#7C3AED" />
                </linearGradient>
              </defs>
              <polyline points="0,50 30,42 60,38 90,44 120,30 150,35 180,20 210,25 240,15 270,18 300,10" stroke="url(#chartGrad)" stroke-width="2" fill="none" />
              <polyline points="0,50 30,42 60,38 90,44 120,30 150,35 180,20 210,25 240,15 270,18 300,10 300,60 0,60" fill="url(#chartGrad)" opacity="0.08" />
            </svg>
            <div class="gc-chart-label">系统健康趋势 · 近7天</div>
          </div>
          <div class="glass-footer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            SLA 99.8% · 系统平稳运行
          </div>
          </div>
        </div>
        <div class="float-card float-card-1">
          <div class="fc-icon" style="background:rgba(13,148,136,0.1);color:#0D9488">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div class="fc-body">
            <div class="fc-title">告警已收敛</div>
            <div class="fc-sub">9 条有效 / 90 条总</div>
          </div>
        </div>
        <div class="float-card float-card-2">
          <div class="fc-icon" style="background:rgba(79,70,229,0.1);color:#4F46E5">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          </div>
          <div class="fc-body">
            <div class="fc-title">MTTR 13min</div>
            <div class="fc-sub">较上月 ↓23%</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── TRUST STATS ─── -->
    <section id="trust" class="trust-section" data-theme="79,70,229">
      <div class="section-container">
        <div ref="trustHeader" class="trust-header rv">
          <div class="section-eyebrow">// 用结果说话</div>
          <h2>真实数据，不再是 PPT</h2>
          <p>已接入团队的复现数字，每一个都经得起验证。</p>
        </div>
        <div class="trust-grid">
          <div v-for="t in trustStats" :key="t.label" class="trust-card rv">
            <div class="trust-icon-wrap" :style="{ background: t.iconBg }">
              <component :is="t.icon" :style="{ color: t.color }" />
            </div>
            <div class="trust-num-wrap">
              <span class="trust-num" :style="{ color: t.color }" :data-target="t.num" :data-suffix="t.suffix">0</span>
              <span class="trust-suffix" :style="{ color: t.color }">{{ t.suffix }}</span>
            </div>
            <div class="trust-label">{{ t.label }}</div>
            <div class="trust-desc">{{ t.desc }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── CAPABILITIES ─── -->
    <section id="capabilities" class="cap-section" data-theme="13,148,136">
      <div class="section-container">
        <div ref="capHeader" class="section-header rv">
          <div class="section-eyebrow">// 能力矩阵</div>
          <h2>五大领域，闭环协作</h2>
          <p>从告警到修复，从预防到验证，每个领域独立进化，拧成一根绳。</p>
        </div>
        <div class="cap-bento">
          <div v-for="(cap, i) in capabilities" :key="cap.title" :ref="el => capRefs[i] = el" class="cap-card rv" :class="`cap-${i} rv-${i}`">
            <div class="cap-icon" :style="{ background: cap.iconBg }">
              <component :is="cap.icon" :style="{ color: cap.iconColor }" />
            </div>
            <div class="cap-badge-tag" :style="{ background: cap.iconBg, color: cap.iconColor }">{{ cap.badge }}</div>
            <h3>{{ cap.title }}</h3>
            <p>{{ cap.desc }}</p>
            <div class="cap-tags">
              <span v-for="tag in cap.tags" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── ORCHESTRATION ─── -->
    <section id="orchestration" class="orch-section" ref="orchSection" data-theme="124,58,237">
      <div class="section-container orch-container">
        <div ref="orchHeader" class="orch-header rv">
          <div class="section-eyebrow">// 编排引擎</div>
          <h2>把运维剧本，画在画布上</h2>
          <p>8 种节点拖拽组合，LLM 推理、知识检索、工具调用、条件分支串成 DAG——运维知识第一次可以被可视化沉淀。</p>
        </div>
        <div ref="orchVisual" class="orch-visual">
          <svg class="dag-svg" viewBox="0 0 800 320" fill="none">
            <!-- Edges with animated flow -->
            <defs>
              <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <polygon points="0 0, 6 3, 0 6" fill="#4F46E5" opacity="0.5" />
              </marker>
              <linearGradient id="edgeGrad1" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#4F46E5" />
                <stop offset="100%" stop-color="#7C3AED" />
              </linearGradient>
              <linearGradient id="edgeGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#7C3AED" />
                <stop offset="100%" stop-color="#0D9488" />
              </linearGradient>
              <linearGradient id="edgeGrad3" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#0D9488" />
                <stop offset="100%" stop-color="#D97706" />
              </linearGradient>
            </defs>
            <!-- Animated dash edges -->
            <path class="dag-edge" d="M120,80 C200,80 220,160 300,160" stroke="url(#edgeGrad1)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <path class="dag-edge" d="M120,80 C200,80 220,240 300,240" stroke="url(#edgeGrad1)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <path class="dag-edge" d="M370,160 C430,160 440,120 500,120" stroke="url(#edgeGrad2)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <path class="dag-edge" d="M370,240 C430,240 440,200 500,200" stroke="url(#edgeGrad2)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <path class="dag-edge" d="M570,120 C620,120 630,160 680,160" stroke="url(#edgeGrad3)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <path class="dag-edge" d="M570,200 C620,200 630,240 680,240" stroke="url(#edgeGrad3)" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrowhead)" />
            <!-- Flowing particles -->
            <circle r="3" fill="#4F46E5" class="dag-particle">
              <animateMotion dur="2s" repeatCount="indefinite" path="M120,80 C200,80 220,160 300,160" />
            </circle>
            <circle r="3" fill="#7C3AED" class="dag-particle">
              <animateMotion dur="2.5s" repeatCount="indefinite" path="M300,160 C370,160 380,120 500,120" />
            </circle>
            <circle r="3" fill="#0D9488" class="dag-particle">
              <animateMotion dur="1.8s" repeatCount="indefinite" path="M500,120 C570,120 580,160 680,160" />
            </circle>
          </svg>
          <!-- Node cards positioned over SVG -->
          <div class="dag-node dag-start">
            <div class="dag-node-icon" style="background:rgba(79,70,229,0.12);color:#4F46E5">S</div>
            <div class="dag-node-body">
              <div class="dag-node-title">开始节点</div>
              <div class="dag-node-sub">注入输入参数</div>
            </div>
            <div class="dag-node-type">start</div>
          </div>
          <div class="dag-node dag-llm">
            <div class="dag-node-icon" style="background:rgba(124,58,237,0.12);color:#7C3AED">K</div>
            <div class="dag-node-body">
              <div class="dag-node-title">知识库检索</div>
              <div class="dag-node-sub">RAG 语义召回</div>
            </div>
            <div class="dag-node-type">knowledge</div>
          </div>
          <div class="dag-node dag-tool">
            <div class="dag-node-icon" style="background:rgba(59,130,246,0.12);color:#3B82F6">L</div>
            <div class="dag-node-body">
              <div class="dag-node-title">LLM 推理</div>
              <div class="dag-node-sub">大模型分析根因</div>
            </div>
            <div class="dag-node-type">llm</div>
          </div>
          <div class="dag-node dag-cond">
            <div class="dag-node-icon" style="background:rgba(217,119,6,0.12);color:#D97706">?</div>
            <div class="dag-node-body">
              <div class="dag-node-title">条件分支</div>
              <div class="dag-node-sub">三路决策路由</div>
            </div>
            <div class="dag-node-type">condition</div>
          </div>
          <div class="dag-node dag-tool2">
            <div class="dag-node-icon" style="background:rgba(13,148,136,0.12);color:#0D9488">T</div>
            <div class="dag-node-body">
              <div class="dag-node-title">工具调用</div>
              <div class="dag-node-sub">执行修复动作</div>
            </div>
            <div class="dag-node-type">tool</div>
          </div>
          <div class="dag-node dag-end">
            <div class="dag-node-icon" style="background:rgba(107,114,128,0.12);color:#9CA3AF">E</div>
            <div class="dag-node-body">
              <div class="dag-node-title">结束节点</div>
              <div class="dag-node-sub">输出处理结果</div>
            </div>
            <div class="dag-node-type">end</div>
          </div>
        </div>
        <div class="orch-features">
          <div v-for="(f, i) in orchFeatures" :key="f.title" :ref="el => orchFeatRefs[i] = el" class="orch-feat rv" :class="`rv-${i}`">
            <div class="of-num" :style="{ background: f.numBg, color: f.numColor }">{{ i + 1 }}</div>
            <div>
              <h4>{{ f.title }}</h4>
              <p>{{ f.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── HOW IT WORKS ─── -->
    <section id="how" class="how-section" data-theme="59,130,246">
      <div class="section-container">
        <div ref="howHeader" class="section-header rv">
          <div class="section-eyebrow">// 工作原理</div>
          <h2>从一句话到一次修复</h2>
          <p>智能体收到自然语言后，4 步完成诊断与修复的真实路径。</p>
        </div>
        <div class="how-grid">
          <div class="how-steps">
            <div v-for="(step, i) in howSteps" :key="step.title" :ref="el => stepRefs[i] = el" class="how-step rv" :class="`rv-${i}`">
              <div class="how-step-num" :class="{ active: i === 0 }">{{ String(i + 1).padStart(2, '0') }}</div>
              <div class="how-step-body">
                <h4>{{ step.title }}</h4>
                <p>{{ step.desc }}</p>
              </div>
            </div>
          </div>
          <div ref="chatCard" class="chat-card rv">
            <div class="chat-hd">
              <span class="chat-dot" />
              自然语言 · 故障分析
            </div>
            <div class="chat-bd">
              <div class="msg user">> 查一下 order-center 最近的异常</div>
              <div class="msg ai">
                检测到 <strong class="hl">3 条 critical 告警</strong>，均指向 <span class="hl-dim">POD-ABC123</span>。<br>
                根因：<strong class="hl-red">OOMKILLED</strong> — 内存超限 98.2%
              </div>
              <div class="msg ai metric">
                memory_usage <span class="hl">98.2%</span> // pod_restarts <span class="hl">+12</span>
              </div>
              <div class="msg ai">
                匹配历史故障，建议重启恢复。<br>
                <span class="hl-em">>> 一键执行修复？</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── HIGHLIGHTS ─── -->
    <section id="highlights" class="highlights-section" data-theme="13,148,136">
      <div class="section-container">
        <div ref="hlHeader" class="section-header rv">
          <div class="section-eyebrow">// 核心亮点</div>
          <h2>每一个设计都为运维场景而生</h2>
        </div>
        <div class="hl-grid">
          <div v-for="(hl, i) in highlights" :key="hl.title" :ref="el => hlRefs[i] = el" class="hl-card rv" :class="`rv-${i}`">
            <div class="hl-icon" :style="{ background: hl.iconBg }">
              <component :is="hl.icon" :style="{ color: hl.iconColor }" />
            </div>
            <div class="hl-num">{{ String(i + 1).padStart(2, '0') }}</div>
            <h3>{{ hl.title }}</h3>
            <p>{{ hl.desc }}</p>
            <div class="hl-tags">
              <span v-for="tag in hl.tags" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── SECURITY ─── -->
    <section id="security" class="security-section" data-theme="79,70,229">
      <div class="section-container">
        <div ref="secHeader" class="section-header rv">
          <div class="section-eyebrow">// 安全与管控</div>
          <h2>AI 越能干，越要管得住</h2>
          <p>六道安全枷锁，让它只做该做的事。</p>
        </div>
        <div class="sec-grid">
          <div v-for="sec in securityItems" :key="sec.title" class="sec-card rv">
            <div class="sec-badge">{{ sec.code }}</div>
            <h3>{{ sec.title }}</h3>
            <p>{{ sec.desc }}</p>
          </div>
        </div>
        <div ref="compareBox" class="compare-box rv">
          <div class="compare-col left">
            <h3>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              传统运维
            </h3>
            <ul>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#7A8898" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>告警轰炸，一天 90+ 条，靠人肉筛选</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#7A8898" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>故障定位靠老员工经验，排查 45 分钟起步</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#7A8898" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>重启、扩容、清理全是手工，重复劳动</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#7A8898" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>知识装在老员工脑子里，离职即失传</li>
            </ul>
          </div>
          <div class="compare-col right">
            <h3>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              AIOps 智能运维体
            </h3>
            <ul>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0D9488" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>AI 收敛去噪，日均 <strong>9 条</strong>有效告警</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0D9488" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>AI 自动构建证据链，<strong>13 分钟</strong>定位根因</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0D9488" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>SOP 工作流自动执行，人工只确认高风险项</li>
              <li><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0D9488" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>知识库 + 图谱沉淀经验，新人也能像老兵</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- ─── CTA ─── -->
    <section class="cta-section">
        <div ref="ctaContent" class="cta-box rv">
        <div class="cta-glow" />
        <h2>现在，轮到你的运维进化</h2>
        <p>把判断力交给智能体——会思考、会决策、会执行，从今天开始。</p>
        <a href="/login" class="cta-btn">
          立即体验
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </a>
      </div>
    </section>

    <footer class="intro-footer">
      <div class="ft-brand">AI<span>Ops</span> · 智能运维体</div>
      <div class="ft-desc">让运维拥有判断力 · MCP 协议原生 · 大模型驱动 · 双工作流引擎</div>
    </footer>
    <div id="back-top" title="返回顶部" role="button" aria-label="返回顶部" @click="scrollTop">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, h, nextTick } from 'vue'

const heroEyebrow = ref(null)
const heroTitle = ref(null)
const heroDesc = ref(null)
const heroBtns = ref(null)
const heroStats = ref(null)
const heroVisual = ref(null)
const trustHeader = ref(null)
const capHeader = ref(null)
const orchSection = ref(null)
const orchHeader = ref(null)
const orchVisual = ref(null)
const howHeader = ref(null)
const chatCard = ref(null)
const hlHeader = ref(null)
const secHeader = ref(null)
const compareBox = ref(null)
const ctaContent = ref(null)

const capRefs = reactive([])
const orchFeatRefs = reactive([])
const stepRefs = reactive([])
const hlRefs = reactive([])

let animFrameId = null

/* ─── Icons ─── */
const mkIcon = (paths) => ({ render: () => h('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, paths) })
const IconClock = mkIcon([h('circle', { cx: 12, cy: 12, r: 10 }), h('path', { d: 'M12 6v6l4 2' })])
const IconBell = mkIcon([h('path', { d: 'M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9' }), h('path', { d: 'M13.73 21a2 2 0 01-3.46 0' })])
const IconCheck = mkIcon([h('polyline', { points: '20 6 9 17 4 12' })])
const IconServer = mkIcon([h('rect', { x: 2, y: 3, width: 20, height: 14, rx: 2 }), h('line', { x1: 8, y1: 21, x2: 16, y2: 21 }), h('line', { x1: 12, y1: 17, x2: 12, y2: 21 })])
const IconOps = mkIcon([h('circle', { cx: 12, cy: 12, r: 10 }), h('path', { d: 'M12 6v6l4 2' })])
const IconSRE = mkIcon([h('path', { d: 'M22 12h-4l-3 9L9 3l-3 9H2' })])
const IconDev = mkIcon([h('polyline', { points: '22 12 18 12 15 21 9 3 6 12 2 12' })])
const IconChaos = mkIcon([h('path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' })])
const IconObs = mkIcon([h('rect', { x: 2, y: 3, width: 20, height: 14, rx: 2 }), h('line', { x1: 8, y1: 21, x2: 16, y2: 21 }), h('line', { x1: 12, y1: 17, x2: 12, y2: 21 })])
const IconNL = mkIcon([h('path', { d: 'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z' })])
const IconDAG = mkIcon([h('circle', { cx: 5, cy: 12, r: 2 }), h('circle', { cx: 19, cy: 6, r: 2 }), h('circle', { cx: 19, cy: 18, r: 2 }), h('line', { x1: 7, y1: 12, x2: 17, y2: 6 }), h('line', { x1: 7, y1: 12, x2: 17, y2: 18 })])
const IconChart = mkIcon([h('line', { x1: 18, y1: 20, x2: 18, y2: 10 }), h('line', { x1: 12, y1: 20, x2: 12, y2: 4 }), h('line', { x1: 6, y1: 20, x2: 6, y2: 14 })])
const IconLink = mkIcon([h('path', { d: 'M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71' }), h('path', { d: 'M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71' })])
const IconShield = mkIcon([h('path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' })])

/* ─── Data ─── */
const trustStats = [
  { num: 13, suffix: 'min', label: '平均故障恢复 MTTR', desc: '从 45 分钟降到 13 分钟，AI 在告警到达前已定位根因。', color: '#4F46E5', iconBg: 'rgba(79,70,229,0.1)', icon: IconClock },
  { num: 9, suffix: '条', label: '日均有效告警', desc: '从日均 90+ 条收敛到 9 条，噪声削减 90%，不再告警疲劳。', color: '#0D9488', iconBg: 'rgba(13,148,136,0.1)', icon: IconBell },
  { num: 80, suffix: '%', label: '高频操作自动化', desc: '重启、扩容、清理、回滚——智能体自动执行，人工只确认高风险项。', color: '#D97706', iconBg: 'rgba(217,119,6,0.1)', icon: IconCheck },
  { num: 500, suffix: '+', label: '纳管资产规模', desc: '服务器、容器、中间件、数据库全栈统一纳管，一个平台看全。', color: '#7C3AED', iconBg: 'rgba(124,58,237,0.1)', icon: IconServer },
]

const capabilities = [
  { title: 'AIOps · 智能运维体', badge: '核心引擎', iconBg: 'rgba(79,70,229,0.1)', iconColor: '#4F46E5', desc: 'LLM Agent 通过 MCP 协议调用 13+ 运维工具，会查告警、会读日志、会问知识库、会下决策——真正能替你干活的智能体。', tags: ['LLM Agent', 'MCP 协议', '智能体编排', '根因分析', '异常检测'], icon: IconOps },
  { title: 'SRE · 可靠性工程', badge: '量化保障', iconBg: 'rgba(13,148,136,0.1)', iconColor: '#0D9488', desc: 'SLO 定义目标，错误预算丈量消耗，Burn Rate 预警烧钱速度——可靠性第一次可以被精确管理。', tags: ['SLO/SLA', '错误预算', 'Burn Rate', 'On-Call'], icon: IconSRE },
  { title: 'DevOps · 自愈执行', badge: '闭环修复', iconBg: 'rgba(217,119,6,0.1)', iconColor: '#D97706', desc: 'SOP 工作流引擎把运维剧本编排成 DAG，只读步骤自动跑，写操作人工确认——既敢自动，又守底线。', tags: ['SOP 工作流', '自愈规则', '蓝绿发布', '变更审批'], icon: IconDev },
  { title: '混沌工程 · 韧性验证', badge: '主动求败', iconBg: 'rgba(220,38,38,0.1)', iconColor: '#DC2626', desc: '主动注入 CPU、内存、网络、进程故障，在用户感知前暴露薄弱环节——稳定性是练出来的。', tags: ['故障注入', '实验场景', '韧性报告'], icon: IconChaos },
  { title: '可观测性 · 全栈感知', badge: '证据链闭环', iconBg: 'rgba(124,58,237,0.1)', iconColor: '#7C3AED', desc: '告警触发后，AI 自动关联指标异常、日志报错、链路断裂、拓扑变更、知识库案例，给出能服众的根因结论。', tags: ['可观测性', 'Kubernetes', 'CMDB', '知识图谱', '拓扑'], icon: IconObs },
]

const orchFeatures = [
  { title: '8 种异构节点，覆盖编排全场景', desc: 'start / end / llm / knowledge / tool / condition / code / http——不是简单调用 API，是真正把 AI 推理和运维动作焊进同一个 DAG。', numBg: 'rgba(79,70,229,0.1)', numColor: '#4F46E5' },
  { title: 'Vue Flow 可视化画布，所见即所得', desc: '拖拽加节点、连线建依赖、缩放看全貌、小地图定位、属性抽屉配置——不用写代码就能编排 AI 工作流。', numBg: 'rgba(124,58,237,0.1)', numColor: '#7C3AED' },
  { title: '变量传递 + 条件路由，工作流会思考', desc: 'runtime_context + Jinja2 模板让节点间数据流动；condition 节点求值后激活匹配分支。', numBg: 'rgba(59,130,246,0.1)', numColor: '#3B82F6' },
  { title: '5 个预置模板，开箱即用', desc: '智能告警根因分析、故障自愈决策、变更影响评估、巡检报告生成——不用从零编排。', numBg: 'rgba(13,148,136,0.1)', numColor: '#0D9488' },
]

const howSteps = [
  { title: '意图识别', desc: 'LLM 解析你的自然语言，路由到对应 MCP 工具——你不用记命令，说人话就行。' },
  { title: '多工具编排', desc: '智能体并行调用告警、指标、日志、资产，知识库 13+ 工具，把散落数据拼成完整证据链。' },
  { title: '知识检索 + 根因推理', desc: '匹配历史故障知识库找相似案例，LLM 综合证据给出根因结论，不是"可能是网络问题"。' },
  { title: '安全执行 + 全审计', desc: '高风险操作必须二次确认，所有执行动作落库审计——AI 敢做事，但不会乱做事。' },
]

const highlights = [
  { title: '自然语言交互', desc: '不再需要记忆命令。说一句人话，AI 帮你分析、定位、下决策。', tags: ['NLU', '意图识别', 'MCP 路由'], icon: IconNL, iconBg: 'rgba(79,70,229,0.1)', iconColor: '#4F46E5' },
  { title: 'SOP 工作流引擎', desc: '8 种节点类型拖拽编排，复杂运维剧本可视化沉淀，新人也能秒上手。', tags: ['Vue Flow', 'DAG', 'Jinja2'], icon: IconDAG, iconBg: 'rgba(13,148,136,0.1)', iconColor: '#0D9488' },
  { title: '错误预算量化', desc: 'SLO/Burn Rate 让可靠性管理从玄学变成数学，预警精确到小时级。', tags: ['SLO', '错误预算', 'Burn Rate'], icon: IconChart, iconBg: 'rgba(217,119,6,0.1)', iconColor: '#D97706' },
  { title: '全链路可观测', desc: '指标、日志、链路三合一，告警即证据，证据链自动生成，根因定位从 45 分钟缩短到 13 分钟。', tags: ['Metrics', 'Logs', 'Traces'], icon: IconLink, iconBg: 'rgba(124,58,237,0.1)', iconColor: '#7C3AED' },
]

const securityItems = [
  { code: '// RBAC', title: '权限控制', desc: '管理员 / 运维 / 只读三级行政权限，细粒度到每个工具调用。' },
  { code: '// CONFIRM', title: '动作确认', desc: '高风险写操作必须人工二次确认，AI 提议但不越权。' },
  { code: '// AUDIT', title: '审计日志', desc: '所有操作记录时间、操作者、结果，支持回放追溯。' },
  { code: '// API KEY', title: '令牌管理', desc: '只读 / 读写 / 管理员三级令牌，可即时吊销。' },
  { code: '// ALLOWLIST', title: '工具白名单', desc: '仅允许预置安全工具执行，禁用任意 shell 命令。' },
  { code: '// SILENCE', title: '告警静默', desc: '维护窗口自动静默，避免无效告警骚扰。' },
]

/* ─── Canvas Dynamic Background: Four-corner Tech Matrix ─── */
function initCanvasBg(canvas) {
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  let w = 0, h = 0
  const CORNERS = { tl:{x:0,y:0,w:0,h:0}, tr:{x:0,y:0,w:0,h:0}, bl:{x:0,y:0,w:0,h:0}, br:{x:0,y:0,w:0,h:0} }
  function computeCorners() {
    const MX = w*0.04, MYT = h*0.10, MYB = h*0.04, CW = w*0.26, CH = h*0.28
    CORNERS.tl = { x: MX, y: MYT, w: CW, h: CH }
    CORNERS.tr = { x: w-MX-CW, y: MYT, w: CW, h: CH }
    CORNERS.bl = { x: MX, y: h-MYB-CH, w: CW, h: CH }
    CORNERS.br = { x: w-MX-CW, y: h-MYB-CH, w: CW, h: CH }
  }

  let curR=199,curG=81,curB=46, tgtR=199,tgtG=81,tgtB=46
  const sections = Array.from(document.querySelectorAll('section[data-theme]'))
  function updateTheme() {
    const vh = window.innerHeight
    let active = sections[0]
    for (const s of sections) { if (s.getBoundingClientRect().top <= vh*0.5) active = s }
    const parts = (active.dataset.theme || '199,81,46').split(',').map(Number)
    tgtR=parts[0]; tgtG=parts[1]; tgtB=parts[2]
  }
  window.addEventListener('scroll', updateTheme, { passive: true })
  updateTheme()

  /* Earth */
  let earthR=0, earthCx=0, earthCy=0, earthRot=0
  const earthLand = []
  const clusters = [[1.6,1.0],[1.9,0.85],[0.5,1.15],[-1.7,0.8],[-1.2,1.4],[2.4,1.45],[0.7,1.3]]
  clusters.forEach(([t,p]) => {
    for (let i=0;i<8;i++) earthLand.push({ theta: t+(Math.random()-0.5)*0.4, phi: Math.max(0.2, Math.min(Math.PI-0.2, p+(Math.random()-0.5)*0.3)) })
  })
  const TILT = -0.32
  function setEarth() {
    const c = CORNERS.tl; earthR = Math.min(c.w,c.h)*0.42; earthCx = c.x+earthR-4; earthCy = c.y+earthR+6
  }
  function projEarth(x,y,z) {
    const cyA=Math.cos(earthRot),syA=Math.sin(earthRot), x1=x*cyA-z*syA, z1=x*syA+z*cyA
    const cxA=Math.cos(TILT),sxA=Math.sin(TILT), y1=y*cxA-z1*sxA, z2=y*sxA+z1*cxA
    return { x: earthCx+x1, y: earthCy+y1, z: z2 }
  }
  function sph(theta,phi,r) { return { x:r*Math.sin(phi)*Math.cos(theta), y:r*Math.cos(phi), z:r*Math.sin(phi)*Math.sin(theta) } }
  function drawEarth(r,g,b) {
    const Rc=earthR; ctx.lineWidth=1
    for (let phi=0.2; phi<Math.PI-0.05; phi+=Math.PI/10) {
      ctx.beginPath(); let started=false
      for (let theta=0; theta<=Math.PI*2+0.01; theta+=0.1) {
        const p=sph(theta,phi,Rc), pr=projEarth(p.x,p.y,p.z)
        if (pr.z>-Rc*0.4) { if(!started){ctx.moveTo(pr.x,pr.y);started=true} else ctx.lineTo(pr.x,pr.y) } else started=false
      }
      ctx.strokeStyle=`rgba(${r},${g},${b},0.16)`; ctx.stroke()
    }
    for (let theta=0; theta<Math.PI*2; theta+=Math.PI/10) {
      ctx.beginPath(); let started=false
      for (let phi=0; phi<=Math.PI+0.01; phi+=0.1) {
        const p=sph(theta,phi,Rc), pr=projEarth(p.x,p.y,p.z)
        if (pr.z>-Rc*0.4) { if(!started){ctx.moveTo(pr.x,pr.y);started=true} else ctx.lineTo(pr.x,pr.y) } else started=false
      }
      ctx.strokeStyle=`rgba(${r},${g},${b},0.14)`; ctx.stroke()
    }
    for (const lp of earthLand) {
      const p=sph(lp.theta,lp.phi,Rc), pr=projEarth(p.x,p.y,p.z)
      if (pr.z>0) {
        ctx.beginPath(); ctx.arc(pr.x,pr.y,1.3,0,Math.PI*2)
        ctx.fillStyle=`rgba(${r},${g},${b},${(pr.z/Rc)*0.7})`; ctx.fill()
      }
    }
  }

  /* Rain */
  const RAIN_POOL='0123456789abcdef{}[]()<>;=+-*/$#_|.&kubectlgetpoddscalerestartlogsdfpsgrepawkexit200404500503okfailexc{}();=>'
  const rainCols = []; let rainBox = null
  function initRain() {
    rainCols.length=0; const c=CORNERS.tr; rainBox=c
    const cols=Math.max(6,Math.floor(c.w/24))
    for (let i=0;i<cols;i++) rainCols.push({ x:c.x+i*24, y:c.y+Math.random()*c.h, speed:0.4+Math.random()*0.9, chars:[], len:8+Math.floor(Math.random()*8) })
    for (const col of rainCols) for (let j=0;j<col.len;j++) col.chars.push(RAIN_POOL[Math.floor(Math.random()*RAIN_POOL.length)])
  }
  function drawRain(r,g,b) {
    ctx.font='13px monospace'; const yMax=rainBox.y+rainBox.h
    for (const col of rainCols) {
      col.y+=col.speed
      if (col.y-col.len*16>yMax) { col.y=rainBox.y-col.len*16; for (let j=0;j<col.len;j++) col.chars[j]=RAIN_POOL[Math.floor(Math.random()*RAIN_POOL.length)] }
      for (let j=0;j<col.len;j++) {
        const cy=col.y-j*16
        if (cy<rainBox.y||cy>yMax) continue
        ctx.fillStyle=`rgba(${r},${g},${b},${(1-j/col.len)*0.26})`; ctx.fillText(col.chars[j],col.x,cy)
      }
    }
  }

  /* Topo */
  let topoNodes=[], topoLinks=[], topoBox=null
  function initTopo() {
    topoNodes.length=0; topoLinks.length=0; const c=CORNERS.bl; topoBox=c
    for (let i=0;i<14;i++) topoNodes.push({ x:c.x+Math.random()*c.w, y:c.y+Math.random()*c.h, vx:(Math.random()-0.5)*0.15, vy:(Math.random()-0.5)*0.15, size:1.5+Math.random()*1.5 })
    for (let i=0;i<topoNodes.length;i++) for (let j=i+1;j<topoNodes.length;j++) { const dx=topoNodes[i].x-topoNodes[j].x, dy=topoNodes[i].y-topoNodes[j].y; if (Math.hypot(dx,dy)<110) topoLinks.push({ a:i, b:j, flow:Math.random() }) }
  }
  function drawTopo(r,g,b) {
    const c=topoBox
    for (const n of topoNodes) { n.x+=n.vx; n.y+=n.vy; if (n.x<c.x||n.x>c.x+c.w) n.vx*=-1; if (n.y<c.y||n.y>c.y+c.h) n.vy*=-1 }
    for (const lk of topoLinks) {
      const a=topoNodes[lk.a], bb=topoNodes[lk.b]
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(bb.x,bb.y)
      ctx.strokeStyle=`rgba(${r},${g},${b},0.12)`; ctx.lineWidth=1; ctx.stroke()
      lk.flow+=0.008; if (lk.flow>1) lk.flow=0
      const fx=a.x+(bb.x-a.x)*lk.flow, fy=a.y+(bb.y-a.y)*lk.flow
      ctx.beginPath(); ctx.arc(fx,fy,1.8,0,Math.PI*2)
      ctx.fillStyle=`rgba(${r},${g},${b},0.5)`; ctx.shadowColor=`rgba(${r},${g},${b},0.4)`; ctx.shadowBlur=5; ctx.fill(); ctx.shadowBlur=0
    }
    for (const n of topoNodes) { ctx.beginPath(); ctx.arc(n.x,n.y,n.size,0,Math.PI*2); ctx.fillStyle=`rgba(${r},${g},${b},0.42)`; ctx.fill() }
  }

  /* Circuit */
  let circuitPaths=[]
  function initCircuit() {
    circuitPaths.length=0; const c=CORNERS.br, ox=c.x, oy=c.y, ow=c.w, oh=c.h
    for (let i=0;i<10;i++) {
      const startX=ox+Math.random()*ow, startY=oy+Math.random()*oh, pts=[{x:startX,y:startY}]; let cx=startX, cy=startY
      for (let s=0;s<4+Math.floor(Math.random()*4);s++) { if (Math.random()<0.5) cx+=(Math.random()-0.5)*60; else cy+=(Math.random()-0.5)*60; cx=Math.max(ox,Math.min(ox+ow,cx)); cy=Math.max(oy,Math.min(oy+oh,cy)); pts.push({x:cx,y:cy}) }
      circuitPaths.push({pts,flow:Math.random()})
    }
  }
  function drawCircuit(r,g,b) {
    for (const cp of circuitPaths) {
      ctx.beginPath(); cp.pts.forEach((p,i)=>{if(i===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y)})
      ctx.strokeStyle=`rgba(${r},${g},${b},0.13)`; ctx.lineWidth=1; ctx.stroke()
      for (const p of cp.pts) { ctx.beginPath(); ctx.arc(p.x,p.y,1.5,0,Math.PI*2); ctx.fillStyle=`rgba(${r},${g},${b},0.25)`; ctx.fill() }
      cp.flow+=0.006; if (cp.flow>1) cp.flow=0
      const totalLen=cp.pts.reduce((s,p,i)=>i===0?0:s+Math.hypot(p.x-cp.pts[i-1].x,p.y-cp.pts[i-1].y),0)
      let target=cp.flow*totalLen, acc=0
      for (let i=1;i<cp.pts.length;i++) {
        const seg=Math.hypot(cp.pts[i].x-cp.pts[i-1].x,cp.pts[i].y-cp.pts[i-1].y)
        if (acc+seg>=target) {
          const t=(target-acc)/seg
          ctx.beginPath(); ctx.arc(cp.pts[i-1].x+(cp.pts[i].x-cp.pts[i-1].x)*t,cp.pts[i-1].y+(cp.pts[i].y-cp.pts[i-1].y)*t,2,0,Math.PI*2)
          ctx.fillStyle=`rgba(${r},${g},${b},0.6)`; ctx.shadowColor=`rgba(${r},${g},${b},0.5)`; ctx.shadowBlur=6; ctx.fill(); ctx.shadowBlur=0
          break
        }
        acc+=seg
      }
    }
  }

  function initAll() { setEarth(); initRain(); initTopo(); initCircuit() }
  function lerp(a,b,t){ return a+(b-a)*t }

  function resize() {
    w=window.innerWidth; h=window.innerHeight
    canvas.width=w*dpr; canvas.height=h*dpr
    canvas.style.width=w+'px'; canvas.style.height=h+'px'
    ctx.setTransform(dpr,0,0,dpr,0,0)
    ctx.fillStyle='#EEF2F7'
    ctx.fillRect(0,0,w,h)
    computeCorners(); initAll()
  }

  function draw() {
    curR=lerp(curR,tgtR,0.05); curG=lerp(curG,tgtG,0.05); curB=lerp(curB,tgtB,0.05)
    document.documentElement.style.setProperty('--theme-r',Math.round(curR))
    document.documentElement.style.setProperty('--theme-g',Math.round(curG))
    document.documentElement.style.setProperty('--theme-b',Math.round(curB))
    const r=Math.round(curR),g=Math.round(curG),b=Math.round(curB)
    ctx.fillStyle='rgba(238,242,247,0.20)'
    ctx.fillRect(0,0,w,h)
    earthRot+=0.0012
    drawEarth(r,g,b); drawRain(r,g,b); drawTopo(r,g,b); drawCircuit(r,g,b)
    animFrameId = requestAnimationFrame(draw)
  }
  resize()
  window.addEventListener('resize',resize)
  draw()
  return () => { window.removeEventListener('resize',resize); window.removeEventListener('scroll',updateTheme) }
}

/* ─── Scroll Reveal ─── */
function initScrollReveal() {
  const els = document.querySelectorAll('.rv')
  const ob = new IntersectionObserver((entries) => {
    entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('in') })
  }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' })
  els.forEach(el => ob.observe(el))
  return ob
}

/* ─── Counter Animation ─── */
function animateCounter(el, target, suffix = '') {
  if (!el) return
  let current = 0
  const step = Math.max(1, Math.floor(target / 40))
  const timer = setInterval(() => {
    current += step
    if (current >= target) { current = target; clearInterval(timer) }
    el.textContent = current + suffix
  }, 30)
}

const scrollTop = () => window.scrollTo({ top: 0, behavior: 'smooth' })

onMounted(() => {
  nextTick(() => {
    const cleanup = initCanvasBg(document.getElementById('bg-canvas'))
    initScrollReveal()

    /* Hero stat counters */
    setTimeout(() => {
      heroStats.value?.querySelectorAll('.hstat-num').forEach(el => {
        animateCounter(el, parseInt(el.dataset.target))
      })
    }, 1200)

    /* Trust counters */
    const trustObs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        document.querySelectorAll('.trust-num').forEach(el => {
          animateCounter(el, parseInt(el.dataset.target), el.dataset.suffix || '')
        })
        trustObs.disconnect()
      }
    }, { threshold: 0.15 })
    if (trustHeader.value) trustObs.observe(trustHeader.value)

    /* DAG nodes reveal */
    const dagObs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        entry.target.querySelectorAll('.dag-node').forEach((node, i) => {
          setTimeout(() => {
            node.style.transition = 'opacity 0.5s ease, transform 0.5s ease'
            node.style.opacity = '1'
            node.style.transform = 'scale(1)'
          }, i * 100)
        })
        dagObs.disconnect()
      }
    }, { threshold: 0.15 })
    if (orchVisual.value) dagObs.observe(orchVisual.value)

    /* Back to top */
    const btBtn = document.getElementById('back-top')
    const onScroll = () => {
      if (!btBtn) return
      if (window.scrollY > 320) btBtn.classList.add('show'); else btBtn.classList.remove('show')
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    window.__btCleanup = onScroll
  })
})

onBeforeUnmount(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  if (window.__btCleanup) window.removeEventListener('scroll', window.__btCleanup)
})
</script>

<style>
:root {
  --theme-r: 199; --theme-g: 81; --theme-b: 46;
}
.intro-page {
  --bg:        #EEF2F7;
  --bg2:       #E2E9F1;
  --surface:   #F4F7FB;
  --surface2:  #E8EEF5;
  --surface3:  #DCE4ED;
  --fg:        #1A2333;
  --fg2:       #4A5868;
  --fg3:       #7A8898;
  --border:    #D0DAE5;
  --theme:     rgb(var(--theme-r), var(--theme-g), var(--theme-b));
  --theme-bg:  rgba(var(--theme-r), var(--theme-g), var(--theme-b), 0.10);
  --radius:    16px;
  --radius-sm: 8px;
  --shadow-soft: 0 8px 30px rgba(26,35,51,0.08);
  --shadow-card: 0 12px 40px rgba(26,35,51,0.10);
  min-height: 100vh;
  background: var(--bg);
  color: var(--fg);
  font-family: 'Plus Jakarta Sans', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow-x: hidden;
}
html { scroll-snap-type: y mandatory; scroll-behavior: smooth; }

/* ─── NAV ─── */
#bg-canvas { position: fixed; inset: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }
.bg-vignette { position: fixed; inset: 0; z-index: 0; pointer-events: none; background: radial-gradient(ellipse 100% 80% at 50% 50%, transparent 40%, rgba(238,242,247,0.6) 100%); }
.bg-grain { position: fixed; inset: 0; z-index: 2; pointer-events: none; opacity: 0.045; mix-blend-mode: multiply; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"); }

.intro-nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  height: 64px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 48px;
  background: rgba(238,242,247,0.78); backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border);
}
.nav-logo { display: flex; align-items: baseline; gap: 2px; text-decoration: none; }
.logo-mark { font-size: 22px; font-weight: 800; color: var(--theme); letter-spacing: -0.03em; }
.logo-type { font-size: 22px; font-weight: 400; color: var(--fg2); letter-spacing: -0.03em; }
.nav-links { display: flex; align-items: center; gap: 24px; }
.nav-links a { font-size: 13px; font-weight: 700; color: var(--fg); text-decoration: none; transition: color 0.2s; }
.nav-links a:hover { color: var(--theme); }
.nav-cta { padding: 9px 22px !important; background: var(--theme-bg) !important; color: var(--theme) !important; border-radius: var(--radius-sm) !important; font-weight: 800 !important; border: 1px solid rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.22); box-shadow: 0 2px 8px rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.18); transition: all 0.2s !important; }
.nav-cta:hover { background: rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.18) !important; box-shadow: 0 4px 14px rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.30) !important; transform: translateY(-1px) !important; }

/* ─── SECTIONS ─── */
section { position: relative; z-index: 1; min-height: 100dvh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 72px 48px 48px; scroll-snap-align: start; }
.section-container { max-width: 1140px; width: 100%; margin: 0 auto; }
.section-header { margin-bottom: 44px; }
.section-eyebrow { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: var(--theme); letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 12px; }
.section-header h2 { font-size: clamp(28px, 3vw, 42px); font-weight: 800; letter-spacing: -0.025em; line-height: 1.15; color: var(--fg); margin-bottom: 12px; }
.section-header p { font-size: 16px; color: var(--fg2); line-height: 1.7; max-width: 560px; }

/* ─── HERO ─── */
.hero-section { flex-direction: row; gap: 80px; padding-top: 100px; overflow: hidden; min-height: 100dvh; }
.hero-mesh { position: absolute; inset: 0; z-index: 0; pointer-events: none; }
.hero-content { position: relative; z-index: 1; flex: 1; max-width: 580px; }
.hero-eyebrow { display: inline-flex; align-items: center; gap: 10px; padding: 6px 14px; background: var(--theme-bg); border: 1px solid rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.22); border-radius: 9999px; font-size: 12px; font-weight: 700; color: var(--theme); margin-bottom: 24px; }
.eyebrow-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--theme); box-shadow: 0 0 8px var(--theme); animation: pulse-dot 2s infinite; }
@keyframes pulse-dot { 0%,100%{opacity:1;} 50%{opacity:0.4;} }
.hero-content h1 { display: flex; flex-direction: column; font-size: clamp(36px,4.2vw,52px); font-weight: 700; letter-spacing: -0.025em; line-height: 1.15; margin-bottom: 24px; }
.title-line { color: var(--fg); }
.title-line.accent { color: var(--theme); }
.hero-content > p { font-size: 16px; color: var(--fg2); line-height: 1.75; margin-bottom: 36px; max-width: 460px; }
.hero-btns { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 36px; }
.hero-btns a { padding: 13px 30px; font-size: 14px; font-weight: 900; letter-spacing: 0.05em; border-radius: var(--radius-sm); transition: all 0.2s; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
.btn-primary { background: #2E6FF2; color: #fff; border: 2px solid #fff; box-shadow: 0 8px 28px rgba(46,111,242,0.70), 0 0 0 1px rgba(30,64,175,0.40), 0 0 48px rgba(46,111,242,0.45); }
.btn-primary:hover { background: #1E5FE0; box-shadow: 0 10px 36px rgba(46,111,242,0.90), 0 0 0 1px rgba(30,64,175,0.60), 0 0 64px rgba(46,111,242,0.65); transform: translateY(-1px); }
.btn-primary:active { transform: scale(0.97); }
.btn-ghost { background: transparent; color: var(--fg2); border: 1px solid var(--border); }
.btn-ghost:hover { border-color: var(--fg2); color: var(--fg); background: var(--surface2); }
.hero-stats { display: flex; align-items: center; gap: 24px; }
.hstat { display: flex; flex-direction: column; }
.hstat-num { font-size: 28px; font-weight: 800; color: var(--fg); letter-spacing: -0.03em; line-height: 1; font-variant-numeric: tabular-nums; }
.hstat-unit { font-size: 14px; font-weight: 600; color: var(--theme); margin-top: 2px; }
.hstat-label { font-size: 11px; color: var(--fg3); margin-top: 4px; font-weight: 500; }
.hstat-div { width: 1px; height: 36px; background: var(--border); }

/* ─── HERO VISUAL ─── */
.hero-visual { position: relative; z-index: 1; flex: 0 0 420px; }
.glass-card { background: var(--surface2); padding: 8px; border-radius: calc(var(--radius) + 8px); border: 1px solid var(--border); box-shadow: var(--shadow-card); }
.glass-card-inner { background: var(--surface); border-radius: var(--radius); overflow: hidden; }
.glass-card-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.gc-title { font-size: 12px; font-weight: 500; color: var(--fg2); }
.gc-badge { display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 700; color: var(--teal, #0D9488); background: rgba(13,148,136,0.10); padding: 3px 10px; border-radius: 9999px; }
.gc-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--teal, #0D9488); box-shadow: 0 0 6px var(--teal, #0D9488); animation: pulse-dot 2s infinite; }
.glass-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; padding: 28px 20px; }
.gc-metric { text-align: center; }
.gc-metric + .gc-metric { border-left: 1px solid var(--border); }
.gc-num { font-size: 36px; font-weight: 700; letter-spacing: -0.02em; color: var(--fg); line-height: 1; }
.gc-num.warn { color: var(--theme); }
.gc-label { font-size: 11px; color: var(--fg3); margin-top: 6px; font-weight: 500; }
.gc-bar { height: 3px; background: var(--border); border-radius: 2px; margin-top: 8px; overflow: hidden; }
.gc-bar-fill { height: 100%; border-radius: 2px; transition: width 1s ease; }
.glass-chart { padding: 0 20px 16px; }
.glass-chart svg { width: 100%; height: 60px; }
.gc-chart-label { font-size: 10px; color: var(--fg3); margin-top: 6px; text-align: center; }
.glass-footer { padding: 14px 20px; border-top: 1px solid var(--border); background: var(--surface2); font-size: 12px; color: var(--fg2); display: flex; align-items: center; gap: 8px; }
.glass-footer svg { color: var(--teal, #0D9488); }
.float-card { position: absolute; display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-soft); animation: float 4s ease-in-out infinite; }
.float-card-1 { top: -20px; right: -30px; animation-delay: 0s; }
.float-card-2 { bottom: 40px; left: -40px; animation-delay: 2s; }
@keyframes float { 0%,100%{transform:translateY(0);} 50%{transform:translateY(-8px);} }
.fc-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.fc-title { font-size: 13px; font-weight: 700; color: var(--fg); }
.fc-sub { font-size: 11px; color: var(--fg3); margin-top: 2px; }

/* ─── TRUST ─── */
.trust-section { background: transparent; }
.trust-header { text-align: center; margin-bottom: 44px; }
.trust-header h2 { margin: 0 auto; font-size: clamp(26px,2.8vw,34px); font-weight: 700; letter-spacing: -0.02em; color: var(--fg); margin-bottom: 12px; }
.trust-header p { font-size: 15px; color: var(--fg2); max-width: 540px; margin: 0 auto; }
.trust-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; }
.trust-card { padding: 36px 24px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); text-align: left; transition: all 0.25s; display: flex; flex-direction: column; gap: 6px; }
.trust-card:hover { border-color: var(--theme); transform: translateY(-2px); box-shadow: 0 8px 30px rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.12); }
.trust-icon-wrap { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 12px; }
.trust-num-wrap { display: flex; align-items: baseline; gap: 2px; }
.trust-num { font-size: clamp(36px,4vw,48px); font-weight: 700; letter-spacing: -0.03em; line-height: 1; color: var(--fg); }
.trust-suffix { font-size: 18px; font-weight: 700; color: var(--theme); }
.trust-label { font-size: 13px; font-weight: 600; color: var(--fg); margin-top: 8px; }
.trust-desc { font-size: 12px; color: var(--fg2); line-height: 1.6; }

/* ─── CAPABILITIES ─── */
.cap-section { background: transparent; }
.cap-bento { display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: auto auto; gap: 14px; }
.cap-card { padding: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); transition: all 0.25s; position: relative; overflow: hidden; }
.cap-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), transparent); opacity: 0; transition: opacity 0.25s; }
.cap-card:hover { border-color: var(--fg3); background: var(--surface2); transform: translateY(-2px); box-shadow: var(--shadow-soft); }
.cap-card:hover::before { opacity: 1; }
.cap-card:nth-child(1) { --accent: #4F46E5; }
.cap-card:nth-child(2) { --accent: #0D9488; }
.cap-card:nth-child(3) { --accent: #D97706; }
.cap-card:nth-child(4) { --accent: #DC2626; }
.cap-card:nth-child(5) { --accent: #7C3AED; grid-column: 1 / -1; }
.cap-icon { width: 42px; height: 42px; border-radius: 11px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.cap-badge-tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 3px 10px; background: var(--surface2); border: 1px solid var(--border); border-radius: 9999px; color: var(--fg2); margin-bottom: 10px; }
.cap-card h3 { font-size: 16px; font-weight: 700; color: var(--fg); margin-bottom: 8px; }
.cap-card > p { font-size: 13px; color: var(--fg2); line-height: 1.6; margin-bottom: 12px; }
.cap-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.cap-tags span { font-size: 11px; font-weight: 500; padding: 4px 10px; background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; color: var(--fg2); }

/* ─── ORCHESTRATION ─── */
.orch-section { background: transparent; flex-direction: column; }
.orch-container { display: flex; flex-direction: column; gap: 40px; }
.orch-header { text-align: center; }
.orch-header p { margin: 0 auto; }
.orch-header .section-eyebrow { color: var(--theme); }
.orch-visual { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 32px; min-height: 360px; box-shadow: var(--shadow-card); }
.orch-visual::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--theme), transparent); }
.dag-svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.dag-edge { opacity: 0.6; }
.dag-particle { opacity: 0.8; }
.dag-node { position: absolute; display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow-soft); min-width: 160px; transition: all 0.2s; opacity: 0; transform: scale(0.8); }
.dag-node:hover { border-color: var(--theme); box-shadow: var(--shadow-card); transform: scale(1.03); }
.dag-start { top: 50%; left: 4%; transform: translateY(-50%); }
.dag-llm { top: 8%; left: 30%; }
.dag-tool { bottom: 8%; left: 30%; }
.dag-cond { top: 50%; left: 52%; transform: translateY(-50%); }
.dag-tool2 { top: 8%; right: 8%; }
.dag-end { bottom: 8%; right: 8%; }
.dag-node-icon { width: 30px; height: 30px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; }
.dag-node-title { font-size: 13px; font-weight: 600; color: var(--fg); }
.dag-node-sub { font-size: 11px; color: var(--fg3); margin-top: 2px; }
.dag-node-type { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: var(--fg3); background: var(--surface2); padding: 2px 6px; border-radius: 4px; }
.orch-features { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; }
.orch-feat { display: flex; gap: 16px; align-items: flex-start; padding: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
.of-num { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; flex-shrink: 0; background: var(--theme-bg); color: var(--theme); border: 1px solid rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.22); }
.orch-feat h4 { font-size: 15px; font-weight: 600; color: var(--fg); margin-bottom: 4px; }
.orch-feat p { font-size: 13px; color: var(--fg2); line-height: 1.6; }

/* ─── HOW IT WORKS ─── */
.how-section { background: transparent; }
.how-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 56px; align-items: start; }
.how-steps { display: flex; flex-direction: column; gap: 12px; }
.how-step { display: flex; gap: 16px; padding: 16px 18px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-soft); transition: all 0.25s; }
.how-step:hover { border-color: var(--theme); transform: translateX(4px); box-shadow: 0 8px 24px rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.10); }
.how-step-num { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; background: var(--surface2); border: 1px solid var(--border); font-size: 13px; font-weight: 700; color: var(--fg2); font-family: 'JetBrains Mono', monospace; }
.how-step-num.active { background: var(--theme-bg); border-color: var(--theme); color: var(--theme); }
.how-step-body h4 { font-size: 15px; font-weight: 600; color: var(--fg); margin-bottom: 4px; }
.how-step-body p { font-size: 13px; color: var(--fg2); line-height: 1.6; }
.chat-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow-card); }
.chat-hd { padding: 14px 20px; border-bottom: 1px solid var(--border); font-size: 12px; font-weight: 500; color: var(--fg2); display: flex; align-items: center; gap: 8px; background: var(--surface2); }
.chat-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--teal, #0D9488); box-shadow: 0 0 8px var(--teal, #0D9488); animation: pulse-dot 2s infinite; }
.chat-bd { padding: 20px; }
.msg { padding: 14px 18px; margin-bottom: 10px; font-size: 13px; line-height: 1.7; border-radius: var(--radius-sm); }
.msg.user { background: var(--surface2); color: var(--fg2); border: 1px solid var(--border); margin-left: 28px; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.msg.ai { background: var(--theme-bg); color: var(--fg); margin-right: 28px; border: 1px solid rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.18); }
.msg.ai.metric { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.hl { color: var(--theme); font-weight: 600; }
.hl-dim { color: var(--fg3); }
.hl-red { color: #DC2626; font-weight: 700; }
.hl-em { color: var(--teal, #0D9488); font-weight: 600; }

/* ─── HIGHLIGHTS ─── */
.highlights-section { background: transparent; }
.hl-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; }
.hl-card { padding: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); transition: all 0.25s; position: relative; overflow: hidden; }
.hl-card:hover { border-color: var(--theme); background: var(--surface2); transform: translateY(-2px); box-shadow: var(--shadow-soft); }
.hl-icon { width: 42px; height: 42px; border-radius: 11px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.hl-num { font-size: 11px; font-weight: 700; color: var(--theme); letter-spacing: 0.1em; margin-bottom: 8px; font-family: 'JetBrains Mono', monospace; }
.hl-card h3 { font-size: 16px; font-weight: 700; color: var(--fg); margin-bottom: 8px; }
.hl-card > p { font-size: 13px; color: var(--fg2); line-height: 1.6; margin-bottom: 14px; }
.hl-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.hl-tags span { font-size: 11px; font-weight: 500; padding: 4px 10px; background: var(--theme-bg); border-radius: 6px; color: var(--theme); }

/* ─── SECURITY ─── */
.security-section { background: transparent; }
.sec-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin-bottom: 20px; }
.sec-card { padding: 16px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); transition: all 0.25s; }
.sec-card:hover { border-color: var(--fg3); background: var(--surface2); }
.sec-badge { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 600; padding: 3px 8px; background: var(--theme-bg); color: var(--theme); border-radius: 5px; margin-bottom: 6px; border: 1px solid rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.18); }
.sec-card h3 { font-size: 14px; font-weight: 600; color: var(--fg); margin-bottom: 3px; }
.sec-card p { font-size: 12px; color: var(--fg2); line-height: 1.45; }
.compare-box { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.compare-col { padding: 18px 16px; border-radius: var(--radius-sm); border: 1px solid var(--border); }
.compare-col.left { background: var(--surface); }
.compare-col.right { background: linear-gradient(135deg, var(--theme-bg) 0%, var(--surface) 100%); border-color: rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.22); }
.compare-col h3 { font-size: 14px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.compare-col.left h3 { color: var(--fg2); }
.compare-col.right h3 { color: var(--theme); }
.compare-col ul { list-style: none; }
.compare-col li { font-size: 12px; color: var(--fg2); padding: 5px 0; border-bottom: 1px solid var(--border); display: flex; align-items: flex-start; gap: 8px; }
.compare-col li:last-child { border: none; }
.compare-col.right li { color: var(--fg); }

/* ─── CTA ─── */
.cta-section { min-height: 60dvh; }
.cta-box { text-align: center; padding: 48px 32px; background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%); border: 1px solid var(--border); border-radius: var(--radius); position: relative; overflow: hidden; max-width: 760px; margin: 0 auto; width: 100%; }
.cta-box::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--theme), transparent); }
.cta-glow { position: absolute; top: -60%; left: 50%; transform: translateX(-50%); width: 400px; height: 400px; background: radial-gradient(circle, rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.08) 0%, transparent 70%); pointer-events: none; }
.cta-box h2 { font-size: clamp(24px,2.6vw,30px); font-weight: 700; color: var(--fg); margin-bottom: 12px; }
.cta-box > p { font-size: 15px; color: var(--fg2); margin-bottom: 32px; }
.cta-btn { display: inline-flex; align-items: center; gap: 10px; padding: 15px 42px; background: #2E6FF2; color: #fff; border: 2px solid #fff; font-size: 15px; font-weight: 900; letter-spacing: 0.05em; border-radius: var(--radius-sm); box-shadow: 0 10px 36px rgba(46,111,242,0.75), 0 0 0 1px rgba(30,64,175,0.40), 0 0 56px rgba(46,111,242,0.50); text-decoration: none; transition: all 0.2s; }
.cta-btn:hover { background: #1E5FE0; box-shadow: 0 12px 44px rgba(46,111,242,0.95), 0 0 0 1px rgba(30,64,175,0.60), 0 0 72px rgba(46,111,242,0.70); transform: translateY(-1px); }
.cta-btn:active { transform: scale(0.97); }
.cta-btn svg { transition: transform 0.2s; }
.cta-btn:hover svg { transform: translateX(4px); }

/* ─── FOOTER ─── */
.intro-footer { position: relative; z-index: 1; text-align: center; padding: 40px 48px; border-top: 1px solid var(--border); background: var(--bg2); scroll-snap-align: start; }
.ft-brand { font-size: 12px; font-weight: 600; color: var(--fg2); margin-bottom: 4px; }
.ft-brand span { color: var(--theme); }
.ft-desc { font-size: 12px; color: var(--fg3); }

/* ─── SCROLL REVEAL ─── */
.rv { opacity: 0; transform: translateY(24px); transition: opacity 0.7s cubic-bezier(0.16,1,0.3,1), transform 0.7s cubic-bezier(0.16,1,0.3,1); }
.rv.in { opacity: 1; transform: translateY(0); }
.rv-1 { transition-delay: 0.1s; }
.rv-2 { transition-delay: 0.2s; }
.rv-3 { transition-delay: 0.3s; }
.rv-4 { transition-delay: 0.4s; }

/* ─── BACK TO TOP ─── */
#back-top { position: fixed; right: 28px; bottom: 28px; z-index: 200; width: 44px; height: 44px; border-radius: 50%; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 6px 20px rgba(26,35,51,0.18); display: flex; align-items: center; justify-content: center; cursor: pointer; opacity: 0; visibility: hidden; transform: translateY(12px); transition: opacity 0.3s, visibility 0.3s, transform 0.3s, background 0.2s, border-color 0.2s; color: var(--fg2); }
#back-top.show { opacity: 1; visibility: visible; transform: translateY(0); }
#back-top:hover { background: var(--theme); border-color: var(--theme); color: #fff; box-shadow: 0 8px 28px rgba(var(--theme-r),var(--theme-g),var(--theme-b),0.45); }

/* ─── RESPONSIVE ─── */
@media (max-width: 1100px) {
  .orch-visual { min-height: 480px; }
  .dag-start { top: 5%; left: 50%; transform: translateX(-50%); }
  .dag-llm { top: 5%; left: 5%; }
  .dag-tool { bottom: 5%; left: 5%; }
  .dag-cond { top: 50%; left: 50%; transform: translate(-50%, -50%); }
  .dag-tool2 { top: 5%; right: 5%; }
  .dag-end { bottom: 5%; right: 5%; }
}
@media (max-width: 1024px) {
  .trust-grid { grid-template-columns: repeat(2,1fr); }
  .cap-bento { grid-template-columns: repeat(2,1fr); }
  .orch-features { grid-template-columns: 1fr; }
  .sec-grid { grid-template-columns: repeat(2,1fr); }
}
@media (max-width: 900px) {
  .hero-section { flex-direction: column; padding-top: 80px; gap: 48px; }
  .hero-visual { flex: none; width: 100%; }
  .how-grid { grid-template-columns: 1fr; }
  .hl-grid { grid-template-columns: 1fr; }
  .compare-box { grid-template-columns: 1fr; }
  .intro-nav { padding: 0 24px; }
  section { padding: 60px 24px 40px; }
}
@media (max-width: 640px) {
  .trust-grid { grid-template-columns: 1fr; }
  .cap-bento { grid-template-columns: 1fr; }
  .cap-card:nth-child(5) { grid-column: auto; }
  .sec-grid { grid-template-columns: 1fr; }
  .hero-stats { flex-wrap: wrap; gap: 16px; }
  .hstat-div { display: none; }
  .intro-nav .nav-links a:not(.nav-cta) { display: none; }
}
</style>
