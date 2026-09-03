// Credit a customer earns on what they buy, and spends on what they buy next.
//
// A register rather than a till: it shows the firm's scheme and every movement
// of credit under it. Spending credit happens where the bill is, not here.
//
// The one thing it must not misstate is what spending does. Redeeming
// **settles** a bill; it does not discount one. The difference is what GST the
// firm collects, so the screen says it rather than leaving a reader to assume
// the familiar thing.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// Show a firm's scheme and every movement of credit under it.
class LoyaltyPage extends StatefulWidget {
  const LoyaltyPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<LoyaltyPage> createState() => _LoyaltyPageState();
}

class _LoyaltyPageState extends State<LoyaltyPage> {
  Json? _settings;
  List<Json> _entries = const [];
  String? _error;
  bool _loading = true;

  bool get _mayView => widget.permissions.hasPermission('LOYALTY_VIEW');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json settings = await widget.api.loyaltySettings();
      final List<Json> entries = await widget.api.loyaltyEntries();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _entries = entries;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'A scheme belongs to one firm and its customers.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading what customers have earned needs the view loyalty '
            'permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: _schemeBanner(),
      primaryContent: _ledger(),
      statusBar: WorkspaceStatusBar(
        total: _entries.length,
        selected: false,
        // Said plainly, because "redeem" sounds like a discount and it is not.
        message: 'Spending credit settles a bill; it does not discount it.',
      ),
    );
  }

  Widget _schemeBanner() {
    final Json? settings = _settings;
    if (settings == null) return const SizedBox.shrink();
    final bool on = settings['is_enabled'] == true;
    final String expiry = settings['expiry_months'] == null
        // Null is a real choice, not a missing value, so it is spelled out.
        ? 'and never expire'
        : 'and expire after ${settings['expiry_months']} months';
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Icon(on ? Icons.card_giftcard : Icons.pause_circle_outline, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              on
                  ? '${settings['points_per_amount']} points per 100, worth '
                      '${settings['amount_per_point']} each $expiry. '
                      'At least ${settings['minimum_redemption_points']} before '
                      'any can be spent.'
                  : 'No scheme is running: nobody is earning anything.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  Widget _ledger() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_entries.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing earned yet',
        message: 'Points are credited when a bill is approved.',
      );
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SingleChildScrollView(
        child: DataTable(
          columns: const [
            DataColumn(label: Text('On')),
            DataColumn(label: Text('Customer')),
            DataColumn(label: Text('Why')),
            DataColumn(label: Text('Against')),
            DataColumn(label: Text('Points')),
            DataColumn(label: Text('Worth')),
            DataColumn(label: Text('Expires')),
          ],
          rows: [
            for (final Json row in _entries)
              DataRow(cells: [
                DataCell(Text(stringValue(row['earned_on']))),
                DataCell(Text(stringValue(row['customer_name']))),
                DataCell(Text(stringValue(row['kind']))),
                DataCell(Text(stringValue(row['sales_invoice_number']))),
                // Signed, so a reader can see at a glance which way it went
                // without decoding the kind first.
                DataCell(Text(_points(row['points']))),
                DataCell(Text(_money(row['amount']))),
                DataCell(Text(
                  row['expires_on'] == null
                      ? 'never'
                      : stringValue(row['expires_on']),
                )),
              ]),
          ],
        ),
      ),
    );
  }

  static String _points(Object? value) {
    final double parsed = double.tryParse('${value ?? 0}') ?? 0;
    final String shown = parsed.toStringAsFixed(2);
    return parsed > 0 ? '+$shown' : shown;
  }

  static String _money(Object? value) =>
      (double.tryParse('${value ?? 0}') ?? 0).toStringAsFixed(2);
}
