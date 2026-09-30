// The five tax master forms (D-DLG-4): what each asks for, which drop-downs it
// loads, and the shape it sends. Every key sent here is one the server's write
// schema in `backend/app/tax/schemas/tax_framework.py` declares, because those
// schemas forbid unknown fields and one stray key fails the whole request.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/geography.dart';
import '../../models/tax_framework.dart';
import '../workspace/paged_fetch.dart';
import 'tax_master_forms.dart';

/// The masters the drop-downs offer, read through the same calls the grids use.
class TaxChoices {
  const TaxChoices({
    this.systems = const <TaxOption>[],
    this.components = const <TaxOption>[],
    this.profiles = const <TaxOption>[],
    this.countries = const <TaxOption>[],
    this.businessProfiles = const <TaxOption>[],
  });

  final List<TaxOption> systems;
  final List<TaxOption> components;
  final List<TaxOption> profiles;
  final List<TaxOption> countries;
  final List<TaxOption> businessProfiles;
}

/// Load what a form needs. Throws [ApiException] when a read is refused.
Future<TaxChoices> loadTaxChoices(
  ApiClient api, {
  bool systems = false,
  bool components = false,
  bool profiles = false,
  bool countries = false,
  bool businessProfiles = false,
}) async {
  return TaxChoices(
    systems: !systems
        ? const <TaxOption>[]
        : <TaxOption>[
            for (final TaxSystemRecord r in await fetchAllPages(
              (int page) =>
                  api.taxSystems(page: page, pageSize: maxApiPageSize),
            ))
              TaxOption(r.id, '${r.code} - ${r.name}'),
          ],
    components: !components
        ? const <TaxOption>[]
        : <TaxOption>[
            for (final TaxComponentRecord r in await fetchAllPages(
              (int page) =>
                  api.taxComponents(page: page, pageSize: maxApiPageSize),
            ))
              TaxOption(r.id, '${r.code} - ${r.name}'),
          ],
    profiles: !profiles
        ? const <TaxOption>[]
        : <TaxOption>[
            for (final TaxProfileRecord r in await fetchAllPages(
              (int page) =>
                  api.taxProfiles(page: page, pageSize: maxApiPageSize),
            ))
              TaxOption(r.id, '${r.code} - ${r.name}'),
          ],
    countries: !countries
        ? const <TaxOption>[]
        : <TaxOption>[
            for (final GeoPlaceRecord r in await api.geoPlaces(
              GeoLevel.country,
            ))
              TaxOption(r.id, r.name),
          ],
    businessProfiles: !businessProfiles
        ? const <TaxOption>[]
        : <TaxOption>[
            for (final r in await fetchAllPages(
              (int page) => api.businessProfiles(page: page),
            ))
              TaxOption(r.id, r.name),
          ],
  );
}

String _firstOr(List<TaxOption> options, String current) =>
    current.isNotEmpty || options.isEmpty ? current : options.first.value;

/// Whether [text] is a plain number for `BETWEEN`.
String? _twoNumbers(String text) {
  final List<String> parts = _splitList(text);
  if (parts.length != 2) return 'Two values: low, high';
  if (parts.any((String p) => double.tryParse(p) == null)) {
    return 'Both values must be numbers';
  }
  return null;
}

List<String> _splitList(String text) => <String>[
      for (final String part in text.split(','))
        if (part.trim().isNotEmpty) part.trim(),
    ];

// ---------------------------------------------------------------- component

Future<bool?> showTaxComponentForm(
  BuildContext context,
  ApiClient api,
  TaxComponentRecord? current,
) async {
  final TaxChoices choices;
  try {
    choices = await loadTaxChoices(api, systems: true);
  } on ApiException catch (exception) {
    if (!context.mounted) return null;
    return _refused(context, exception);
  }
  if (!context.mounted) return null;
  return showTaxMasterDialog(
    context,
    title: current == null ? 'Create tax component' : 'Edit tax component',
    noun: 'tax component',
    isEdit: current != null,
    fields: <TaxFieldSpec>[
      TaxFieldSpec(
        key: 'tax_system_id',
        label: 'Tax system',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.systems,
      ),
      const TaxFieldSpec(
        key: 'code',
        label: 'Code',
        required: true,
        uppercase: true,
      ),
      const TaxFieldSpec(key: 'name', label: 'Name', required: true),
      const TaxFieldSpec(key: 'label', label: 'Label', clearable: false),
      const TaxFieldSpec(
        key: 'short_label',
        label: 'Short label',
      ),
      const TaxFieldSpec(
        key: 'percentage',
        label: 'Rate (%)',
        kind: TaxFieldKind.decimal,
        required: true,
        min: 0,
        max: 100,
      ),
      const TaxFieldSpec(
        key: 'calculation_order',
        label: 'Calculation order',
        kind: TaxFieldKind.integer,
        min: 0,
        max: 100000,
        helper: 'Lower numbers are worked out first.',
      ),
      const TaxFieldSpec(
        key: 'display_order',
        label: 'Display order',
        kind: TaxFieldKind.integer,
        min: 0,
        max: 100000,
      ),
      const TaxFieldSpec(
        key: 'included_in_price',
        label: 'Already included in the price',
        kind: TaxFieldKind.toggle,
      ),
      const TaxFieldSpec(
        key: 'recoverable',
        label: 'Recoverable as input credit',
        kind: TaxFieldKind.toggle,
      ),
    ],
    initial: <String, Object?>{
      'tax_system_id': _firstOr(choices.systems, current?.taxSystemId ?? ''),
      'code': current?.code ?? '',
      'name': current?.name ?? '',
      'label': current?.label ?? '',
      'short_label': current?.shortLabel ?? '',
      'percentage': current?.percentage ?? '0',
      'calculation_order': '${current?.calculationOrder ?? 0}',
      'display_order': '${current?.displayOrder ?? 0}',
      'included_in_price': current?.includedInPrice ?? false,
      'recoverable': current?.recoverable ?? false,
    },
    onSave: (Map<String, Object?> payload) async {
      if (current == null) {
        await api.createTaxComponent(payload);
      } else {
        await api.updateTaxComponent(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
    },
  );
}

// ------------------------------------------------------------------ profile

Future<bool?> showTaxProfileForm(
  BuildContext context,
  ApiClient api,
  TaxProfileRecord? current,
) async {
  final TaxChoices choices;
  try {
    choices = await loadTaxChoices(
      api,
      systems: true,
      components: true,
      businessProfiles: true,
    );
  } on ApiException catch (exception) {
    if (!context.mounted) return null;
    return _refused(context, exception);
  }
  if (!context.mounted) return null;
  return showTaxMasterDialog(
    context,
    title: current == null ? 'Create tax profile' : 'Edit tax profile',
    noun: 'tax profile',
    isEdit: current != null,
    fields: <TaxFieldSpec>[
      TaxFieldSpec(
        key: 'tax_system_id',
        label: 'Tax system',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.systems,
      ),
      TaxFieldSpec(
        key: 'business_profile_id',
        label: 'Business profile',
        kind: TaxFieldKind.select,
        options: choices.businessProfiles,
        helper: 'Leave on None to apply to every business profile.',
      ),
      const TaxFieldSpec(
        key: 'code',
        label: 'Code',
        required: true,
        uppercase: true,
      ),
      const TaxFieldSpec(key: 'name', label: 'Name', required: true),
      const TaxFieldSpec(key: 'label', label: 'Label', clearable: false),
      const TaxFieldSpec(
        key: 'group_code',
        label: 'Group code',
        uppercase: true,
      ),
      const TaxFieldSpec(
        key: 'description',
        label: 'Description',
        kind: TaxFieldKind.multiline,
      ),
      const TaxFieldSpec(
        key: 'display_order',
        label: 'Display order',
        kind: TaxFieldKind.integer,
        min: 0,
        max: 100000,
      ),
      const TaxFieldSpec(
        key: 'is_historical',
        label: 'Historical (kept for old documents only)',
        kind: TaxFieldKind.toggle,
      ),
      const TaxFieldSpec(
        key: 'effective_from',
        label: 'Effective from',
        kind: TaxFieldKind.date,
      ),
      const TaxFieldSpec(
        key: 'effective_to',
        label: 'Effective to',
        kind: TaxFieldKind.date,
      ),
    ],
    initial: <String, Object?>{
      'tax_system_id': _firstOr(choices.systems, current?.taxSystemId ?? ''),
      'business_profile_id': current?.businessProfileId ?? '',
      'code': current?.code ?? '',
      'name': current?.name ?? '',
      'label': current?.label ?? '',
      'group_code': current?.groupCode ?? '',
      'description': current?.description ?? '',
      'display_order': '${current?.displayOrder ?? 0}',
      'is_historical': current?.isHistorical ?? false,
      'effective_from': current?.effectiveFrom ?? '',
      'effective_to': current?.effectiveTo ?? '',
    },
    rows: <TaxRowsSpec>[
      TaxRowsSpec(
        key: 'components',
        title: 'Components',
        addLabel: 'Add component',
        emptyText: 'No components yet. A profile with none charges no tax.',
        maxRows: 50,
        initialRows: <Map<String, Object?>>[
          for (final TaxProfileComponentRecord c
              in current?.components ?? const <TaxProfileComponentRecord>[])
            <String, Object?>{
              'tax_component_id': c.taxComponentId,
              'label': c.label,
              'short_label': c.shortLabel,
              'calculation_order': '${c.calculationOrder}',
              'percentage': c.percentage,
              'included_in_price': c.includedInPrice,
              'recoverable': c.recoverable,
            },
        ],
        newRow: () => <String, Object?>{
          'tax_component_id': '',
          'label': '',
          'short_label': '',
          'calculation_order': '0',
          'percentage': '0',
          'included_in_price': false,
          'recoverable': false,
        },
        fieldsFor: (Map<String, Object?> row) => <TaxFieldSpec>[
          TaxFieldSpec(
            key: 'tax_component_id',
            label: 'Component',
            kind: TaxFieldKind.select,
            required: true,
            options: choices.components,
          ),
          const TaxFieldSpec(
            key: 'percentage',
            label: 'Rate (%)',
            kind: TaxFieldKind.decimal,
            required: true,
            min: 0,
            max: 100,
          ),
          const TaxFieldSpec(
            key: 'calculation_order',
            label: 'Order',
            kind: TaxFieldKind.integer,
            min: 0,
            max: 100000,
          ),
          const TaxFieldSpec(key: 'label', label: 'Label'),
          const TaxFieldSpec(key: 'short_label', label: 'Short label'),
          const TaxFieldSpec(
            key: 'included_in_price',
            label: 'In price',
            kind: TaxFieldKind.toggle,
          ),
          const TaxFieldSpec(
            key: 'recoverable',
            label: 'Recoverable',
            kind: TaxFieldKind.toggle,
          ),
        ],
        toPayload: (Map<String, Object?> row, int index) => <String, Object?>{
          'tax_component_id': row['tax_component_id'],
          if ('${row['label']}'.trim().isNotEmpty)
            'label': '${row['label']}'.trim(),
          if ('${row['short_label']}'.trim().isNotEmpty)
            'short_label': '${row['short_label']}'.trim(),
          'calculation_order':
              int.tryParse('${row['calculation_order']}'.trim()) ?? 0,
          'percentage': '${row['percentage']}'.trim(),
          'included_in_price': row['included_in_price'] == true,
          'recoverable': row['recoverable'] == true,
        },
      ),
    ],
    onSave: (Map<String, Object?> payload) async {
      if (current == null) {
        await api.createTaxProfile(payload);
      } else {
        await api.updateTaxProfile(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
    },
  );
}

// ---------------------------------------------------------- country mapping

Future<bool?> showTaxCountryMappingForm(
  BuildContext context,
  ApiClient api,
  TaxCountryMappingRecord? current,
) async {
  final TaxChoices choices;
  try {
    choices = await loadTaxChoices(
      api,
      systems: true,
      countries: true,
      businessProfiles: true,
    );
  } on ApiException catch (exception) {
    if (!context.mounted) return null;
    return _refused(context, exception);
  }
  if (!context.mounted) return null;
  return showTaxMasterDialog(
    context,
    title: current == null ? 'Create country mapping' : 'Edit country mapping',
    noun: 'country mapping',
    isEdit: current != null,
    fields: <TaxFieldSpec>[
      TaxFieldSpec(
        key: 'country_id',
        label: 'Country',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.countries,
      ),
      TaxFieldSpec(
        key: 'tax_system_id',
        label: 'Tax system',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.systems,
      ),
      TaxFieldSpec(
        key: 'business_profile_id',
        label: 'Business profile',
        kind: TaxFieldKind.select,
        options: choices.businessProfiles,
      ),
      const TaxFieldSpec(
        key: 'is_default',
        label: 'Default system for this country',
        kind: TaxFieldKind.toggle,
      ),
      const TaxFieldSpec(
        key: 'effective_from',
        label: 'Effective from',
        kind: TaxFieldKind.date,
      ),
      const TaxFieldSpec(
        key: 'effective_to',
        label: 'Effective to',
        kind: TaxFieldKind.date,
      ),
    ],
    initial: <String, Object?>{
      'country_id': _firstOr(choices.countries, current?.countryId ?? ''),
      'tax_system_id': _firstOr(choices.systems, current?.taxSystemId ?? ''),
      'business_profile_id': current?.businessProfileId ?? '',
      'is_default': current?.isDefault ?? true,
      'effective_from': current?.effectiveFrom ?? '',
      'effective_to': current?.effectiveTo ?? '',
    },
    onSave: (Map<String, Object?> payload) async {
      if (current == null) {
        await api.createTaxCountryMapping(payload);
      } else {
        await api.updateTaxCountryMapping(current.id, payload);
      }
    },
  );
}

// -------------------------------------------------------- migration mapping

Future<bool?> showTaxMigrationMappingForm(
  BuildContext context,
  ApiClient api,
  TaxMigrationMappingRecord? current,
) async {
  final TaxChoices choices;
  try {
    choices = await loadTaxChoices(api, profiles: true);
  } on ApiException catch (exception) {
    if (!context.mounted) return null;
    return _refused(context, exception);
  }
  if (!context.mounted) return null;
  return showTaxMasterDialog(
    context,
    title:
        current == null ? 'Create migration mapping' : 'Edit migration mapping',
    noun: 'migration mapping',
    isEdit: current != null,
    fields: <TaxFieldSpec>[
      const TaxFieldSpec(
        key: 'legacy_tax_code',
        label: 'Old tax code',
        required: true,
      ),
      const TaxFieldSpec(
        key: 'legacy_tax_name',
        label: 'Old tax name',
        required: true,
      ),
      const TaxFieldSpec(key: 'source_system', label: 'Came from'),
      const TaxFieldSpec(
        key: 'legacy_rate',
        label: 'Old rate (%)',
        kind: TaxFieldKind.decimal,
        min: 0,
        max: 100,
      ),
      TaxFieldSpec(
        key: 'target_tax_profile_id',
        label: 'Becomes tax profile',
        kind: TaxFieldKind.select,
        options: choices.profiles,
      ),
      const TaxFieldSpec(
        key: 'keep_historical',
        label: 'Keep the old tax on historical documents',
        kind: TaxFieldKind.toggle,
      ),
      const TaxFieldSpec(
        key: 'notes',
        label: 'Notes',
        kind: TaxFieldKind.multiline,
      ),
    ],
    initial: <String, Object?>{
      'legacy_tax_code': current?.legacyTaxCode ?? '',
      'legacy_tax_name': current?.legacyTaxName ?? '',
      'source_system': current?.sourceSystem ?? '',
      'legacy_rate': current?.legacyRate ?? '',
      'target_tax_profile_id': current?.targetTaxProfileId ?? '',
      'keep_historical': current?.keepHistorical ?? true,
      'notes': current?.notes ?? '',
    },
    onSave: (Map<String, Object?> payload) async {
      if (current == null) {
        await api.createTaxMigrationMapping(payload);
      } else {
        await api.updateTaxMigrationMapping(current.id, payload);
      }
    },
  );
}

// --------------------------------------------------------------------- rule

/// A stored condition as the editor's row.
Map<String, Object?> _conditionRow(TaxRuleConditionRecord c) {
  final Object? json = c.valueJson;
  final List<Object?>? listed = json is Map && json['values'] is List
      ? List<Object?>.from(json['values'] as List)
      : json is List
          ? List<Object?>.from(json)
          : null;
  String type = 'text';
  String value = c.valueText;
  bool flag = false;
  if (listed != null) {
    value = listed.join(', ');
  } else if (c.valueBoolean != null) {
    type = 'boolean';
    flag = c.valueBoolean!;
  } else if (c.valueDate.isNotEmpty) {
    type = 'date';
    value = c.valueDate;
  } else if (c.valueNumber.isNotEmpty) {
    type = 'number';
    value = c.valueNumber;
  }
  return <String, Object?>{
    'field_key': c.fieldKey,
    'operator': c.operatorType,
    'value_type': type,
    'value': value,
    'value_bool': flag,
  };
}

/// One condition row as the server declares it.
Map<String, Object?> _conditionPayload(Map<String, Object?> row, int index) {
  final String operator = '${row['operator']}';
  final String value = '${row['value']}'.trim();
  final Map<String, Object?> out = <String, Object?>{
    'sequence': index + 1,
    'field_key': '${row['field_key']}'.trim(),
    'operator': operator,
  };
  if (taxValuelessOperators.contains(operator)) return out;
  if (taxListOperators.contains(operator)) {
    final List<String> parts = _splitList(value);
    out['value_json'] = <String, Object?>{
      'values': operator == 'BETWEEN'
          ? <num>[for (final String p in parts) num.parse(p)]
          : parts,
    };
    return out;
  }
  final bool comparison = const <String>{
    'GREATER_THAN',
    'GREATER_OR_EQUAL',
    'LESS_THAN',
    'LESS_OR_EQUAL',
  }.contains(operator);
  switch (comparison ? 'number' : '${row['value_type']}') {
    case 'number':
      out['value_number'] = value;
    case 'date':
      out['value_date'] = value;
    case 'boolean':
      out['value_boolean'] = row['value_bool'] == true;
    default:
      out['value_text'] = value;
  }
  return out;
}

List<TaxFieldSpec> _conditionFields(Map<String, Object?> row) {
  final String operator = '${row['operator']}';
  return <TaxFieldSpec>[
    const TaxFieldSpec(
      key: 'field_key',
      label: 'Field',
      required: true,
      helper: 'e.g. transaction_type',
    ),
    const TaxFieldSpec(
      key: 'operator',
      label: 'Operator',
      kind: TaxFieldKind.select,
      required: true,
      options: taxOperatorOptions,
    ),
    if (taxListOperators.contains(operator))
      TaxFieldSpec(
        key: 'value',
        label: operator == 'BETWEEN' ? 'Low, high' : 'Values (comma separated)',
        required: true,
        wide: true,
        check: operator == 'BETWEEN' ? _twoNumbers : null,
      )
    else if (!taxValuelessOperators.contains(operator)) ...<TaxFieldSpec>[
      if (operator == 'EQUALS' || operator == 'NOT_EQUALS')
        const TaxFieldSpec(
          key: 'value_type',
          label: 'Value is a',
          kind: TaxFieldKind.select,
          required: true,
          options: taxValueTypeOptions,
        ),
      if ('${row['value_type']}' == 'boolean' &&
          (operator == 'EQUALS' || operator == 'NOT_EQUALS'))
        const TaxFieldSpec(
          key: 'value_bool',
          label: 'Value',
          kind: TaxFieldKind.toggle,
        )
      else
        TaxFieldSpec(
          key: 'value',
          label: 'Value',
          required: true,
          kind: '${row['value_type']}' == 'date' &&
                  (operator == 'EQUALS' || operator == 'NOT_EQUALS')
              ? TaxFieldKind.date
              : operator == 'EQUALS' || operator == 'NOT_EQUALS'
                  ? ('${row['value_type']}' == 'number'
                      ? TaxFieldKind.decimal
                      : TaxFieldKind.text)
                  : TaxFieldKind.decimal,
          min: operator == 'EQUALS' || operator == 'NOT_EQUALS' ? null : 0,
        ),
    ],
  ];
}

List<TaxFieldSpec> _actionFields(
  Map<String, Object?> row,
  TaxChoices choices,
) {
  final String type = '${row['action_type']}';
  return <TaxFieldSpec>[
    const TaxFieldSpec(
      key: 'action_type',
      label: 'Then',
      kind: TaxFieldKind.select,
      required: true,
      options: taxActionOptions,
      wide: true,
    ),
    if (type == 'APPLY_TAX_PROFILE')
      TaxFieldSpec(
        key: 'target_tax_profile_id',
        label: 'Tax profile',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.profiles,
      ),
    if (type == 'APPLY_TAX_COMPONENT' ||
        type == 'OVERRIDE_COMPONENT_PERCENTAGE')
      TaxFieldSpec(
        key: 'target_tax_component_id',
        label: 'Tax component',
        kind: TaxFieldKind.select,
        required: true,
        options: choices.components,
      ),
    if (type == 'OVERRIDE_COMPONENT_PERCENTAGE')
      const TaxFieldSpec(
        key: 'percentage_override',
        label: 'New rate (%)',
        kind: TaxFieldKind.decimal,
        required: true,
        min: 0,
        max: 100,
      ),
  ];
}

Map<String, Object?> _actionPayload(Map<String, Object?> row, int index) {
  final String type = '${row['action_type']}';
  final Object? parameters = row['_parameters'];
  return <String, Object?>{
    'sequence': index + 1,
    'action_type': type,
    if (type == 'APPLY_TAX_PROFILE')
      'target_tax_profile_id': row['target_tax_profile_id'],
    if (type == 'APPLY_TAX_COMPONENT' ||
        type == 'OVERRIDE_COMPONENT_PERCENTAGE')
      'target_tax_component_id': row['target_tax_component_id'],
    if (type == 'OVERRIDE_COMPONENT_PERCENTAGE')
      'percentage_override': '${row['percentage_override']}'.trim(),
    if (parameters is Map && parameters.isNotEmpty) 'parameters': parameters,
  };
}

Future<bool?> showTaxRuleForm(
  BuildContext context,
  ApiClient api,
  TaxRuleRecord? current,
) async {
  final TaxChoices choices;
  try {
    choices = await loadTaxChoices(
      api,
      components: true,
      profiles: true,
      countries: true,
      businessProfiles: true,
    );
  } on ApiException catch (exception) {
    if (!context.mounted) return null;
    return _refused(context, exception);
  }
  if (!context.mounted) return null;
  return showTaxMasterDialog(
    context,
    title: current == null ? 'Create tax rule' : 'Edit tax rule',
    noun: 'tax rule',
    isEdit: current != null,
    fields: <TaxFieldSpec>[
      const TaxFieldSpec(
        key: 'code',
        label: 'Code',
        required: true,
        uppercase: true,
      ),
      const TaxFieldSpec(key: 'name', label: 'Name', required: true),
      const TaxFieldSpec(
        key: 'description',
        label: 'Description',
        kind: TaxFieldKind.multiline,
      ),
      const TaxFieldSpec(
        key: 'priority',
        label: 'Priority',
        kind: TaxFieldKind.integer,
        required: true,
        min: 1,
        max: 100000,
        helper: 'Lower numbers are tried first; the first match wins.',
      ),
      const TaxFieldSpec(
        key: 'status',
        label: 'Status',
        kind: TaxFieldKind.select,
        required: true,
        options: taxStatusOptions,
      ),
      TaxFieldSpec(
        key: 'tax_profile_id',
        label: 'Tax profile',
        kind: TaxFieldKind.select,
        options: choices.profiles,
      ),
      TaxFieldSpec(
        key: 'country_id',
        label: 'Country',
        kind: TaxFieldKind.select,
        options: choices.countries,
      ),
      TaxFieldSpec(
        key: 'business_profile_id',
        label: 'Business profile',
        kind: TaxFieldKind.select,
        options: choices.businessProfiles,
      ),
      const TaxFieldSpec(
        key: 'effective_from',
        label: 'Effective from',
        kind: TaxFieldKind.date,
      ),
      const TaxFieldSpec(
        key: 'effective_to',
        label: 'Effective to',
        kind: TaxFieldKind.date,
      ),
    ],
    initial: <String, Object?>{
      'code': current?.code ?? '',
      'name': current?.name ?? '',
      'description': current?.description ?? '',
      'priority': '${current?.priority ?? 100}',
      'status': current?.status ?? 'DRAFT',
      'tax_profile_id': current == null
          ? _firstOr(choices.profiles, '')
          : current.taxProfileId,
      'country_id': current?.countryId ?? '',
      'business_profile_id': current?.businessProfileId ?? '',
      'effective_from': current?.effectiveFrom ?? '',
      'effective_to': current?.effectiveTo ?? '',
    },
    rows: <TaxRowsSpec>[
      TaxRowsSpec(
        key: 'conditions',
        title: 'Conditions (all must hold)',
        addLabel: 'Add condition',
        emptyText: 'No conditions: the rule matches every transaction in '
            'its scope.',
        maxRows: 100,
        initialRows: <Map<String, Object?>>[
          for (final TaxRuleConditionRecord c
              in current?.conditions ?? const <TaxRuleConditionRecord>[])
            _conditionRow(c),
        ],
        newRow: () => <String, Object?>{
          'field_key': '',
          'operator': 'EQUALS',
          'value_type': 'text',
          'value': '',
          'value_bool': false,
        },
        fieldsFor: _conditionFields,
        toPayload: _conditionPayload,
      ),
      TaxRowsSpec(
        key: 'actions',
        title: 'Actions',
        addLabel: 'Add action',
        emptyText: 'No actions yet.',
        maxRows: 50,
        initialRows: <Map<String, Object?>>[
          for (final TaxRuleActionRecord a
              in current?.actions ?? const <TaxRuleActionRecord>[])
            <String, Object?>{
              'action_type': a.actionType,
              'target_tax_profile_id': a.targetTaxProfileId,
              'target_tax_component_id': a.targetTaxComponentId,
              'percentage_override': a.percentageOverride,
              '_parameters': a.parameters,
            },
        ],
        newRow: () => <String, Object?>{
          'action_type': 'APPLY_TAX_PROFILE',
          'target_tax_profile_id': '',
          'target_tax_component_id': '',
          'percentage_override': '',
        },
        fieldsFor: (Map<String, Object?> row) => _actionFields(row, choices),
        toPayload: _actionPayload,
      ),
    ],
    onSave: (Map<String, Object?> payload) async {
      if (current == null) {
        await api.createTaxRule(payload);
      } else {
        await api.updateTaxRule(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
    },
  );
}

/// A read the form needed was refused: say so and do not open a form that
/// would have empty drop-downs.
Future<bool?> _refused(BuildContext context, ApiException exception) async {
  if (!context.mounted) return null;
  NotificationService.show(
    context,
    exception.message,
    kind: AppNotificationKind.error,
  );
  return null;
}
