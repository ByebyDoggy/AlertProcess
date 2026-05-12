"""
Service 层 - 规则链业务逻辑

封装规则链的业务逻辑，包括 CRUD、校验、执行等。
"""

from typing import Optional, List
import uuid
import json
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import HTTPException

from services.base import BaseService
from repositories import RuleChainRepository
from contracts.rule_chain import (
    RuleChainCreateRequest,
    RuleChainUpdateRequest,
    RuleChainResponse,
    ValidateRequest,
    ValidateResponse,
    ValidateError,
    ExecuteRequest,
    ExecuteResponse,
)
from database.models import RuleChainDB
from engine.parser import ChainParser
from engine.validator import ChainValidator
from engine.executor import ChainExecutor
from nodes.base import NodeRegistry, NodeCategory


class RuleChainService(BaseService[RuleChainDB]):
    """规则链业务逻辑服务"""

    def __init__(self, db: Session):
        super().__init__(db)
        self.repo = RuleChainRepository(db)

    def get_chain(self, chain_id: str) -> RuleChainResponse:
        """
        获取规则链

        Args:
            chain_id: 规则链 ID

        Returns:
            规则链响应

        Raises:
            HTTPException: 规则链不存在
        """
        chain = self.repo.get_by_id(chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        return self._to_response(chain)

    def list_chains(self, skip: int = 0, limit: int = 100) -> List[RuleChainResponse]:
        """
        获取规则链列表

        Args:
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            规则链列表
        """
        chains = self.repo.get_all(skip=skip, limit=limit)
        return [self._to_response(chain) for chain in chains]

    def create_chain(self, request: RuleChainCreateRequest) -> RuleChainResponse:
        """
        创建规则链

        Args:
            request: 创建请求

        Returns:
            创建的规则链

        Raises:
            HTTPException: 创建失败
        """
        # 生成 ID
        chain_id = str(uuid.uuid4())

        # 构建配置
        chain_config = {
            "nodes": [node.model_dump(by_alias=True, exclude_none=True) for node in request.nodes],
            "edges": [edge.model_dump(by_alias=True, exclude_none=True) for edge in request.edges],
            "sequence_phases": request.sequence_phases or [],
        }

        # 创建数据库实体
        db_chain = RuleChainDB(
            id=chain_id,
            name=request.name,
            description=request.description,
            chain_config=json.dumps(chain_config),
            enabled=1 if request.enabled else 0,
        )

        # 保存到数据库
        created = self.repo.create(db_chain)

        return self._to_response(created)

    def update_chain(self, chain_id: str, request: RuleChainUpdateRequest) -> RuleChainResponse:
        """
        更新规则链

        Args:
            chain_id: 规则链 ID
            request: 更新请求

        Returns:
            更新后的规则链

        Raises:
            HTTPException: 规则链不存在
        """
        chain = self.repo.get_by_id(chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        # 准备更新数据
        updates = {}

        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.enabled is not None:
            updates["enabled"] = 1 if request.enabled else 0

        # 更新配置
        if request.nodes is not None or request.edges is not None or request.sequence_phases is not None:
            existing_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config

            nodes = request.nodes if request.nodes is not None else existing_config.get("nodes", [])
            edges = request.edges if request.edges is not None else existing_config.get("edges", [])
            sequence_phases = request.sequence_phases if request.sequence_phases is not None else existing_config.get("sequence_phases", [])

            chain_config = {
                "nodes": [node.model_dump(by_alias=True, exclude_none=True) if hasattr(node, 'model_dump') else node for node in nodes],
                "edges": [edge.model_dump(by_alias=True, exclude_none=True) if hasattr(edge, 'model_dump') else edge for edge in edges],
                "sequence_phases": sequence_phases,
            }
            updates["chain_config"] = json.dumps(chain_config)

        # 执行更新
        updated = self.repo.update(chain_id, updates)

        return self._to_response(updated)

    def delete_chain(self, chain_id: str) -> dict:
        """
        删除规则链

        Args:
            chain_id: 规则链 ID

        Returns:
            删除结果

        Raises:
            HTTPException: 规则链不存在
        """
        success = self.repo.delete(chain_id)
        if not success:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        return {"status": "success", "message": "Rule chain deleted"}

    def validate_chain(self, request: ValidateRequest) -> ValidateResponse:
        """
        校验规则链配置

        Args:
            request: 校验请求

        Returns:
            校验结果
        """
        errors = []
        warnings = []

        # 检查是否为空
        if not request.nodes:
            error = ValidateError(
                type="error",
                severity="error",
                code="EMPTY_CHAIN",
                field="nodes",
                field_path="nodes",
                message="规则链至少需要一个节点",
                suggestion="添加一个 input 类节点作为规则链入口。",
            )
            return ValidateResponse(valid=False, errors=[error], normalized_config={"nodes": [], "edges": []})

        # 构建配置
        normalized_config = {
            "nodes": [node.model_dump(by_alias=True, exclude_none=True) for node in request.nodes],
            "edges": [edge.model_dump(by_alias=True, exclude_none=True) for edge in request.edges],
            "sequence_phases": [],
        }

        # 解析规则链
        parsed_chain = ChainParser.parse(normalized_config)

        # 执行校验
        validation_errors = ChainValidator().validate(parsed_chain)

        for validation_error in validation_errors:
            target = errors if validation_error.level == "error" else warnings
            target.append(self._to_validate_error(validation_error))

        # 统计信息
        trigger_count = sum(
            1 for node in parsed_chain.nodes
            if NodeRegistry.get(node.node_type)
            and NodeRegistry.get(node.node_type).category == NodeCategory.INPUT
        )

        stats = {
            "node_count": len(request.nodes),
            "edge_count": len(request.edges),
            "trigger_count": trigger_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }

        return ValidateResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_config=normalized_config,
            stats=stats,
        )

    async def execute_chain(self, request: ExecuteRequest) -> ExecuteResponse:
        """
        执行规则链

        Args:
            request: 执行请求

        Returns:
            执行结果

        Raises:
            HTTPException: 规则链不存在或执行失败
        """
        import time

        # 获取规则链
        chain = self.repo.get_by_id(request.chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        # 解析配置
        chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config
        parsed_chain = ChainParser.parse(chain_config)

        # 执行规则链
        executor = ChainExecutor()
        execution_id = str(uuid.uuid4())

        start_time = time.monotonic()
        try:
            ctx = await executor.execute(parsed_chain, request.alert_data, dry_run=request.dry_run)
            duration_ms = (time.monotonic() - start_time) * 1000

            return ExecuteResponse(
                success=ctx.get_success(),
                execution_id=execution_id,
                chain_id=request.chain_id,
                duration_ms=duration_ms,
                result={
                    "final_score": ctx.final_score,
                    "final_severity": ctx.final_severity,
                    "labels": ctx.collected_labels,
                    "actions_executed": ctx.actions_executed,
                    "errors": ctx.errors,
                },
                error=None if ctx.get_success() else "; ".join(ctx.errors),
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            return ExecuteResponse(
                success=False,
                execution_id=execution_id,
                chain_id=request.chain_id,
                duration_ms=duration_ms,
                result={},
                error=str(e),
            )

    def search_chains(
        self,
        keyword: Optional[str] = None,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[RuleChainResponse]:
        """
        搜索规则链

        Args:
            keyword: 关键词
            enabled: 是否启用
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            符合条件的规则链列表
        """
        chains = self.repo.search(keyword=keyword, enabled=enabled, skip=skip, limit=limit)
        return [self._to_response(chain) for chain in chains]

    def toggle_enabled(self, chain_id: str, enabled: bool) -> RuleChainResponse:
        """
        切换规则链启用状态

        Args:
            chain_id: 规则链 ID
            enabled: 是否启用

        Returns:
            更新后的规则链

        Raises:
            HTTPException: 规则链不存在
        """
        chain = self.repo.toggle_enabled(chain_id, enabled)
        if not chain:
            raise HTTPException(status_code=404, detail="Rule chain not found")

        return self._to_response(chain)

    def _to_response(self, chain: RuleChainDB) -> RuleChainResponse:
        """将数据库模型转换为响应模型"""
        chain_config = json.loads(chain.chain_config) if isinstance(chain.chain_config, str) else chain.chain_config

        return RuleChainResponse(
            id=chain.id,
            name=chain.name,
            description=chain.description,
            enabled=bool(chain.enabled),
            chain_config=chain_config,
            created_at=chain.created_at,
            updated_at=chain.updated_at,
        )

    def _to_validate_error(self, error) -> ValidateError:
        """将校验错误转换为契约模型"""
        severity = "warning" if error.level == "warning" else "error"
        return ValidateError(
            type=severity,
            severity=severity,
            code=self._validate_error_code(error.field, error.message),
            field=error.field,
            field_path=self._validate_field_path(error),
            message=error.message,
            node_id=error.node_id,
            edge_id=error.edge_id,
            suggestion=self._suggest_fix(error),
        )

    def _validate_error_code(self, field: str, message: str) -> str:
        """生成错误代码"""
        if field == "topology" and "node type" in message.lower():
            return "UNKNOWN_NODE_TYPE"
        if field == "topology" and ("未知节点类型" in message or "δ֪" in message):
            return "UNKNOWN_NODE_TYPE"
        if field:
            return field.upper()
        return "VALIDATION"

    def _validate_field_path(self, error) -> str:
        """生成字段路径"""
        if error.node_id:
            return f"nodes.{error.node_id}.{error.field or 'validation'}"
        if error.edge_id:
            return f"edges.{error.edge_id}.{error.field or 'validation'}"
        return error.field or "chain"

    def _suggest_fix(self, error) -> str | None:
        """生成修复建议"""
        if error.field == "topology" and "未知节点类型" in error.message:
            return "调用 /rule-chain/schema/mcp 获取可用 node_type 后替换。"
        if error.field == "port":
            return "检查 sourcePort/targetPort 是否存在于对应节点 schema 的 outputs/inputs。"
        if error.field == "data_type":
            return "调用 /rule-chain/schema/connection-rules 检查端口 data_type 是否兼容。"
        if error.field == "config":
            return "按节点 config_schema 修正 config 字段。"
        if error.field == "structure":
            return "确保规则链包含且只包含一个 input 节点，并且所有必要节点从 trigger 可达。"
        return None
