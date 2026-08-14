"""架构巡检图 + 服务调用拓扑 演示数据播种脚本
幂等运行: 检测到已有数据则跳过。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta
import random
from app.database import get_session_for, get_db_mode
from app.models import Span, Asset, AssetRelation

random.seed(42)

SERVICES = [
    ("api-gateway", "1"),
    ("user-service", "1"),
    ("order-service", "1"),
    ("payment-service", "1"),
    ("inventory-service", "1"),
    ("notification-service", "1"),
    ("redis-cache", "3"),
    ("mysql-db", "3"),
]

# 调用关系: (caller, callee, count, error_rate)
CALL_EDGES = [
    ("api-gateway", "user-service", 150, 0.02),
    ("api-gateway", "order-service", 200, 0.05),
    ("api-gateway", "payment-service", 80, 0.01),
    ("user-service", "redis-cache", 300, 0.0),
    ("order-service", "inventory-service", 120, 0.08),
    ("order-service", "payment-service", 90, 0.03),
    ("order-service", "redis-cache", 250, 0.0),
    ("payment-service", "notification-service", 60, 0.01),
    ("payment-service", "mysql-db", 180, 0.12),
    ("inventory-service", "mysql-db", 100, 0.06),
    ("notification-service", "user-service", 40, 0.0),
]

# 资产: 健康巡检图用
ASSETS = [
    ("api-gateway-01", "api_gateway", "api-gateway", "online", "default", "1"),
    ("user-service-01", "api", "user-service", "online", "default", "1"),
    ("order-service-01", "api", "order-service", "online", "default", "1"),
    ("payment-service-01", "api", "payment-service", "online", "default", "1"),
    ("inventory-service-01", "api", "inventory-service", "online", "default", "1"),
    ("notification-service-01", "api", "notification-service", "online", "default", "1"),
    ("redis-master-01", "redis", "redis", "online", "default", "3-db"),
    ("mysql-master-01", "mysql", "mysql", "online", "default", "3-db"),
    ("nginx-lb-01", "loadbalancer", "nginx", "online", "infrastructure", "4"),
    ("monitor-prometheus", "server", "prometheus", "online", "monitoring", "4"),
    ("monitor-grafana", "server", "grafana", "online", "monitoring", "4"),
    ("k8s-master-01", "node", "kubernetes", "online", "infrastructure", "4"),
    ("k8s-node-01", "node", "kubernetes", "online", "infrastructure", "4"),
    ("k8s-node-02", "node", "kubernetes", "offline", "infrastructure", "4"),
    ("log-es-01", "elasticsearch", "elasticsearch", "online", "monitoring", "3-db"),
]


def seed():
    mode = get_db_mode()
    db = get_session_for(mode)()
    now = datetime.now()

    # ---- 检查是否已有数据 ----
    existing = db.query(Span).count()
    if existing > 100:
        print(f"已有 {existing} 条 Span, 跳过演示 Span 数据")
    else:
        # 删旧数据
        db.query(Span).delete()
        # 生成演示 Span
        trace_counter = 0
        span_counter = 0
        for caller, callee, count, err_rate in CALL_EDGES:
            for i in range(count):
                trace_id = f"demo-trace-{trace_counter:04d}"
                trace_counter += 1
                base_time = now - timedelta(hours=random.randint(0, 72), minutes=random.randint(0, 59))
                is_error = random.random() < err_rate
                dur = random.uniform(2, 50)
                # 父 span (caller)
                parent_span_id = f"span-{span_counter:04d}"
                db.add(Span(
                    trace_id=trace_id,
                    span_id=parent_span_id,
                    parent_span_id="",
                    service_name=caller,
                    operation_name=f"call_{callee}",
                    started_at=base_time,
                    ended_at=base_time + timedelta(milliseconds=dur),
                    duration_ms=dur,
                    status="OK" if not is_error else "ERROR",
                ))
                span_counter += 1
                # 子 span (callee)
                child_span_id = f"span-{span_counter:04d}"
                db.add(Span(
                    trace_id=trace_id,
                    span_id=child_span_id,
                    parent_span_id=parent_span_id,
                    service_name=callee,
                    operation_name=f"handle_{caller}",
                    started_at=base_time + timedelta(milliseconds=dur * 0.3),
                    ended_at=base_time + timedelta(milliseconds=dur),
                    duration_ms=dur * 0.7,
                    status="OK" if not is_error else "ERROR",
                ))
                span_counter += 1
        db.commit()
        print(f"播种演示 Span: {span_counter} 条, {trace_counter} 个 trace, {len(CALL_EDGES)} 种调用关系")

    # ---- 检查资产 ----
    existing_assets = db.query(Asset).count()
    if existing_assets > 50:
        print(f"已有 {existing_assets} 个资产, 跳过演示资产")
    else:
        # 清空旧数据(避免health_map脏数据)
        db.query(AssetRelation).delete()
        db.query(Asset).delete()
        for name, ci_type, service, status, domain, layer in ASSETS:
            a = Asset(
                name=name,
                ci_type=ci_type,
                ip=f"10.0.{random.randint(1, 10)}.{random.randint(1, 250)}",
                status=status,
                health_status="green" if status == "online" else "red",
                ci_attributes=f'{{"service":"{service}","domain":"{domain}","layer":"{layer}","owner":"demo","demo":true}}',
            )
            db.add(a)
            db.flush()
        db.commit()
        asset_count = len(ASSETS)
        print(f"播种演示资产: {asset_count} 个")

        # 资产关系
        relations = [
            ("api-gateway-01", "user-service-01", "routes_to"),
            ("api-gateway-01", "order-service-01", "routes_to"),
            ("api-gateway-01", "payment-service-01", "routes_to"),
            ("user-service-01", "redis-master-01", "depends_on"),
            ("order-service-01", "inventory-service-01", "depends_on"),
            ("order-service-01", "payment-service-01", "depends_on"),
            ("order-service-01", "redis-master-01", "depends_on"),
            ("payment-service-01", "notification-service-01", "depends_on"),
            ("payment-service-01", "mysql-master-01", "depends_on"),
            ("inventory-service-01", "mysql-master-01", "depends_on"),
            ("nginx-lb-01", "api-gateway-01", "routes_to"),
            ("monitor-prometheus", "monitor-grafana", "connected_to"),
            ("k8s-master-01", "k8s-node-01", "member_of"),
            ("k8s-master-01", "k8s-node-02", "member_of"),
        ]
        for parent_name, child_name, rel_type in relations:
            p = db.query(Asset).filter(Asset.name == parent_name).first()
            c = db.query(Asset).filter(Asset.name == child_name).first()
            if p and c:
                r = AssetRelation(parent_id=p.id, child_id=c.id, relation_type=rel_type)
                db.add(r)
        db.commit()
        print(f"播种演示资产关系: {len(relations)} 条")

    db.close()
    print("✅ 演示数据播种完成！")


if __name__ == "__main__":
    seed()