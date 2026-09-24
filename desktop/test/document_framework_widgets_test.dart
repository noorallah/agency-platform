import 'package:agency_desktop/models/document_framework.dart';
import 'package:agency_desktop/ui/document_framework/document_framework_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('document framework widgets render generic lifecycle surfaces', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(
              children: [
                EnterpriseDocumentHeader(
                  header: const DocumentHeaderSnapshot(
                    documentTypeCode: 'PURCHASE_ORDER',
                    documentTypeName: 'Purchase Order',
                    documentNumber: 'PO-2026-000001',
                    documentDate: '2026-08-03',
                    reference: 'REF-01',
                    branch: 'Head Office',
                    warehouse: 'Main Warehouse',
                    firm: 'Agency Pvt Ltd',
                    businessProfile: 'Generic',
                    currency: 'INR',
                    exchangeRate: '1.0000',
                    status: 'Draft',
                    remarks: 'Reusable lifecycle header',
                    createdBy: 'Admin',
                    approvedBy: '',
                  ),
                ),
                EnterpriseDocumentLines(
                  lines: const [
                    DocumentLineSnapshot(
                      lineNumber: 1,
                      product: 'Laptop',
                      description: 'Business laptop',
                      uom: 'Nos',
                      packaging: 'Box',
                      quantity: '1',
                      freeQuantity: '0',
                      unitPrice: '50000',
                      discount: '0',
                      taxProfile: 'GST 18%',
                      amount: '50000',
                      netAmount: '59000',
                      remarks: 'Urgent',
                    ),
                  ],
                ),
                EnterpriseTotalsPanel(
                  totals: const DocumentTotalsSnapshot(
                    subtotal: '50000',
                    discount: '0',
                    tax: '9000',
                    charges: '0',
                    roundOff: '0',
                    grandTotal: '59000',
                  ),
                ),
                EnterpriseTimeline(
                  entries: const [
                    DocumentTimelineSnapshot(
                      occurredAt: '2026-08-03T10:00:00Z',
                      action: 'Created',
                      toState: 'Draft',
                      actor: 'Admin',
                      remarks: 'Initial creation',
                    ),
                  ],
                ),
                EnterpriseApprovalPanel(
                  status: 'Pending approval',
                  actions: const [Text('Approve later')],
                ),
                EnterpriseDocumentToolbar(
                  onAction: (_) {},
                  isEnabled: (_) => true,
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(find.text('PO-2026-000001'), findsOneWidget);
    expect(find.text('Laptop'), findsOneWidget);
    expect(find.text('59000'), findsWidgets);
    expect(find.text('Created'), findsWidgets);
    expect(find.text('Approve later'), findsOneWidget);
    expect(find.text('New'), findsOneWidget);
  });

  testWidgets('the header shows the party when one is set, hides it otherwise',
      (tester) async {
    // The customer on a sale, the vendor on a purchase -- named for display
    // so the header is not silent about who the document is with
    // (docs/BACKLOG.md 18.3). The field is omitted, not blanked, on a
    // document that does not carry it, so the five views not yet wired do
    // not grow an empty "Party -" row.
    Future<void> pumpHeader(DocumentHeaderSnapshot header) => tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: EnterpriseDocumentHeader(header: header),
              ),
            ),
          ),
        );

    await pumpHeader(const DocumentHeaderSnapshot(
      documentTypeCode: 'SALES_INVOICE',
      documentTypeName: 'Sales Invoice',
      documentNumber: 'SI-2026-2027-000009',
      documentDate: '2026-08-22',
      status: 'Approved',
      party: 'QuickTech Retail',
      partyLabel: 'Customer',
    ));
    expect(find.text('Customer'), findsOneWidget);
    expect(find.text('QuickTech Retail'), findsOneWidget);

    await pumpHeader(const DocumentHeaderSnapshot(
      documentTypeCode: 'PURCHASE_ORDER',
      documentTypeName: 'Purchase Order',
      documentNumber: 'PO-1',
      documentDate: '2026-08-22',
      status: 'Draft',
    ));
    expect(find.text('Party'), findsNothing,
        reason: 'a document with no party carries no party field');
  });

  testWidgets('a saved line shows the rate it got beside the amount, and the '
      'header its coupon', (tester) async {
    // The Discount column was the amount alone and the coupon was on no
    // screen once the order was saved; a salesman asking "what did this line
    // get" had no route once the order was approved (BL-31.14).
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(
              children: [
                EnterpriseDocumentHeader(
                  header: const DocumentHeaderSnapshot(
                    documentTypeCode: 'SALES_ORDER',
                    documentTypeName: 'Sales Order',
                    documentNumber: 'SO-1',
                    documentDate: '2026-09-24',
                    status: 'Approved',
                    coupon: 'WELCOME10',
                  ),
                ),
                EnterpriseDocumentLines(
                  lines: const [
                    DocumentLineSnapshot(
                      lineNumber: 1,
                      product: 'Laptop',
                      quantity: '2',
                      unitPrice: '500.00',
                      discount: '100.00',
                      discountPercent: '10.00',
                    ),
                    DocumentLineSnapshot(
                      lineNumber: 2,
                      product: 'Mouse',
                      quantity: '1',
                      unitPrice: '50.00',
                      discount: '0.00',
                      discountPercent: '0.00',
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(find.text('Coupon'), findsOneWidget);
    expect(find.text('WELCOME10'), findsOneWidget);
    expect(find.text('100.00 (10.00%)'), findsOneWidget);
    // No arrangement, no "(0.00%)".
    expect(find.text('0.00'), findsOneWidget);
  });

  testWidgets('a header with no coupon shows no Coupon field', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: EnterpriseDocumentHeader(
            header: DocumentHeaderSnapshot(
              documentTypeCode: 'PURCHASE_ORDER',
              documentTypeName: 'Purchase Order',
              documentNumber: 'PO-1',
              documentDate: '2026-09-24',
              status: 'Draft',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Coupon'), findsNothing);
  });
}
