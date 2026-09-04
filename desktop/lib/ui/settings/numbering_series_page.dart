import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';
import 'numbering_series_editor.dart';

/// How every document number in the system is built.
///
/// The rule behind `SI-2026-2027-000008`. It had endpoints and no screen, so
/// "what will the next invoice be called" and "why did the numbering restart"
/// were questions only the database could answer.
///
/// Editable by a firm's own administrator, which needed the endpoints to move
/// first: they required a **platform** admin, so a firm could not change the
/// prefix on its own invoice series. What a firm calls its documents is its
/// business; the lifecycle those documents move through is still the
/// platform's, and document types and states stay where they were.
///
/// `next_sequence` remains off limits on an existing series. It is a counter
/// the server advances under a lock, and setting it back would mint a number
/// a document already holds -- so it is offered when a series is created and
/// shown read-only afterwards.
class NumberingSeriesPage extends StatefulWidget {
  const NumberingSeriesPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<NumberingSeriesPage> createState() => _NumberingSeriesPageState();
}

class _NumberingSeriesPageState extends State<NumberingSeriesPage> {
  List<NumberingRule> _rules = const [];
  List<DocumentTypeRecord> _types = const [];
  final Map<String, String> _previews = {};
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('SETTINGS_VIEW');

  /// Changing how documents are numbered is an administrative act, so it
  /// takes `SETTINGS_UPDATE` -- seeded to `FIRM_ADMIN` alone, and not to any
  /// operational role. The server enforces the same code; this only decides
  /// whether the controls are worth showing.
  bool get _canEdit => widget.permissions.hasPermission('SETTINGS_UPDATE');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<NumberingRule> rules = await widget.api.numberingRules();
      // Only needed to create a series, and only fetched where the controls
      // exist -- a reader with no permission to change anything should not be
      // made to wait on a list they cannot use.
      final List<DocumentTypeRecord> types =
          _canEdit ? await widget.api.documentTypes() : const [];
      if (!mounted) return;
      setState(() {
        _rules = rules;
        _types = types;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _rules = const [];
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Ask the server what the next number would be.
  ///
  /// The preview is asked for rather than assembled here: the pattern involves
  /// the financial year, the branch and a counter under a lock, and a client
  /// that guessed would disagree with the document that eventually gets made.
  Future<void> _preview(NumberingRule rule) async {
    try {
      final String preview = await widget.api.previewNumber(rule.id);
      if (!mounted) return;
      setState(() => _previews[rule.id] = preview);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _previews[rule.id] = exception.message);
    }
  }

  /// Describe a new series, or change one that exists.
  ///
  /// One dialog for both, because the fields are the same question either
  /// way; what differs is that a new series may say where its counter starts
  /// and an existing one may not.
  Future<void> _edit({NumberingRule? rule}) async {
    final Map<String, dynamic>? body =
        await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => NumberingSeriesEditor(documentTypes: _types, rule: rule),
    );
    if (body == null || !mounted) return;
    setState(() => _error = null);
    try {
      if (rule == null) {
        await widget.api.createNumberingRule(body);
      } else {
        await widget.api.updateNumberingRule(rule.id, body);
      }
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    // The preview is stale the moment the shape changes, and a number left on
    // screen from the old rule is worse than none.
    _previews.clear();
    await _load();
  }

  Future<void> _delete(NumberingRule rule) async {
    final bool confirmed = await showDialog<bool>(
          context: context,
          builder: (BuildContext dialogContext) => AlertDialog(
            title: const Text('Retire this numbering series?'),
            content: Text(
              'Documents already numbered by "\${rule.name}" keep the numbers '
              'they have. New documents of this kind will need another '
              'series, or the firm will not be able to raise one.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: const Text('Retire'),
              ),
            ],
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    setState(() => _error = null);
    try {
      await widget.api.deleteNumberingRule(rule.id);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    _previews.remove(rule.id);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Numbering series',
        message: 'You do not have permission to view settings.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Numbering series',
        message: 'Choose a firm to see how its documents are numbered.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        if (_canEdit)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.lg,
              AppSpacing.lg,
              0,
            ),
            child: Row(children: [
              const Expanded(
                child: Text(
                  'A series decides what this firm calls its own documents.',
                ),
              ),
              FilledButton.icon(
                onPressed: _types.isEmpty ? null : () => unawaited(_edit()),
                icon: const Icon(Icons.add),
                label: const Text('New series'),
              ),
            ]),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ),
        Expanded(
          child: _rules.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No numbering rules yet',
                  message: 'A rule is created for a document type the first '
                      'time the firm raises one of that kind, or you can '
                      'describe one here.',
                )
              : ListView.separated(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  itemCount: _rules.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) => _tile(context, _rules[index]),
                ),
        ),
      ]),
    );
  }

  Widget _tile(BuildContext context, NumberingRule rule) {
    final String? preview = _previews[rule.id];
    return ListTile(
      title: Text(rule.name),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The shape in words rather than as six booleans nobody can read.
          Text(rule.shape, style: Theme.of(context).textTheme.bodySmall),
          Text(
            'next #${rule.nextSequence}'
            '${rule.autoReset ? " · restarts each financial year" : ""}'
            '${rule.manualAllowed ? " · a number may be typed in" : ""}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (preview != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                'Next: $preview',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
        ],
      ),
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        if (rule.isDefault) const StatusBadge(label: 'DEFAULT'),
        if (!rule.isActive)
          const Padding(
            padding: EdgeInsets.only(left: AppSpacing.sm),
            child: StatusBadge(label: 'INACTIVE'),
          ),
        const SizedBox(width: AppSpacing.md),
        TextButton(
          onPressed: () => unawaited(_preview(rule)),
          child: const Text('Preview next'),
        ),
        if (_canEdit) ...[
          IconButton(
            tooltip: 'Edit',
            onPressed: () => unawaited(_edit(rule: rule)),
            icon: const Icon(Icons.edit_outlined),
          ),
          IconButton(
            tooltip: 'Retire',
            onPressed: () => unawaited(_delete(rule)),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ]),
    );
  }
}
