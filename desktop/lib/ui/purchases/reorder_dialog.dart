import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../workspace/save_in_dialog.dart';

/// Below reorder level, and the draft orders that put it right (42.9).
///
/// Every product at or below its reorder level in a warehouse, with what is
/// available, what is already on order, the supplier last billed for it and a
/// suggested quantity -- up to the maximum level, or the shortfall where no
/// maximum is set. Tick rows, adjust a quantity if wanted, and **Raise draft
/// orders**: the server raises one DRAFT per supplier per warehouse through
/// the order's own save path, all or none, so nothing is half-ordered.
///
/// A row no supplier has billed yet cannot be ticked: nobody has said who
/// sells it. Its suggestion is still shown, so the buyer knows it is short.
class ReorderDialog extends StatefulWidget {
  const ReorderDialog({
    super.key,
    required this.api,
    this.canRaiseRequisition = false,
  });

  final ApiClient api;

  /// Offer **Raise requisition** (BUY-7): the same picks as a request to buy
  /// that someone approves, instead of draft orders.
  final bool canRaiseRequisition;

  @override
  State<ReorderDialog> createState() => _ReorderDialogState();
}

class _ReorderDialogState extends State<ReorderDialog>
    with SaveInDialog<ReorderDialog> {
  List<Json> _rows = const [];
  bool _loading = true;
  String? _loadError;
  String? _planningNote;
  final Set<int> _ticked = <int>{};

  /// One box per row, owned here (CLAUDE.md: a dialog owns its controllers).
  final List<TextEditingController> _quantities = <TextEditingController>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _quantities) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<Json> rows = await widget.api.belowReorderLevel();
      // Which basis the firm plans on is a note, not a precondition: a
      // refusal to read it (no view permission) just leaves the note out.
      String? basis;
      try {
        final Json planning = await widget.api.reorderPlanning();
        basis = stringValue(planning['basis']) == 'SALES'
            ? 'From sales: ${stringValue(planning['sales_window_days'])}-day '
                'average, ${stringValue(planning['lead_time_days'])} days '
                'lead time, ${stringValue(planning['safety_days'])} days '
                'safety, ${stringValue(planning['cover_days'])} days cover. '
                'A level typed on a product wins.'
            : 'Typed levels per product.';
      } on ApiException {
        basis = null;
      }
      if (!mounted) return;
      _planningNote = basis;
      for (final TextEditingController controller in _quantities) {
        controller.dispose();
      }
      _quantities
        ..clear()
        ..addAll([
          for (final Json row in rows)
            TextEditingController(text: _plain(row['suggested_quantity'])),
        ]);
      setState(() {
        _rows = rows;
        _ticked
          ..clear()
          ..addAll([
            for (int i = 0; i < rows.length; i++)
              if (_orderable(rows[i]) && _positive(_quantities[i].text)) i,
          ]);
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

  static bool _orderable(Json row) => stringValue(row['supplier_id']).isNotEmpty;

  static bool _positive(String text) => (double.tryParse(text.trim()) ?? 0) > 0;

  /// A quantity as the server sent it, without trailing zeros.
  static String _plain(dynamic value) {
    final double? number = double.tryParse(stringValue(value));
    if (number == null) return stringValue(value);
    return number == number.roundToDouble()
        ? number.toStringAsFixed(0)
        : number.toString();
  }

  Future<void> _raise({bool requisition = false}) async {
    final List<Json> items = [
      for (final int index in _ticked.toList()..sort())
        <String, dynamic>{
          'warehouse_id': _rows[index]['warehouse_id'],
          'product_id': _rows[index]['product_id'],
          'quantity': _quantities[index].text.trim(),
        },
    ];
    await saveAndClose<Json>(() => requisition
        ? widget.api.raiseReorderRequisitions(items)
        : widget.api.raiseReorderDrafts(items));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool canRaise = !_loading &&
        !saving &&
        _ticked.isNotEmpty &&
        _ticked.every((index) => _positive(_quantities[index].text));
    return AlertDialog(
      icon: const Icon(Icons.inventory_outlined),
      title: const Text('Below reorder level'),
      content: SizedBox(
        width: 900,
        height: 420,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Suggested is up to the maximum level, less what is available '
              'and what is already on order; without a maximum, the shortfall '
              'to the reorder level. One draft order is raised per supplier '
              'per warehouse.',
              style: theme.textTheme.bodySmall,
            ),
            if (_planningNote != null) ...[
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Planning basis -- $_planningNote',
                key: const ValueKey('reorder-planning-note'),
                style: theme.textTheme.bodySmall
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
            ],
            const SizedBox(height: AppSpacing.sm),
            saveErrorBanner(),
            Expanded(child: _body(theme)),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        if (widget.canRaiseRequisition)
          OutlinedButton(
            key: const ValueKey('reorder-requisition'),
            onPressed: canRaise ? () => _raise(requisition: true) : null,
            child: const Text('Raise requisition'),
          ),
        FilledButton(
          key: const ValueKey('reorder-raise'),
          onPressed: canRaise ? _raise : null,
          child: Text(saving
              ? 'Raising…'
              : 'Raise draft orders (${_ticked.length})'),
        ),
      ],
    );
  }

  Widget _body(ThemeData theme) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_loadError != null) {
      return Center(
        child: Text(
          'The stock levels could not be read: $_loadError',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.error),
        ),
      );
    }
    if (_rows.isEmpty) {
      return Center(
        child: Text(
          'Nothing is at or below its reorder level.',
          style: theme.textTheme.bodyMedium,
        ),
      );
    }
    final TextStyle? head = theme.textTheme.labelSmall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          const SizedBox(width: 40),
          Expanded(flex: 2, child: Text('Warehouse', style: head)),
          Expanded(flex: 4, child: Text('Product', style: head)),
          Expanded(flex: 2, child: Text('Basis', style: head)),
          Expanded(flex: 2, child: Text('Avg/day', style: head)),
          Expanded(flex: 2, child: Text('Available', style: head)),
          Expanded(flex: 2, child: Text('Reorder at', style: head)),
          Expanded(flex: 2, child: Text('On order', style: head)),
          Expanded(flex: 2, child: Text('Order', style: head)),
          Expanded(flex: 4, child: Text('Supplier', style: head)),
        ]),
        const Divider(height: 8),
        Expanded(
          child: ListView.builder(
            itemCount: _rows.length,
            itemBuilder: (context, index) => _row(theme, index),
          ),
        ),
      ],
    );
  }

  Widget _row(ThemeData theme, int index) {
    final Json row = _rows[index];
    final bool orderable = _orderable(row);
    final TextStyle? cell = theme.textTheme.bodySmall;
    return Row(
      key: ValueKey('reorder-row-$index'),
      children: [
        SizedBox(
          width: 40,
          child: Checkbox(
            key: ValueKey('reorder-tick-$index'),
            value: _ticked.contains(index),
            onChanged: orderable && !saving
                ? (value) => setState(() => value == true
                    ? _ticked.add(index)
                    : _ticked.remove(index))
                : null,
          ),
        ),
        Expanded(
            flex: 2,
            child: Text(stringValue(row['warehouse_code']), style: cell)),
        Expanded(
          flex: 4,
          child: Text(
            '${stringValue(row['product_code'])} · '
            '${stringValue(row['product_name'])}',
            style: cell,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        Expanded(
          flex: 2,
          child: Text(
            stringValue(row['basis']) == 'SALES'
                ? 'Sales'
                : stringValue(row['basis']).isEmpty
                    ? ''
                    : 'Level',
            style: cell,
          ),
        ),
        Expanded(
          flex: 2,
          child: Text(
            row['average_daily_sales'] == null
                ? ''
                : _plain(row['average_daily_sales']),
            style: cell,
          ),
        ),
        Expanded(
            flex: 2,
            child: Text(_plain(row['available_quantity']), style: cell)),
        Expanded(
            flex: 2, child: Text(_plain(row['reorder_level']), style: cell)),
        Expanded(
            flex: 2,
            child: Text(_plain(row['on_order_quantity']), style: cell)),
        Expanded(
          flex: 2,
          child: Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: TextField(
              key: ValueKey('reorder-quantity-$index'),
              controller: _quantities[index],
              enabled: orderable && !saving,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              style: cell,
              decoration: const InputDecoration(isDense: true),
              onChanged: (_) => setState(() {}),
            ),
          ),
        ),
        Expanded(
          flex: 4,
          child: Text(
            orderable
                ? stringValue(row['supplier_name'])
                : 'No supplier has billed it yet',
            style: orderable
                ? cell
                : cell?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
