from datetime import datetime
from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AgentGroundTruth, AgentGroundTruthRun, AIProvider
from app.services import ab_test_service, agent_eval_service
import json
import time

router = APIRouter(prefix="/agent/api/ground-truth", tags=["agent_ground_truth"])


def _gt_to_dict(g):
    return {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "question": g.question,
        "expected_answer": g.expected_answer,
        "expected_tools": json.loads(g.expected_tools) if g.expected_tools else [],
        "tags": g.tags or "",
        "difficulty": g.difficulty,
        "is_active": bool(g.is_active),
        "created_at": g.created_at.strftime("%Y-%m-%d %H:%M:%S") if g.created_at else None,
    }


def _run_to_dict(r):
    return {
        "id": r.id,
        "test_id": r.test_id,
        "session_id": r.session_id,
        "provider_id": r.provider_id,
        "model_name": r.model_name,
        "actual_answer": (r.actual_answer or "")[:500],
        "answer_score": r.answer_score,
        "tool_score": r.tool_score,
        "total_score": r.total_score,
        "latency_ms": r.latency_ms,
        "error": r.error or "",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }


@router.get("/tests")
def list_tests(
    category: str = "",
    is_active: bool = None,
    db: Session = Depends(get_db),
):
    q = db.query(AgentGroundTruth)
    if category:
        q = q.filter(AgentGroundTruth.category == category)
    if is_active is not None:
        q = q.filter(AgentGroundTruth.is_active == is_active)
    items = q.order_by(AgentGroundTruth.created_at.desc()).all()
    return JSONResponse({"items": [_gt_to_dict(g) for g in items], "total": len(items)})


@router.post("/tests")
def create_test(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        gt = AgentGroundTruth(
            name=payload.get("name", ""),
            category=payload.get("category", "qa"),
            question=payload.get("question", ""),
            expected_answer=payload.get("expected_answer", ""),
            expected_tools=json.dumps(payload.get("expected_tools", []), ensure_ascii=False),
            tags=payload.get("tags", ""),
            difficulty=payload.get("difficulty", "medium"),
            is_active=True,
        )
        db.add(gt)
        db.commit()
        db.refresh(gt)
        return JSONResponse({"ok": True, "id": gt.id, "item": _gt_to_dict(gt)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.put("/tests/{test_id}")
def update_test(test_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        gt = db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).first()
        if not gt:
            return JSONResponse({"error": "not found"}, status_code=404)
        if "name" in payload:
            gt.name = payload["name"]
        if "category" in payload:
            gt.category = payload["category"]
        if "question" in payload:
            gt.question = payload["question"]
        if "expected_answer" in payload:
            gt.expected_answer = payload["expected_answer"]
        if "expected_tools" in payload:
            gt.expected_tools = json.dumps(payload["expected_tools"], ensure_ascii=False)
        if "tags" in payload:
            gt.tags = payload["tags"]
        if "difficulty" in payload:
            gt.difficulty = payload["difficulty"]
        if "is_active" in payload:
            gt.is_active = payload["is_active"]
        gt.updated_at = datetime.now()
        db.commit()
        db.refresh(gt)
        return JSONResponse({"ok": True, "item": _gt_to_dict(gt)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.delete("/tests/{test_id}")
def delete_test(test_id: int, db: Session = Depends(get_db)):
    try:
        db.query(AgentGroundTruthRun).filter(AgentGroundTruthRun.test_id == test_id).delete()
        db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).delete()
        db.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/tests/{test_id}/run")
def run_single_test(test_id: int, provider_id: int = Query(0), db: Session = Depends(get_db)):
    try:
        gt = db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).first()
        if not gt:
            return JSONResponse({"error": "not found"}, status_code=404)

        provider = None
        if provider_id:
            provider = db.query(AIProvider).filter(AIProvider.id == provider_id, AIProvider.is_enabled == True).first()
        if not provider:
            provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        if not provider:
            return JSONResponse({"error": "No enabled AI provider"})

        from app.services.agent_service import call_llm, get_mcp_manifest
        from sqlalchemy import text

        system_prompt = f"你是一个运维 AI 助手。请回答用户的问题。\n\n预期行为参考：{gt.expected_answer}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": gt.question},
        ]

        openai_tools = []
        mcp_tools = get_mcp_manifest()
        for t in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
            })

        start = time.time()
        response = call_llm(provider, messages, openai_tools if openai_tools else None)
        latency = int((time.time() - start) * 1000)

        if "error" in response:
            return JSONResponse({"error": response["error"]}, status_code=500)

        choice = response.get("choices", [{}])[0]
        resp_msg = choice.get("message", {})
        actual_answer = resp_msg.get("content", "") or ""
        tool_calls_raw = resp_msg.get("tool_calls") or []
        actual_tools = [tc["function"]["name"] for tc in tool_calls_raw] if tool_calls_raw else []

        expected_tools = json.loads(gt.expected_tools) if gt.expected_tools else []
        tool_score = _calc_tool_score(actual_tools, expected_tools)
        answer_score = _calc_answer_similarity(actual_answer, gt.expected_answer)
        total_score = round(answer_score * 0.6 + tool_score * 0.4, 3)

        run = AgentGroundTruthRun(
            test_id=test_id, provider_id=provider.id,
            model_name=provider.model or "",
            actual_answer=actual_answer,
            actual_tools=json.dumps(actual_tools),
            answer_score=answer_score,
            tool_score=tool_score,
            total_score=total_score,
            latency_ms=latency,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return JSONResponse({"ok": True, "run": _run_to_dict(run)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/runs")
def list_runs(test_id: int = Query(0), limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    q = db.query(AgentGroundTruthRun)
    if test_id:
        q = q.filter(AgentGroundTruthRun.test_id == test_id)
    items = q.order_by(AgentGroundTruthRun.created_at.desc()).limit(limit).all()
    return JSONResponse({"items": [_run_to_dict(r) for r in items], "total": len(items)})


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_tests = db.query(AgentGroundTruth).count()
    active_tests = db.query(AgentGroundTruth).filter(AgentGroundTruth.is_active == True).count()
    total_runs = db.query(AgentGroundTruthRun).count()
    avg_score = db.query(
        AgentGroundTruthRun.total_score
    ).filter(
        AgentGroundTruthRun.total_score > 0
    ).all()
    avg = round(sum(s[0] for s in avg_score) / len(avg_score), 3) if avg_score else 0
    by_category = {}
    for cat in db.query(AgentGroundTruth.category).distinct().all():
        c = cat[0]
        cnt = db.query(AgentGroundTruth).filter(AgentGroundTruth.category == c).count()
        by_category[c] = cnt
    return JSONResponse({
        "total_tests": total_tests,
        "active_tests": active_tests,
        "total_runs": total_runs,
        "avg_total_score": avg,
        "by_category": by_category,
    })


def _calc_tool_score(actual: list, expected: list) -> float:
    if not expected:
        return 1.0
    if not actual:
        return 0.0
    hits = sum(1 for t in expected if t in actual)
    return round(hits / len(expected), 3)


def _calc_answer_similarity(actual: str, expected: str) -> float:
    if not expected:
        return 1.0
    if not actual:
        return 0.0
    actual_set = set(actual.lower().split())
    expected_set = set(expected.lower().split())
    if not expected_set:
        return 1.0
    intersection = actual_set & expected_set
    jaccard = len(intersection) / len(expected_set)
    return round(min(jaccard, 1.0), 3)
