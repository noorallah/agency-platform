import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/bill_paper.dart';

/// What the person decided before a sales bill is printed.
class BillPaperChoice {
  const BillPaperChoice(this.paper);

  /// `HALF` or `A4` to send as the `paper` query, or null to send none.
  final String? paper;
}

/// Say which paper this bill needs and, on a half-page firm, let the person
/// switch this one print between half and full page.
///
/// A firm on one paper is asked nothing. Returns null when the person
/// cancelled, which is not an error. An [ApiException] from the server
/// propagates to the caller, which already reports it.
Future<BillPaperChoice?> askBillPaper(
  BuildContext context,
  ApiClient api, {
  required String invoiceId,
  required String number,
}) async {
  final BillPaper info = await api.salesInvoicePaper(invoiceId);
  if (info.firmPaper != 'HALF') return const BillPaperChoice(null);
  if (!context.mounted) return null;
  final String? chosen = await showDialog<String>(
    context: context,
    builder: (BuildContext dialogContext) =>
        _BillPaperDialog(info: info, number: number),
  );
  if (chosen == null) return null;
  return BillPaperChoice(info.mayChoose ? chosen : null);
}

class _BillPaperDialog extends StatefulWidget {
  const _BillPaperDialog({required this.info, required this.number});

  final BillPaper info;
  final String number;

  @override
  State<_BillPaperDialog> createState() => _BillPaperDialogState();
}

class _BillPaperDialogState extends State<_BillPaperDialog> {
  late String _paper = widget.info.paper == 'A4' ? 'A4' : 'HALF';

  String get _sentence {
    final BillPaper info = widget.info;
    if (!info.fitsHalfPage) {
      return 'This bill prints on a Full page: it is too long for half a page.';
    }
    if (_paper == 'HALF') return 'This bill prints on a Half page.';
    if (info.customerPaper == 'A4' && _paper == info.paper) {
      return "This bill prints on a Full page: this customer's bills are set "
          'to a full page.';
    }
    return 'This bill prints on a Full page.';
  }

  @override
  Widget build(BuildContext context) {
    final BillPaper info = widget.info;
    final bool choose = info.mayChoose && info.fitsHalfPage;
    return AlertDialog(
      title: Text('Print ${widget.number}'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (choose) ...<Widget>[
              SegmentedButton<String>(
                segments: const <ButtonSegment<String>>[
                  ButtonSegment<String>(value: 'HALF', label: Text('Half page')),
                  ButtonSegment<String>(value: 'A4', label: Text('Full page')),
                ],
                selected: <String>{_paper},
                onSelectionChanged: (Set<String> next) =>
                    setState(() => _paper = next.first),
              ),
              const SizedBox(height: 12),
            ],
            Text(_sentence),
            const SizedBox(height: 8),
            Text(
              "Check the paper in the printer's tray before printing.",
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          autofocus: true,
          onPressed: () => Navigator.of(context).pop(_paper),
          child: const Text('Print'),
        ),
      ],
    );
  }
}
