// PG-4: the supplier's bill (a PDF or a phone photo) kept with a purchase bill
// and with a goods receipt. The server stores, lists, serves and deletes the
// files; these tests pin the desktop half -- the panel, who sees Add and
// Delete, the hint on a document not yet saved, and the checks made before a
// byte is sent.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/document_file.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/ui/goods_receipts/goods_receipt_editor_dialog.dart';
import 'package:agency_desktop/ui/purchases/document_attachments_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> removed = <String>[];
  List<DocumentFileRecord> files = const [
    DocumentFileRecord(
      id: 'f-1',
      fileName: 'supplier-bill.pdf',
      contentType: 'application/pdf',
      sizeBytes: 2048,
      caption: 'page one',
      createdAt: '2026-10-04T09:30:00Z',
    ),
  ];

  @override
  Future<List<DocumentFileRecord>> listDocumentFiles(
    AttachableDocument kind,
    String documentId,
  ) async =>
      files;

  @override
  Future<void> removeDocumentFile(
    AttachableDocument kind,
    String documentId,
    String fileId,
  ) async {
    removed.add('$kind/$documentId/$fileId');
    files = const [];
  }

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async =>
      <String, dynamic>{
        'data': const <Json>[],
        'pagination': <String, dynamic>{'total_records': 0},
      };
}

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  String? documentId = 'bill-1',
  bool canEdit = true,
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: DocumentAttachmentsDialog(
        api: api,
        kind: AttachableDocument.purchaseInvoice,
        documentId: documentId,
        subtitle: 'PI-0001',
        canEdit: canEdit,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows name, size, date and caption', (tester) async {
    await _open(tester, _Api());

    expect(find.text('supplier-bill.pdf'), findsOneWidget);
    expect(find.text('2 KB · 2026-10-04 · page one'), findsOneWidget);
    expect(find.byKey(const ValueKey('document-file-add')), findsOneWidget);
  });

  testWidgets('deleting asks first and then calls the api', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    await tester.tap(find.byTooltip('Delete'));
    await tester.pumpAndSettle();
    expect(api.removed, isEmpty);

    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    expect(api.removed, ['AttachableDocument.purchaseInvoice/bill-1/f-1']);
    expect(find.text('Nothing is attached yet.'), findsOneWidget);
  });

  testWidgets('without the permission Add and Delete are hidden',
      (tester) async {
    await _open(tester, _Api(), canEdit: false);

    expect(find.text('supplier-bill.pdf'), findsOneWidget);
    expect(find.byKey(const ValueKey('document-file-add')), findsNothing);
    expect(find.byTooltip('Delete'), findsNothing);
    // Looking is still allowed.
    expect(find.byTooltip('Open'), findsOneWidget);
    expect(find.byTooltip('Save as'), findsOneWidget);
  });

  testWidgets('a document not yet saved says to save first', (tester) async {
    await _open(tester, _Api(), documentId: null);

    expect(find.text('Save first to attach files'), findsOneWidget);
    expect(find.byKey(const ValueKey('document-file-add')), findsNothing);
  });

  test('a wrong type or a file over 10 MB is refused before sending', () {
    expect(documentFileProblem('bill.pdf', 1024), isNull);
    expect(documentFileProblem('photo.JPG', 1024), isNull);
    expect(documentFileProblem('photo.jpeg', 1024), isNull);
    expect(documentFileProblem('scan.png', maxDocumentFileBytes), isNull);

    expect(documentFileProblem('sheet.xlsx', 1024), contains('PDF, JPG or PNG'));
    expect(documentFileProblem('notes', 1024), contains('PDF, JPG or PNG'));
    expect(documentFileProblem('big.pdf', maxDocumentFileBytes + 1),
        contains('10 MB'));
    expect(documentFileProblem('empty.pdf', 0), contains('empty'));
  });

  for (final Size size in const [Size(1366, 768), Size(800, 600)]) {
    testWidgets('the panel does not overflow at ${size.width.toInt()}x'
        '${size.height.toInt()}', (tester) async {
      await _open(tester, _Api(), size: size);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the receipt window with its Attachments button does not '
        'overflow at ${size.width.toInt()}x${size.height.toInt()}',
        (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: GoodsReceiptEditorDialog(
            api: _Api(),
            purchaseOrders: const [],
            warehouses: const [],
            products: const [],
            existing: GoodsReceiptRecord.fromJson(<String, dynamic>{
              'id': 'gr-1',
              'receipt_number': 'GRN-0001',
              'status': 'DRAFT',
              'lines': <Json>[],
            }),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('goods-receipt-attachments')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
