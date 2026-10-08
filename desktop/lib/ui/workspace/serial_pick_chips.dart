import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';

/// Pick existing serial numbers off a shelf: one chip per unit, with a heading
/// that says how many are picked of how many are needed.
///
/// The picker for a document that moves units already numbered -- a stock
/// transfer, a one-step move -- as the delivery note's picker does for goods
/// going out. [needed] is null where the editor cannot tell how many units
/// there are, and the heading then only counts what is picked.
class SerialPickChips extends StatelessWidget {
  const SerialPickChips({
    super.key,
    required this.title,
    required this.onShelf,
    required this.picked,
    required this.onToggle,
    this.needed,
    this.emptyMessage =
        'No serial numbers of this product are AVAILABLE in the source '
            'warehouse. Number the units under Inventory -> Batch & Serial '
            'first.',
    this.enabled = true,
  });

  /// What the picks are for, e.g. "Pick the units that are moving".
  final String title;
  final List<PickedSerial> onShelf;
  final List<String> picked;
  final int? needed;
  final String emptyMessage;
  final bool enabled;

  /// Called with the serial's id and whether it is now picked.
  final void Function(String id, bool picked) onToggle;

  @override
  Widget build(BuildContext context) {
    final bool short = needed != null && picked.length != needed;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          needed == null
              ? '$title - ${picked.length} picked'
              : '$title - ${picked.length} of $needed picked',
          key: const ValueKey('serial-pick-count'),
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: short ? Theme.of(context).colorScheme.error : null,
              ),
        ),
        const SizedBox(height: AppSpacing.xs),
        if (onShelf.isEmpty)
          Text(emptyMessage, style: Theme.of(context).textTheme.bodySmall)
        else
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              for (final PickedSerial serial in onShelf)
                FilterChip(
                  key: ValueKey<String>('serial-pick-${serial.id}'),
                  label: Text(serial.serialNumber),
                  selected: picked.contains(serial.id),
                  onSelected: enabled
                      ? (value) => onToggle(serial.id, value)
                      : null,
                ),
            ],
          ),
      ],
    );
  }
}
