<template>
  <div class="comp-ops">
    <div class="page-header">
      <h1>🛠️ 组件智能运维</h1>
      <p>对标 Agentic AIOps 组件方案 · 覆盖 50 个主流基础设施组件 · AI智能体 + Agent Skills + MCP 工具</p>
    </div>

    <!-- 统计 -->
    <div class="stat-grid">
      <div class="stat-card"><div class="val ok">{{ comps.filter(c=>c.status==='full').length }}</div><div class="lbl">✅ 已覆盖</div></div>
      <div class="stat-card"><div class="val blue">{{ comps.filter(c=>c.status==='skill').length }}</div><div class="lbl">🧩 技能包</div></div>
      <div class="stat-card"><div class="val warn">{{ comps.filter(c=>c.status==='base').length }}</div><div class="lbl">⚠️ 基础</div></div>
      <div class="stat-card"><div class="val gray">{{ comps.filter(c=>c.status==='none').length }}</div><div class="lbl">❌ 待补</div></div>
    </div>

    <!-- 分类页签 -->
    <div class="cat-tabs">
      <span class="ct" :class="{active: cat==='all'}" @click="cat='all'">全部 ({{comps.length}})</span>
      <span v-for="c in categories" :key="c.key" class="ct" :class="{active: cat===c.key}" @click="cat=c.key">
        {{ c.label }} ({{ comps.filter(x=>x.type===c.key).length }})
      </span>
    </div>

    <!-- 组件卡片 -->
    <div class="comp-grid">
      <div v-for="c in shown" :key="c.name" class="comp-card" :class="'st-'+c.status">
        <div class="comp-head">
          <span class="name">{{ c.name }}</span>
          <span class="st-badge" :class="'st-'+c.status">{{ statusLabel(c.status) }}</span>
        </div>
        <div class="comp-cat">{{ categoryLabel(c.type) }}</div>
        <div class="comp-desc">{{ c.note }}</div>
        <div class="comp-assets">
          <span class="asset-label">绑定资产</span>
          <span v-if="c.assets && c.assets.length" v-for="a in c.assets" :key="a.id"
                class="asset-tag" :class="a.status === 'online' ? 'on' : (a.status === 'offline' ? 'off' : 'na')"
                :title="`${a.name} (${a.ip}) · ${a.status}`">{{ a.name }}</span>
          <span v-else class="asset-none">未纳管实例</span>
        </div>
        <div class="comp-foot">
          <span v-if="c.skill" class="skill-tag">{{ c.skill }}</span>
          <button v-if="c.skill" class="btn btn-sm" @click="goSkills(c)">🧩 技能</button>
          <button class="btn btn-sm btn-primary" :disabled="!c.assets || !c.assets.length" @click="ask(c)">🤖 问 AI</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import request from '@/api/request'

const cat = ref('all')

const categories = [
  { key: 'db', label: '📊 数据库' },
  { key: 'mq', label: '☁️ 中间件/缓存' },
  { key: 'infra', label: '🖥️ 基础设施' },
  { key: 'plat', label: '🛠️ 平台/配套' },
]

// status: full=已覆盖(工具+页面) skill=技能包(可Agent调用) base=有纳管基础缺专门工具 none=无专门覆盖
const comps = reactive([
  // 数据库
  { name: 'MySQL', type: 'db', status: 'full', skill: 'mysql-smart-ops', note: '慢SQL/锁/复制巡检 (query_mysql)' },
  { name: 'PostgreSQL', type: 'db', status: 'base', skill: '', note: '数据源可连，缺专门诊断工具' },
  { name: 'Oracle', type: 'db', status: 'base', skill: '', note: '数据源/SSH 可纳管' },
  { name: 'SQL Server', type: 'db', status: 'base', skill: '', note: 'SSH 可纳管' },
  { name: '达梦 DM', type: 'db', status: 'base', skill: '', note: '信创纳管，缺专门诊断' },
  { name: '人大金仓', type: 'db', status: 'base', skill: '', note: '信创纳管' },
  { name: 'openGauss', type: 'db', status: 'base', skill: '', note: '信创纳管' },
  { name: 'OceanBase', type: 'db', status: 'base', skill: '', note: '信创纳管' },
  { name: 'MongoDB', type: 'db', status: 'base', skill: '', note: 'SSH 可纳管' },
  { name: 'Elasticsearch', type: 'db', status: 'full', skill: 'elasticsearch-smart-ops', note: '集群/索引/日志 (数据源+es集成)' },
  { name: 'OpenSearch', type: 'db', status: 'base', skill: '', note: '复用 ES 通道' },
  { name: 'ClickHouse', type: 'db', status: 'base', skill: '', note: 'SSH 可纳管' },
  { name: 'TDengine', type: 'db', status: 'none', skill: '', note: '无专门覆盖' },
  { name: 'StarRocks/Doris', type: 'db', status: 'none', skill: '', note: '无专门覆盖' },
  { name: 'Neo4j/图库', type: 'db', status: 'none', skill: '', note: '无专门覆盖(知识图谱除外)' },
  // 中间件/缓存
  { name: 'Redis', type: 'mq', status: 'full', skill: 'redis-smart-ops', note: '内存/热Key/命中率 (redis_monitor)' },
  { name: 'Kafka', type: 'mq', status: 'full', skill: 'kafka-smart-ops', note: '消费延迟/Topic/Broker (kafka_monitor)' },
  { name: 'RabbitMQ', type: 'mq', status: 'base', skill: '', note: '数据源可接' },
  { name: 'RocketMQ', type: 'mq', status: 'base', skill: '', note: '数据源可接' },
  { name: 'Memcached', type: 'mq', status: 'none', skill: '', note: '无专门覆盖' },
  { name: 'Nacos', type: 'mq', status: 'base', skill: '', note: '注册/配置中心可纳管' },
  { name: 'ZooKeeper', type: 'mq', status: 'base', skill: '', note: '资产可纳管' },
  { name: 'etcd', type: 'mq', status: 'base', skill: '', note: 'K8s 底层，可纳管' },
  // 基础设施
  { name: 'Kubernetes', type: 'infra', status: 'full', skill: 'k8s-smart-ops', note: 'Pod/调度/事件 (资源+巡检+离线部署)' },
  { name: 'Linux 服务器', type: 'infra', status: 'full', skill: 'linux-server-ops', note: 'CPU/内存/磁盘 (SSH 21+指标)' },
  { name: 'Windows 服务器', type: 'infra', status: 'base', skill: '', note: 'SSH 纳管' },
  { name: '网络设备', type: 'infra', status: 'full', skill: 'network-smart-ops', note: '接口/LLDP/链路 (net_device_query+SNMP)' },
  { name: 'Nginx', type: 'infra', status: 'full', skill: 'nginx-smart-ops', note: '502/连接数/配置采集' },
  { name: 'Prometheus', type: 'infra', status: 'full', skill: '', note: '数据源+指标分析+告警规则' },
  { name: 'Grafana', type: 'infra', status: 'base', skill: '', note: '可接，缺专门 tool' },
  { name: 'Zabbix', type: 'infra', status: 'base', skill: '', note: '可接，缺触发器优化' },
  // 平台/配套
  { name: 'SkyWalking', type: 'plat', status: 'base', skill: '', note: 'trace 通道，缺专门 tool' },
  { name: 'GitLab', type: 'plat', status: 'base', skill: '', note: '代码检索，缺 CI 诊断' },
  { name: 'InfluxDB', type: 'plat', status: 'base', skill: '', note: '数据源可接' },
  { name: 'Kibana', type: 'plat', status: 'base', skill: '', note: '复用 ES 通道' },
  { name: 'MSSQL·阿里等 (长尾)', type: 'plat', status: 'none', skill: '', note: '按需补充' },
])

const shown = computed(() => cat.value === 'all' ? comps : comps.filter(c => c.type === cat.value))

function statusLabel(s) {
  return { full: '已覆盖', skill: '技能包', base: '基础', none: '待补' }[s] || s
}
function categoryLabel(t) {
  const c = categories.find(x => x.key === t)
  return c ? c.label.replace(/^[\w]+\s*/, '') : t
}

function goSkills(c) {
  // 跳转到技能中心（可查看/调用该组件技能包）
  window._navigateTo && window._navigateTo('skills')
}
async function loadBoundAssets() {
  for (const c of comps) {
    try {
      const data = await request.get('/component-ops/api/assets', { params: { name: c.name } })
      c.assets = (data && data.items) || []
    } catch (e) {
      c.assets = c.assets || []
    }
  }
}
async function ask(c) {
  // 跳到 AI 智能助手，并预填带目标资产的组件运维提问
  let text = `请对「${c.name}」组件做一次智能运维巡检。`
  try {
    const data = await request.get('/component-ops/api/prompt', { params: { name: c.name } })
    if (data && data.prompt) text = data.prompt
  } catch (e) { /* 后端不可用时用默认提问 */ }
  if (window._aiPrefill) window._aiPrefill(text)
  else window._aiPrefillQueue = window._aiPrefillQueue || text
  window._navigateTo && window._navigateTo('ai-ops-assistant')
}
onMounted(loadBoundAssets)
</script>

<style scoped>
.comp-ops { padding: 20px; color: #1f2937; }
.page-header h1 { margin: 0 0 4px; font-size: 20px; }
.page-header p { margin: 0 0 16px; color: #6b7280; font-size: 13px; }

.stat-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:12px; text-align:center; }
.val { font-size:24px; font-weight:700; } .val.ok{color:#10b981}.val.blue{color:#3b82f6}.val.warn{color:#f59e0b}.val.gray{color:#9ca3af}
.lbl { font-size:12px; color:#6b7280; }

.cat-tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
.ct { padding:6px 12px; border:1px solid #e5e7eb; border-radius:16px; cursor:pointer; font-size:12px; color:#374151; background:#fff; }
.ct.active { background:#3b82f6; color:#fff; border-color:#3b82f6; }

.comp-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; }
.comp-card { background:#fff; border:1px solid #e5e7eb; border-left:4px solid #d1d5db; border-radius:8px; padding:12px; }
.comp-card.st-full{ border-left-color:#10b981 } .comp-card.st-skill{ border-left-color:#3b82f6 }
.comp-card.st-base{ border-left-color:#f59e0b } .comp-card.st-none{ border-left-color:#d1d5db }
.comp-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
.name { font-weight:600; font-size:14px; }
.st-badge { font-size:11px; padding:1px 8px; border-radius:10px; color:#fff; }
.st-badge.st-full{background:#10b981}.st-badge.st-skill{background:#3b82f6}.st-badge.st-base{background:#f59e0b}.st-badge.st-none{background:#9ca3af}
.comp-cat { font-size:11px; color:#6b7280; margin-bottom:4px; }
.comp-desc { font-size:12px; color:#4b5563; margin-bottom:8px; min-height:30px; }
.comp-assets { display:flex; gap:4px; align-items:center; flex-wrap:wrap; margin-bottom:8px; min-height:18px; }
.asset-label { font-size:11px; color:#9ca3af; margin-right:2px; }
.asset-tag { font-size:11px; padding:1px 6px; border-radius:8px; }
.asset-tag.on { background:#d1fae5; color:#047857; }
.asset-tag.off { background:#fee2e2; color:#b91c1c; }
.asset-tag.na { background:#f3f4f6; color:#4b5563; }
.asset-none { font-size:11px; color:#c0c4cc; }
.comp-foot { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.skill-tag { font-size:11px; background:#ede9fe; color:#6d28d9; padding:1px 6px; border-radius:8px; }
.btn { padding:5px 10px; border:1px solid #d1d5db; background:#fff; border-radius:6px; cursor:pointer; font-size:12px; }
.btn-primary { background:#3b82f6; color:#fff; border-color:#3b82f6; }
.btn-sm { font-size:12px; }
</style>
