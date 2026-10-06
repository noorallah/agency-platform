import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/entities.dart' show Json;
import '../../models/price_revision.dart';
import '../workspace/desktop_framework.dart';

/// What the "Price history" section calls (MST-2): read a product's dated
/// rates, record new ones, remove one typed in error.
class PriceRevisionActions {
  const PriceRevisionActions({
    required this.load,
    required this.add,
    required this.delete,
  });

  factory PriceRevisionActions.of(ApiClient api) => PriceRevisionActions(
        load: api.productPriceRevisions,
        add: api.addProductPriceRevision,
        delete: api.deleteProductPriceRevision,
      );

  final Future<List<PriceRevision>> Function(String productId) load;
  final Future<PriceRevision> Function(String productId, Json body) add;
  final Future<void> Function(String productId, String revisionId) delete;
}

/// The dated rates of a saved product: a grid with the row in force marked,
/// "New rates from..." and delete. New rates are a new row from a date, never
/// an edit, and documents take the rate in force on their own date.
class PriceRevisionsSection extends StatefulWidget {
  const PriceRevisionsSection({
    super.key,
    required this.productId,
    required this.actions,
    required this.canManage,
  });

  final String productId;
  final PriceRevisionActions actions;
  final bool canManage;

  @override
  State<PriceRevisionsSection> createState() => _PriceRevisionsSectionState();
}

class _PriceRevisionsSectionState extends State<PriceRevisionsSection> {
  List<PriceRevision>? _rows;
  String? _error;
  String? _selectedId;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  Future<void> _reload() async {
    try {
      final List<PriceRevision> rows =
          await widget.actions.load(widget.productId);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _error = null;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _rows ??= const <PriceRevision>[];
        _error = exception.message;
      });
    }
  }

  Future<void> _add() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => NewRatesDialog(
        productId: widget.productId,
        onSave: widget.actions.add,
      ),
    );
    if (saved == true) await _reload();
  }

  Future<void> _delete(PriceRevision row) async {
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete these rates?',
      message: 'Remove the rates from ${row.effectiveFrom}? Use this only for '
          'a row typed in error; a price change is a new row.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.actions.delete(widget.productId, row.id);
      await _reload();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<PriceRevision>? rows = _rows;
    PriceRevision? selected;
    for (final PriceRevision row in rows ?? const <PriceRevision>[]) {
      if (row.id == _selectedId) selected = row;
    }
    final PriceRevision? target = selected;
    String shown(String value) => value.isEmpty ? '—' : value;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.canManage)
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              OutlinedButton.icon(
                key: const ValueKey('price-revision-add'),
                onPressed: _add,
                icon: const Icon(Icons.add),
                label: const Text('New rates from…'),
              ),
              OutlinedButton.icon(
                key: const ValueKey('price-revision-delete'),
                onPressed: target == null ? null : () => _delete(target),
                icon: const Icon(Icons.delete_outline),
                label: const Text('Delete row'),
              ),
            ],
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (rows == null)
          const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (rows.isEmpty)
          const StandardEmptyState(
            type: EmptyStateType.noRecords,
            message: 'No dated rates yet. New rates from a date apply to '
                'documents on or after it.',
          )
        else
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              showCheckboxColumn: false,
              columns: const [
                DataColumn(label: Text('From')),
                DataColumn(label: Text('Selling'), numeric: true),
                DataColumn(label: Text('Purchase'), numeric: true),
                DataColumn(label: Text('MRP'), numeric: true),
                DataColumn(label: Text('Remarks')),
                DataColumn(label: Text('Status')),
              ],
              rows: [
                for (final PriceRevision row in rows)
                  DataRow(
                    key: ValueKey<String>('price-revision-row-${row.id}'),
                    selected: row.id == _selectedId,
                    onSelectChanged: (_) =>
                        setState(() => _selectedId = row.id),
                    cells: [
                      DataCell(Text(row.effectiveFrom)),
                      DataCell(Text(shown(row.sellingPrice))),
                      DataCell(Text(shown(row.purchasePrice))),
                      DataCell(Text(shown(row.mrp))),
                      DataCell(Text(row.remarks)),
                      DataCell(Text(row.isCurrent ? 'In force' : '')),
                    ],
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// New rates from a date. A blank price keeps that price as it is, so nothing
/// is prefilled; the save runs here and a refusal (the same date twice) stays
/// in the dialog with everything typed.
class NewRatesDialog extends StatefulWidget {
  const NewRatesDialog({
    super.key,
    required this.productId,
    required this.onSave,
    this.today,
  });

  final String productId;
  final Future<PriceRevision> Function(String productId, Json body) onSave;

  /// The day new rates may start at the earliest. Left null it is this
  /// computer's day, which is what the screen has always defaulted to; the
  /// server judges it again on the firm's own calendar and refuses an earlier
  /// date (D-PRC-15).
  final DateTime? today;

  @override
  State<NewRatesDialog> createState() => _NewRatesDialogState();
}

class _NewRatesDialogState extends State<NewRatesDialog> with SaveInDialog {
  final TextEditingController _selling = TextEditingController();
  final TextEditingController _purchase = TextEditingController();
  final TextEditingController _mrp = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  late final DateTime _today =
      DateUtils.dateOnly(widget.today ?? DateTime.now());
  late DateTime _from = _today;
  String? _problem;

  @override
  void dispose() {
    _selling.dispose();
    _purchase.dispose();
    _mrp.dispose();
    _remarks.dispose();
    super.dispose();
  }

  String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _from,
      // New rates start today or later; a date already gone would be taken
      // in silence as today's price.
      firstDate: _today,
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _from = picked);
  }

  void _save() {
    final Json body = <String, dynamic>{'effective_from': _iso(_from)};
    bool anyPrice = false;
    void put(String key, TextEditingController controller,
        {bool price = true}) {
      final String value = controller.text.trim();
      if (value.isEmpty) return;
      body[key] = value;
      if (price) anyPrice = true;
    }

    put('selling_price', _selling);
    put('purchase_price', _purchase);
    put('mrp', _mrp);
    put('remarks', _remarks, price: false);
    if (!anyPrice) {
      setState(() => _problem = 'Enter at least one price.');
      return;
    }
    setState(() => _problem = null);
    unawaited(saveAndClose<bool>(() async {
      await widget.onSave(widget.productId, body);
      return true;
    }));
  }

  Widget _price(String key, String label, TextEditingController controller) =>
      Padding(
        padding: const EdgeInsets.only(top: 12),
        child: TextField(
          key: ValueKey<String>(key),
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: label,
            helperText: 'Blank keeps that price as it is',
          ),
        ),
      );

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('New rates from…'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                if (_problem != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      _problem!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error),
                    ),
                  ),
                InkWell(
                  key: const ValueKey('price-revision-from'),
                  onTap: _pickDate,
                  child: InputDecorator(
                    decoration: const InputDecoration(
                      labelText: 'Effective from',
                      helperText: 'Today or later. Documents dated on or '
                          'after this day use these rates',
                      helperMaxLines: 2,
                      suffixIcon: Icon(Icons.calendar_today, size: 18),
                    ),
                    child: Text(_iso(_from)),
                  ),
                ),
                _price('price-revision-selling', 'Selling price', _selling),
                _price('price-revision-purchase', 'Purchase price', _purchase),
                _price('price-revision-mrp', 'MRP', _mrp),
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: TextField(
                    key: const ValueKey('price-revision-remarks'),
                    controller: _remarks,
                    maxLines: 2,
                    decoration: const InputDecoration(labelText: 'Remarks'),
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('price-revision-save'),
            onPressed: saving ? null : _save,
            child: const Text('Save'),
          ),
        ],
      );
}

/// Bring dated rates in from a file: the shared [MasterImportDialog] wired to
/// the price revision endpoints. There is nothing to update -- a revision is a
/// new row -- and the server's template is a CSV only.
class PriceRevisionImportDialog extends StatelessWidget {
  const PriceRevisionImportDialog({
    super.key,
    required this.api,
    this.pickFileOverride,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final Future<XFile?> Function()? pickFileOverride;
  final SaveBytesOverride? saveBytesOverride;

  @override
  Widget build(BuildContext context) => MasterImportDialog(
        noun: 'price revisions',
        fileStem: 'price_revision',
        downloadTemplate: (format) => api.productPriceRevisionImportTemplate(),
        checkFile: ({
          required String fileName,
          required List<int> bytes,
          required bool updateExisting,
          required bool apply,
          Map<String, String?>? mapping,
        }) =>
            api.checkProductPriceRevisionImportFile(
          fileName: fileName,
          bytes: bytes,
          apply: apply,
        ),
        canUpdate: false,
        offersUpdate: false,
        csvOnly: true,
        pickFileOverride: pickFileOverride,
        saveBytesOverride: saveBytesOverride,
      );
}
