import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';

/// Edit one numbering series, or describe a new one.
///
/// The form a firm uses to say what its own documents are called. It carries
/// two rules that are easy to get wrong and expensive to discover late.
///
/// **The counter is not editable on an existing series.** `next_sequence` is
/// advanced by the server under a lock, and setting it back would mint a
/// number a document already holds -- which the per-firm uniqueness key would
/// then refuse, on a document somebody is trying to raise. It is offered only
/// when the series is being created, where "start at 500 because that is where
/// the old system left off" is a real and ordinary thing to want.
///
/// **A series that restarts each financial year has to say which year it is.**
/// Otherwise the first document of April repeats a number issued in March.
/// The server refuses that combination; this form says so while it is being
/// chosen rather than leaving the refusal to explain it afterwards.
class NumberingSeriesEditor extends StatefulWidget {
  const NumberingSeriesEditor({
    super.key,
    required this.documentTypes,
    this.rule,
  });

  /// The types a new series can be attached to. Empty when editing, since an
  /// existing series keeps the type it was made for.
  final List<DocumentTypeRecord> documentTypes;

  /// The series being edited, or null to describe a new one.
  final NumberingRule? rule;

  @override
  State<NumberingSeriesEditor> createState() => _NumberingSeriesEditorState();
}

class _NumberingSeriesEditorState extends State<NumberingSeriesEditor> {
  late final TextEditingController _code;
  late final TextEditingController _name;
  late final TextEditingController _prefix;
  late final TextEditingController _suffix;
  late final TextEditingController _separator;
  late final TextEditingController _padding;
  late final TextEditingController _startAt;

  String? _documentTypeId;
  late bool _includeFinancialYear;
  late bool _includeBranchCode;
  late bool _includeCompanyCode;
  late bool _autoReset;
  late bool _manualAllowed;
  late bool _isDefault;
  late bool _isActive;

  bool get _creating => widget.rule == null;

  /// Whether the series would issue the same number in two financial years.
  ///
  /// The server refuses this, and says the same thing. Shown here so the
  /// person choosing it finds out while they are choosing rather than when
  /// the save comes back.
  bool get _wouldRepeatItself => _autoReset && !_includeFinancialYear;

  @override
  void initState() {
    super.initState();
    final NumberingRule? rule = widget.rule;
    _code = TextEditingController(text: rule?.code ?? '');
    _name = TextEditingController(text: rule?.name ?? '');
    _prefix = TextEditingController(text: rule?.prefix ?? '');
    _suffix = TextEditingController(text: rule?.suffix ?? '');
    _separator = TextEditingController(text: rule?.separator ?? '-');
    _padding = TextEditingController(
      text: '${rule?.sequencePadding ?? 6}',
    );
    _startAt = TextEditingController(text: '1');
    _documentTypeId = rule?.documentTypeId ??
        (widget.documentTypes.isEmpty ? null : widget.documentTypes.first.id);
    _includeFinancialYear = rule?.includeFinancialYear ?? true;
    _includeBranchCode = rule?.includeBranchCode ?? false;
    _includeCompanyCode = rule?.includeCompanyCode ?? false;
    // Both default to on for a new series, which is the shape every seeded
    // rule has and the only pairing that cannot repeat a number.
    _autoReset = rule?.autoReset ?? true;
    _manualAllowed = rule?.manualAllowed ?? false;
    _isDefault = rule?.isDefault ?? false;
    _isActive = rule?.isActive ?? true;
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _prefix.dispose();
    _suffix.dispose();
    _separator.dispose();
    _padding.dispose();
    _startAt.dispose();
    super.dispose();
  }

  /// What the number will look like, assembled from the choices on screen.
  ///
  /// A sketch, not the answer: the real one comes from `previewNumber`, which
  /// knows the financial year, the branch and the counter. This is here so the
  /// effect of a switch is visible as it is flipped.
  String get _sketch {
    final int padding = int.tryParse(_padding.text) ?? 6;
    final String separator =
        _separator.text.isEmpty ? '-' : _separator.text;
    final List<String> parts = [
      if (_prefix.text.isNotEmpty) _prefix.text,
      if (_includeCompanyCode) 'FIRM',
      if (_includeBranchCode) 'BR',
      if (_includeFinancialYear) '2026-2027',
      '0' * (padding < 1 ? 6 : padding),
      if (_suffix.text.isNotEmpty) _suffix.text,
    ];
    return parts.join(separator);
  }

  /// The body to send. Every field is stated, so nothing is left to a default.
  Map<String, dynamic> get result => <String, dynamic>{
        'document_type_id': _documentTypeId,
        'code': _code.text.trim().toUpperCase(),
        'name': _name.text.trim(),
        'prefix': _prefix.text.trim(),
        'suffix': _suffix.text.trim(),
        'separator': _separator.text.isEmpty ? '-' : _separator.text,
        'include_financial_year': _includeFinancialYear,
        'include_branch_code': _includeBranchCode,
        'include_company_code': _includeCompanyCode,
        'auto_reset': _autoReset,
        'manual_allowed': _manualAllowed,
        'sequence_padding': int.tryParse(_padding.text) ?? 6,
        'is_default': _isDefault,
        'is_active': _isActive,
        // Only on create. Sending it for an existing series would move a
        // counter the server owns, and `exclude_unset` on the server means
        // leaving it out genuinely leaves it alone.
        if (_creating) 'next_sequence': int.tryParse(_startAt.text) ?? 1,
      };

  bool get _isComplete =>
      _documentTypeId != null &&
      _code.text.trim().length >= 2 &&
      _name.text.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return WorkspaceDialog(
      title: _creating ? 'New numbering series' : 'Edit numbering series',
      subtitle: 'What this firm calls its own documents.',
      icon: Icons.tag,
      onClose: () => Navigator.of(context).pop(),
      onSave: _isComplete ? () => Navigator.of(context).pop(result) : null,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_creating)
              DropdownButtonFormField<String>(
                initialValue: _documentTypeId,
                decoration: const InputDecoration(
                  labelText: 'Document type',
                  helperText: 'Which kind of document this series numbers.',
                ),
                items: [
                  for (final DocumentTypeRecord type in widget.documentTypes)
                    DropdownMenuItem<String>(
                      value: type.id,
                      child: Text('${type.name} (${type.code})'),
                    ),
                ],
                onChanged: (String? value) =>
                    setState(() => _documentTypeId = value),
              ),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _code,
                  textCapitalization: TextCapitalization.characters,
                  decoration: const InputDecoration(
                    labelText: 'Code',
                    helperText: 'Letters, digits, _ and - only.',
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                flex: 2,
                child: TextField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Name'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _prefix,
                  decoration: const InputDecoration(labelText: 'Prefix'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextField(
                  controller: _suffix,
                  decoration: const InputDecoration(labelText: 'Suffix'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              SizedBox(
                width: 110,
                child: TextField(
                  controller: _separator,
                  decoration: const InputDecoration(labelText: 'Separator'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              SizedBox(
                width: 110,
                child: TextField(
                  controller: _padding,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Digits'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.lg),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Looks like', style: theme.textTheme.labelMedium),
                    const SizedBox(height: AppSpacing.xs),
                    Text(_sketch, style: theme.textTheme.titleMedium),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'A sketch. The real next number comes from the server, '
                      'which knows the year, the branch and the counter.',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            SwitchListTile(
              value: _includeFinancialYear,
              onChanged: (bool value) =>
                  setState(() => _includeFinancialYear = value),
              title: const Text('Include the financial year'),
              subtitle: const Text(
                'Puts 2026-2027 in the number, so documents from different '
                'years can never share one.',
              ),
            ),
            SwitchListTile(
              value: _autoReset,
              onChanged: (bool value) => setState(() => _autoReset = value),
              title: const Text('Restart numbering each financial year'),
              subtitle: Text(
                _autoReset
                    ? 'Every year begins again at 1.'
                    : 'One continuous series for the life of this rule.',
              ),
            ),
            if (_wouldRepeatItself)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.xs,
                ),
                child: Row(children: [
                  Icon(Icons.error_outline,
                      size: 18, color: theme.colorScheme.error),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'This restarts every year behind a number that does not '
                      'say which year it is, so the first document of April '
                      'would repeat one issued in March. Switch on the '
                      'financial year, or turn the restart off.',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ),
                ]),
              ),
            SwitchListTile(
              value: _includeBranchCode,
              onChanged: (bool value) =>
                  setState(() => _includeBranchCode = value),
              title: const Text('Include the branch code'),
              subtitle: const Text(
                'Each branch then counts separately, with its own run of '
                'numbers.',
              ),
            ),
            SwitchListTile(
              value: _includeCompanyCode,
              onChanged: (bool value) =>
                  setState(() => _includeCompanyCode = value),
              title: const Text('Include the firm code'),
            ),
            SwitchListTile(
              value: _manualAllowed,
              onChanged: (bool value) =>
                  setState(() => _manualAllowed = value),
              title: const Text('Allow a number to be typed in'),
              subtitle: const Text(
                'For entering a document that was written by hand elsewhere.',
              ),
            ),
            SwitchListTile(
              value: _isDefault,
              onChanged: (bool value) => setState(() => _isDefault = value),
              title: const Text('Use this series by default'),
            ),
            SwitchListTile(
              value: _isActive,
              onChanged: (bool value) => setState(() => _isActive = value),
              title: const Text('Active'),
            ),
            const SizedBox(height: AppSpacing.md),
            if (_creating)
              TextField(
                controller: _startAt,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Start numbering at',
                  helperText: 'Usually 1. Set it higher to carry on from '
                      'wherever an old system left off.',
                ),
              )
            else
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.lock_outline),
                title: Text('Next number: ${widget.rule!.nextSequence}'),
                subtitle: const Text(
                  'The counter belongs to the server, which advances it under '
                  'a lock. Moving it back here would hand out a number a '
                  'document already holds.',
                ),
              ),
          ],
        ),
      ),
    );
  }
}
