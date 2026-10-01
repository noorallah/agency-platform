import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/gst_documents.dart';
import '../workspace/save_in_dialog.dart';

/// The firm's GST document policy (backlog 77.1): when e-invoicing and the
/// 30-day reporting limit start to apply to it, and what happens when a sale's
/// goods are dispatched before its tax invoice exists.
///
/// Reading needs `TAX_VIEW`, so anyone a refusal reaches can see the rule
/// behind it. Changing it needs `TAX_MANAGE_SETTINGS`.
class GstDocumentsSettingsDialog extends StatefulWidget {
  const GstDocumentsSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<GstDocumentsSettingsDialog> createState() =>
      _GstDocumentsSettingsDialogState();
}

class _GstDocumentsSettingsDialogState extends State<GstDocumentsSettingsDialog>
    with SaveInDialog<GstDocumentsSettingsDialog> {
  static const List<String> _enforcements = ['OFF', 'WARN', 'BLOCK'];

  String? _einvoiceFrom;
  String? _thirtyDayFrom;
  String _dispatch = 'OFF';
  bool _routeSaleNeedsInvoice = false;
  String _itcBasis = 'ALL';
  final TextEditingController _tolerance =
      TextEditingController(text: '1.00');
  bool _isConfigured = false;
  bool _loading = true;
  String? _loadError;

  bool get _mayManage => widget.permissions.hasPermission('TAX_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _tolerance.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final GstComplianceSettings settings =
          await widget.api.gstComplianceSettings();
      if (!mounted) return;
      setState(() {
        _einvoiceFrom = settings.einvoiceApplicableFrom;
        _thirtyDayFrom = settings.thirtyDayRuleFrom;
        _dispatch = _enforcements.contains(settings.dispatchWithoutInvoice)
            ? settings.dispatchWithoutInvoice
            : 'OFF';
        _routeSaleNeedsInvoice = settings.routeSaleNeedsInvoice;
        _itcBasis =
            settings.itcClaimBasis == 'MATCHED_ONLY' ? 'MATCHED_ONLY' : 'ALL';
        _tolerance.text = settings.gstr2bTolerance;
        _isConfigured = settings.isConfigured;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _save() => saveAndClose<bool>(() async {
        await widget.api.updateGstComplianceSettings(
          GstComplianceSettings(
            einvoiceApplicableFrom: _einvoiceFrom,
            thirtyDayRuleFrom: _thirtyDayFrom,
            dispatchWithoutInvoice: _dispatch,
            routeSaleNeedsInvoice: _routeSaleNeedsInvoice,
            isConfigured: true,
            itcClaimBasis: _itcBasis,
            gstr2bTolerance: _tolerance.text.trim().isEmpty
                ? '1.00'
                : _tolerance.text.trim(),
          ),
        );
        if (mounted) {
          NotificationService.show(
            context,
            'GST document settings saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  String get _dispatchExplanation => switch (_dispatch) {
        'BLOCK' => 'Goods cannot be dispatched on a sale that has no invoice '
            'yet. The person is offered "Dispatch and invoice" instead.',
        'WARN' => 'The person is told the sale has no invoice yet and may '
            'dispatch anyway, or dispatch and invoice in one step.',
        _ => 'Dispatching a sale before its invoice is not checked.',
      };

  Future<void> _pickDate(String? current, ValueChanged<String?> onPicked) async {
    final DateTime? now = DateTime.tryParse(current ?? '');
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: now ?? DateTime.now(),
      firstDate: DateTime(2017),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() => onPicked(picked.toIso8601String().split('T').first));
  }

  Widget _dateField({
    required Key fieldKey,
    required String label,
    required String helper,
    required String? value,
    required ValueChanged<String?> onChanged,
    required bool editable,
  }) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        InkWell(
          key: fieldKey,
          onTap: editable ? () => _pickDate(value, onChanged) : null,
          child: InputDecorator(
            decoration: InputDecoration(
              labelText: label,
              suffixIcon: value == null || !editable
                  ? const Icon(Icons.event, size: 18)
                  : IconButton(
                      tooltip: 'Clear',
                      iconSize: 16,
                      onPressed: () => setState(() => onChanged(null)),
                      icon: const Icon(Icons.close),
                    ),
            ),
            child: Text(value ?? 'Not set'),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(helper, style: theme.textTheme.bodySmall),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool editable = _mayManage && !_loading && _loadError == null;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.receipt_long_outlined),
      title: const Text('GST documents'),
      content: SizedBox(
        width: 480,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'GST law wants a sale\'s tax invoice to exist before the '
                    'goods leave. These settings say how this firm is held '
                    'to that.',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (!_isConfigured && _loadError == null) ...[
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'This firm has not chosen, so it is using the default '
                      "shown here. Saving makes it the firm's own.",
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  if (_loadError != null)
                    Text(
                      _loadError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    )
                  else ...[
                    saveErrorBanner(),
                    _dateField(
                      fieldKey: const ValueKey('gst-einvoice-from'),
                      label: 'E-invoicing applies from',
                      helper: 'The first day this firm must report its '
                          'invoices to the e-invoice portal. Leave empty if '
                          'it does not yet apply.',
                      value: _einvoiceFrom,
                      onChanged: (value) => _einvoiceFrom = value,
                      editable: editable && !saving,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    _dateField(
                      fieldKey: const ValueKey('gst-thirty-day-from'),
                      label: '30-day reporting limit applies from',
                      helper: 'From this day an invoice older than 30 days '
                          'can no longer be reported. Needs the e-invoicing '
                          'date, and cannot be earlier than it.',
                      value: _thirtyDayFrom,
                      onChanged: (value) => _thirtyDayFrom = value,
                      editable: editable && !saving,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-dispatch-policy'),
                      isExpanded: true,
                      initialValue: _dispatch,
                      decoration: const InputDecoration(
                        labelText: 'Dispatch of a sale before its invoice',
                      ),
                      items: const [
                        DropdownMenuItem(value: 'OFF', child: Text('Off')),
                        DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                        DropdownMenuItem(value: 'BLOCK', child: Text('Block')),
                      ],
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _dispatch = value ?? _dispatch)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(_dispatchExplanation, style: theme.textTheme.bodySmall),
                    const SizedBox(height: AppSpacing.md),
                    SwitchListTile(
                      key: const ValueKey('gst-route-sale-needs-invoice'),
                      contentPadding: EdgeInsets.zero,
                      title: const Text(
                        'Van or route sales need the invoice before the van '
                        'leaves',
                      ),
                      subtitle: const Text(
                        'Off lets a van load goods on a challan and invoice '
                        'what it sells afterwards, as the law allows.',
                      ),
                      value: _routeSaleNeedsInvoice,
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _routeSaleNeedsInvoice = value)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-itc-basis'),
                      isExpanded: true,
                      initialValue: _itcBasis,
                      decoration: const InputDecoration(
                        labelText: 'Claim input credit',
                      ),
                      items: const [
                        DropdownMenuItem(
                          value: 'ALL',
                          child: Text('All bills (list what 2B lacks)'),
                        ),
                        DropdownMenuItem(
                          value: 'MATCHED_ONLY',
                          child: Text('Only bills matched to GSTR-2B'),
                        ),
                      ],
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _itcBasis = value ?? _itcBasis)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('gst-2b-tolerance'),
                      controller: _tolerance,
                      enabled: editable && !saving,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Matching tolerance (₹)',
                        helperText: 'How far a bill may differ from GSTR-2B '
                            'and still count as matched.',
                      ),
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      'Changing the GST document settings needs the manage '
                      'tax settings permission.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        FilledButton(
          key: const ValueKey('gst-settings-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
