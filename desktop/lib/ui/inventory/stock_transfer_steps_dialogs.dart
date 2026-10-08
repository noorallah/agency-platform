import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';
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

  /// Which of a serial-tracked line's units did not arrive, and which came
  /// damaged, by serial id.
  final List<String> shortIds = [];
  final List<String> damagedIds = [];

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

  /// Whole units, or null where the box does not hold one yet.
  int? _units(double? value) =>
      value == null || value != value.roundToDouble() ? null : value.toInt();

  /// Whether the units of this line have to be named: it is serial-tracked,
  /// and some arrived short or damaged.
  bool _namesUnits(_ReceiptDraft row) =>
      row.line.serialTracked &&
      row.line.serials.isNotEmpty &&
      (((_short(row) ?? 0) > 0) ||
          ((double.tryParse(row.damaged.text.trim()) ?? 0) > 0));

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
      if (_namesUnits(row)) {
        final int? shortUnits = _units(_short(row));
        final int? damagedUnits = _units(damaged);
        if (shortUnits != null && row.shortIds.length != shortUnits) {
          return 'Tick which $shortUnits unit(s) of $name did not arrive: '
              '${row.shortIds.length} ticked.';
        }
        if (damagedUnits != null && row.damagedIds.length != damagedUnits) {
          return 'Tick which $damagedUnits unit(s) of $name arrived damaged: '
              '${row.damagedIds.length} ticked.';
        }
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
            if (_namesUnits(row) && row.shortIds.isNotEmpty)
              'short_serial_ids': [...row.shortIds],
            if (_namesUnits(row) && row.damagedIds.isNotEmpty)
              'damaged_serial_ids': [...row.damagedIds],
          },
      ],
    };
    await submit<Json>(body, widget.onSave);
  }

  Widget _receiveRow(int index) {
    return Row(
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
            decoration: const InputDecoration(labelText: 'Received'),
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
            decoration: const InputDecoration(labelText: 'Damaged'),
            keyboardType: TextInputType.number,
            onChanged: (_) => setState(() {}),
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
    );
  }

  /// Tick the units of a serial-tracked line that are short and the ones that
  /// arrived damaged. A unit is one or the other, so ticking it in one list
  /// takes it out of the other.
  Widget _unitPicks(int index) {
    final _ReceiptDraft row = _rows[index];
    final int? shortUnits = _units(_short(row));
    final int? damagedUnits = _units(double.tryParse(row.damaged.text.trim()));
    final TextStyle? label = Theme.of(context).textTheme.labelMedium;
    Widget chips(String part, List<String> mine, List<String> other) => Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final PickedSerial serial in row.line.serials)
              FilterChip(
                key: ValueKey<String>('receive-$part-pick-$index-${serial.id}'),
                label: Text(serial.serialNumber),
                selected: mine.contains(serial.id),
                onSelected: saving
                    ? null
                    : (value) => setState(() {
                          if (value) {
                            mine.add(serial.id);
                            other.remove(serial.id);
                          } else {
                            mine.remove(serial.id);
                          }
                        }),
              ),
          ],
        );
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if ((shortUnits ?? 0) > 0) ...[
            Text(
              'Which units did not arrive - ${row.shortIds.length} of '
              '$shortUnits ticked',
              style: label,
            ),
            const SizedBox(height: AppSpacing.xs),
            chips('short', row.shortIds, row.damagedIds),
          ],
          if ((damagedUnits ?? 0) > 0) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Which units arrived damaged - ${row.damagedIds.length} of '
              '$damagedUnits ticked',
              style: label,
            ),
            const SizedBox(height: AppSpacing.xs),
            chips('damaged', row.damagedIds, row.shortIds),
          ],
        ],
      ),
    );
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
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _receiveRow(index),
                      if (_namesUnits(_rows[index])) _unitPicks(index),
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
