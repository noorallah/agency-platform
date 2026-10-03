import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/stock_transfer.dart';
import '../workspace/save_in_dialog.dart';

String _today(DateTime date) => date.toIso8601String().substring(0, 10);

/// Send a draft transfer out (STK-1): the date it leaves and the vehicle that
/// carries it. The stock leaves the source warehouse when this saves.
class DispatchTransferDialog extends StatefulWidget {
  const DispatchTransferDialog({
    super.key,
    required this.transfer,
    required this.onSave,
  });

  final StockTransferRecord transfer;

  /// Dispatches with the body; a refusal is an `ApiException` shown here.
  final Future<void> Function(Json body) onSave;

  @override
  State<DispatchTransferDialog> createState() => _DispatchTransferDialogState();
}

class _DispatchTransferDialogState extends State<DispatchTransferDialog>
    with SaveInDialog {
  late final TextEditingController _vehicle =
      TextEditingController(text: widget.transfer.vehicleNumber);
  late final TextEditingController _transporter =
      TextEditingController(text: widget.transfer.transporterName);
  DateTime _when = DateTime.now();

  @override
  void dispose() {
    _vehicle.dispose();
    _transporter.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final Json body = <String, dynamic>{
      'dispatched_on': _today(_when),
      if (_vehicle.text.trim().isNotEmpty)
        'vehicle_number': _vehicle.text.trim(),
      if (_transporter.text.trim().isNotEmpty)
        'transporter_name': _transporter.text.trim(),
    };
    await submit<Json>(body, widget.onSave);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Dispatch ${widget.transfer.transferNumber}'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                '${widget.transfer.fromWarehouseName} to '
                '${widget.transfer.toWarehouseName}. The stock leaves the '
                'source warehouse now and is in transit until it is received.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              InkWell(
                onTap: saving
                    ? null
                    : () async {
                        final DateTime? picked = await showDatePicker(
                          context: context,
                          initialDate: _when,
                          firstDate: DateTime(2000),
                          lastDate: DateTime(2100),
                        );
                        if (picked != null) setState(() => _when = picked);
                      },
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'Dispatch date',
                    suffixIcon: Icon(Icons.calendar_today, size: 18),
                  ),
                  child: Text(_today(_when)),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('dispatch-vehicle'),
                controller: _vehicle,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Vehicle number'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('dispatch-transporter'),
                controller: _transporter,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Transporter'),
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
          key: const ValueKey('dispatch-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Dispatching...' : 'Dispatch'),
        ),
      ],
    );
  }
}

class _ReceiptDraft {
  _ReceiptDraft(this.line)
      : received = TextEditingController(text: line.quantity),
        damaged = TextEditingController(text: '0');

  final StockTransferLineRecord line;
  final TextEditingController received;
  final TextEditingController damaged;

  void dispose() {
    received.dispose();
    damaged.dispose();
  }
}

/// Book in what arrived (STK-1): one row per line with the quantity sent, the
/// quantity received (damaged included) and how much of it is damaged. What
/// did not arrive is the shortage, and the server writes it off.
class ReceiveTransferDialog extends StatefulWidget {
  const ReceiveTransferDialog({
    super.key,
    required this.transfer,
    required this.onSave,
  });

  final StockTransferRecord transfer;

  /// Receives with the body; a refusal is an `ApiException` shown here.
  final Future<void> Function(Json body) onSave;

  @override
  State<ReceiveTransferDialog> createState() => _ReceiveTransferDialogState();
}

class _ReceiveTransferDialogState extends State<ReceiveTransferDialog>
    with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  late final List<_ReceiptDraft> _rows = [
    for (final StockTransferLineRecord line in widget.transfer.lines)
      _ReceiptDraft(line),
  ];
  DateTime _when = DateTime.now();
  String? _problem;

  @override
  void dispose() {
    _remarks.dispose();
    for (final _ReceiptDraft row in _rows) {
      row.dispose();
    }
    super.dispose();
  }

  double _sent(_ReceiptDraft row) => double.tryParse(row.line.quantity) ?? 0;

  double? _short(_ReceiptDraft row) {
    final double? received = double.tryParse(row.received.text.trim());
    if (received == null) return null;
    return _sent(row) - received;
  }

  String _shortText(_ReceiptDraft row) {
    final double? value = _short(row);
    if (value == null) return '-';
    if (value == value.roundToDouble()) return value.toInt().toString();
    return value.toStringAsFixed(4).replaceFirst(RegExp(r'0+$'), '');
  }

  String? _validate() {
    for (final _ReceiptDraft row in _rows) {
      final double? received = double.tryParse(row.received.text.trim());
      final double? damaged = double.tryParse(row.damaged.text.trim());
      final String name = row.line.productLabel;
      if (received == null || damaged == null) {
        return 'Enter received and damaged quantities for $name.';
      }
      if (received < 0 || damaged < 0) {
        return 'Quantities for $name cannot be negative.';
      }
      if (received > _sent(row)) {
        return 'More of $name was received than was sent.';
      }
      if (damaged > received) {
        return 'More of $name is damaged than was received.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final String? problem = _validate();
    setState(() {
      _problem = problem;
      saveError = null;
    });
    if (problem != null) return;
    final Json body = <String, dynamic>{
      'received_on': _today(_when),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        for (final _ReceiptDraft row in _rows)
          <String, dynamic>{
            'line_number': row.line.lineNumber,
            'received_quantity': row.received.text.trim(),
            'damaged_quantity': row.damaged.text.trim(),
          },
      ],
    };
    await submit<Json>(body, widget.onSave);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Receive ${widget.transfer.transferNumber}'),
      content: SizedBox(
        width: 760,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(
                    _problem!,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
              Text(
                'Received includes anything damaged. What was sent but not '
                'received is the shortage and is written off.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              InkWell(
                onTap: saving
                    ? null
                    : () async {
                        final DateTime? picked = await showDatePicker(
                          context: context,
                          initialDate: _when,
                          firstDate: DateTime(2000),
                          lastDate: DateTime(2100),
                        );
                        if (picked != null) setState(() => _when = picked);
                      },
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'Received on',
                    suffixIcon: Icon(Icons.calendar_today, size: 18),
                  ),
                  child: Text(_today(_when)),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              for (int index = 0; index < _rows.length; index++)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.only(top: AppSpacing.md),
                          child: Text(
                            _rows[index].line.productLabel,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 90,
                        child: Padding(
                          padding: const EdgeInsets.only(top: AppSpacing.md),
                          child: Text('Sent ${_rows[index].line.quantity}'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      SizedBox(
                        width: 110,
                        child: TextField(
                          key: ValueKey('receive-received-$index'),
                          controller: _rows[index].received,
                          enabled: !saving,
                          decoration:
                              const InputDecoration(labelText: 'Received'),
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      SizedBox(
                        width: 110,
                        child: TextField(
                          key: ValueKey('receive-damaged-$index'),
                          controller: _rows[index].damaged,
                          enabled: !saving,
                          decoration:
                              const InputDecoration(labelText: 'Damaged'),
                          keyboardType: TextInputType.number,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      SizedBox(
                        width: 90,
                        child: Padding(
                          padding: const EdgeInsets.only(top: AppSpacing.md),
                          child: Text(
                            'Short ${_shortText(_rows[index])}',
                            key: ValueKey('receive-short-$index'),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              TextField(
                key: const ValueKey('receive-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
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
          key: const ValueKey('receive-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Receiving...' : 'Receive'),
        ),
      ],
    );
  }
}
