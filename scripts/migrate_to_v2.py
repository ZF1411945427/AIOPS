"""数据迁移脚本：将现有文档重新索引到 Milvus V2.

使用方式：
  python scripts/migrate_to_v2.py
  
功能：
1. 读取所有 KbDocument 记录
2. 对每个文档执行智能切片 + BGE-M3 Embedding
3. 存入 Milvus
4. 更新文档状态为 indexed
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session_for
from app.models import KbDocument
from app.services import rag_engine_v2, vector_store


def main():
    print("=" * 60)
    print("知识库 V2 迁移脚本")
    print("将现有文档索引到 Milvus (BGE-M3 Embedding)")
    print("=" * 60)

    # 检查 Milvus 连接
    try:
        stats = vector_store.get_stats()
        print(f"✅ Milvus 连接正常，当前切片数: {stats.get('total_chunks', 0)}")
    except Exception as e:
        print(f"❌ Milvus 连接失败: {e}")
        sys.exit(1)

    # 获取数据库会话
    db = next(get_session_for("sqlite"))

    # 读取所有文档
    docs = db.query(KbDocument).all()
    if not docs:
        print("📭 数据库中没有文档，无需迁移")
        return

    print(f"\n📄 找到 {len(docs)} 个文档，开始索引...\n")

    success_count = 0
    fail_count = 0

    for doc in docs:
        print(f"  [{doc.id}] {doc.title[:40]}...", end=" ")
        if not doc.content or not doc.content.strip():
            print("⚠️ 内容为空，跳过")
            fail_count += 1
            continue

        try:
            success, msg = rag_engine_v2.index_document_v2(db, doc.id)
            if success:
                print(f"✅ {msg}")
                success_count += 1
            else:
                print(f"❌ {msg}")
                fail_count += 1
        except Exception as e:
            print(f"❌ 异常: {e}")
            fail_count += 1

    # 最终统计
    final_stats = vector_store.get_stats()
    print("\n" + "=" * 60)
    print(f"迁移完成！")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  Milvus 总切片数: {final_stats.get('total_chunks', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
