import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// Put the customers on a round into the order they are called.
///
/// `visit_sequence` has been a column on the assignment since the first
/// migration and was writable through the API from the start — but the `GET`
/// returned bare ids, so nothing could read back the order it had saved and no
/// screen ever offered to set it. A round whose stops have no order is a set of
/// customers, not a route.
///
/// Drag to reorder. Saving renumbers 1..N, which is deliberate: gaps and
/// duplicates in a hand-typed sequence are what a drag list exists to avoid.
class CallOrderDialog extends StatefulWidget {
  const CallOrderDialog({
    super.key,
    required this.routeName,
    required this.assignments,
    required this.nameFor,
  });

  final String routeName;

  /// In the order the server returned them, which is already call order with
  /// the unplaced customers last.
  final List<TerritoryCustomerAssignmentRecord> assignments;

  /// Resolves a customer id to something a person recognises.
  final String Function(String customerId) nameFor;

  @override
  State<CallOrderDialog> createState() => _CallOrderDialogState();
}

class _CallOrderDialogState extends State<CallOrderDialog> {
  late final List<TerritoryCustomerAssignmentRecord> _order =
      List<TerritoryCustomerAssignmentRecord>.from(widget.assignments);

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Call order — ${widget.routeName}'),
        content: SizedBox(
          width: 560,
          height: 460,
          child: _order.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nobody on this round',
                  message: 'Put customers on the route first, then come back '
                      'to set the order they are called in.',
                )
              : Column(
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'Drag to reorder. The round is walked top to bottom.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Expanded(
                      child: ReorderableListView.builder(
                        buildDefaultDragHandles: false,
                        itemCount: _order.length,
                        // `onReorderItem`, not `onReorder`: the older callback
                        // reports the target index in the list as it stood
                        // before the item was lifted out, so every caller has
                        // to decrement it by hand. This one is already
                        // adjusted.
                        onReorderItem: (oldIndex, newIndex) => setState(() {
                          _order.insert(newIndex, _order.removeAt(oldIndex));
                        }),
                        itemBuilder: (context, index) {
                          final TerritoryCustomerAssignmentRecord row =
                              _order[index];
                          return ListTile(
                            key: ValueKey<String>(row.customerId),
                            dense: true,
                            leading: CircleAvatar(
                              radius: 14,
                              child: Text('${index + 1}'),
                            ),
                            title: Text(
                              widget.nameFor(row.customerId),
                              overflow: TextOverflow.ellipsis,
                            ),
                            subtitle: row.isPotential
                                ? const Text('Potential customer')
                                : null,
                            trailing: ReorderableDragStartListener(
                              index: index,
                              child: const Icon(Icons.drag_handle),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _order.isEmpty
                ? null
                : () => Navigator.pop<List<TerritoryCustomerAssignmentRecord>>(
                      context,
                      <TerritoryCustomerAssignmentRecord>[
                        for (int index = 0; index < _order.length; index++)
                          _order[index].withSequence(index + 1),
                      ],
                    ),
            child: const Text('Save order'),
          ),
        ],
      );
}
