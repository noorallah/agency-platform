import 'entities.dart';

class TaxSystemRecord {
  const TaxSystemRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.displayName,
    required this.status,
    required this.countryId,
    required this.businessProfileId,
    required this.effectiveFrom,
    required this.effectiveTo,
    required this.displayOrder,
    required this.isDeleted,
  });

  final String id;
  final String code;
  final String name;
  final String displayName;
  final String status;
  final String countryId;
  final String businessProfileId;
  final String effectiveFrom;
  final String effectiveTo;
  final int displayOrder;
  final bool isDeleted;

  factory TaxSystemRecord.fromJson(Json json) => TaxSystemRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        displayName: stringValue(json['display_name']),
        status: stringValue(json['status']),
        countryId: stringValue(json['country_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        displayOrder: (json['display_order'] as num?)?.toInt() ?? 0,
        isDeleted: boolValue(json['is_deleted']),
      );
}

class TaxComponentRecord {
  const TaxComponentRecord({
    required this.id,
    required this.taxSystemId,
    required this.code,
    required this.name,
    required this.label,
    required this.percentage,
    required this.status,
    required this.isDeleted,
  });

  final String id;
  final String taxSystemId;
  final String code;
  final String name;
  final String label;
  final String percentage;
  final String status;
  final bool isDeleted;

  factory TaxComponentRecord.fromJson(Json json) => TaxComponentRecord(
        id: stringValue(json['id']),
        taxSystemId: stringValue(json['tax_system_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        label: stringValue(json['label']),
        percentage: stringValue(json['percentage']),
        status: stringValue(json['status']),
        isDeleted: boolValue(json['is_deleted']),
      );
}

class TaxProfileComponentRecord {
  const TaxProfileComponentRecord({
    required this.id,
    required this.taxComponentId,
    required this.percentage,
    required this.label,
    required this.shortLabel,
    required this.calculationOrder,
  });

  final String id;
  final String taxComponentId;
  final String percentage;
  final String label;
  final String shortLabel;
  final int calculationOrder;

  factory TaxProfileComponentRecord.fromJson(Json json) =>
      TaxProfileComponentRecord(
        id: stringValue(json['id']),
        taxComponentId: stringValue(json['tax_component_id']),
        percentage: stringValue(json['percentage']),
        label: stringValue(json['label']),
        shortLabel: stringValue(json['short_label']),
        calculationOrder: (json['calculation_order'] as num?)?.toInt() ?? 0,
      );
}

class TaxProfileRecord {
  const TaxProfileRecord({
    required this.id,
    required this.taxSystemId,
    required this.code,
    required this.name,
    required this.label,
    required this.status,
    required this.isHistorical,
    required this.isDeleted,
    required this.components,
  });

  final String id;
  final String taxSystemId;
  final String code;
  final String name;
  final String label;
  final String status;
  final bool isHistorical;
  final bool isDeleted;
  final List<TaxProfileComponentRecord> components;

  factory TaxProfileRecord.fromJson(Json json) => TaxProfileRecord(
        id: stringValue(json['id']),
        taxSystemId: stringValue(json['tax_system_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        label: stringValue(json['label']),
        status: stringValue(json['status']),
        isHistorical: boolValue(json['is_historical']),
        isDeleted: boolValue(json['is_deleted']),
        components: _objects(json['components'])
            .map(TaxProfileComponentRecord.fromJson)
            .toList(),
      );
}

class TaxCountryMappingRecord {
  const TaxCountryMappingRecord({
    required this.id,
    required this.countryId,
    required this.businessProfileId,
    required this.taxSystemId,
    required this.status,
    required this.isDefault,
    required this.isDeleted,
  });

  final String id;
  final String countryId;
  final String businessProfileId;
  final String taxSystemId;
  final String status;
  final bool isDefault;
  final bool isDeleted;

  factory TaxCountryMappingRecord.fromJson(Json json) =>
      TaxCountryMappingRecord(
        id: stringValue(json['id']),
        countryId: stringValue(json['country_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        taxSystemId: stringValue(json['tax_system_id']),
        status: stringValue(json['status']),
        isDefault: boolValue(json['is_default']),
        isDeleted: boolValue(json['is_deleted']),
      );
}

class TaxMigrationMappingRecord {
  const TaxMigrationMappingRecord({
    required this.id,
    required this.legacyTaxCode,
    required this.legacyTaxName,
    required this.sourceSystem,
    required this.legacyRate,
    required this.targetTaxProfileId,
    required this.keepHistorical,
    required this.status,
    required this.notes,
    required this.isDeleted,
  });

  final String id;
  final String legacyTaxCode;
  final String legacyTaxName;
  final String sourceSystem;
  final String legacyRate;
  final String targetTaxProfileId;
  final bool keepHistorical;
  final String status;
  final String notes;
  final bool isDeleted;

  factory TaxMigrationMappingRecord.fromJson(Json json) =>
      TaxMigrationMappingRecord(
        id: stringValue(json['id']),
        legacyTaxCode: stringValue(json['legacy_tax_code']),
        legacyTaxName: stringValue(json['legacy_tax_name']),
        sourceSystem: stringValue(json['source_system']),
        legacyRate: stringValue(json['legacy_rate']),
        targetTaxProfileId: stringValue(json['target_tax_profile_id']),
        keepHistorical: boolValue(json['keep_historical']),
        status: stringValue(json['status']),
        notes: stringValue(json['notes']),
        isDeleted: boolValue(json['is_deleted']),
      );
}

class TaxSettingsRecord {
  const TaxSettingsRecord({
    required this.id,
    required this.primaryLabel,
    required this.componentLabel,
    required this.profileLabel,
    required this.reportLabel,
    required this.allowMixedHistorical,
    required this.additionalSettings,
  });

  final String id;
  final String primaryLabel;
  final String componentLabel;
  final String profileLabel;
  final String reportLabel;
  final bool allowMixedHistorical;
  final Json additionalSettings;

  factory TaxSettingsRecord.fromJson(Json json) => TaxSettingsRecord(
        id: stringValue(json['id']),
        primaryLabel: stringValue(json['primary_label']),
        componentLabel: stringValue(json['component_label']),
        profileLabel: stringValue(json['profile_label']),
        reportLabel: stringValue(json['report_label']),
        allowMixedHistorical: boolValue(json['allow_mixed_historical']),
        additionalSettings: json['additional_settings'] is Map
            ? Map<String, dynamic>.from(json['additional_settings'] as Map)
            : const {},
      );
}

class EffectiveDateRecord {
  const EffectiveDateRecord({
    required this.entityType,
    required this.entityId,
    required this.code,
    required this.name,
    required this.status,
    required this.effectiveFrom,
    required this.effectiveTo,
  });

  final String entityType;
  final String entityId;
  final String code;
  final String name;
  final String status;
  final String effectiveFrom;
  final String effectiveTo;

  factory EffectiveDateRecord.fromJson(Json json) => EffectiveDateRecord(
        entityType: stringValue(json['entity_type']),
        entityId: stringValue(json['entity_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        status: stringValue(json['status']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
      );
}

class TaxHistoryRecord {
  const TaxHistoryRecord({
    required this.id,
    required this.action,
    required this.entityType,
    required this.entityId,
    required this.actorId,
    required this.createdAt,
  });

  final String id;
  final String action;
  final String entityType;
  final String entityId;
  final String actorId;
  final String createdAt;

  factory TaxHistoryRecord.fromJson(Json json) => TaxHistoryRecord(
        id: stringValue(json['id']),
        action: stringValue(json['action']),
        entityType: stringValue(json['entity_type']),
        entityId: stringValue(json['entity_id']),
        actorId: stringValue(json['actor_id']),
        createdAt: stringValue(json['created_at']),
      );
}

class TaxRuleConditionRecord {
  const TaxRuleConditionRecord({
    required this.id,
    required this.taxRuleId,
    required this.sequence,
    required this.fieldKey,
    required this.operatorType,
    required this.valueText,
    required this.valueNumber,
  });

  final String id;
  final String taxRuleId;
  final int sequence;
  final String fieldKey;
  final String operatorType;
  final String valueText;
  final String valueNumber;

  factory TaxRuleConditionRecord.fromJson(Json json) => TaxRuleConditionRecord(
        id: stringValue(json['id']),
        taxRuleId: stringValue(json['tax_rule_id']),
        sequence: (json['sequence'] as num?)?.toInt() ?? 0,
        fieldKey: stringValue(json['field_key']),
        operatorType: stringValue(json['operator']),
        valueText: stringValue(json['value_text']),
        valueNumber: stringValue(json['value_number']),
      );
}

class TaxRuleActionRecord {
  const TaxRuleActionRecord({
    required this.id,
    required this.taxRuleId,
    required this.sequence,
    required this.actionType,
    required this.targetTaxProfileId,
    required this.targetTaxComponentId,
    required this.percentageOverride,
  });

  final String id;
  final String taxRuleId;
  final int sequence;
  final String actionType;
  final String targetTaxProfileId;
  final String targetTaxComponentId;
  final String percentageOverride;

  factory TaxRuleActionRecord.fromJson(Json json) => TaxRuleActionRecord(
        id: stringValue(json['id']),
        taxRuleId: stringValue(json['tax_rule_id']),
        sequence: (json['sequence'] as num?)?.toInt() ?? 0,
        actionType: stringValue(json['action_type']),
        targetTaxProfileId: stringValue(json['target_tax_profile_id']),
        targetTaxComponentId: stringValue(json['target_tax_component_id']),
        percentageOverride: stringValue(json['percentage_override']),
      );
}

class TaxRuleRecord {
  const TaxRuleRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.description,
    required this.priority,
    required this.status,
    required this.countryId,
    required this.businessProfileId,
    required this.taxProfileId,
    required this.versionGroupId,
    required this.versionNumber,
    required this.supersedesRuleId,
    required this.effectiveFrom,
    required this.effectiveTo,
    required this.isDeleted,
    required this.conditions,
    required this.actions,
  });

  final String id;
  final String code;
  final String name;
  final String description;
  final int priority;
  final String status;
  final String countryId;
  final String businessProfileId;
  final String taxProfileId;
  final String versionGroupId;
  final int versionNumber;
  final String supersedesRuleId;
  final String effectiveFrom;
  final String effectiveTo;
  final bool isDeleted;
  final List<TaxRuleConditionRecord> conditions;
  final List<TaxRuleActionRecord> actions;

  factory TaxRuleRecord.fromJson(Json json) => TaxRuleRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        description: stringValue(json['description']),
        priority: (json['priority'] as num?)?.toInt() ?? 0,
        status: stringValue(json['status']),
        countryId: stringValue(json['country_id']),
        businessProfileId: stringValue(json['business_profile_id']),
        taxProfileId: stringValue(json['tax_profile_id']),
        versionGroupId: stringValue(json['version_group_id']),
        versionNumber: (json['version_number'] as num?)?.toInt() ?? 0,
        supersedesRuleId: stringValue(json['supersedes_rule_id']),
        effectiveFrom: stringValue(json['effective_from']),
        effectiveTo: stringValue(json['effective_to']),
        isDeleted: boolValue(json['is_deleted']),
        conditions: _objects(json['conditions'])
            .map(TaxRuleConditionRecord.fromJson)
            .toList(),
        actions:
            _objects(json['actions']).map(TaxRuleActionRecord.fromJson).toList(),
      );
}

class TaxRulePriorityRecord {
  const TaxRulePriorityRecord({
    required this.id,
    required this.code,
    required this.name,
    required this.priority,
    required this.status,
    required this.versionNumber,
    required this.conditionCount,
    required this.actionCount,
  });

  final String id;
  final String code;
  final String name;
  final int priority;
  final String status;
  final int versionNumber;
  final int conditionCount;
  final int actionCount;

  factory TaxRulePriorityRecord.fromJson(Json json) => TaxRulePriorityRecord(
        id: stringValue(json['id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        priority: (json['priority'] as num?)?.toInt() ?? 0,
        status: stringValue(json['status']),
        versionNumber: (json['version_number'] as num?)?.toInt() ?? 0,
        conditionCount: (json['condition_count'] as num?)?.toInt() ?? 0,
        actionCount: (json['action_count'] as num?)?.toInt() ?? 0,
      );
}

class TaxRuleSimulationComponentRecord {
  const TaxRuleSimulationComponentRecord({
    required this.taxComponentId,
    required this.code,
    required this.label,
    required this.percentage,
    required this.amount,
    required this.source,
  });

  final String taxComponentId;
  final String code;
  final String label;
  final String percentage;
  final String amount;
  final String source;

  factory TaxRuleSimulationComponentRecord.fromJson(Json json) =>
      TaxRuleSimulationComponentRecord(
        taxComponentId: stringValue(json['tax_component_id']),
        code: stringValue(json['code']),
        label: stringValue(json['label']),
        percentage: stringValue(json['percentage']),
        amount: stringValue(json['amount']),
        source: stringValue(json['source']),
      );
}

class TaxRuleDecisionRecord {
  const TaxRuleDecisionRecord({
    required this.ruleId,
    required this.code,
    required this.name,
    required this.priority,
    required this.versionNumber,
    required this.matched,
    required this.reasons,
  });

  final String ruleId;
  final String code;
  final String name;
  final int priority;
  final int versionNumber;
  final bool matched;
  final List<String> reasons;

  factory TaxRuleDecisionRecord.fromJson(Json json) => TaxRuleDecisionRecord(
        ruleId: stringValue(json['rule_id']),
        code: stringValue(json['code']),
        name: stringValue(json['name']),
        priority: (json['priority'] as num?)?.toInt() ?? 0,
        versionNumber: (json['version_number'] as num?)?.toInt() ?? 0,
        matched: boolValue(json['matched']),
        reasons: (json['reasons'] as List?)
                ?.whereType<Object?>()
                .map((item) => stringValue(item))
                .toList() ??
            const [],
      );
}

class TaxRuleSimulationResultRecord {
  const TaxRuleSimulationResultRecord({
    required this.transactionType,
    required this.transactionDate,
    required this.matchedRuleId,
    required this.appliedTaxProfileId,
    required this.baseAmount,
    required this.totalTaxAmount,
    required this.exempt,
    required this.zeroRated,
    required this.reverseCharge,
    required this.inputCreditAllowed,
    required this.matchedRuleReason,
    required this.appliedComponents,
    required this.decisions,
  });

  final String transactionType;
  final String transactionDate;
  final String matchedRuleId;
  final String appliedTaxProfileId;
  final String baseAmount;
  final String totalTaxAmount;
  final bool exempt;
  final bool zeroRated;
  final bool reverseCharge;
  final bool? inputCreditAllowed;
  final String matchedRuleReason;
  final List<TaxRuleSimulationComponentRecord> appliedComponents;
  final List<TaxRuleDecisionRecord> decisions;

  factory TaxRuleSimulationResultRecord.fromJson(Json json) =>
      TaxRuleSimulationResultRecord(
        transactionType: stringValue(json['transaction_type']),
        transactionDate: stringValue(json['transaction_date']),
        matchedRuleId: stringValue(json['matched_rule_id']),
        appliedTaxProfileId: stringValue(json['applied_tax_profile_id']),
        baseAmount: stringValue(json['base_amount']),
        totalTaxAmount: stringValue(json['total_tax_amount']),
        exempt: boolValue(json['exempt']),
        zeroRated: boolValue(json['zero_rated']),
        reverseCharge: boolValue(json['reverse_charge']),
        inputCreditAllowed: json.containsKey('input_credit_allowed')
            ? json['input_credit_allowed'] as bool?
            : null,
        matchedRuleReason: stringValue(json['matched_rule_reason']),
        appliedComponents: _objects(json['applied_components'])
            .map(TaxRuleSimulationComponentRecord.fromJson)
            .toList(),
        decisions:
            _objects(json['decisions']).map(TaxRuleDecisionRecord.fromJson).toList(),
      );
}

class TaxRuleExecutionLogRecord {
  const TaxRuleExecutionLogRecord({
    required this.id,
    required this.executionMode,
    required this.transactionType,
    required this.matchedRuleId,
    required this.appliedTaxProfileId,
    required this.createdAt,
  });

  final String id;
  final String executionMode;
  final String transactionType;
  final String matchedRuleId;
  final String appliedTaxProfileId;
  final String createdAt;

  factory TaxRuleExecutionLogRecord.fromJson(Json json) =>
      TaxRuleExecutionLogRecord(
        id: stringValue(json['id']),
        executionMode: stringValue(json['execution_mode']),
        transactionType: stringValue(json['transaction_type']),
        matchedRuleId: stringValue(json['matched_rule_id']),
        appliedTaxProfileId: stringValue(json['applied_tax_profile_id']),
        createdAt: stringValue(json['created_at']),
      );
}

List<Json> _objects(dynamic value) => value is List
    ? value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
    : const [];
