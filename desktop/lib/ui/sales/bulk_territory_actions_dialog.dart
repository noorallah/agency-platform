import 'package:flutter/material.dart';

/// What a bulk action does to the ticked territories.
enum BulkTerritoryAction {
  /// Set every ticked territory to one status.
  status,

  /// Reparent every ticked territory under one node.
  move,

  /// Replace the customer list on every ticked territory.
  customers,

  /// Replace the salesperson list on every ticked territory.
  salesmen,
}

/// The choice a user made in the bulk dialog.
class BulkTerritoryChoice {
  const BulkTerritoryChoice({required this.action, this.status, this.parentId});

  final BulkTerritoryAction action;

  /// Set for [BulkTerritoryAction.status].
  final String? status;

  /// Set for [BulkTerritoryAction.move]. Empty string means "no parent (root)".
  final String? parentId;
}

/// One parent a batch can be moved under.
class BulkParentOption {
  const BulkParentOption({required this.id, required this.label});

  final String id;
  final String label;
}

/// Pick one operation to apply to several territories at once.
///
/// The four bulk endpoints have existed since the module was written and no
/// screen reached any of them, so a firm reorganising a hierarchy had to open
/// and save each territory one at a time.
///
/// Two of the four **replace** a list rather than adding to it, which is a very
/// different thing to do to twenty territories than to one. The option says so
/// in its own subtitle, and the confirmation that follows repeats the count.
class BulkTerritoryActionsDialog extends StatefulWidget {
  const BulkTerritoryActionsDialog({
    super.key,
    required this.count,
    required this.parents,
    this.canAssignCustomers = true,
    this.canAssignSalesmen = true,
    this.canUpdate = true,
  });

  /// How many territories are ticked.
  final int count;

  /// Nodes a batch may be moved under.
  final List<BulkParentOption> parents;

  final bool canAssignCustomers;
  final bool canAssignSalesmen;
  final bool canUpdate;

  @override
  State<BulkTerritoryActionsDialog> createState() =>
      _BulkTerritoryActionsDialogState();
}

class _BulkTerritoryActionsDialogState
    extends State<BulkTerritoryActionsDialog> {
  BulkTerritoryAction? _action;
  String _status = 'ACTIVE';
  String _parentId = '';

  /// A permission the user lacks hides the option rather than showing it
  /// disabled: the four operations are guarded by three different codes, and a
  /// greyed row with no explanation reads as a broken screen.
  bool _allows(BulkTerritoryAction action) => switch (action) {
        BulkTerritoryAction.status || BulkTerritoryAction.move =>
          widget.canUpdate,
        BulkTerritoryAction.customers => widget.canAssignCustomers,
        BulkTerritoryAction.salesmen => widget.canAssignSalesmen,
      };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text(
        'Bulk actions on ${widget.count} '
        'territor${widget.count == 1 ? 'y' : 'ies'}',
      ),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: RadioGroup<BulkTerritoryAction>(
            groupValue: _action,
            onChanged: (value) => setState(() => _action = value),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'The whole batch is applied together. If one territory is '
                  'refused, none of them change.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                if (_allows(BulkTerritoryAction.status)) ...[
                  const RadioListTile<BulkTerritoryAction>(
                    value: BulkTerritoryAction.status,
                    contentPadding: EdgeInsets.zero,
                    title: Text('Change status'),
                    subtitle:
                        Text('Set every ticked territory to one status.'),
                  ),
                  if (_action == BulkTerritoryAction.status)
                    Padding(
                      padding: const EdgeInsets.only(left: 16, bottom: 8),
                      child: DropdownButtonFormField<String>(
                        initialValue: _status,
                        decoration:
                            const InputDecoration(labelText: 'New status'),
                        items: const [
                          DropdownMenuItem(
                              value: 'DRAFT', child: Text('Draft')),
                          DropdownMenuItem(
                              value: 'ACTIVE', child: Text('Active')),
                          DropdownMenuItem(
                              value: 'INACTIVE', child: Text('Inactive')),
                          DropdownMenuItem(
                              value: 'ARCHIVED', child: Text('Archived')),
                        ],
                        onChanged: (value) =>
                            setState(() => _status = value ?? 'ACTIVE'),
                      ),
                    ),
                ],
                if (_allows(BulkTerritoryAction.move)) ...[
                  const RadioListTile<BulkTerritoryAction>(
                    value: BulkTerritoryAction.move,
                    contentPadding: EdgeInsets.zero,
                    title: Text('Move under a parent'),
                    subtitle: Text(
                      'Reparent them all. Their children move with them.',
                    ),
                  ),
                  if (_action == BulkTerritoryAction.move)
                    Padding(
                      padding: const EdgeInsets.only(left: 16, bottom: 8),
                      child: DropdownButtonFormField<String>(
                        initialValue: _parentId,
                        isExpanded: true,
                        decoration:
                            const InputDecoration(labelText: 'New parent'),
                        items: [
                          const DropdownMenuItem<String>(
                            value: '',
                            child: Text('No parent (root)'),
                          ),
                          for (final BulkParentOption option in widget.parents)
                            DropdownMenuItem<String>(
                              value: option.id,
                              child: Text(option.label),
                            ),
                        ],
                        onChanged: (value) =>
                            setState(() => _parentId = value ?? ''),
                      ),
                    ),
                ],
                // "Replaces", not "adds": the endpoint sends the whole list, so
                // anybody already on those rounds who is not picked comes off.
                if (_allows(BulkTerritoryAction.customers))
                  const RadioListTile<BulkTerritoryAction>(
                    value: BulkTerritoryAction.customers,
                    contentPadding: EdgeInsets.zero,
                    title: Text('Set customers'),
                    subtitle: Text(
                      'Replaces the customer list on every ticked territory.',
                    ),
                  ),
                if (_allows(BulkTerritoryAction.salesmen))
                  const RadioListTile<BulkTerritoryAction>(
                    value: BulkTerritoryAction.salesmen,
                    contentPadding: EdgeInsets.zero,
                    title: Text('Set salespeople'),
                    subtitle: Text(
                      'Replaces the salesperson list on every ticked territory.',
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _action == null
              ? null
              : () => Navigator.pop(
                    context,
                    BulkTerritoryChoice(
                      action: _action!,
                      status: _status,
                      parentId: _parentId,
                    ),
                  ),
          child: const Text('Continue'),
        ),
      ],
    );
  }
}
