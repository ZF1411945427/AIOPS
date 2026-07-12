"""Embedding 服务：BGE-small-zh 本地 + OpenAI API 双模式.

模式：
- bge-m3（默认）：本地 BGE-small-zh-v1.5 模型，中文效果好，CPU 友好
- openai：OpenAI text-embedding-3-large，需要 API Key
"""
import os
from pathlib import Path
import threading
from typing import List, Optional

# 全局缓存
_bge_model = None
_bge_lock = threading.Lock()

# 配置
DEFAULT_MODE = "bge-m3"
OPENAI_MODEL = "text-embedding-3-large"
OPENAI_DIMENSION = 512  # BGE-small-zh 输出维度
_LOCAL_MODEL_DIR = str(Path(__file__).resolve().parent.parent.parent / "models" / "bge-small-zh-v1.5")


def get_embedding_mode() -> str:
    """获取当前 embedding 模式（从环境变量或配置读取）"""
    return os.environ.get("EMBEDDING_MODE", DEFAULT_MODE)


def set_embedding_mode(mode: str):
    """设置 embedding 模式"""
    os.environ["EMBEDDING_MODE"] = mode


def _get_bge_model():
    """懒加载 BGE 模型（从项目内本地目录加载）"""
    global _bge_model
    if _bge_model is not None:
        return _bge_model
    with _bge_lock:
        if _bge_model is not None:
            return _bge_model
        from app.logger import logger
        logger.info(f"加载 BGE 模型: {_LOCAL_MODEL_DIR} ...")
        from sentence_transformers import SentenceTransformer
        _bge_model = SentenceTransformer(_LOCAL_MODEL_DIR)
        logger.info("BGE 模型加载完成")
        return _bge_model


def _embed_bge_m3(texts: List[str]) -> List[List[float]]:
    """使用 BGE 模型生成 embedding"""
    model = _get_bge_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return embeddings.tolist()


def _embed_openai(texts: List[str]) -> List[List[float]]:
    """使用 OpenAI API 生成 embedding"""
    import openai
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("未配置 OPENAI_API_KEY 环境变量")
    client = openai.OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=OPENAI_MODEL,
        input=texts,
        dimensions=OPENAI_DIMENSION,
    )
    return [item.embedding for item in response.data]


def embed_texts(texts: List[str], mode: Optional[str] = None) -> List[List[float]]:
    """生成文本的 embedding 向量
    
    Args:
        texts: 文本列表
        mode: embedding 模式，None 则使用默认模式
    
    Returns:
        向量列表，每个向量为 List[float]
    """
    if not texts:
        return []
    mode = mode or get_embedding_mode()
    if mode == "openai":
        return _embed_openai(texts)
    else:
        return _embed_bge_m3(texts)


def embed_query(query: str, mode: Optional[str] = None) -> List[float]:
    """生成单条查询的 embedding"""
    results = embed_texts([query], mode)
    return results[0] if results else []


def get_embedding_dimension(mode: Optional[str] = None) -> int:
    """获取 embedding 向量维度"""
    mode = mode or get_embedding_mode()
    if mode == "openai":
        return OPENAI_DIMENSION
    return 512  # BGE-small-zh-v1.5 输出维度


def preload_model():
    """后台线程预加载 BGE-M3 模型（避免首次请求阻塞）"""
    def _load():
        try:
            _get_bge_model()
        except Exception as e:
            logger.warning(f"预加载 BGE-M3 失败: {e}")
    t = threading.Thread(target=_load, daemon=True)
    t.start()


# 启动时自动预加载
preload_model()
