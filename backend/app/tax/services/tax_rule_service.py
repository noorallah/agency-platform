"""Versioned tax rule CRUD and tax engine simulation services."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.common.audit.models.audit_log import AuditLog
from app.common.audit.services import record_audit
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.utils.dates import utc_now
from app.products.models import Product
from app.tax.models import (
    TaxComponent,
    TaxProfile,
    TaxProfileComponent,
    TaxRule,
    TaxRuleAction,
    TaxRuleCondition,
    TaxRuleExecutionLog,
)
from app.tax.schemas import (
    TaxRuleActionType,
    TaxRuleActionWrite,
    TaxRuleComponentPreview,
    TaxRuleConditionOperator,
    TaxRuleConditionWrite,
    TaxRuleEvaluationDecision,
    TaxRuleExecutionLogResponse,
    TaxRulePriorityRecord,
    TaxRuleResponse,
    TaxRuleSimulationRequest,
    TaxRuleSimulationResponse,
    TaxRuleWrite,
    TaxStatus,
)


class TaxRuleService:
    """Manage versioned tax rules and execute simulation previews."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_rules(
        self,
        *,
        firm_scope: UUID,
        page: int,
        page_size: int,
        search: str | None,
        country_id: UUID | None,
        business_profile_id: UUID | None,
        tax_profile_id: UUID | None,
        transaction_type: str | None,
        status: TaxStatus | None,
        include_deleted: bool,
    ) -> tuple[list[TaxRule], int]:
        statement = self._base_rule_query(firm_scope=firm_scope)
        count = (
            select(func.count())
            .select_from(TaxRule)
            .where(TaxRule.firm_id == firm_scope)
        )
        if not include_deleted:
            statement = statement.where(TaxRule.is_deleted.is_(False))
            count = count.where(TaxRule.is_deleted.is_(False))
        if country_id is not None:
            statement = statement.where(TaxRule.country_id == country_id)
            count = count.where(TaxRule.country_id == country_id)
        if business_profile_id is not None:
            statement = statement.where(
                TaxRule.business_profile_id == business_profile_id
            )
            count = count.where(TaxRule.business_profile_id == business_profile_id)
        if tax_profile_id is not None:
            statement = statement.where(TaxRule.tax_profile_id == tax_profile_id)
            count = count.where(TaxRule.tax_profile_id == tax_profile_id)
        if status is not None:
            statement = statement.where(TaxRule.status == status.value)
            count = count.where(TaxRule.status == status.value)
        if search:
            term = f"%{search.strip()}%"
            condition = or_(
                TaxRule.code.ilike(term),
                TaxRule.name.ilike(term),
                TaxRule.description.ilike(term),
            )
            statement = statement.where(condition)
            count = count.where(condition)
        if transaction_type:
            transaction_term = transaction_type.strip().upper()
            statement = statement.where(
                TaxRule.conditions.any(
                    TaxRuleCondition.is_deleted.is_(False),
                    TaxRuleCondition.field_key == "transaction_type",
                    TaxRuleCondition.value_text == transaction_term,
                )
            )
            count = count.where(
                TaxRule.conditions.any(
                    TaxRuleCondition.is_deleted.is_(False),
                    TaxRuleCondition.field_key == "transaction_type",
                    TaxRuleCondition.value_text == transaction_term,
                )
            )
        rows = self._session.scalars(
            statement.order_by(
                TaxRule.priority.asc(),
                TaxRule.code.asc(),
                TaxRule.version_number.desc(),
                TaxRule.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), int(self._session.scalar(count) or 0)

    def list_conditions(
        self, *, firm_scope: UUID, rule_id: UUID | None = None
    ) -> list[TaxRuleCondition]:
        statement = select(TaxRuleCondition).where(
            TaxRuleCondition.firm_id == firm_scope,
            TaxRuleCondition.is_deleted.is_(False),
        )
        if rule_id is not None:
            statement = statement.where(TaxRuleCondition.tax_rule_id == rule_id)
        return list(
            self._session.scalars(
                statement.order_by(
                    TaxRuleCondition.tax_rule_id.asc(),
                    TaxRuleCondition.sequence.asc(),
                )
            ).all()
        )

    def list_priorities(self, *, firm_scope: UUID) -> list[TaxRulePriorityRecord]:
        rows = self._session.scalars(
            self._base_rule_query(firm_scope=firm_scope)
            .where(TaxRule.is_deleted.is_(False))
            .order_by(
                TaxRule.priority.asc(),
                TaxRule.code.asc(),
                TaxRule.version_number.desc(),
            )
        ).all()
        return [
            TaxRulePriorityRecord(
                id=row.id,
                code=row.code,
                name=row.name,
                priority=row.priority,
                status=row.status,
                version_number=row.version_number,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                condition_count=len(row.conditions),
                action_count=len(row.actions),
            )
            for row in rows
        ]

    def rule_history(
        self,
        *,
        firm_scope: UUID,
        code: str | None = None,
        version_group_id: UUID | None = None,
    ) -> list[TaxRule]:
        statement = self._base_rule_query(firm_scope=firm_scope).where(
            TaxRule.is_deleted.is_(False)
        )
        if code:
            statement = statement.where(TaxRule.code == code.strip().upper())
        if version_group_id is not None:
            statement = statement.where(TaxRule.version_group_id == version_group_id)
        return list(
            self._session.scalars(
                statement.order_by(TaxRule.code.asc(), TaxRule.version_number.asc())
            ).all()
        )

    def list_execution_logs(
        self,
        *,
        firm_scope: UUID,
        limit: int = 200,
        matched_rule_id: UUID | None = None,
    ) -> list[TaxRuleExecutionLog]:
        statement = select(TaxRuleExecutionLog).where(
            TaxRuleExecutionLog.firm_id == firm_scope
        )
        if matched_rule_id is not None:
            statement = statement.where(
                TaxRuleExecutionLog.matched_rule_id == matched_rule_id
            )
        return list(
            self._session.scalars(
                statement.order_by(TaxRuleExecutionLog.created_at.desc()).limit(limit)
            ).all()
        )

    def create_rule(
        self, data: TaxRuleWrite, *, firm_id: UUID, actor_id: UUID
    ) -> TaxRule:
        self._validate_rule_references(data, firm_scope=firm_id)
        now = utc_now()
        row = TaxRule(
            firm_id=firm_id,
            country_id=data.country_id,
            business_profile_id=data.business_profile_id,
            tax_profile_id=data.tax_profile_id,
            code=data.code,
            name=data.name,
            description=data.description,
            priority=data.priority,
            status=data.status.value,
            version_group_id=uuid4(),
            version_number=1,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        row.conditions = self._build_conditions(
            data.conditions, firm_id=firm_id, actor_id=actor_id
        )
        row.actions = self._build_actions(
            data.actions, firm_id=firm_id, actor_id=actor_id
        )
        self._session.add(row)
        self._flush_conflicts("Tax rule code already exists for this version.")
        record_audit(
            self._session,
            action="tax.rule.created",
            entity_type="tax_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_id,
            after_data={"code": row.code, "version_number": row.version_number},
        )
        self._commit()
        self._session.refresh(row)
        return row

    def update_rule(
        self, rule_id: UUID, data: TaxRuleWrite, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxRule:
        row = self.get_rule(rule_id, firm_scope=firm_scope, include_deleted=True)
        self._validate_rule_references(data, firm_scope=firm_scope)
        if row.status == TaxStatus.DRAFT.value:
            before = {
                "code": row.code,
                "priority": row.priority,
                "status": row.status,
                "version_number": row.version_number,
            }
            row.country_id = data.country_id
            row.business_profile_id = data.business_profile_id
            row.tax_profile_id = data.tax_profile_id
            row.code = data.code
            row.name = data.name
            row.description = data.description
            row.priority = data.priority
            row.status = data.status.value
            row.effective_from = data.effective_from
            row.effective_to = data.effective_to
            row.updated_by = actor_id
            self._replace_conditions(row, data.conditions, actor_id=actor_id)
            self._replace_actions(row, data.actions, actor_id=actor_id)
            self._flush_conflicts("Tax rule code already exists for this version.")
            record_audit(
                self._session,
                action="tax.rule.updated",
                entity_type="tax_rule",
                entity_id=row.id,
                actor_id=actor_id,
                firm_id=firm_scope,
                before_data=before,
                after_data={
                    "code": row.code,
                    "priority": row.priority,
                    "status": row.status,
                    "version_number": row.version_number,
                },
            )
            self._commit()
            self._session.refresh(row)
            return row

        now = utc_now()
        version = TaxRule(
            firm_id=firm_scope,
            country_id=data.country_id,
            business_profile_id=data.business_profile_id,
            tax_profile_id=data.tax_profile_id,
            code=data.code,
            name=data.name,
            description=data.description,
            priority=data.priority,
            status=data.status.value,
            version_group_id=row.version_group_id,
            version_number=row.version_number + 1,
            supersedes_rule_id=row.id,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        version.conditions = self._build_conditions(
            data.conditions,
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        version.actions = self._build_actions(
            data.actions,
            firm_id=firm_scope,
            actor_id=actor_id,
        )
        self._session.add(version)
        self._flush_conflicts("Tax rule code already exists for this version.")
        record_audit(
            self._session,
            action="tax.rule.versioned",
            entity_type="tax_rule",
            entity_id=version.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"supersedes_rule_id": str(row.id)},
            after_data={"code": version.code, "version_number": version.version_number},
        )
        self._commit()
        self._session.refresh(version)
        return version

    def delete_rule(self, rule_id: UUID, *, firm_scope: UUID, actor_id: UUID) -> None:
        row = self.get_rule(rule_id, firm_scope=firm_scope, include_deleted=False)
        self._soft_delete(row, actor_id=actor_id)
        record_audit(
            self._session,
            action="tax.rule.deleted",
            entity_type="tax_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            before_data={"code": row.code},
        )
        self._commit()

    def restore_rule(
        self, rule_id: UUID, *, firm_scope: UUID, actor_id: UUID
    ) -> TaxRule:
        row = self.get_rule(rule_id, firm_scope=firm_scope, include_deleted=True)
        self._restore_row(row, actor_id=actor_id)
        record_audit(
            self._session,
            action="tax.rule.restored",
            entity_type="tax_rule",
            entity_id=row.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={"code": row.code},
        )
        self._commit()
        return row

    def export_rules_csv(self, *, firm_scope: UUID, search: str | None) -> str:
        rows, _ = self.list_rules(
            firm_scope=firm_scope,
            page=1,
            page_size=10000,
            search=search,
            country_id=None,
            business_profile_id=None,
            tax_profile_id=None,
            transaction_type=None,
            status=None,
            include_deleted=False,
        )
        import csv

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "code",
                "name",
                "priority",
                "status",
                "version_number",
                "effective_from",
                "effective_to",
                "condition_count",
                "action_count",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.code,
                    row.name,
                    row.priority,
                    row.status,
                    row.version_number,
                    row.effective_from or "",
                    row.effective_to or "",
                    len(row.conditions),
                    len(row.actions),
                ]
            )
        return buffer.getvalue()

    def import_rules(
        self,
        rules: list[TaxRuleWrite],
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> list[TaxRule]:
        created: list[TaxRule] = []
        for payload in rules:
            created.append(
                self.create_rule(payload, firm_id=firm_scope, actor_id=actor_id)
            )
        return created

    def simulate(
        self,
        data: TaxRuleSimulationRequest,
        *,
        firm_scope: UUID,
        actor_id: UUID,
    ) -> TaxRuleSimulationResponse:
        context = self._build_context(data, firm_scope=firm_scope)
        transaction_date = context["transaction_date"]
        rules = self._session.scalars(
            self._base_rule_query(firm_scope=firm_scope)
            .where(
                TaxRule.is_deleted.is_(False),
                TaxRule.status == TaxStatus.ACTIVE.value,
            )
            .order_by(
                TaxRule.priority.asc(),
                TaxRule.code.asc(),
                TaxRule.version_number.desc(),
                TaxRule.created_at.asc(),
            )
        ).all()

        decisions: list[TaxRuleEvaluationDecision] = []
        matched_rule: TaxRule | None = None
        matched_reasons: list[str] = []
        for rule in rules:
            matched, reasons = self._rule_matches(rule, context, transaction_date)
            decisions.append(
                TaxRuleEvaluationDecision(
                    rule_id=rule.id,
                    code=rule.code,
                    name=rule.name,
                    priority=rule.priority,
                    version_number=rule.version_number,
                    matched=matched,
                    reasons=reasons,
                )
            )
            if matched and matched_rule is None:
                matched_rule = rule
                matched_reasons = reasons
                break

        applied_profile_id: UUID | None = context.get("tax_profile_id")
        components = self._components_for_profile(
            applied_profile_id, firm_scope=firm_scope
        )
        exempt = False
        zero_rated = False
        reverse_charge = False
        input_credit_allowed: bool | None = None

        if matched_rule is not None:
            action_result = self._apply_actions(
                matched_rule,
                firm_scope=firm_scope,
                base_profile_id=applied_profile_id,
                existing_components=components,
            )
            applied_profile_id = action_result["applied_tax_profile_id"]
            components = action_result["components"]
            exempt = action_result["exempt"]
            zero_rated = action_result["zero_rated"]
            reverse_charge = action_result["reverse_charge"]
            input_credit_allowed = action_result["input_credit_allowed"]

        base_amount = Decimal(str(context.get("invoice_value") or "0"))
        if exempt:
            components = []
        preview_components = [
            TaxRuleComponentPreview(
                tax_component_id=item["tax_component_id"],
                code=item["code"],
                label=item["label"],
                percentage=Decimal(str(item["percentage"])),
                amount=self._quantize(
                    base_amount * Decimal(str(item["percentage"])) / Decimal("100")
                ),
                included_in_price=bool(item["included_in_price"]),
                recoverable=bool(item["recoverable"]),
                source=str(item["source"]),
            )
            for item in components
        ]
        total_tax_amount = self._quantize(
            sum((component.amount for component in preview_components), Decimal("0"))
        )
        response = TaxRuleSimulationResponse(
            transaction_type=str(context["transaction_type"]),
            transaction_date=transaction_date,
            matched_rule_id=matched_rule.id if matched_rule is not None else None,
            applied_tax_profile_id=applied_profile_id,
            applied_components=preview_components,
            total_tax_amount=total_tax_amount,
            base_amount=base_amount,
            exempt=exempt,
            zero_rated=zero_rated,
            reverse_charge=reverse_charge,
            input_credit_allowed=input_credit_allowed,
            matched_rule_reason=matched_reasons[0] if matched_reasons else None,
            decisions=decisions,
        )
        now = utc_now()
        log = TaxRuleExecutionLog(
            firm_id=firm_scope,
            execution_mode="SIMULATION",
            transaction_type=str(context["transaction_type"]),
            country_id=context.get("country_id"),
            business_profile_id=context.get("business_profile_id"),
            tax_profile_id=context.get("tax_profile_id"),
            matched_rule_id=matched_rule.id if matched_rule is not None else None,
            applied_tax_profile_id=applied_profile_id,
            input_payload=data.model_dump(mode="json", exclude_none=False),
            evaluation_trace={
                "decisions": [item.model_dump(mode="json") for item in decisions]
            },
            result_payload=response.model_dump(mode="json"),
            created_by=actor_id,
            created_at=now,
            updated_by=actor_id,
            updated_at=now,
        )
        self._session.add(log)
        self._session.flush()
        record_audit(
            self._session,
            action="tax.rule.simulated",
            entity_type="tax_rule_execution_log",
            entity_id=log.id,
            actor_id=actor_id,
            firm_id=firm_scope,
            after_data={
                "matched_rule_id": str(response.matched_rule_id or ""),
                "transaction_type": response.transaction_type,
            },
        )
        self._commit()
        return response

    def get_rule(
        self, rule_id: UUID, *, firm_scope: UUID, include_deleted: bool = False
    ) -> TaxRule:
        row = self._session.scalar(
            self._base_rule_query(firm_scope=firm_scope).where(TaxRule.id == rule_id)
        )
        if row is None or (row.is_deleted and not include_deleted):
            raise ResourceNotFoundError("Tax rule was not found.")
        return row

    def _base_rule_query(self, *, firm_scope: UUID):
        return (
            select(TaxRule)
            .where(TaxRule.firm_id == firm_scope)
            .options(
                selectinload(TaxRule.conditions),
                selectinload(TaxRule.actions).selectinload(
                    TaxRuleAction.target_tax_component
                ),
                selectinload(TaxRule.actions).selectinload(
                    TaxRuleAction.target_tax_profile
                ),
            )
        )

    def _build_conditions(
        self,
        items: list[TaxRuleConditionWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[TaxRuleCondition]:
        return [
            TaxRuleCondition(
                firm_id=firm_id,
                sequence=item.sequence,
                field_key=item.field_key,
                operator=item.operator.value,
                value_text=item.value_text,
                value_number=item.value_number,
                value_date=item.value_date,
                value_boolean=item.value_boolean,
                value_json=item.value_json,
                created_by=actor_id,
                created_at=utc_now(),
                updated_by=actor_id,
                updated_at=utc_now(),
            )
            for item in items
        ]

    def _build_actions(
        self,
        items: list[TaxRuleActionWrite],
        *,
        firm_id: UUID,
        actor_id: UUID,
    ) -> list[TaxRuleAction]:
        return [
            TaxRuleAction(
                firm_id=firm_id,
                sequence=item.sequence,
                action_type=item.action_type.value,
                target_tax_profile_id=item.target_tax_profile_id,
                target_tax_component_id=item.target_tax_component_id,
                percentage_override=item.percentage_override,
                parameters=item.parameters,
                created_by=actor_id,
                created_at=utc_now(),
                updated_by=actor_id,
                updated_at=utc_now(),
            )
            for item in items
        ]

    def _replace_conditions(
        self, row: TaxRule, items: list[TaxRuleConditionWrite], *, actor_id: UUID
    ) -> None:
        for existing in row.conditions:
            self._soft_delete(existing, actor_id=actor_id)
        row.conditions = self._build_conditions(
            items, firm_id=row.firm_id, actor_id=actor_id
        )

    def _replace_actions(
        self, row: TaxRule, items: list[TaxRuleActionWrite], *, actor_id: UUID
    ) -> None:
        for existing in row.actions:
            self._soft_delete(existing, actor_id=actor_id)
        row.actions = self._build_actions(items, firm_id=row.firm_id, actor_id=actor_id)

    def _validate_rule_references(
        self, data: TaxRuleWrite, *, firm_scope: UUID
    ) -> None:
        if data.tax_profile_id is not None:
            self._assert_profile_exists(data.tax_profile_id, firm_scope=firm_scope)
        for action in data.actions:
            if action.target_tax_profile_id is not None:
                self._assert_profile_exists(
                    action.target_tax_profile_id, firm_scope=firm_scope
                )
            if action.target_tax_component_id is not None:
                self._assert_component_exists(
                    action.target_tax_component_id,
                    firm_scope=firm_scope,
                )

    def _assert_profile_exists(self, profile_id: UUID, *, firm_scope: UUID) -> None:
        profile = self._session.scalar(
            select(TaxProfile.id).where(
                TaxProfile.id == profile_id,
                TaxProfile.firm_id == firm_scope,
                TaxProfile.is_deleted.is_(False),
            )
        )
        if profile is None:
            raise ValidationError("The selected tax profile is unavailable.")

    def _assert_component_exists(self, component_id: UUID, *, firm_scope: UUID) -> None:
        component = self._session.scalar(
            select(TaxComponent.id).where(
                TaxComponent.id == component_id,
                TaxComponent.firm_id == firm_scope,
                TaxComponent.is_deleted.is_(False),
            )
        )
        if component is None:
            raise ValidationError("The selected tax component is unavailable.")

    def _build_context(
        self, data: TaxRuleSimulationRequest, *, firm_scope: UUID
    ) -> dict[str, Any]:
        context = data.model_dump(exclude_none=True)
        context["transaction_type"] = data.transaction_type.strip().upper()
        context["transaction_date"] = data.transaction_date or utc_now().date()
        if data.product_id is not None:
            product = self._session.scalar(
                select(Product).where(
                    Product.id == data.product_id,
                    Product.firm_id == firm_scope,
                    Product.is_deleted.is_(False),
                )
            )
            if product is None:
                raise ValidationError("The selected product is unavailable.")
            context.setdefault("tax_profile_group_code", product.tax_profile_group_code)
            context.setdefault("product_category_id", product.category_id)
            context.setdefault("product_type", product.product_type)
        return context

    def _rule_matches(
        self,
        rule: TaxRule,
        context: dict[str, Any],
        transaction_date: date,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if rule.country_id is not None and context.get("country_id") != rule.country_id:
            return False, ["Country did not match the rule scope."]
        if (
            rule.business_profile_id is not None
            and context.get("business_profile_id") != rule.business_profile_id
        ):
            return False, ["Business profile did not match the rule scope."]
        if (
            rule.tax_profile_id is not None
            and context.get("tax_profile_id") != rule.tax_profile_id
        ):
            return False, ["Tax profile did not match the rule scope."]
        if rule.effective_from is not None and transaction_date < rule.effective_from:
            return False, ["Transaction date is before the rule effective date."]
        if rule.effective_to is not None and transaction_date > rule.effective_to:
            return False, ["Transaction date is after the rule effective date."]
        for condition in rule.conditions:
            matched, reason = self._condition_matches(
                condition, context, transaction_date
            )
            if not matched:
                return False, [reason]
            reasons.append(reason)
        if not reasons:
            reasons.append(
                "Rule matched because its scope and effective window were valid."
            )
        return True, reasons

    def _condition_matches(
        self,
        condition: TaxRuleCondition,
        context: dict[str, Any],
        transaction_date: date,
    ) -> tuple[bool, str]:
        actual = context.get(condition.field_key)
        if actual is None and condition.field_key == "transaction_date":
            actual = transaction_date
        operator = TaxRuleConditionOperator(condition.operator)
        expected = self._condition_expected_value(condition)
        if operator == TaxRuleConditionOperator.EXISTS:
            matched = actual is not None and str(actual) != ""
        elif operator == TaxRuleConditionOperator.NOT_EXISTS:
            matched = actual is None or str(actual) == ""
        elif operator == TaxRuleConditionOperator.EQUALS:
            matched = self._normalize_compare(actual) == self._normalize_compare(
                expected
            )
        elif operator == TaxRuleConditionOperator.NOT_EQUALS:
            matched = self._normalize_compare(actual) != self._normalize_compare(
                expected
            )
        elif operator == TaxRuleConditionOperator.IN:
            values = expected if isinstance(expected, list) else [expected]
            matched = self._normalize_compare(actual) in {
                self._normalize_compare(value) for value in values
            }
        elif operator == TaxRuleConditionOperator.NOT_IN:
            values = expected if isinstance(expected, list) else [expected]
            matched = self._normalize_compare(actual) not in {
                self._normalize_compare(value) for value in values
            }
        elif operator == TaxRuleConditionOperator.GREATER_THAN:
            matched = self._as_decimal(actual) > self._as_decimal(expected)
        elif operator == TaxRuleConditionOperator.GREATER_OR_EQUAL:
            matched = self._as_decimal(actual) >= self._as_decimal(expected)
        elif operator == TaxRuleConditionOperator.LESS_THAN:
            matched = self._as_decimal(actual) < self._as_decimal(expected)
        elif operator == TaxRuleConditionOperator.LESS_OR_EQUAL:
            matched = self._as_decimal(actual) <= self._as_decimal(expected)
        elif operator == TaxRuleConditionOperator.BETWEEN:
            if not isinstance(expected, list) or len(expected) != 2:
                raise ValidationError("BETWEEN requires exactly two comparison values.")
            actual_decimal = self._as_decimal(actual)
            matched = (
                self._as_decimal(expected[0])
                <= actual_decimal
                <= self._as_decimal(expected[1])
            )
        else:
            matched = False
        if matched:
            return True, f"{condition.field_key} satisfied {condition.operator}."
        return False, f"{condition.field_key} failed {condition.operator}."

    def _condition_expected_value(self, condition: TaxRuleCondition) -> Any:
        if condition.value_json is not None:
            if isinstance(condition.value_json, dict):
                if "values" in condition.value_json and isinstance(
                    condition.value_json["values"], list
                ):
                    return condition.value_json["values"]
            return condition.value_json
        if condition.value_text is not None:
            return condition.value_text
        if condition.value_number is not None:
            return condition.value_number
        if condition.value_date is not None:
            return condition.value_date
        return condition.value_boolean

    def _components_for_profile(
        self, profile_id: UUID | None, *, firm_scope: UUID
    ) -> list[dict[str, Any]]:
        if profile_id is None:
            return []
        profile = self._session.scalar(
            select(TaxProfile)
            .where(
                TaxProfile.id == profile_id,
                TaxProfile.firm_id == firm_scope,
                TaxProfile.is_deleted.is_(False),
            )
            .options(
                selectinload(TaxProfile.components).selectinload(
                    TaxProfileComponent.tax_component
                )
            )
        )
        if profile is None:
            return []
        items: list[dict[str, Any]] = []
        for component in profile.components:
            code = ""
            if component.tax_component is not None:
                code = component.tax_component.code
            items.append(
                {
                    "tax_component_id": component.tax_component_id,
                    "code": code,
                    "label": component.label or code,
                    "percentage": component.percentage,
                    "included_in_price": component.included_in_price,
                    "recoverable": component.recoverable,
                    "source": "PROFILE",
                }
            )
        return items

    def _apply_actions(
        self,
        rule: TaxRule,
        *,
        firm_scope: UUID,
        base_profile_id: UUID | None,
        existing_components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        components = [dict(item) for item in existing_components]
        applied_profile_id = base_profile_id
        exempt = False
        zero_rated = False
        reverse_charge = False
        input_credit_allowed: bool | None = None
        for action in sorted(rule.actions, key=lambda item: item.sequence):
            action_type = TaxRuleActionType(action.action_type)
            if action_type == TaxRuleActionType.APPLY_TAX_PROFILE:
                applied_profile_id = action.target_tax_profile_id
                components = self._components_for_profile(
                    applied_profile_id, firm_scope=firm_scope
                )
            elif action_type == TaxRuleActionType.APPLY_TAX_COMPONENT:
                if action.target_tax_component is None:
                    continue
                percentage = (
                    action.percentage_override
                    if action.percentage_override is not None
                    else action.target_tax_component.percentage
                )
                components.append(
                    {
                        "tax_component_id": action.target_tax_component_id,
                        "code": action.target_tax_component.code,
                        "label": action.target_tax_component.label,
                        "percentage": percentage,
                        "included_in_price": action.target_tax_component.included_in_price,
                        "recoverable": action.target_tax_component.recoverable,
                        "source": "RULE_ACTION",
                    }
                )
            elif action_type == TaxRuleActionType.EXEMPT_TAX:
                exempt = True
                components = []
            elif action_type == TaxRuleActionType.ZERO_RATED:
                zero_rated = True
                for item in components:
                    item["percentage"] = Decimal("0")
                    item["source"] = "ZERO_RATED"
            elif action_type == TaxRuleActionType.REVERSE_CHARGE:
                reverse_charge = True
            elif action_type == TaxRuleActionType.INPUT_CREDIT_ALLOWED:
                input_credit_allowed = True
            elif action_type == TaxRuleActionType.INPUT_CREDIT_BLOCKED:
                input_credit_allowed = False
            elif action_type == TaxRuleActionType.OVERRIDE_COMPONENT_PERCENTAGE:
                if action.target_tax_component_id is None:
                    continue
                overridden = False
                for item in components:
                    if item["tax_component_id"] == action.target_tax_component_id:
                        item["percentage"] = action.percentage_override or Decimal("0")
                        item["source"] = "OVERRIDE"
                        overridden = True
                        break
                if not overridden and action.target_tax_component is not None:
                    components.append(
                        {
                            "tax_component_id": action.target_tax_component_id,
                            "code": action.target_tax_component.code,
                            "label": action.target_tax_component.label,
                            "percentage": action.percentage_override or Decimal("0"),
                            "included_in_price": action.target_tax_component.included_in_price,
                            "recoverable": action.target_tax_component.recoverable,
                            "source": "OVERRIDE",
                        }
                    )
        return {
            "applied_tax_profile_id": applied_profile_id,
            "components": components,
            "exempt": exempt,
            "zero_rated": zero_rated,
            "reverse_charge": reverse_charge,
            "input_credit_allowed": input_credit_allowed,
        }

    @staticmethod
    def _normalize_compare(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, str):
            return value.strip().upper()
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        return str(value)

    @staticmethod
    def _as_decimal(value: Any) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @staticmethod
    def _soft_delete(row: Any, *, actor_id: UUID) -> None:
        row.is_deleted = True
        row.deleted_at = utc_now()
        row.updated_by = actor_id

    @staticmethod
    def _restore_row(row: Any, *, actor_id: UUID) -> None:
        row.is_deleted = False
        row.deleted_at = None
        row.updated_by = actor_id

    def _flush_conflicts(self, conflict_message: str) -> None:
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(conflict_message) from exc

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("Unable to persist tax rule changes.") from exc
