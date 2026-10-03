// What awaits the signed-in person's sign-off (PLT-1): sales and purchase
// documents whose amount puts them on a chain of up to three levels. A row is
// signed at its next level, or rejected with a reason; rows of one type can be
// rejected together. The last sign-off approves the document. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/approval.dart';
import '../../models/bulk_action.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// Ask for optional remarks before signing. Returns null when dismissed and
/// the (possibly empty) text on confirm; owns its controller.
class _RemarksDialog extends StatefulWidget {
  const _RemarksDialog({required this.title});

  final String title;

  @override
  State<_RemarksDialog> createState() => _RemarksDialogState();
}

class _RemarksDialogState extends State<_RemarksDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 420,
        child: TextField(
          key: const ValueKey('sign-off-remarks'),
          controller: _controller,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Remarks (optional)'),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('sign-off-confirm'),
          onPressed: () => Navigator.of(context).pop(_controller.text.trim()),
          child: const Text('Sign off'),
        ),
      ],
    );
  }
}

/// List what is waiting, sign it off, reject it, or reject several at once.
class ApprovalsPage extends StatefulWidget {
  const ApprovalsPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<ApprovalsPage> createState() => _ApprovalsPageState();
}

class _ApprovalsPageState extends State<ApprovalsPage> {
  List<ApprovalStatus> _rows = const [];
  String? _error;
  String? _selectedId;
  ApprovalStatus? _detail;
  Set<String> _ticked = <String>{};
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayApprove =>
      widget.permissions.hasPermission('SALES_APPROVE') ||
      widget.permissions.hasPermission('PURCHASE_APPROVE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayApprove) unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<ApprovalStatus> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.documentNumber.toLowerCase().contains(q) ||
            approvalTypeLabel(row.documentType).toLowerCase().contains(q))
        .toList();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ApprovalStatus> rows = await widget.api.pendingApprovals();
      if (!mounted) return;
      final Set<String> ids = {
        for (final ApprovalStatus row in rows) row.documentId,
      };
      setState(() {
        _rows = rows;
        _loading = false;
        _ticked = _ticked.intersection(ids);
        if (_selectedId != null && !ids.contains(_selectedId)) {
          _selectedId = null;
        }
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  ApprovalStatus? get _selected {
    if (_selectedId == null) return null;
    if (_detail != null && _detail!.documentId == _selectedId) return _detail;
    return _rows.where((row) => row.documentId == _selectedId).firstOrNull;
  }

  void _pick(ApprovalStatus row) {
    setState(() {
      _selectedId = row.documentId;
      _detail = row;
    });
    unawaited(_read(row));
  }

  /// Re-read the picked document's chain, so the steps are the server's and
  /// not the list's.
  Future<void> _read(ApprovalStatus row) async {
    try {
      final ApprovalStatus fresh =
          await widget.api.approvalStatus(row.documentType, row.documentId);
      if (!mounted || _selectedId != row.documentId) return;
      setState(() => _detail = fresh);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  List<ApprovalStatus> get _tickedRows =>
      _rows.where((row) => _ticked.contains(row.documentId)).toList();

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _signOff(ApprovalStatus row) async {
    final String? remarks = await showDialog<String>(
      context: context,
      builder: (_) => _RemarksDialog(title: 'Sign off ${row.documentNumber}'),
    );
    if (remarks == null || !mounted) return;
    try {
      final ApprovalStatus after = await widget.api.signOffApproval({
        'document_type': row.documentType,
        'document_id': row.documentId,
        if (remarks.isNotEmpty) 'remarks': remarks,
      });
      if (!mounted) return;
      _tell(
        after.status == 'APPROVED'
            ? '${row.documentNumber} approved.'
            : '${row.documentNumber} signed at level ${row.nextLevel}.',
        AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      // A module refusal keeps the signature, so the list is read again.
      _tell(error.message, AppNotificationKind.error);
    }
    if (mounted) await _load();
  }

  Future<void> _reject(ApprovalStatus row) async {
    final String? reason = await askForReason(
      context,
      title: 'Reject ${row.documentNumber}',
      explanation: 'The document goes back to its author with this reason.',
      confirmLabel: 'Reject',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.rejectApproval({
        'document_type': row.documentType,
        'document_id': row.documentId,
        'reason': reason,
      });
      if (!mounted) return;
      _tell('${row.documentNumber} rejected.', AppNotificationKind.success);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
    if (mounted) await _load();
  }

  Future<void> _bulkReject() async {
    final List<ApprovalStatus> rows = _tickedRows;
    if (rows.isEmpty) return;
    final Set<String> types = {
      for (final ApprovalStatus row in rows) row.documentType,
    };
    if (types.length > 1) {
      _tell('Tick documents of one type at a time.', AppNotificationKind.error);
      return;
    }
    final String type = types.first;
    final String? reason = await askForReason(
      context,
      title: 'Reject ${rows.length} documents',
      explanation: 'Each document is rejected on its own; one the server '
          'refuses does not stop the others. The reason is recorded on every '
          'document rejected.',
      confirmLabel: 'Reject documents',
    );
    if (reason == null || !mounted) return;
    await runBulkAction(
      context,
      verb: 'Rejected',
      rows: [
        for (final ApprovalStatus row in rows)
          (id: row.documentId, version: null),
      ],
      send: (List<BulkRow> picked) => widget.api.bulkRejectApprovals({
        'document_type': type,
        'items': [
          for (final BulkRow row in picked)
            <String, dynamic>{
              'id': row.id,
              if (row.version != null) 'version': row.version,
            },
        ],
        'reason': reason,
      }),
    );
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Approvals belong to one firm’s documents.',
      );
    }
    if (!_mayApprove) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot sign off documents',
        message: 'Signing off needs the approve sales or approve purchases '
            'permission.',
      );
    }
    final ApprovalStatus? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Documents whose amount needs more than one signature wait here '
          'for the level your roles can sign. The last sign-off approves the '
          'document.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number or document type',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: _ticked.isNotEmpty
          ? SelectionSummary(
              title: '${_ticked.length} selected',
              detail: 'Reject them together, one type at a time',
              onClear: () => setState(() => _ticked = <String>{}),
            )
          : picked == null
              ? null
              : SelectionSummary.document(
                  number: picked.documentNumber,
                  party: approvalTypeLabel(picked.documentType),
                  total: picked.amount,
                  onClear: () => setState(() {
                    _selectedId = null;
                    _detail = null;
                  }),
                ),
      detailsWidth: 400,
      detailsPanel: picked == null ? null : _details(picked),
      primaryContent: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error)),
                  ),
                const SizedBox(height: AppSpacing.md),
                Expanded(child: _grid()),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Awaiting your sign-off',
      ),
    );
  }

  WorkspaceToolbar _toolbar(ApprovalStatus? row) {
    return WorkspaceToolbar(
      actions: const [ToolbarAction.refresh],
      isEnabled: (action) => true,
      onAction: (action) => unawaited(_load()),
      commands: [
        if (_ticked.isNotEmpty)
          ToolbarCommand(
            id: 'bulk-reject',
            label: 'Reject selected',
            icon: Icons.playlist_remove_outlined,
            onPressed: () => unawaited(_bulkReject()),
          )
        else if (row != null) ...[
          ToolbarCommand(
            id: 'sign-off',
            label: 'Sign off',
            icon: Icons.verified_outlined,
            onPressed: () => unawaited(_signOff(row)),
          ),
          ToolbarCommand(
            id: 'reject',
            label: 'Reject',
            icon: Icons.block_outlined,
            onPressed: () => unawaited(_reject(row)),
          ),
        ],
      ],
    );
  }

  Widget _grid() {
    final List<ApprovalStatus> rows = _shown;
    if (rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing is waiting for you',
        message: 'Documents that need your sign-off appear here.',
      );
    }
    return EnterpriseDataGrid<ApprovalStatus>(
      items: rows,
      total: rows.length,
      pageOffset: 0,
      rowsPerPage: rows.length,
      availableRowsPerPage: [rows.length],
      selectedId: _selectedId,
      selectedIds: _ticked,
      onSelectionChanged: (value) => setState(() => _ticked = value),
      columns: const [
        GridColumn(key: 'type', label: 'Type'),
        GridColumn(key: 'number', label: 'Number'),
        GridColumn(key: 'amount', label: 'Amount', numeric: true),
        GridColumn(key: 'level', label: 'Next level', priority: 1),
        GridColumn(key: 'steps', label: 'Sign-offs', priority: 2),
      ],
      id: (row) => row.documentId,
      cells: (row) => [
        approvalTypeLabel(row.documentType),
        row.documentNumber,
        _money(row.amount),
        row.nextLevel == null ? '' : 'Level ${row.nextLevel}',
        row.summary,
      ],
      onSelect: _pick,
      onOpen: _pick,
      onPageChanged: (_) {},
    );
  }

  Widget _details(ApprovalStatus row) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      key: const ValueKey('approval-details'),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(row.documentNumber, style: theme.textTheme.titleMedium),
          Text(
            '${approvalTypeLabel(row.documentType)} · ${_money(row.amount)}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          for (final ApprovalStep step in row.steps)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    step.isSigned
                        ? Icons.check_circle_outline
                        : Icons.radio_button_unchecked,
                    size: 18,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      step.isSigned
                          ? 'Level ${step.level} (${step.roles.join(' or ')}): '
                              'signed by ${step.signedBy} on ${step.signedAt}'
                          : 'Level ${step.level} (${step.roles.join(' or ')}): '
                              'awaiting sign-off',
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
