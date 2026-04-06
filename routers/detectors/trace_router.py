"""
交易分析 API 路由
================
端点:
  POST   /detectors/trace/analyze          -- 分析交易调用链
  GET    /detectors/trace/supported-chains  -- 支持的区块链列表
  GET    /detectors/trace/signatures        -- 4-byte 签名查询 (供前端)
  GET    /detectors/trace/stats             -- 签名库统计信息

参考文档: docs/dev-plan-trace-analysis.md §3.7
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from detectors.trace.analyzer import TxTraceAnalyzer
from detectors.trace.signature_db import SignatureDB
from detectors.trace.provider import MultiRpcClient
from detectors.trace.behaviors.flash_loan import FlashLoanDetector
from detectors.trace.behaviors.token_flow import TokenFlowDetector

logger = logging.getLogger(__name__)

trace_router = APIRouter(prefix="/detectors/trace", tags=["trace-analysis"])

# 全局单例 (延迟初始化, 在首次请求时创建)
_analyzer: TxTraceAnalyzer | None = None
_sig_db: SignatureDB | None = None


def _get_analyzer() -> TxTraceAnalyzer:
    """获取全局分析器实例 (懒加载)"""
    global _analyzer
    if _analyzer is None:
        logger.info("[trace_router] Initializing TxTraceAnalyzer...")
        _analyzer = TxTraceAnalyzer()
    return _analyzer


def _get_sig_db() -> SignatureDB:
    """获取全局签名数据库实例 (懒加载)"""
    global _sig_db
    if _sig_db is None:
        _sig_db = SignatureDB()
    return _sig_db


# ================================================================
# Request/Response 模型
# ================================================================

class AnalyzeRequest(BaseModel):
    """分析请求体"""
    tx_hash: str = Field(
        ...,
        description="Transaction hash (with 0x prefix)",
        pattern=r"^0x[0-9a-fA-F]{64}$",
        examples=["0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d"],
    )
    chain_id: int = Field(
        default=1,
        ge=1,
        description="Chain ID (1=Ethereum, 56=BSC, 137=Polygon...)",
    )
    run_behavior_detect: bool = Field(
        default=True,
        description="Whether to run behavior detection (flash loan, arbitrage, etc.)",
    )


class AnalyzeResponse(BaseModel):
    """分析响应体 — 直接使用 FullAnalysisResult.to_dict() 结构"""
    meta: dict = {}
    txInfo: dict = {}
    root: dict | None = None
    behaviors: list[dict] = []
    protocols: list[dict] = []
    tokenFlows: list[dict] = []
    balanceChanges: list[dict] = []
    selectorStats: list[dict] = []


# ── 拆分端点的请求/响应模型 ──

class PanelRequest(BaseModel):
    """面板数据请求 — 共享基础参数"""
    tx_hash: str = Field(
        ...,
        description="Transaction hash (with 0x prefix)",
        pattern=r"^0x[0-9a-fA-F]{64}$",
    )
    chain_id: int = Field(default=1, ge=1, description="Chain ID")


# ================================================================
# 端点实现
# ================================================================

@trace_router.post("/analyze", response_model=None)
async def analyze_transaction(req: AnalyzeRequest):
    """
    分析交易的完整调用链

    Request Body:
      { "tx_hash": "0x...", "chain_id": 56, "run_behavior_detect": true }

    Response (FullAnalysisResult):
      {
        "meta": {"totalNodes": 151, "maxDepth": 11, ...},
        "txInfo": {"txHash": "...", "chainId": 56, "status": true, ...},
        "root": { /* nested CallNode tree */ },
        "behaviors": [ /* BehaviorResult[] */ ],
        "protocols": [ /* ProtocolInfo[] */ ],
        "tokenFlows": [ /* TokenFlowItem[] */ ],
        "selectorStats": [{"selector":"0x...","sig":"transfer(...)", "count":12}]
      }
    """
    t0 = time.time()
    analyzer = _get_analyzer()

    try:
        result = await analyzer.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=req.run_behavior_detect,
        )
        elapsed = time.time() - t0
        result.meta["apiElapsedSeconds"] = round(elapsed, 3)

        # 返回字典形式 (FastAPI 自动 JSON 序列化)
        return result.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[analyze] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


# ── 拆分端点: 各面板独立数据获取 (并发友好) ──

@trace_router.post("/call-tree", response_model=None)
async def get_call_tree(req: PanelRequest):
    """
    获取交易调用树数据（仅 root + meta + txInfo + selectorStats）

    适用于 CallTreeView 面板独立加载，避免等待 token flow / behavior 等计算。
    """
    t0 = time.time()
    analyzer = _get_analyzer()
    try:
        result = await analyzer.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=False,
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "meta": result.meta,
            "txInfo": result.tx_info.to_dict(),
            "root": result.root.to_dict() if result.root else None,
            "selectorStats": result.selector_stats,
            "apiElapsedSeconds": elapsed,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[call-tree] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Call tree analysis failed: {str(e)}")


@trace_router.post("/balance-changes", response_model=None)
async def get_balance_changes(req: PanelRequest):
    """
    获取交易余额变化数据

    适用于 BalanceChangesPanel 面板独立加载。
    """
    t0 = time.time()
    analyzer = _get_analyzer()
    try:
        result = await analyzer.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=False,
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "balanceChanges": [b.to_dict() for b in result.balance_changes],
            "apiElapsedSeconds": elapsed,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[balance-changes] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Balance changes analysis failed: {str(e)}")


@trace_router.post("/token-flows", response_model=None)
async def get_token_flows(req: PanelRequest):
    """
    获取 Token 流转数据

    适用于 TokenFlowPanel 面板独立加载。
    """
    t0 = time.time()
    analyzer = _get_analyzer()
    try:
        result = await analyzer.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=False,
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "tokenFlows": [f.to_dict() for f in result.token_flows],
            "apiElapsedSeconds": elapsed,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[token-flows] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Token flows analysis failed: {str(e)}")


@trace_router.post("/behaviors", response_model=None)
async def get_behaviors(req: PanelRequest):
    """
    获取行为检测结果

    适用于 BehaviorPanel 面板独立加载。包含完整分析流程中的行为检测步骤。
    """
    t0 = time.time()
    analyzer = _get_analyzer()
    try:
        result = await analyzer.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=True,
        )
        elapsed = round(time.time() - t0, 3)
        return {
            "behaviors": [b.to_dict() for b in result.behaviors],
            "protocols": [p.to_dict() for p in result.protocols],
            "apiElapsedSeconds": elapsed,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[behaviors] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Behavior detection failed: {str(e)}")


@trace_router.post("/analyze-with-flash-detect", response_model=None)
async def analyze_with_flash_detection(req: AnalyzeRequest):
    """
    分析交易并使用 FlashLoanDetector 进行闪电贷专项检测

    与 /analyze 类似，但使用 FlashLoanDetector 实例（继承自 TxTraceAnalyzer），
    额外运行闪电贷检测逻辑。
    """
    t0 = time.time()
    detector = FlashLoanDetector()

    try:
        result = await detector.analyze(
            tx_hash=req.tx_hash,
            chain_id=req.chain_id,
            run_behavior_detect=True,
        )
        elapsed = time.time() - t0
        result.meta["apiElapsedSeconds"] = round(elapsed, 3)
        result.meta["detectorType"] = "FlashLoanDetector"

        await detector.close()
        return result.to_dict()

    finally:
        await detector.close()


@trace_router.get("/supported-chains")
async def get_supported_chains():
    """
    返回支持的区块链列表 (供前端下拉选择)

    Response:
      [
        {"chainId": 1, "name": "Ethereum", "rpcCount": 4, "explorer": "..."},
        {"chainId": 56, "name": "BSC", ...},
        ...
      ]
    """
    return MultiRpcClient.supported_chains()


@trace_router.get("/signatures")
async def search_signatures(
    prefix: str = Query(default="", description="Selector hex prefix, e.g. '0xa90'"),
    hex: str = Query(default="", alias="hex", description="Exact selector, e.g. '0xa9059cbb'. Returns ALL signatures for this selector."),
    limit: int = Query(default=20, ge=1, le=100, description="Max results (for prefix search)"),
):
    """
    前端调用: 根据 selector 搜索函数签名

    两种模式:
      ?prefix=0xa905&limit=20   -- 前缀模糊搜索（返回多条 selector 的最佳签名）
      ?hex=0xa9059cbb           -- 精确查询该 selector 的全部候选签名

    Response (prefix mode):
      {"results": [{"selector":"...", "signature":"..."}], "total": N}

    Response (exact/hex mode):
      {
        "selector": "0xa9059cbb",
        "signatures": [
          {"text": "transfer(address,uint256)", "num_results": 12345},
          {"text": "transfer(address,address,uint256)", ...}
        ],
        "total": 2,
        "source": "db" | "api"
      }
    """
    db = _get_sig_db()

    # 精确查询模式：返回一个 selector 的全部签名
    if hex:
        result = db.lookup_by_hex(hex.strip())
        return result

    total = db.count()

    if not prefix:
        return {"results": [], "total": total}

    results = db.prefix_search(prefix.strip(), limit=limit)
    return {"results": results, "total": total}


@trace_router.get("/stats")
async def get_signature_stats():
    """
    签名库统计 (显示在前端页面底部)

    Response:
      {
        "total_signatures": 420000,
        "unique_selectors": 85000,
        "db_path": "data/signatures.db",
        "is_fallback_mode": false
      }
    """
    db = _get_sig_db()
    return db.get_stats()
