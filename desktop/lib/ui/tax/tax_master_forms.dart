// Forms for the tax masters that have no screen of their own: components,
// profiles, country mappings, migration mappings and rules.
//
// D-DLG-4: these used to be one generic dialog of raw text boxes labelled by
// API keys (`tax_system_id`, `is_default`), with a rule's conditions and a
// profile's components typed as JSON. It also closed *before* the save ran, so
// a refusal was reported after the typing was gone, and it leaked its
// controllers. Here the dialog owns its state, calls the save itself, keeps
// the form open with the server's message on a refusal, and closes only on
// success.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';

/// How a field is asked for.
enum TaxFieldKind { text, multiline, integer, decimal, select, toggle, date }

/// One entry of a drop-down: the id the server wants and the name people read.
class TaxOption {
  const TaxOption(this.value, this.label);

  final String value;
  final String label;
}

/// One field of a form or of a repeating row.
class TaxFieldSpec {
  const TaxFieldSpec({
    required this.key,
    required this.label,
    this.kind = TaxFieldKind.text,
    this.required = false,
    this.options = const <TaxOption>[],
    this.helper,
    this.uppercase = false,
    this.clearable = true,
    this.min,
    this.max,
    this.wide = false,
    this.check,
  });

  final String key;
  final String label;
  final TaxFieldKind kind;

  /// An extra check on a non-empty value, returning the complaint.
  final String? Function(String text)? check;
  final bool required;
  final List<TaxOption> options;
  final String? helper;

  /// Codes are stored upper-case; the field says so rather than refusing.
  final bool uppercase;

  /// Whether emptying the box on an edit sends `null` (clear it) rather than
  /// leaving the stored value alone.
  final bool clearable;
  final num? min;
  final num? max;
  final bool wide;
}

/// A repeating list of rows, for a rule's conditions or a profile's
/// components, in place of a JSON box.
class TaxRowsSpec {
  const TaxRowsSpec({
    required this.key,
    required this.title,
    required this.addLabel,
    required this.emptyText,
    required this.initialRows,
    required this.fieldsFor,
    required this.toPayload,
    required this.newRow,
    this.maxRows = 100,
  });

  final String key;
  final String title;
  final String addLabel;
  final String emptyText;
  final List<Map<String, Object?>> initialRows;

  /// The fields a row shows, which may depend on what the row already holds
  /// (a condition's value box follows its operator).
  final List<TaxFieldSpec> Function(Map<String, Object?> row) fieldsFor;

  /// One row as the server declares it. [index] is its position, from zero.
  final Map<String, Object?> Function(Map<String, Object?> row, int index)
      toPayload;
  final Map<String, Object?> Function() newRow;
  final int maxRows;
}

final RegExp _codePattern = RegExp(r'^[A-Z0-9_-]+$');

/// Whether [text] is a code the server will accept.
bool isTaxCode(String text) =>
    text.length >= 2 && text.length <= 50 && _codePattern.hasMatch(text);

/// The master forms' dialog. Returns true once the save has succeeded.
Future<bool?> showTaxMasterDialog(
  BuildContext context, {
  required String title,
  required String noun,
  required bool isEdit,
  required List<TaxFieldSpec> fields,
  required Map<String, Object?> initial,
  required Future<void> Function(Map<String, Object?> payload) onSave,
  List<TaxRowsSpec> rows = const <TaxRowsSpec>[],
}) =>
    showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => TaxMasterDialog(
        title: title,
        noun: noun,
        isEdit: isEdit,
        fields: fields,
        initial: initial,
        onSave: onSave,
        rows: rows,
      ),
    );

class TaxMasterDialog extends StatefulWidget {
  const TaxMasterDialog({
    super.key,
    required this.title,
    required this.noun,
    required this.isEdit,
    required this.fields,
    required this.initial,
    required this.onSave,
    this.rows = const <TaxRowsSpec>[],
  });

  final String title;
  final String noun;
  final bool isEdit;
  final List<TaxFieldSpec> fields;
  final Map<String, Object?> initial;
  final Future<void> Function(Map<String, Object?> payload) onSave;
  final List<TaxRowsSpec> rows;

  @override
  State<TaxMasterDialog> createState() => _TaxMasterDialogState();
}

class _TaxMasterDialogState extends State<TaxMasterDialog> {
  late final Map<String, Object?> _values = <String, Object?>{
    for (final TaxFieldSpec field in widget.fields)
      field.key: widget.initial[field.key] ??
          (field.kind == TaxFieldKind.toggle ? false : ''),
  };
  late final Map<String, List<Map<String, Object?>>> _rows =
      <String, List<Map<String, Object?>>>{
    for (final TaxRowsSpec spec in widget.rows)
      spec.key: <Map<String, Object?>>[
        for (final Map<String, Object?> row in spec.initialRows)
          <String, Object?>{...row, '_id': _nextRowId++},
      ],
  };
  int _nextRowId = 0;
  final Map<String, String> _errors = <String, String>{};
  bool _saving = false;
  String? _failure;

  String _text(String key) => (_values[key] ?? '').toString().trim();

  /// Checks one value against its spec, returning the complaint or null.
  String? _check(TaxFieldSpec field, Object? raw) {
    if (field.kind == TaxFieldKind.toggle) return null;
    final String text = (raw ?? '').toString().trim();
    if (text.isEmpty) return field.required ? 'Required' : null;
    switch (field.kind) {
      case TaxFieldKind.integer:
        final int? value = int.tryParse(text);
        if (value == null) return 'Whole number';
        if (field.min != null && value < field.min!) {
          return 'At least ${field.min}';
        }
        if (field.max != null && value > field.max!) {
          return 'At most ${field.max}';
        }
      case TaxFieldKind.decimal:
        final double? value = double.tryParse(text);
        if (value == null) return 'Number';
        if (field.min != null && value < field.min!) {
          return 'At least ${field.min}';
        }
        if (field.max != null && value > field.max!) {
          return 'At most ${field.max}';
        }
      case TaxFieldKind.text when field.uppercase:
        if (!isTaxCode(text.toUpperCase())) {
          return 'Letters, digits, - or _ (2 to 50)';
        }
      default:
        break;
    }
    return field.check?.call(text);
  }

  dynamic _send(TaxFieldSpec field, Object? raw, {required bool forEdit}) {
    if (field.kind == TaxFieldKind.toggle) return raw == true;
    String text = (raw ?? '').toString().trim();
    if (text.isEmpty) {
      return forEdit && field.clearable ? null : _omit;
    }
    if (field.uppercase) text = text.toUpperCase();
    return text;
  }

  static const Object _omit = Object();

  Future<void> _save() async {
    _errors.clear();
    for (final TaxFieldSpec field in widget.fields) {
      final String? problem = _check(field, _values[field.key]);
      if (problem != null) _errors[field.key] = problem;
    }
    final String from = _text('effective_from');
    final String to = _text('effective_to');
    if (from.isNotEmpty && to.isNotEmpty && from.compareTo(to) > 0) {
      _errors['effective_to'] = 'Cannot be before the start';
    }
    for (final TaxRowsSpec spec in widget.rows) {
      for (final Map<String, Object?> row in _rows[spec.key]!) {
        for (final TaxFieldSpec field in spec.fieldsFor(row)) {
          final String? problem = _check(field, row[field.key]);
          if (problem != null) _errors['${row['_id']}.${field.key}'] = problem;
        }
      }
    }
    if (_errors.isNotEmpty) {
      setState(() => _failure = 'Some fields need attention.');
      return;
    }
    final Map<String, Object?> payload = <String, Object?>{};
    for (final TaxFieldSpec field in widget.fields) {
      final dynamic sent =
          _send(field, _values[field.key], forEdit: widget.isEdit);
      if (!identical(sent, _omit)) payload[field.key] = sent;
    }
    for (final TaxRowsSpec spec in widget.rows) {
      final List<Map<String, Object?>> list = _rows[spec.key]!;
      payload[spec.key] = <Map<String, Object?>>[
        for (int i = 0; i < list.length; i++) spec.toPayload(list[i], i),
      ];
    }
    setState(() {
      _saving = true;
      _failure = null;
    });
    try {
      await widget.onSave(payload);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _failure = saveFailureMessage(
          exception,
          widget.noun,
          changesKept: true,
        );
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final double maxHeight = MediaQuery.sizeOf(context).height * 0.9;
    return AlertDialog(
      title: Text(widget.title),
      content: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: 700, maxHeight: maxHeight - 140),
        child: SizedBox(
          width: 700,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (_failure != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Container(
                      key: const ValueKey<String>('tax-form-failure'),
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.errorContainer,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        _failure!,
                        style: TextStyle(
                          color: theme.colorScheme.onErrorContainer,
                        ),
                      ),
                    ),
                  ),
                Wrap(
                  spacing: 16,
                  runSpacing: 12,
                  children: <Widget>[
                    for (final TaxFieldSpec field in widget.fields)
                      SizedBox(
                        width:
                            field.wide || field.kind == TaxFieldKind.multiline
                                ? 700
                                : 342,
                        child: _FieldControl(
                          fieldKey: ValueKey<String>('tax-field-${field.key}'),
                          spec: field,
                          value: _values[field.key],
                          error: _errors[field.key],
                          enabled: !_saving,
                          onChanged: (Object? value) => setState(() {
                            _values[field.key] = value;
                            _errors.remove(field.key);
                          }),
                        ),
                      ),
                  ],
                ),
                for (final TaxRowsSpec spec in widget.rows) _rowsEditor(spec),
              ],
            ),
          ),
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save'),
        ),
      ],
    );
  }

  Widget _rowsEditor(TaxRowsSpec spec) {
    final List<Map<String, Object?>> list = _rows[spec.key]!;
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(spec.title, style: theme.textTheme.titleSmall),
              ),
              TextButton.icon(
                key: ValueKey<String>('tax-rows-add-${spec.key}'),
                onPressed: _saving || list.length >= spec.maxRows
                    ? null
                    : () => setState(() {
                          list.add(<String, Object?>{
                            ...spec.newRow(),
                            '_id': _nextRowId++,
                          });
                        }),
                icon: const Icon(Icons.add),
                label: Text(spec.addLabel),
              ),
            ],
          ),
          if (list.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(spec.emptyText, style: theme.textTheme.bodySmall),
            ),
          for (int i = 0; i < list.length; i++)
            Card(
              key: ValueKey<String>('tax-row-${spec.key}-${list[i]['_id']}'),
              margin: const EdgeInsets.only(top: 8),
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Padding(
                      padding: const EdgeInsets.only(top: 14, right: 8),
                      child: Text('${i + 1}.'),
                    ),
                    Expanded(
                      child: Wrap(
                        spacing: 12,
                        runSpacing: 10,
                        children: <Widget>[
                          for (final TaxFieldSpec field
                              in spec.fieldsFor(list[i]))
                            SizedBox(
                              width: field.wide ? 560 : 200,
                              child: _FieldControl(
                                fieldKey: ValueKey<String>(
                                  'tax-row-${spec.key}-${list[i]['_id']}-${field.key}',
                                ),
                                spec: field,
                                value: list[i][field.key],
                                error:
                                    _errors['${list[i]['_id']}.${field.key}'],
                                enabled: !_saving,
                                identity: '${list[i]['_id']}',
                                onChanged: (Object? value) => setState(() {
                                  list[i][field.key] = value;
                                  _errors.remove(
                                    '${list[i]['_id']}.${field.key}',
                                  );
                                }),
                              ),
                            ),
                        ],
                      ),
                    ),
                    IconButton(
                      key: ValueKey<String>('tax-row-remove-${spec.key}-$i'),
                      tooltip: 'Remove',
                      onPressed: _saving
                          ? null
                          : () => setState(() => list.removeAt(i)),
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// One input, chosen by the field's kind.
class _FieldControl extends StatelessWidget {
  const _FieldControl({
    required this.fieldKey,
    required this.spec,
    required this.value,
    required this.error,
    required this.enabled,
    required this.onChanged,
    this.identity = '',
  });

  final Key fieldKey;
  final TaxFieldSpec spec;
  final Object? value;
  final String? error;
  final bool enabled;
  final ValueChanged<Object?> onChanged;

  /// Distinguishes the same field in two rows, so a removed row does not hand
  /// its typed text to the one below it.
  final String identity;

  String get _label => spec.required ? '${spec.label} *' : spec.label;

  @override
  Widget build(BuildContext context) {
    switch (spec.kind) {
      case TaxFieldKind.toggle:
        return SwitchListTile(
          key: fieldKey,
          contentPadding: EdgeInsets.zero,
          dense: true,
          title: Text(spec.label),
          subtitle: spec.helper == null ? null : Text(spec.helper!),
          value: value == true,
          onChanged: enabled ? (bool v) => onChanged(v) : null,
        );
      case TaxFieldKind.select:
        final String current = (value ?? '').toString();
        final bool known =
            current.isEmpty || spec.options.any((o) => o.value == current);
        return DropdownButtonFormField<String>(
          key: fieldKey,
          initialValue: known ? current : '',
          isExpanded: true,
          decoration: InputDecoration(
            labelText: _label,
            helperText: spec.helper,
            errorText: error,
            border: const OutlineInputBorder(),
          ),
          items: <DropdownMenuItem<String>>[
            if (!spec.required)
              const DropdownMenuItem<String>(value: '', child: Text('None')),
            if (spec.required && current.isEmpty)
              const DropdownMenuItem<String>(
                value: '',
                child: Text('Choose...'),
              ),
            for (final TaxOption option in spec.options)
              DropdownMenuItem<String>(
                value: option.value,
                child: Text(option.label, overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: enabled ? (String? v) => onChanged(v ?? '') : null,
        );
      case TaxFieldKind.date:
        final String current = (value ?? '').toString();
        return InkWell(
          key: fieldKey,
          onTap: !enabled
              ? null
              : () async {
                  final DateTime now = DateTime.now();
                  final DateTime? picked = await showDatePicker(
                    context: context,
                    initialDate: DateTime.tryParse(current) ?? now,
                    firstDate: DateTime(2000),
                    lastDate: DateTime(2100),
                  );
                  if (picked != null) {
                    onChanged(_isoDate(picked));
                  }
                },
          child: InputDecorator(
            decoration: InputDecoration(
              labelText: _label,
              helperText: spec.helper,
              errorText: error,
              border: const OutlineInputBorder(),
              suffixIcon: current.isEmpty
                  ? const Icon(Icons.calendar_today_outlined, size: 18)
                  : IconButton(
                      tooltip: 'Clear date',
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: enabled ? () => onChanged('') : null,
                    ),
            ),
            child: Text(current.isEmpty ? '' : current),
          ),
        );
      case TaxFieldKind.text:
      case TaxFieldKind.multiline:
      case TaxFieldKind.integer:
      case TaxFieldKind.decimal:
        return TextFormField(
          key: ValueKey<String>(
              '${(fieldKey as ValueKey<String>).value}-$identity'),
          initialValue: (value ?? '').toString(),
          enabled: enabled,
          minLines: spec.kind == TaxFieldKind.multiline ? 2 : 1,
          maxLines: spec.kind == TaxFieldKind.multiline ? 4 : 1,
          textCapitalization: spec.uppercase
              ? TextCapitalization.characters
              : TextCapitalization.none,
          keyboardType: spec.kind == TaxFieldKind.integer
              ? TextInputType.number
              : spec.kind == TaxFieldKind.decimal
                  ? const TextInputType.numberWithOptions(decimal: true)
                  : TextInputType.text,
          decoration: InputDecoration(
            labelText: _label,
            helperText: spec.helper,
            errorText: error,
            border: const OutlineInputBorder(),
          ),
          onChanged: onChanged,
        );
    }
  }
}

String _isoDate(DateTime date) => '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';

/// The common status choices of a tax master.
const List<TaxOption> taxStatusOptions = <TaxOption>[
  TaxOption('DRAFT', 'Draft'),
  TaxOption('ACTIVE', 'Active'),
  TaxOption('INACTIVE', 'Inactive'),
  TaxOption('ARCHIVED', 'Archived'),
];

/// Operators a rule condition may use, with the names people read.
const List<TaxOption> taxOperatorOptions = <TaxOption>[
  TaxOption('EQUALS', 'Equals'),
  TaxOption('NOT_EQUALS', 'Does not equal'),
  TaxOption('IN', 'Is one of'),
  TaxOption('NOT_IN', 'Is not one of'),
  TaxOption('GREATER_THAN', 'Greater than'),
  TaxOption('GREATER_OR_EQUAL', 'Greater than or equal to'),
  TaxOption('LESS_THAN', 'Less than'),
  TaxOption('LESS_OR_EQUAL', 'Less than or equal to'),
  TaxOption('BETWEEN', 'Between (two values)'),
  TaxOption('EXISTS', 'Has a value'),
  TaxOption('NOT_EXISTS', 'Has no value'),
];

/// What a rule does when it matches.
const List<TaxOption> taxActionOptions = <TaxOption>[
  TaxOption('APPLY_TAX_PROFILE', 'Apply a tax profile'),
  TaxOption('APPLY_TAX_COMPONENT', 'Apply a tax component'),
  TaxOption('EXEMPT_TAX', 'Exempt from tax'),
  TaxOption('ZERO_RATED', 'Zero rated'),
  TaxOption('REVERSE_CHARGE', 'Reverse charge'),
  TaxOption('INPUT_CREDIT_ALLOWED', 'Input credit allowed'),
  TaxOption('INPUT_CREDIT_BLOCKED', 'Input credit blocked'),
  TaxOption('OVERRIDE_COMPONENT_PERCENTAGE', 'Override a component rate'),
];

/// The ways a single condition value can be typed.
const List<TaxOption> taxValueTypeOptions = <TaxOption>[
  TaxOption('text', 'Text'),
  TaxOption('number', 'Number'),
  TaxOption('date', 'Date'),
  TaxOption('boolean', 'Yes / No'),
];

/// Operators that compare against a list rather than one value.
const Set<String> taxListOperators = <String>{'IN', 'NOT_IN', 'BETWEEN'};

/// Operators that need no value at all.
const Set<String> taxValuelessOperators = <String>{'EXISTS', 'NOT_EXISTS'};
