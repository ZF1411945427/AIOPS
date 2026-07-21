<template>
  <div class="guide-page">
    <div class="guide-header">
      <h1>用户操作指南</h1>
      <p class="guide-subtitle">AIOps 智能运维平台 · 24条核心链路 · 从入门到精通</p>
    </div>

    <div class="guide-grid">
      <div v-for="group in guideGroups" :key="group.id" class="guide-group" :id="group.id">
        <div class="group-header">
          <span class="group-num">{{ group.num }}</span>
          <h2 class="group-title">{{ group.title }}</h2>
        </div>

        <div class="group-steps">
          <h3 class="steps-title">操作步骤</h3>
          <div v-for="(step, idx) in group.steps" :key="idx" class="step-item">
            <div class="step-num">{{ idx + 1 }}</div>
            <div class="step-content">
              <div class="step-path">
                <span class="path-label">操作入口</span>
                <span class="path-value">{{ step.path }}</span>
              </div>
              <div class="step-action">{{ step.action }}</div>
              <div class="step-expect">预期结果：{{ step.expect }}</div>
            </div>
          </div>
        </div>

        <div class="group-links">
          <h3 class="links-title">快速入口</h3>
          <div class="links-row">
            <a v-for="link in group.links" :key="link.href" :href="link.href" class="guide-link" target="_blank">
              <span class="link-icon">{{ link.icon }}</span>
              <span class="link-text">{{ link.label }}</span>
            </a>
          </div>
        </div>

        <div class="group-flow">
          <h3 class="flow-title">流程总览</h3>
          <div class="flow-tags">
            <span v-for="(tag, idx) in group.flowTags" :key="tag" class="flow-tag">
              {{ tag }} <span v-if="idx < group.flowTags.length - 1" class="flow-arrow">→</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="guide-footer">
      <p>有问题或者需求，请联系：<span class="contact-phone">400-XXX-XXXX</span></p>
    </div>
  </div>
</template>

<script setup>
const guideGroups = [
  {
    id: 'chain-1',
    num: '链路1',
    title: '核心数据流（完整闭环）',
    flowTags: ['资产发现', '指标采集', '可观测性', '异常检测', '告警', '故障单', '审批', '知识沉淀', 'AI检索', '自愈'],
    steps: [
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产自动发现', action: '点击「新建发现任务」，填写任务名称、发现协议(SSH)、目标范围(192.168.1.1-10)、探测端口(22)、选择认证凭据，点击「立即执行」', expect: '扫描完成后在资产列表看到新发现的服务器，状态为「在线」' },
      { path: '侧边栏 → 运维工作台 → 可观测性 → 指标监控（后台自动）', action: '无需操作，等待3-5分钟让系统自动采集指标数据', expect: '在指标监控页面看到各资产的CPU、内存、磁盘、网络等20+指标的趋势图' },
      { path: '侧边栏 → 智能分析室 → 异常检测 → 异常检测配置', action: '点击「新建规则」，选择指标名称(cpu_usage)、选择资产、算法推荐自动选择，点击保存后启用', expect: '规则状态变为「已启用」，系统开始按算法检测异常' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警列表（后台自动）', action: '无需操作，当检测到异常时自动生成告警', expect: '告警列表出现新告警，显示红色/橙色严重级别徽章' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警详情', action: '点击某条告警的「确认」按钮，确认收到该告警', expect: '告警状态从「待处理」变为「已确认」' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理', action: '点击「新建故障单」，填写标题、严重级别、影响范围、描述，点击提交', expect: '故障列表显示新故障单，状态为「待处理」' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情', action: '故障处理完成后，点击「提交审批」，填写审批备注，确认提交', expect: '故障状态从「待处理」变为「待审批」' },
      { path: '侧边栏 → 知识库 → AI知识草稿（后台自动）', action: '无需操作，故障审批通过后5分钟内自动生成知识草稿', expect: 'AI知识草稿页面出现新草稿，状态为「待审批」' },
      { path: '侧边栏 → 知识库 → AI知识草稿', action: '点击某条草稿的「审批」，查看完整知识内容，点击「通过」', expect: '草稿变为「已通过」，知识库列表出现新入库条目' },
      { path: '侧边栏 → AI运维智能体 → AI智能助手', action: '在聊天框输入「CPU使用率过高怎么处理？」，发送问题', expect: 'AI根据知识库内容生成回答，并在回答中引用知识来源' }
    ],
    links: [
      { icon: '🖥️', label: '资产发现', href: '/assets/discovery' },
      { icon: '📊', label: '指标监控', href: '/observability/metrics' },
      { icon: '🔔', label: '告警列表', href: '/alerts' },
      { icon: '📝', label: '故障管理', href: '/incidents' },
      { icon: '🤖', label: 'AI助手', href: '/ai/chat' },
    ]
  },
  {
    id: 'chain-2',
    num: '链路2',
    title: 'K8s指标接入',
    flowTags: ['配置集群', '资源查询', 'HPA推荐', '资源优化'],
    steps: [
      { path: '侧边栏 → 运维工作台 → K8s资源 → K8s集群管理', action: '点击「添加集群」，填写集群名称、API Server地址、认证方式(Token)、Token、命名空间，点击保存', expect: '集群列表显示新集群，状态为「已连接」' },
      { path: '侧边栏 → 运维工作台 → K8s资源 → K8s资源列表', action: '选择集群和命名空间，点击Tab切换查看Node/Pod/Deployment/Service，点击某个Pod查看详情', expect: '显示Pod的镜像、端口、资源限制、事件列表，Warning/Error事件高亮' },
      { path: '侧边栏 → 运维工作台 → K8s资源 → HPA推荐', action: '选择集群，查看Deployment列表的CPU/内存使用率和建议值，点击「复制配置」获取HPA YAML', expect: '生成可直接应用的HPA配置YAML' },
      { path: '侧边栏 → 运维工作台 → K8s资源 → 资源优化', action: '选择集群，查看优化建议列表，筛选critical/warning级别的超配/欠配问题', expect: '显示CPU/内存超配或欠配的Pod及调整建议' },
    ],
    links: [
      { icon: '☸️', label: 'K8s集群', href: '/k8s/clusters' },
      { icon: '📦', label: 'K8s资源', href: '/k8s/resources' },
    ]
  },
  {
    id: 'chain-3',
    num: '链路3',
    title: 'K8s事件接入告警',
    flowTags: ['K8s事件采集', '事件过滤', '告警生成', '去重防抖动'],
    steps: [
      { path: '侧边栏 → 运维工作台 → K8s资源 → K8s事件列表（后台自动）', action: '无需操作，后台定时采集K8s Events，过滤Warning/Error类型事件', expect: '事件列表显示K8s Warning/Error事件，severity字段标注事件级别' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警列表（后台自动）', action: '无需操作，K8s事件自动映射为告警（OOMKilling/CrashLoopBackOff等）', expect: '告警列表显示K8s事件触发的告警，标题格式为「事件原因: 涉及Pod/资源名」' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警详情', action: '点击K8s事件告警查看详情，包括事件原因、namespace、Pod名称、重复次数', expect: '告警详情显示完整的K8s事件上下文信息' },
    ],
    links: [
      { icon: '☸️', label: 'K8s事件', href: '/k8s/events' },
      { icon: '🔔', label: '告警列表', href: '/alerts' },
    ]
  },
  {
    id: 'chain-4',
    num: '链路4',
    title: '移动端告警推送与控制',
    flowTags: ['WebSocket连接', '实时推送', '确认静默', '批量操作'],
    steps: [
      { path: '移动端 → 告警中心 → 告警列表（WebSocket自动连接）', action: '打开移动端告警列表页，WebSocket自动连接ws://host/api/ws/alerts', expect: '页面顶部显示「已连接」状态指示器' },
      { path: '移动端 → 告警中心 → 告警列表', action: '查看告警列表，新告警通过WebSocket实时推送', expect: '新告警实时显示并高亮，点击气泡刷新列表' },
      { path: '移动端 → 告警中心 → 告警列表 → 告警详情', action: '点击某条告警进入详情，点击「确认告警」或「触发自愈」', expect: '告警状态变为「已确认」，自愈执行结果弹窗显示' },
      { path: '移动端 → 告警中心 → 告警列表（多选模式）', action: '长按某条告警进入多选模式，勾选多条后点击「批量确认」或「批量解决」', expect: '所有选中告警状态批量更新，显示Toast提示' },
    ],
    links: [
      { icon: '📱', label: '移动端', href: '/mobile' },
      { icon: '🔔', label: '告警列表', href: '/alerts' },
    ]
  },
  {
    id: 'chain-5',
    num: '链路5',
    title: '事件变更关联故障',
    flowTags: ['资产变更', '变更记录', 'RCA关联', 'Timeline展示'],
    steps: [
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产列表 → 资产详情', action: '点击某条资产的「编辑」按钮修改属性，保存后查看「变更历史」Tab', expect: '变更历史显示修改的字段、旧值→新值、操作人、操作时间' },
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产列表 → 健康扫描', action: '点击「健康扫描」按钮，等待批量扫描完成', expect: 'Toast提示「健康扫描完成」，评分变化的资产自动写入变更历史' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情 → RCA分析', action: '在故障详情页点击「RCA分析」，查看Timeline部分的变更记录', expect: 'Timeline显示故障时间窗口内的资产变更记录，帮助判断故障是否由变更引发' },
    ],
    links: [
      { icon: '🔄', label: '资产变更', href: '/assets' },
      { icon: '📝', label: '故障管理', href: '/incidents' },
    ]
  },
  {
    id: 'chain-6',
    num: '链路6',
    title: '知识指导SRE实践',
    flowTags: ['告警知识推荐', '知识库搜索', 'RCA沉淀'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警详情', action: '在告警详情页底部查看「相关知识」区块，点击推荐知识查看完整内容', expect: '显示与该告警匹配的知识条目：标题、症状、解决方案、匹配度分数' },
      { path: '侧边栏 → 知识库 → 知识管理 → 知识库', action: '浏览知识列表，筛选来源（手动/AI生成/告警案例/故障案例），点击知识标题查看详情', expect: '详情页显示结构化知识内容，SOP步骤以卡片形式展示' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情（后台自动）', action: '故障RCA分析完成后，无需操作，系统自动将RCA结果写入知识库', expect: '知识库列表出现新条目，source_type=incident_case' },
    ],
    links: [
      { icon: '📚', label: '知识库', href: '/knowledge' },
      { icon: '🔔', label: '告警详情', href: '/alerts' },
    ]
  },
  {
    id: 'chain-7',
    num: '链路7',
    title: 'SLO违规监控',
    flowTags: ['SLO配置', '手动计算', 'Error Budget', 'Burn Rate'],
    steps: [
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → SLO管理 → SLO配置', action: '点击「新建SLO」，填写SLO名称、关联服务、SLO目标(99.9%)、时间窗口(滚动28天)，点击保存', expect: 'SLO配置出现在列表中，状态为「未计算」' },
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → SLO仪表盘', action: '查看SLO卡片的状态（healthy/warning/critical）、当前可用性、Error Budget剩余、燃烧速率，点击「重新计算」', expect: '显示计算后的可用性百分比、Error Budget消耗趋势、燃烧速率变化' },
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → SLO仪表盘 → SLO详情', action: '点击某张SLO卡片，弹窗显示历史可用性趋势图、Error Budget消耗趋势、关联告警列表', expect: '趋势图展示SLO指标随时间的变化，可关联查看相关告警' },
    ],
    links: [
      { icon: '📈', label: 'SLO管理', href: '/slo' },
      { icon: '📊', label: 'SLO仪表盘', href: '/slo/dashboard' },
    ]
  },
  {
    id: 'chain-8',
    num: '链路8',
    title: '告警直接触发自动响应',
    flowTags: ['规则配置', 'SSH执行', '效果追踪', '30分钟验证'],
    steps: [
      { path: '侧边栏 → 运维工作台 → 任务中心 → 自愈规则配置', action: '点击「新建规则」，填写规则名称、关联告警规则、动作类型(restart/clean/run_command/notify)、服务名称，点击保存并启用', expect: '规则列表显示新规则，状态为「已启用」' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 自愈执行（后台自动）', action: '无需操作，当匹配规则触发时自动执行（SSH远程连接→执行命令→写入执行日志→更新告警状态）', expect: '自愈执行列表出现新记录，显示执行动作、目标资产、执行结果（成功/失败）' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 自愈效果分析', action: '查看效果统计卡片（总次数/成功次数/成功率/平均恢复时间）和效果历史列表', expect: '显示自愈执行后的恢复状态：resolved（已恢复）/failed（未恢复）' },
    ],
    links: [
      { icon: '⚡', label: '自愈规则', href: '/remediation/rules' },
      { icon: '📝', label: '自愈执行', href: '/remediation/exec' },
      { icon: '📊', label: '效果分析', href: '/remediation/effect' },
    ]
  },
  {
    id: 'chain-9',
    num: '链路9',
    title: '故障自动沉淀知识',
    flowTags: ['故障关闭', '自动归档', 'LLM生成', '知识草稿'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情（后台自动）', action: '故障审批通过后，无需操作，系统在5分钟内自动触发知识沉淀', expect: '后台调用LLM生成结构化知识（标题/症状/根因/解决方案/标签）' },
      { path: '侧边栏 → 知识库 → AI知识草稿', action: '查看草稿列表，新生成的草稿显示「AI生成」标签，状态为「待审批」', expect: '点击草稿查看完整知识内容：标题、症状、根因、解决方案、SOP步骤' },
      { path: '侧边栏 → 知识库 → AI知识草稿 → 审批', action: '点击某条草稿的「审批」，确认内容无误后点击「通过」', expect: '草稿变为「已通过」，自动创建KnowledgeBase记录，RAG索引更新' },
    ],
    links: [
      { icon: '🤖', label: 'AI知识草稿', href: '/knowledge/drafts' },
      { icon: '📚', label: '知识库', href: '/knowledge' },
    ]
  },
  {
    id: 'chain-10',
    num: '链路10',
    title: 'AI直接检索知识',
    flowTags: ['AI问答', 'RAG检索', 'TF-IDF', '采纳为知识'],
    steps: [
      { path: '侧边栏 → AI运维智能体 → AI智能助手', action: '在聊天框输入「如何处理nginx进程CPU占用过高？」，发送问题', expect: 'AI自动调用query_knowledge_rag工具检索知识库，TF-IDF向量化+余弦相似度匹配' },
      { path: '侧边栏 → AI运维智能体 → AI智能助手', action: '查看AI回答中的知识引用（如「根据知识库《CPU使用率过高处理》...」），点击「采纳为知识」', expect: '生成新的知识草稿进入审批流程，Toast提示「已生成知识草稿」' },
      { path: '侧边栏 → AI运维智能体 → AI智能助手', action: '输入「统一搜索：nginx故障处理方案」，AI调用unified_search同时检索知识库/文档/Runbook', expect: '搜索结果按相关性排序，来源类型以标签区分（知识库/文档/Runbook）' },
    ],
    links: [
      { icon: '🤖', label: 'AI助手', href: '/ai/chat' },
      { icon: '📚', label: '知识库', href: '/knowledge' },
    ]
  },
  {
    id: 'chain-11',
    num: '链路11',
    title: '故障内部审批流',
    flowTags: ['创建故障', '提交审批', '审批通过/驳回', '状态机'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 故障管理', action: '点击「新建故障单」，填写标题、严重级别(critical/high/medium/low)、影响范围、描述，点击提交', expect: '故障列表显示新故障单，状态为「待处理」' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情', action: '故障处理完成后，点击「提交审批」，填写审批备注，确认提交', expect: '故障状态从「待处理」变为「待审批」，审批历史记录显示submit动作' },
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情（审批人）', action: '审批人在「待我审批」过滤中找到该故障，点击「通过」或「驳回」，填写意见', expect: '通过：状态变为「已解决」，触发知识自动沉淀；驳回：状态退回「待处理」' },
    ],
    links: [
      { icon: '📝', label: '故障管理', href: '/incidents' },
      { icon: '✅', label: '审批', href: '/incidents?filter=pending_approval' },
    ]
  },
  {
    id: 'chain-12',
    num: '链路12',
    title: '告警静默管理',
    flowTags: ['创建静默', '静默生效', '到期恢复', '取消静默'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警列表 → 告警详情', action: '点击「静默告警」，选择静默时长(30分钟/1小时/6小时/24小时/自定义)，填写原因，提交', expect: '告警列表中该告警显示灰色「静默中」标签，鼠标悬停显示原因和结束时间' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 静默管理', action: '查看所有静默规则列表，状态分为「生效中」和「已过期」', expect: '生效中的规则显示绿色徽章，过期的规则显示灰色' },
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警列表 → 告警详情', action: '点击静默中的告警，点击「取消静默」按钮', expect: '告警状态立即恢复，「静默中」标签消失' },
    ],
    links: [
      { icon: '🔕', label: '静默管理', href: '/alerts/silence' },
      { icon: '🔔', label: '告警列表', href: '/alerts' },
    ]
  },
  {
    id: 'chain-13',
    num: '链路13',
    title: '告警触发巡检自动化',
    flowTags: ['告警触发', '自动匹配', '健康评分', 'AI报告'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 告警中心 → 告警详情', action: '在告警详情页点击「触发巡检」按钮', expect: 'Toast提示「巡检任务已创建」，系统自动匹配CI类型创建巡检任务' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 智能巡检 → 巡检记录（后台自动）', action: '无需操作，后台执行9类检查项（CPU/内存/磁盘/告警/资产状态/Span错误率等），生成健康评分', expect: '巡检记录列表显示新记录，状态为「已完成」' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 智能巡检 → 巡检记录 → 巡检详情', action: '点击某条巡检记录的「查看详情」，显示健康评分、AI生成的巡检报告', expect: '报告包含：摘要、评分解读、异常分析、趋势预判、处置建议、风险预警' },
    ],
    links: [
      { icon: '🔍', label: '智能巡检', href: '/inspection' },
      { icon: '🔔', label: '告警详情', href: '/alerts' },
    ]
  },
  {
    id: 'chain-14',
    num: '链路14',
    title: '混沌工程稳态验证',
    flowTags: ['配置实验', '故障注入', '稳态验证', '自动回滚'],
    steps: [
      { path: '侧边栏 → 可靠性工程 → 混沌工程 → 混沌实验', action: '点击「新建实验」，填写实验名称、目标资产、故障类型(CPU压力/网络延迟等)、持续时间、稳态配置(指标+阈值)', expect: '实验配置出现在列表中' },
      { path: '侧边栏 → 可靠性工程 → 混沌工程 → 混沌实验 → 实验详情', action: '点击某条实验的「启动」按钮，等待执行完成', expect: '状态从「执行中」变为「已完成」，显示Before/After对比柱状图和稳态验证结果' },
      { path: '侧边栏 → 可靠性工程 → 混沌工程 → 混沌实验 → 实验详情', action: '查看执行记录列表，包括：稳态通过/失败状态、采集指标对比、触发告警数、自动回滚状态', expect: '稳态通过显示绿色徽章，失败显示红色；自动回滚成功标记为「已清理」' },
    ],
    links: [
      { icon: '💥', label: '混沌工程', href: '/chaos' },
      { icon: '📊', label: '实验记录', href: '/chaos/experiments' },
    ]
  },
  {
    id: 'chain-15',
    num: '链路15',
    title: 'On-Call自动轮转与交接班',
    flowTags: ['配置值班表', '自动轮转', '手动轮转', '交接班'],
    steps: [
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → On-Call值班表', action: '点击「新建值班表」，填写团队名称、值班成员(JSON数组)、轮转方式(weekly/monthly)、当前值班人、周期时间，保存', expect: '值班表出现在列表中，当前值班人卡片高亮显示' },
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → On-Call值班表（后台自动）', action: '无需操作，当current_period_ended_at < now且is_auto_rotate=True时自动轮转', expect: '下次查询时显示新的值班人，members列表索引循环移动' },
      { path: '侧边栏 → 可靠性工程 → SRE可靠性 → On-Call值班表', action: '点击某条值班表的「手动轮转」立即切换到下一位，或点击「交接班」选择指定人员', expect: '当前值班人立即切换，历史记录显示交接信息' },
    ],
    links: [
      { icon: '👥', label: 'OnCall值班', href: '/oncall' },
      { icon: '🔄', label: '交接班', href: '/oncall/handover' },
    ]
  },
  {
    id: 'chain-16',
    num: '链路16',
    title: 'AI Agent质量评估与A/B测试',
    flowTags: ['评估统计', 'A/B分流', 'GroundTruth', '评分'],
    steps: [
      { path: '侧边栏 → AI运维智能体 → Agent评估', action: '查看评估统计卡片（总次数/成功率/幻觉率/延迟/Token消耗），切换时间范围(7天/30天/90天)', expect: '显示各工具的成功率柱状图、幻觉率趋势线、延迟分布、Token消耗TOP-N' },
      { path: '侧边栏 → AI运维智能体 → A/B测试', action: '点击「新建测试」，填写测试名称、A组Provider、B组Provider、分流比例(50/50)，保存', expect: '测试配置出现在列表中，自动按MD5哈希分流执行' },
      { path: '侧边栏 → AI运维智能体 → A/B测试 → 测试详情', action: '查看A/B两组对比统计（成功率/延迟/请求数）和胜者标记', expect: '胜者以绿色高亮显示，差距>5%才算胜负' },
      { path: '侧边栏 → AI运维智能体 → Agent评估 → GroundTruth测试', action: '点击「新建用例」，填写问题、期望工具、期望参数、期望答案、分类标签', expect: '用例出现在列表中，默认启用' },
      { path: '侧边栏 → AI运维智能体 → Agent评估 → GroundTruth测试', action: '点击某条用例的「执行」或「批量执行」，查看评分结果（语义相似度×0.5 + 工具匹配度×0.5）', expect: '评分结果弹窗显示：综合评分≥0.6为通过，显示实际调用工具和参数' },
    ],
    links: [
      { icon: '📊', label: 'Agent评估', href: '/agent/eval' },
      { icon: '🔬', label: 'A/B测试', href: '/agent/abtest' },
      { icon: '✅', label: 'GroundTruth', href: '/agent/groundtruth' },
    ]
  },
  {
    id: 'chain-17',
    num: '链路17',
    title: '异常检测精度回测与算法择优',
    flowTags: ['上传标注', '基准统计', 'F1评分', '算法推荐'],
    steps: [
      { path: '侧边栏 → 智能分析室 → 异常检测 → 异常检测基准', action: '点击「新建基准」，选择资产、指标名称、算法，上传CSV标注数据(timestamp,value,is_anomaly)', expect: '基准列表显示新记录及计算的Precision/Recall/F1分数' },
      { path: '侧边栏 → 智能分析室 → 异常检测 → 异常检测基准', action: '查看统计概览卡片（总基准数/平均F1/最佳算法）和算法F1对比柱状图', expect: '柱状图直观展示各算法性能差异' },
      { path: '侧边栏 → 智能分析室 → 异常检测 → 异常检测配置', action: '新建规则时点击「推荐算法」按钮，系统自动根据标注数据或指标特征推荐最优算法', expect: '算法字段自动填充，显示推荐理由（如「基于标注数据，MAD算法F1最高」）' },
    ],
    links: [
      { icon: '📉', label: '异常基准', href: '/anomaly/benchmark' },
      { icon: '🤖', label: '异常配置', href: '/anomaly/config' },
    ]
  },
  {
    id: 'chain-18',
    num: '链路18',
    title: 'SOP知识自动生成',
    flowTags: ['故障单生成', 'LLM生成', 'SOP步骤', '审批入库'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 故障管理 → 故障详情', action: '在已解决故障详情页点击「生成SOP知识」按钮', expect: 'Toast提示「SOP知识已生成」，后台调用LLM生成结构化SOP' },
      { path: '侧边栏 → 知识库 → AI知识草稿', action: '查看草稿列表，新生成的SOP草稿显示「sop」标签，点击查看SOP步骤卡片', expect: 'SOP步骤以卡片形式展示：步骤号/动作/命令/预期结果' },
      { path: '侧边栏 → 知识库 → AI知识草稿 → 审批', action: '点击某条SOP草稿的「审批」，确认SOP步骤无误后点击「通过」', expect: '草稿变为「已通过」，知识库列表出现新入库条目，source_type=auto' },
    ],
    links: [
      { icon: '📑', label: 'SOP知识', href: '/knowledge/drafts' },
      { icon: '📝', label: '故障管理', href: '/incidents' },
    ]
  },
  {
    id: 'chain-19',
    num: '链路19',
    title: '运营数据飞轮',
    flowTags: ['6大KPI', '告警趋势', 'MTTR', '自愈效果', 'AI效能'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 运营分析看板', action: '页面加载时自动调用6个API，查看6大KPI卡片：总告警数/总故障数/MTTR/自愈成功率/AI任务完成率/通知送达率', expect: 'KPI卡片以数字+徽章形式展示关键指标' },
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 运营分析看板', action: '查看6张ECharts图表：告警趋势图/MTTR趋势图/自愈效果饼图/AI效能图/通知统计图/工具排行图', expect: '图表支持交互：悬停查看数值、点击钻取详情、缩放时间范围' },
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 运营分析看板', action: '切换时间范围按钮（7天/30天/90天），分析运营数据变化趋势', expect: '所有图表和数据按选中时间范围重新计算' },
    ],
    links: [
      { icon: '📊', label: '运营看板', href: '/ops/analytics' },
      { icon: '📈', label: '趋势分析', href: '/ops/trend' },
    ]
  },
  {
    id: 'chain-20',
    num: '链路20',
    title: '分层诊断工具体系',
    flowTags: ['Snapshot快照', 'Focused定向', 'Flexible灵活', '命令校验'],
    steps: [
      { path: '侧边栏 → 运维工作台 → 任务中心 → 诊断工具中心', action: '查看三层工具分类：Snapshot层(6个只读概览)/Focused层(12个定向诊断)/Flexible层(2个灵活查询)', expect: '工具按风险等级着色（绿=read_only/蓝=low/黄=medium/橙=high/红=critical）' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 诊断工具中心', action: '选择工具（如os.overview）和资产，点击「执行」', expect: '右侧面板显示命令输出stdout和退出码(exit 0=成功)' },
      { path: '侧边栏 → 运维工作台 → 任务中心 → 诊断工具中心', action: '选择Flexible层工具（如flex.shell），输入Shell命令，点击「校验」', expect: '安全命令显示绿色「校验通过」，危险命令（rm -rf/kill等）显示红色「危险命令拦截」' },
    ],
    links: [
      { icon: '🔧', label: '诊断工具', href: '/diagnostic/tools' },
      { icon: '📋', label: '工具注册表', href: '/diagnostic/registry' },
    ]
  },
  {
    id: 'chain-21',
    num: '链路21',
    title: '仪表盘拖拽自定义',
    flowTags: ['预置模板', '拖拽卡片', '配置数据源', '设为默认'],
    steps: [
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 自定义仪表盘', action: '查看3套预置模板（运维总览/告警中心/SRE看板），点击模板名称切换视图', expect: '页面显示该模板对应的卡片网格布局' },
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 自定义仪表盘', action: '点击「新建布局」，填写布局名称和描述，保存后点击「添加卡片」从左侧卡片库拖拽到画布', expect: '卡片自动吸附到gridstack网格，拖拽边缘调整大小' },
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 自定义仪表盘', action: '点击卡片右上角「设置」配置数据源和刷新间隔，点击「保存」', expect: '布局配置持久化到数据库' },
      { path: '侧边栏 → 值班驾驶舱 → 运行概览 → 自定义仪表盘', action: '在布局列表点击某布局的「设为默认」', expect: '登录后自动加载该默认布局' },
    ],
    links: [
      { icon: '📺', label: '自定义仪表盘', href: '/dashboard' },
      { icon: '📊', label: '卡片库', href: '/dashboard/cards' },
    ]
  },
  {
    id: 'chain-22',
    num: '链路22',
    title: '资产健康度评分与变更跟踪',
    flowTags: ['健康评分', '批量扫描', '变更历史', '评分计算'],
    steps: [
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产列表', action: '查看资产列表的健康评分徽章（绿色≥80/黄色60-79/红色<60），点击某资产查看评分详情', expect: '详情显示评分计算：基础分40 + CPU分(最高20) + 内存分(最高20) + 磁盘分(最高20) - 告警惩罚' },
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产列表', action: '点击「健康扫描」按钮，等待批量扫描完成', expect: 'Toast提示「健康扫描完成」，状态变化的资产评分徽章更新' },
      { path: '侧边栏 → 运维工作台 → 资产管理 → 资产详情 → 变更历史', action: '查看该资产的所有变更记录列表，筛选类型（字段更新/健康状态变化）', expect: '变更历史按时间倒序排列，健康状态变化以颜色标记' },
    ],
    links: [
      { icon: '💚', label: '资产管理', href: '/assets' },
      { icon: '🔄', label: '变更历史', href: '/assets/changes' },
    ]
  },
  {
    id: 'chain-23',
    num: '链路23',
    title: '移动端运维闭环',
    flowTags: ['日志搜索', '告警批量', '故障单创建', 'AI会话'],
    steps: [
      { path: '移动端 → 运维工具 → 日志搜索', action: '输入关键词、选择日志级别(ERROR/WARN/INFO/DEBUG)和数据源，点击「搜索」', expect: '显示日志列表，级别以颜色标记，点击查看JSON格式化详情' },
      { path: '移动端 → 告警中心 → 告警列表', action: '长按某条告警进入多选模式，勾选多条后点击「批量确认」或「批量解决」', expect: '所有选中告警状态批量更新，显示Toast提示' },
      { path: '移动端 → 故障管理 → 故障列表 → 新建故障单', action: '点击「+」按钮，填写标题、严重级别、影响范围、紧急联系人、描述，提交', expect: '故障单创建成功，Toast提示，返回故障列表' },
      { path: '移动端 → AI助手 → 会话列表', action: '点击右上角「历史」查看历史会话列表，点击某会话继续对话或删除', expect: '会话按时间倒序排列，点击加载历史消息继续对话' },
    ],
    links: [
      { icon: '📱', label: '移动端', href: '/mobile' },
      { icon: '📝', label: '故障单', href: '/mobile/incidents' },
      { icon: '🤖', label: 'AI助手', href: '/mobile/ai' },
    ]
  },
  {
    id: 'chain-24',
    num: '链路24',
    title: 'Agent能力中心',
    flowTags: ['工具注册表', '风险分级', 'LLM暴露', 'Internal工具'],
    steps: [
      { path: '侧边栏 → AI运维智能体 → Agent能力中心', action: '查看能力统计卡片（工具总数41/LLM工具24/Internal工具17）和风险等级分布饼图', expect: '统计卡片显示各风险等级数量：read_only=20/low=4/medium=6/high=5/critical=3/advisory=3' },
      { path: '侧边栏 → AI运维智能体 → Agent能力中心', action: '浏览工具注册表网格，筛选风险等级（read_only/low/medium/high/critical/advisory）或范围（LLM/Internal）', expect: '工具按风险等级着色（绿=read_only/蓝=low/黄=medium/橙=high/红=critical/灰=advisory）' },
      { path: '侧边栏 → AI运维智能体 → Agent能力中心', action: '点击某工具卡片查看详情弹窗：工具名称/描述/风险等级/input_schema/安全策略说明', expect: '弹窗显示完整的工具定义和JSON Schema格式的参数说明' },
    ],
    links: [
      { icon: '🧠', label: 'Agent能力', href: '/agent/capabilities' },
      { icon: '📋', label: '工具注册表', href: '/agent/tools' },
    ]
  }
]
</script>

<style scoped>
.guide-page {
  min-height: 100vh;
  background: #F8F9FA;
  padding: 48px;
  color: #111827;
  font-family: 'Plus Jakarta Sans', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.guide-header {
  text-align: center;
  margin-bottom: 48px;
}

.guide-header h1 {
  font-size: 36px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: #111827;
  margin-bottom: 12px;
}

.guide-subtitle {
  font-size: 16px;
  color: #6B7280;
  font-weight: 500;
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(560px, 1fr));
  gap: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.guide-group {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 16px;
  padding: 24px;
  transition: all 0.3s ease;
}

.guide-group:hover {
  border-color: #C7512E;
  box-shadow: 0 4px 20px rgba(199, 81, 46, 0.1);
}

.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.group-num {
  font-size: 12px;
  font-weight: 700;
  color: #FFFFFF;
  background: #C7512E;
  padding: 4px 10px;
  border-radius: 6px;
}

.group-title {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  letter-spacing: -0.02em;
}

.group-steps {
  margin-bottom: 20px;
}

.steps-title,
.links-title,
.flow-title {
  font-size: 12px;
  font-weight: 600;
  color: #6B7280;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.step-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #F9FAFB;
  border-radius: 8px;
  margin-bottom: 10px;
}

.step-num {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  background: #C7512E;
  color: #FFFFFF;
  font-size: 12px;
  font-weight: 700;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-content {
  flex: 1;
}

.step-path {
  margin-bottom: 6px;
}

.path-label {
  font-size: 10px;
  font-weight: 600;
  color: #9CA3AF;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.path-value {
  font-size: 12px;
  color: #374151;
  font-weight: 500;
  margin-left: 6px;
}

.step-action {
  font-size: 12px;
  color: #111827;
  line-height: 1.5;
  margin-bottom: 6px;
}

.step-expect {
  font-size: 11px;
  color: #059669;
  background: rgba(5, 150, 105, 0.08);
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
}

.group-links {
  margin-bottom: 16px;
}

.links-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.guide-link {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: #F3F4F6;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  text-decoration: none;
  transition: all 0.2s;
}

.guide-link:hover {
  background: #C7512E;
  border-color: #C7512E;
  color: #FFFFFF;
}

.link-icon {
  font-size: 12px;
}

.link-text {
  font-size: 11px;
  font-weight: 500;
}

.group-flow {
  padding-top: 16px;
  border-top: 1px solid #E5E7EB;
}

.flow-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.flow-tag {
  font-size: 11px;
  color: #374151;
  background: #F3F4F6;
  padding: 3px 8px;
  border-radius: 4px;
}

.flow-arrow {
  color: #C7512E;
  font-weight: 600;
  margin: 0 2px;
}

.guide-footer {
  text-align: center;
  margin-top: 48px;
  padding-top: 32px;
  border-top: 1px solid #E5E7EB;
  color: #6B7280;
  font-size: 14px;
}

.contact-phone {
  color: #C7512E;
  font-weight: 600;
}

@media (max-width: 768px) {
  .guide-page {
    padding: 24px 16px;
  }

  .guide-header h1 {
    font-size: 28px;
  }

  .guide-grid {
    grid-template-columns: 1fr;
  }
}
</style>
