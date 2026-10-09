// A document view says who created and who approved the document, and what a
// goods receipt records about the supplier's invoice and the e-way bill
// (D-UI-88). Both people were '-' on every view: the header was never told,
// and the history that could tell it read `actor` where the server sends
// `actor_id`. The business profile is the firm's and is no longer shown.

import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:agency_desktop/ui/document_framework/history_words.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _clerk = '11111111-1111-4111-8111-111111111111';
const String _manager = '22222222-2222-4222-8222-222222222222';

DocumentTimelineSnapshot _event(String action, String actor, String at) =>
    DocumentTimelineSnapshot.fromJson(<String, dynamic>{
      'action': action,
      'actor_id': actor,
      'occurred_at': at,
    });

void main() {
  setUp(() {
    FirmPeople.reset();
    FirmPeople.configure(
      load: () async => const <FirmMember>[
        FirmMember(userId: _clerk, fullName: 'Store Clerk'),
        FirmMember(userId: _manager, fullName: 'Purchase Manager'),
      ],
      firmId: () => 'firm-1',
    );
  });
  tearDown(FirmPeople.reset);

  test('a history event reads the person the server sends as actor_id', () {
    expect(_event('CREATED', _clerk, '2026-10-09T10:00:00').actor, _clerk);
  });

  test('the history says who created and who last approved', () {
    // Newest first, as the server sends it.
    final List<DocumentTimelineSnapshot> history = <DocumentTimelineSnapshot>[
      _event('CLOSED', _clerk, '2026-10-09T12:00:00'),
      _event('APPROVED', _manager, '2026-10-09T11:00:00'),
      _event('CREATED', _clerk, '2026-10-09T10:00:00'),
    ];
    expect(historyCreatedBy(history), _clerk);
    expect(historyApprovedBy(history), _manager);
    // A goods receipt is completed, not approved.
    expect(
      historyApprovedBy(<DocumentTimelineSnapshot>[
        _event('COMPLETED', _manager, '2026-10-09T11:00:00'),
        _event('CREATED', _clerk, '2026-10-09T10:00:00'),
      ]),
      _manager,
    );
    // A draft has been approved by nobody.
    expect(
      historyApprovedBy(<DocumentTimelineSnapshot>[
        _event('CREATED', _clerk, '2026-10-09T10:00:00'),
      ]),
      '',
    );
  });

  testWidgets('the header names both people and shows no business profile',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: EnterpriseDocumentHeader(
              header: const DocumentHeaderSnapshot(
                documentTypeCode: 'PURCHASE_INVOICE',
                documentTypeName: 'Purchase Invoice',
                documentNumber: 'PI-1',
                documentDate: '2026-10-09',
                status: 'APPROVED',
                more: <String, String>{
                  'E-way bill no.': '123456789012',
                  'Vehicle number': '',
                },
              ),
              history: <DocumentTimelineSnapshot>[
                _event('APPROVED', _manager, '2026-10-09T11:00:00'),
                _event('CREATED', _clerk, '2026-10-09T10:00:00'),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Store Clerk'), findsOneWidget);
    expect(find.text('Purchase Manager'), findsOneWidget);
    expect(find.text('Business profile'), findsNothing);
    expect(find.text('123456789012'), findsOneWidget);
    // An empty extra is not given a label.
    expect(find.text('Vehicle number'), findsNothing);
  });

  test("a purchase order's own history words are read the same way", () {
    // Its history writes `purchase.approved`, not `APPROVED`.
    final List<DocumentTimelineSnapshot> history = <DocumentTimelineSnapshot>[
      _event('purchase.approved', _manager, '2026-10-09T11:00:00'),
      _event('purchase.created', _clerk, '2026-10-09T10:00:00'),
    ];
    expect(historyCreatedBy(history), _clerk);
    expect(historyApprovedBy(history), _manager);
    // An approval that was withdrawn is no longer an approval.
    expect(
      historyApprovedBy(<DocumentTimelineSnapshot>[
        _event('purchase.approval_withdrawn', _clerk, '2026-10-09T12:00:00'),
        ...history,
      ]),
      '',
    );
  });

  testWidgets('the one-page order names both people above its history',
      (WidgetTester tester) async {
    Future<void> pump(List<DocumentTimelineSnapshot> history) =>
        tester.pumpWidget(
          MaterialApp(
            home: Scaffold(body: DocumentPeopleLine(history: history)),
          ),
        );
    await pump(<DocumentTimelineSnapshot>[
      _event('purchase.approved', _manager, '2026-10-09T11:00:00'),
      _event('purchase.created', _clerk, '2026-10-09T10:00:00'),
    ]);
    await tester.pumpAndSettle();
    expect(find.text('Created by'), findsOneWidget);
    expect(find.text('Store Clerk'), findsOneWidget);
    expect(find.text('Approved by'), findsOneWidget);
    expect(find.text('Purchase Manager'), findsOneWidget);
    // An order nobody has saved yet says nothing.
    await pump(const <DocumentTimelineSnapshot>[]);
    await tester.pumpAndSettle();
    expect(find.text('Created by'), findsNothing);
  });

  test('a goods receipt hands its invoice number and e-way bill to the view',
      () {
    final GoodsReceiptRecord receipt =
        GoodsReceiptRecord.fromJson(<String, dynamic>{
      'id': 'gr-1',
      'grn_number': 'GRN-1',
      'invoice_reference': 'INV-77',
      'eway_bill_number': '123456789012',
      'eway_bill_date': '2026-10-08',
    });
    final Map<String, String> more = receipt.toHeader().more;
    expect(more["Supplier's invoice number"], 'INV-77');
    expect(more['E-way bill no.'], '123456789012');
    expect(more['E-way bill date'], '2026-10-08');
  });
}
