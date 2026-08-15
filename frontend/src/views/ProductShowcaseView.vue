<template>
  <div class="showcase">
    <!-- Top nav -->
    <nav class="topnav">
      <div class="nav-brand">
        <span class="nb-mark">智渊</span><span class="nb-sub">AIOPS</span>
      </div>
      <div class="nav-links">
        <a href="#components">组件商店</a>
        <a href="#security">安全扫描</a>
        <a href="#compare">优势对比</a>
        <a href="#cta">开始使用</a>
        <a href="/login" class="nav-btn">登录平台</a>
      </div>
    </nav>

    <!-- Hero -->
    <section class="hero">
      <div class="hero-glow g1"></div><div class="hero-glow g2"></div>
      <div class="hero-content">
        <div class="eyebrow">组件智能运维 · Agentic AIOps</div>
        <h1>覆盖 <em>54+</em> 主流组件<br/>一个平台，全生命周期智能运维</h1>
        <p class="sub">一键部署 · 自动配置优化 · Trivy 漏洞扫描 · 高可用巡检 · AI 健康分析</p>
        <div class="hero-btns">
          <a href="#components" class="btn-p">探索组件商店</a>
          <a href="/login" class="btn-g">进入平台 →</a>
        </div>
        <div class="hero-stats">
          <div class="hs"><div class="hs-n">54+</div><div class="hs-l">已支持组件</div></div>
          <div class="hs"><div class="hs-n">4</div><div class="hs-l">种部署方式</div></div>
          <div class="hs"><div class="hs-n">AI</div><div class="hs-l">智能体驱动</div></div>
          <div class="hs"><div class="hs-n">Trivy</div><div class="hs-l">漏洞扫描</div></div>
        </div>
      </div>
    </section>

    <!-- Components -->
    <section id="components" class="section">
      <div class="sec-head">
        <div class="sec-eyebrow">// 组件应用商店</div>
        <h2>54+ 组件，一套部署体系</h2>
        <p>数据库 · 缓存 · 消息 · 中间件 · 可观测 · 平台，全场景覆盖；每种组件支持 传统 / Docker / K8s-Helm / 高可用 四种部署方式。</p>
      </div>
      <div class="cat-grid">
        <div v-for="cat in categories" :key="cat.name" class="cat-card">
          <div class="cat-title">{{ cat.icon }} {{ cat.name }}</div>
          <div class="cat-comps">
            <span v-for="c in cat.items" :key="c" class="comp-chip">{{ c }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Security -->
    <section id="security" class="section alt">
      <div class="sec-head">
        <div class="sec-eyebrow">// 安全合规</div>
        <h2>生产级漏洞扫描</h2>
        <p>内置 Trivy 镜像扫描（SBOM + CVE 全网数据库），无 Trivy 环境自动回退版本比对，关键组件漏洞一目了然。</p>
      </div>
      <div class="sec-feat">
        <div class="feat"><div class="f-ic">🛡️</div><div><b>Trivy 镜像扫描</b><p>SBOM + 漏洞数据库，聚合 critical/high/medium</p></div></div>
        <div class="feat"><div class="f-ic">🧭</div><div><b>四合一体检</b><p>健康 + 配置 + 漏洞 + AI 分析，一键闭环</p></div></div>
        <div class="feat"><div class="f-ic">🤖</div><div><b>AI 健康分析</b><p>大模型输出健康评分、根因与优化建议</p></div></div>
      </div>
    </section>

    <!-- Compare -->
    <section id="compare" class="section">
      <div class="sec-head">
        <div class="sec-eyebrow">// 优势对比</div>
        <h2>不只是覆盖广，更要做得深</h2>
      </div>
      <div class="compare-table">
        <table>
          <thead><tr><th>能力维度</th><th class="me">智渊 AIOps</th><th>传统组件方案</th></tr></thead>
          <tbody>
            <tr v-for="c in compare" :key="c.dim">
              <td class="dim">{{ c.dim }}</td>
              <td class="me-ok">✔ {{ c.me }}</td>
              <td>{{ c.other }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- CTA -->
    <section id="cta" class="cta">
      <h2>现在，轮到你的组件库进化</h2>
      <p>登录智渊 AIOps，体验组件应用商店与 AI 智能体带来的运维变革</p>
      <a href="/login" class="btn-p big">立即登录 →</a>
    </section>

    <footer class="foot">© {{ year }} 智渊 AIOps. All rights reserved.</footer>
  </div>
</template>

<script setup>
import { h } from 'vue'
const year = new Date().getFullYear()

const categories = [
  { icon: '🗄️', name: '数据库', items: ['MySQL','PostgreSQL','MongoDB','Elasticsearch','TiDB','MariaDB','ClickHouse','TDengine','InfluxDB','达梦 DM','人大金仓','openGauss','OceanBase','Doris','StarRocks','Neo4j','Cassandra','HBase','Redis Cluster','MySQL 高可用'] },
  { icon: '🔴', name: '缓存', items: ['Redis','Redis Cluster','Valkey','Memcached'] },
  { icon: '📨', name: '消息队列', items: ['Kafka','RabbitMQ','RocketMQ','ActiveMQ','NATS','EMQX(MQTT)','Mosquitto'] },
  { icon: '🧩', name: '中间件/网关', items: ['Nacos','ZooKeeper','etcd','Consul','APISIX','Traefik','HAProxy','Keycloak','Vault','OpenVPN'] },
  { icon: '📈', name: '可观测', items: ['Prometheus','Grafana','Kibana','Logstash','Loki','Jaeger','Alertmanager','VictoriaMetrics','OpenTelemetry'] },
  { icon: '⚙️', name: '平台/存储', items: ['Nginx','MinIO(S3)','GitLab','Jenkins','Docker Registry'] },
]

const compare = [
  { dim: '组件覆盖', me: '54+ 主流组件全场景覆盖', other: '仅核心几十种' },
  { dim: '部署方式', me: '传统 / Docker / K8s-Helm / 高可用 4 选', other: '单一方式' },
  { dim: '漏洞扫描', me: 'Trivy 镜像级 SBOM+CVE', other: '无 / 基础比对' },
  { dim: 'AI 闭环', me: '部署→体检→AI 根因与建议一键完成', other: '分散、需人工' },
  { dim: '离线交付', me: '离线仓库 + K8s 离线一键集群', other: '依赖公网' },
]
</script>

<style scoped>
.showcase { background: #07070f; color: #e8e6ff; font-family: 'Plus Jakarta Sans', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; overflow-x: hidden; }
.topnav { position: sticky; top: 0; z-index: 50; display: flex; justify-content: space-between; align-items: center; padding: 16px 40px; background: rgba(7,7,15,0.7); backdrop-filter: blur(14px); border-bottom: 1px solid rgba(167,139,250,0.12); }
.nav-brand .nb-mark { font-weight: 800; font-size: 20px; background: linear-gradient(120deg,#f0abfc,#a78bfa,#22d3ee); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.nb-sub { font-size: 13px; color: rgba(255,255,255,0.4); margin-left: 8px; letter-spacing: 1px; }
.nav-links { display: flex; gap: 24px; align-items: center; }
.nav-links a { color: rgba(255,255,255,0.6); text-decoration: none; font-size: 14px; transition: color .2s; }
.nav-links a:hover { color: #fff; }
.nav-btn { padding: 8px 18px; border: 1px solid rgba(167,139,250,0.4); border-radius: 8px; color: #d8b4fe !important; }
.nav-btn:hover { background: rgba(139,92,246,0.15); }
.hero { position: relative; padding: 120px 40px 100px; text-align: center; overflow: hidden; }
.hero-glow { position: absolute; border-radius: 50%; filter: blur(90px); }
.g1 { width: 500px; height: 500px; background: rgba(124,58,237,0.35); top: -150px; left: -100px; }
.g2 { width: 400px; height: 400px; background: rgba(192,38,211,0.25); bottom: -100px; right: -80px; }
.hero-content { position: relative; max-width: 900px; margin: 0 auto; }
.eyebrow { display: inline-block; padding: 6px 16px; border: 1px solid rgba(167,139,250,0.3); border-radius: 20px; color: #c084fc; font-size: 13px; letter-spacing: 2px; margin-bottom: 28px; }
.hero h1 { font-size: clamp(34px, 5vw, 58px); font-weight: 800; line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 24px; }
.hero h1 em { font-style: normal; background: linear-gradient(120deg,#f0abfc,#a78bfa,#22d3ee); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.sub { font-size: 17px; color: rgba(255,255,255,0.55); max-width: 560px; margin: 0 auto 36px; line-height: 1.6; }
.hero-btns { display: flex; justify-content: center; gap: 16px; margin-bottom: 56px; }
.btn-p { padding: 13px 30px; background: linear-gradient(120deg,#8b5cf6,#c026d3); color: #fff; border-radius: 30px; text-decoration: none; font-weight: 600; box-shadow: 0 8px 30px rgba(139,92,246,0.35); }
.btn-p.big { font-size: 17px; padding: 16px 42px; }
.btn-g { padding: 13px 30px; border: 1px solid rgba(255,255,255,0.25); color: #e8e6ff; border-radius: 30px; text-decoration: none; font-weight: 600; }
.hero-stats { display: flex; justify-content: center; gap: 60px; }
.hs-n { font-size: 30px; font-weight: 800; color: #fff; }
.hs-l { font-size: 12px; color: rgba(255,255,255,0.45); margin-top: 4px; }
.section { padding: 90px 40px; }
.section.alt { background: rgba(139,92,246,0.04); border-block: 1px solid rgba(167,139,250,0.1); }
.sec-head { max-width: 760px; margin: 0 auto 50px; text-align: center; }
.sec-eyebrow { color: #c084fc; font-size: 13px; letter-spacing: 2px; margin-bottom: 16px; }
.sec-head h2 { font-size: 32px; font-weight: 800; margin: 0 0 14px; }
.sec-head p { color: rgba(255,255,255,0.55); line-height: 1.7; }
.cat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px,1fr)); gap: 18px; max-width: 1200px; margin: 0 auto; }
.cat-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(167,139,250,0.14); border-radius: 14px; padding: 22px; }
.cat-title { font-size: 16px; font-weight: 700; margin-bottom: 14px; }
.cat-comps { display: flex; flex-wrap: wrap; gap: 8px; }
.comp-chip { font-size: 12px; padding: 5px 11px; background: rgba(139,92,246,0.12); color: #d8b4fe; border-radius: 8px; border: 1px solid rgba(167,139,250,0.15); }
.sec-feat { display: grid; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); gap: 18px; max-width: 1000px; margin: 0 auto; }
.feat { display: flex; gap: 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(167,139,250,0.12); border-radius: 12px; padding: 20px; }
.f-ic { font-size: 26px; }
.feat b { font-size: 15px; }
.feat p { color: rgba(255,255,255,0.5); font-size: 13px; margin: 5px 0 0; line-height: 1.6; }
.compare-table { max-width: 900px; margin: 0 auto; overflow-x: auto; }
.compare-table table { width: 100%; border-collapse: collapse; }
.compare-table th, .compare-table td { padding: 15px 18px; text-align: left; font-size: 14px; border-bottom: 1px solid rgba(167,139,250,0.12); }
.compare-table th { color: rgba(255,255,255,0.4); font-weight: 600; font-size: 12px; letter-spacing: 1px; }
.compare-table th.me { color: #d8b4fe; }
.dim { color: #fff; font-weight: 600; width: 30%; }
.me-ok { color: #6ee7b7; }
.cta { text-align: center; padding: 100px 40px; background: linear-gradient(160deg, rgba(124,58,237,0.18), rgba(192,38,211,0.1)); }
.cta h2 { font-size: 34px; font-weight: 800; margin: 0 0 16px; }
.cta p { color: rgba(255,255,255,0.55); margin: 0 0 30px; }
.foot { text-align: center; padding: 28px; color: rgba(255,255,255,0.3); font-size: 13px; }
@media (max-width: 800px) {
  .nav-links a:not(.nav-btn) { display: none; }
  .hero { padding: 80px 24px; }
  .hero-stats { gap: 30px; }
}
</style>
