import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/einvoice.dart';
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
  // The server's default, so the box never shows Off while it loads (D-UI-1).
  String _dispatch = 'WARN';
  bool _routeSaleNeedsInvoice = false;
  String _itcBasis = 'ALL';
  String _rule37 = 'REPORT';
  String _rule42 = 'REPORT';
  String _supplierIrn = 'WARN';
  String _frequency = 'MONTHLY';
  String? _quarterlyFrom;
  String _qrmpMethod = 'FIXED_SUM';
  final TextEditingController _tolerance =
      TextEditingController(text: '1.00');
  final TextEditingController _ewayLimit =
      TextEditingController(text: '50000');
  bool _isConfigured = false;
  // How e-invoices reach the portal (A42). Null where the server did not say,
  // which hides the choice rather than guessing one.
  EInvoiceSettings? _filing;
  String _provider = 'SANDBOX';
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
    _ewayLimit.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      _filing = await widget.api.einvoiceSettings();
      _provider = _filing!.provider;
    } on ApiException {
      _filing = null;
    }
    try {
      final GstComplianceSettings settings =
          await widget.api.gstComplianceSettings();
      if (!mounted) return;
      setState(() {
        _einvoiceFrom = settings.einvoiceApplicableFrom;
        _thirtyDayFrom = settings.thirtyDayRuleFrom;
        _dispatch = _enforcements.contains(settings.dispatchWithoutInvoice)
            ? settings.dispatchWithoutInvoice
            : 'WARN';
        _routeSaleNeedsInvoice = settings.routeSaleNeedsInvoice;
        _itcBasis =
            settings.itcClaimBasis == 'MATCHED_ONLY' ? 'MATCHED_ONLY' : 'ALL';
        _rule37 = const ['OFF', 'REPORT', 'POST'].contains(settings.rule37Mode)
            ? settings.rule37Mode
            : 'REPORT';
        _rule42 = const ['OFF', 'REPORT', 'POST'].contains(settings.rule42Mode)
            ? settings.rule42Mode
            : 'REPORT';
        _supplierIrn = settings.supplierIrnCheck == 'OFF' ? 'OFF' : 'WARN';
        _frequency =
            settings.filingFrequency == 'QUARTERLY' ? 'QUARTERLY' : 'MONTHLY';
        _quarterlyFrom = settings.quarterlyFrom;
        _qrmpMethod = settings.qrmpPaymentMethod == 'SELF_ASSESSMENT'
            ? 'SELF_ASSESSMENT'
            : 'FIXED_SUM';
        _tolerance.text = settings.gstr2bTolerance;
        _ewayLimit.text = settings.ewayBillLimit;
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
            rule37Mode: _rule37,
            rule42Mode: _rule42,
            supplierIrnCheck: _supplierIrn,
            gstr2bTolerance: _tolerance.text.trim().isEmpty
                ? '1.00'
                : _tolerance.text.trim(),
            ewayBillLimit: _ewayLimit.text.trim().isEmpty
                ? '50000'
                : _ewayLimit.text.trim(),
            filingFrequency: _frequency,
            quarterlyFrom: _frequency == 'QUARTERLY' ? _quarterlyFrom : null,
            qrmpPaymentMethod: _qrmpMethod,
          ),
        );
        final EInvoiceSettings? filing = _filing;
        if (filing != null && _provider != filing.provider) {
          _filing = await widget.api.updateEinvoiceSettings(_provider);
        }
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

  static String _providerLabel(String code) => switch (code) {
        'SANDBOX' => 'Sandbox (rehearsal, nothing filed)',
        'OFFLINE' => 'Offline: upload on the e-invoice portal',
        _ => code,
      };

  /// Quarter starts to offer: the last four and the next two, plus whatever
  /// the firm already has.
  List<String> get _quarterStarts {
    final DateTime now = DateTime.now();
    final int current = (now.month - 1) ~/ 3;
    final List<String> out = [
      for (int offset = -4; offset <= 2; offset++)
        _isoDate(DateTime(now.year, (current + offset) * 3 + 1)),
    ];
    final String? held = _quarterlyFrom;
    if (held != null && !out.contains(held)) out.insert(0, held);
    return out;
  }

  static String _isoDate(DateTime v) => '${v.year.toString().padLeft(4, '0')}-'
      '${v.month.toString().padLeft(2, '0')}-'
      '${v.day.toString().padLeft(2, '0')}';

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
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-rule37-mode'),
                      isExpanded: true,
                      initialValue: _rule37,
                      decoration: const InputDecoration(
                        labelText: '180-day unpaid bills (rule 37)',
                        helperText: 'Credit on a bill unpaid 180 days after '
                            'its date is reversed, and reclaimed when paid.',
                        helperMaxLines: 2,
                      ),
                      items: const [
                        DropdownMenuItem(value: 'OFF', child: Text('Off')),
                        DropdownMenuItem(
                          value: 'REPORT',
                          child: Text('Report only'),
                        ),
                        DropdownMenuItem(
                          value: 'POST',
                          child: Text('Report and post'),
                        ),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(() => _rule37 = value ?? _rule37)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-rule42-mode'),
                      isExpanded: true,
                      initialValue: _rule42,
                      decoration: const InputDecoration(
                        labelText:
                            'Rule 42 — common credit for exempt sales',
                        helperText: 'Gives back the share of common input '
                            'credit that exempt, nil-rated and non-GST sales '
                            'take (D1 = C2 × E / F)',
                        helperMaxLines: 2,
                      ),
                      items: const [
                        DropdownMenuItem(value: 'OFF', child: Text('Off')),
                        DropdownMenuItem(
                          value: 'REPORT',
                          child: Text('Report'),
                        ),
                        DropdownMenuItem(
                          value: 'POST',
                          child: Text('Report and post'),
                        ),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(() => _rule42 = value ?? _rule42)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-supplier-irn-check'),
                      isExpanded: true,
                      initialValue: _supplierIrn,
                      decoration: const InputDecoration(
                        labelText: 'Supplier bill without an IRN',
                        helperText: 'Warn when a supplier marked as '
                            'e-invoicing sends a bill with no IRN '
                            '(rule 48(4)).',
                        helperMaxLines: 2,
                      ),
                      items: const [
                        DropdownMenuItem(value: 'OFF', child: Text('Off')),
                        DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                      ],
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _supplierIrn = value ?? _supplierIrn)
                          : null,
                    ),
                    if (_filing != null) ...[
                      const SizedBox(height: AppSpacing.md),
                      DropdownButtonFormField<String>(
                        key: const ValueKey('einvoice-filing-provider'),
                        isExpanded: true,
                        initialValue: _filing!.available.contains(_provider)
                            ? _provider
                            : null,
                        decoration: const InputDecoration(
                          labelText: 'E-invoice filing',
                        ),
                        items: [
                          for (final String code in _filing!.available)
                            DropdownMenuItem(
                              value: code,
                              child: Text(_providerLabel(code)),
                            ),
                        ],
                        onChanged: editable && !saving
                            ? (value) =>
                                setState(() => _provider = value ?? _provider)
                            : null,
                      ),
                    ],
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
                    const SizedBox(height: AppSpacing.lg),
                    Text('Return filing', style: theme.textTheme.titleSmall),
                    const SizedBox(height: AppSpacing.sm),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('gst-filing-frequency'),
                      isExpanded: true,
                      initialValue: _frequency,
                      decoration: const InputDecoration(
                        labelText: 'Returns are filed',
                        helperText: 'Quarterly (QRMP) files GSTR-1 and 3B '
                            'once a quarter and deposits tax by PMT-06 in the '
                            'first two months. Open to firms under 5 crore.',
                        helperMaxLines: 3,
                      ),
                      items: const [
                        DropdownMenuItem(
                            value: 'MONTHLY', child: Text('Monthly')),
                        DropdownMenuItem(
                            value: 'QUARTERLY',
                            child: Text('Quarterly (QRMP)')),
                      ],
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _frequency = value ?? _frequency)
                          : null,
                    ),
                    if (_frequency == 'QUARTERLY') ...[
                      const SizedBox(height: AppSpacing.md),
                      DropdownButtonFormField<String?>(
                        key: const ValueKey('gst-quarterly-from'),
                        isExpanded: true,
                        initialValue: _quarterlyFrom,
                        decoration: const InputDecoration(
                          labelText: 'Quarterly from',
                          helperText: 'The quarter the firm started QRMP. '
                              'Earlier periods stay monthly.',
                          helperMaxLines: 2,
                        ),
                        items: [
                          const DropdownMenuItem<String?>(
                              value: null, child: Text('Every period')),
                          for (final String start in _quarterStarts)
                            DropdownMenuItem<String?>(
                                value: start, child: Text(start)),
                        ],
                        onChanged: editable && !saving
                            ? (value) => setState(() => _quarterlyFrom = value)
                            : null,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      DropdownButtonFormField<String>(
                        key: const ValueKey('gst-qrmp-method'),
                        isExpanded: true,
                        initialValue: _qrmpMethod,
                        decoration: const InputDecoration(
                          labelText: 'PMT-06 deposit method',
                          helperText: 'Fixed sum is 35% of the last '
                              "quarter's cash paid; self-assessment deposits "
                              'what the month actually owes.',
                          helperMaxLines: 3,
                        ),
                        items: const [
                          DropdownMenuItem(
                              value: 'FIXED_SUM',
                              child: Text('Fixed sum: 35% of last quarter')),
                          DropdownMenuItem(
                              value: 'SELF_ASSESSMENT',
                              child: Text('Self-assessment')),
                        ],
                        onChanged: editable && !saving
                            ? (value) => setState(
                                () => _qrmpMethod = value ?? _qrmpMethod)
                            : null,
                      ),
                    ],
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      key: const ValueKey('gst-eway-limit'),
                      controller: _ewayLimit,
                      enabled: editable && !saving,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'E-way bill needed above (₹)',
                        helperText: 'A consignment worth more than this needs '
                            'an e-way bill. The law says ₹50,000; some states '
                            'set their own.',
                        helperMaxLines: 2,
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
