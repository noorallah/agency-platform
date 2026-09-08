import 'package:flutter/material.dart';

import '../../models/entities.dart';

/// Choose the firm to land in at sign-in.
///
/// Distinct from the firm switcher on purpose. Switching is for now: it
/// changes what every screen shows until sign-out. The primary is for next
/// time: it changes nothing on screen today and decides where the next
/// session starts. Putting both on one control made each read as the other.
///
/// Returns the chosen firm's id, or null for a dismissal. The dialog owns its
/// selection; the caller makes the call, so the refusal -- a firm the person
/// does not belong to -- is shown where the choice was made.
Future<String?> choosePrimaryFirm(
  BuildContext context, {
  required List<AssignedFirm> firms,
}) =>
    showDialog<String>(
      context: context,
      builder: (_) => _PrimaryFirmDialog(firms: firms),
    );

class _PrimaryFirmDialog extends StatefulWidget {
  const _PrimaryFirmDialog({required this.firms});

  final List<AssignedFirm> firms;

  @override
  State<_PrimaryFirmDialog> createState() => _PrimaryFirmDialogState();
}

class _PrimaryFirmDialogState extends State<_PrimaryFirmDialog> {
  late String? _chosen = widget.firms
      .where((firm) => firm.isPrimary)
      .map((firm) => firm.id)
      .firstOrNull;

  bool get _changed =>
      _chosen != null &&
      !widget.firms.any((firm) => firm.id == _chosen && firm.isPrimary);

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Primary firm'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'The firm you start in when you sign in. Switching firms in the '
              'header is for this session only; this decides the next one.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            RadioGroup<String>(
              groupValue: _chosen,
              onChanged: (value) => setState(() => _chosen = value),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final AssignedFirm firm in widget.firms)
                    RadioListTile<String>(
                      dense: true,
                      value: firm.id,
                      title: Text(firm.name),
                      subtitle: Text(firm.code),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          // Dead until the choice differs from what is already primary:
          // saving the same answer is a request that changes nothing.
          onPressed:
              _changed ? () => Navigator.of(context).pop(_chosen) : null,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
