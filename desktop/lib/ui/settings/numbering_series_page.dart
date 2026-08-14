import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';

/// How every document number in the system is built.
///
/// The rule behind `SI-2026-2027-000008`. It had endpoints and no screen, so
/// "what will the next invoice be called" and "why did the numbering restart"
/// were questions only the database could answer.
///
/// Read-only on purpose. A numbering rule decides the identity of documents
/// that already exist, and `next_sequence` in particular is a counter the
/// server advances under a lock; a form that let somebody set it back would
/// mint a number a document already holds.
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
  final Map<String, String> _previews = {};
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('SETTINGS_VIEW');

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
      if (!mounted) return;
      setState(() => _rules = rules);
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
                      'time the firm raises one of that kind.',
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
      ]),
    );
  }
}
