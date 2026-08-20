"""语音服务(STT/TTS)云引擎配置 CRUD。

对应 CONTRACT.md 26.6。前端「智能体配置(AiProvidersView.vue)」面板调用。
敏感字段 access_key_secret: 列表/详情一律返回 has_access_key(bool), 绝不返回明文/密文;
前端编辑时置空, 保存空值=不更新(与 AIProvider 一致)。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import VoiceProvider
from app.logger import logger

router = APIRouter(prefix="/ai/voice", tags=["ai-voice"])


def _to_dict(p: VoiceProvider):
    return {
        "id": p.id,
        "name": p.name,
        "engine": p.engine,
        "engine_type": p.engine_type,
        "app_id": p.app_id,
        "access_key_id": p.access_key_id,
        "has_access_key": bool(p.access_key_secret),
        "region": p.region,
        "stt_model": p.stt_model,
        "tts_voice": p.tts_voice,
        "base_url": p.base_url,
        "extra_json": p.extra_json,
        "is_enabled": p.is_enabled,
        "priority": p.priority,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/providers")
def voice_providers_list(db: Session = Depends(get_db)):
    providers = db.query(VoiceProvider).order_by(VoiceProvider.priority.asc()).all()
    return {"providers": [_to_dict(p) for p in providers]}


@router.get("/resolved")
def voice_resolved(db: Session = Depends(get_db)):
    """返回当前 STT / TTS 各自生效的引擎(前端展示用)。"""
    from app.services import voice_service
    stt = voice_service.resolve_stt_provider(db)
    tts = voice_service.resolve_tts_provider(db)
    return {
        "stt": {
            "engine": stt.engine if stt else "local",
            "name": stt.name if stt else "本地 sherpa-onnx",
            "configured": stt is not None,
        },
        "tts": {
            "engine": tts.engine if tts else "edge-tts",
            "name": tts.name if tts else "edge-tts(微软)",
            "configured": tts is not None,
        },
    }


@router.post("/providers/create")
def voice_provider_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        return {"status": "error", "message": "名称不能为空"}
    exists = db.query(VoiceProvider).filter(VoiceProvider.name == name).first()
    if exists:
        return {"status": "error", "message": "名称已存在"}
    p = VoiceProvider(
        name=name,
        engine=payload.get("engine", "aliyun"),
        engine_type=payload.get("engine_type", "both"),
        app_id=payload.get("app_id", "") or "",
        access_key_id=payload.get("access_key_id", "") or "",
        region=payload.get("region", "") or "",
        stt_model=payload.get("stt_model", "") or "",
        tts_voice=payload.get("tts_voice", "") or "",
        base_url=payload.get("base_url", "") or "",
        extra_json=payload.get("extra_json", "{}") or "{}",
        is_enabled=bool(payload.get("is_enabled", True)),
        priority=int(payload.get("priority", 10) or 10),
    )
    if payload.get("access_key_secret"):
        p.set_access_key_secret(payload["access_key_secret"])
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"status": "ok", "id": p.id}


@router.put("/providers/{provider_id}/edit")
def voice_provider_edit(provider_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    p = db.query(VoiceProvider).filter(VoiceProvider.id == provider_id).first()
    if not p:
        return {"status": "error", "message": "配置不存在"}
    p.name = (payload.get("name") or "").strip() or p.name
    p.engine = payload.get("engine", p.engine)
    p.engine_type = payload.get("engine_type", p.engine_type)
    p.app_id = payload.get("app_id", p.app_id) or ""
    p.access_key_id = payload.get("access_key_id", p.access_key_id) or ""
    p.region = payload.get("region", p.region) or ""
    p.stt_model = payload.get("stt_model", p.stt_model) or ""
    p.tts_voice = payload.get("tts_voice", p.tts_voice) or ""
    p.base_url = payload.get("base_url", p.base_url) or ""
    p.extra_json = payload.get("extra_json", p.extra_json) or "{}"
    p.is_enabled = bool(payload.get("is_enabled", p.is_enabled))
    p.priority = int(payload.get("priority", p.priority) or 10)
    if payload.get("access_key_secret"):
        p.set_access_key_secret(payload["access_key_secret"])
    p.updated_at = datetime.now()
    db.commit()
    return {"status": "ok"}


@router.post("/providers/{provider_id}/toggle")
def voice_provider_toggle(provider_id: int, db: Session = Depends(get_db)):
    p = db.query(VoiceProvider).filter(VoiceProvider.id == provider_id).first()
    if p:
        p.is_enabled = not p.is_enabled
        db.commit()
    return {"status": "ok", "enabled": p.is_enabled if p else None}


@router.delete("/providers/{provider_id}/delete")
def voice_provider_delete(provider_id: int, db: Session = Depends(get_db)):
    p = db.query(VoiceProvider).filter(VoiceProvider.id == provider_id).first()
    if p:
        db.delete(p)
        db.commit()
    return {"status": "ok"}


@router.post("/providers/{provider_id}/test")
def voice_provider_test(provider_id: int, db: Session = Depends(get_db)):
    """用该配置实测一次 STT/TTS(不落库)。返回结果供前端判断密钥/配置是否正确。"""
    p = db.query(VoiceProvider).filter(VoiceProvider.id == provider_id).first()
    if not p:
        return {"status": "error", "message": "配置不存在"}
    from app.services import voice_service

    result = {"engine": p.engine, "engine_type": p.engine_type, "stt": None, "tts": None}
    # 手动构造一个临时标记, 让 voice_service 的 resolve_* 能选中本条:
    # 这里直接调私有实现做连通性测试, 复用真实引擎函数。
    if p.engine_type in ("stt", "both") and hasattr(voice_service, f"_{p.engine}_stt"):
        try:
            # 用一个很短的无 PCM 音频会很糟; 改为仅验证鉴权 token 获取
            ok, msg = _test_auth(p)
            result["auth"] = {"ok": ok, "msg": msg}
        except Exception as e:
            result["auth"] = {"ok": False, "msg": str(e)}

    # TTS 可用真实短文本验证(云端可免费合成, 成本极低)
    if p.engine_type in ("tts", "both"):
        try:
            if p.engine == "aliyun":
                data, mime = voice_service._aliyun_tts(p, "阿里云语音测试")
                result["tts"] = {"ok": bool(data), "bytes": len(data) if data else 0}
            elif p.engine == "baidu":
                data, mime = voice_service._baidu_tts(p, "百度语音测试")
                result["tts"] = {"ok": bool(data), "bytes": len(data) if data else 0}
            elif p.engine == "tencent":
                data, mime = voice_service._tencent_tts(p, "腾讯语音测试")
                result["tts"] = {"ok": bool(data), "bytes": len(data) if data else 0}
            elif p.engine == "edge-tts":
                data, mime, eng = voice_service._edge_tts("语音测试", "jarvis")
                result["tts"] = {"ok": bool(data), "bytes": len(data) if data else 0}
        except Exception as e:
            result["tts"] = {"ok": False, "msg": str(e)}

    ok_all = (result.get("stt") or {"ok": True}).get("ok", True) and (result.get("tts") or {"ok": True}).get("ok", True) and (result.get("auth") or {"ok": True}).get("ok", True)
    return {**result, "status": "ok" if ok_all else "error"}


def _test_auth(p: VoiceProvider):
    """仅验证各家鉴权 token/密钥是否正确(不消耗识别额度)。"""
    if not p.get_access_key_secret() or not p.access_key_id:
        return False, "缺少 AccessKeyId 或 SecretKey"
    try:
        if p.engine == "aliyun":
            from app.services.voice_service import _aliyun_get_token
            token = _aliyun_get_token(p.access_key_id, p.get_access_key_secret())
            return (True, "连通, Token 获取成功") if token else (False, "Token 获取失败, 请检查 AccessKeyId/SecretKey")
        if p.engine == "baidu":
            from app.services.voice_service import _baidu_get_token
            token = _baidu_get_token(p.access_key_id, p.get_access_key_secret())
            return (True, "连通, Token 获取成功") if token else (False, "Token 获取失败, 请检查 API Key/Secret Key")
        if p.engine == "tencent":
            return True, "腾讯云(需 tencentcloud-sdk-python, 未做连通预检)"
        if p.engine == "edge-tts":
            return True, "edge-tts: 无需密钥"
        return True, "本地/其他引擎: 无需密钥"
    except Exception as e:
        return False, f"测试异常: {e}"
