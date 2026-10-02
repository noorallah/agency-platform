import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/inventory.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_evidence_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_evidence_picker.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Photos and documents kept with a stock movement or a count sheet (STK-9).
class _EvidenceApi extends ApiClient {
  _EvidenceApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<StockAttachmentRecord> files = [
    const StockAttachmentRecord(
      id: 'a-1',
      inventoryTransactionId: 'tx-1',
      fileName: 'damage.jpg',
      filePath: '/tmp/damage.jpg',
      caption: 'Crushed cartons',
      createdAt: '2026-10-03T10:00:00Z',
    ),
  ];
  List<Json>? attached;
  String? removed;
  String? refuse;

  @override
  Future<List<StockAttachmentRecord>> listMovementAttachments(
    String transactionId,
  ) async =>
      List.of(files);

  @override
  Future<List<StockAttachmentRecord>> attachToMovement(
    String transactionId,
    List<Json> items,
  ) async {
    if (refuse != null) throw ApiException(refuse!);
    attached = items;
    files.add(StockAttachmentRecord(
      id: 'a-2',
      inventoryTransactionId: transactionId,
      fileName: items.first['file_name'] as String,
      filePath: items.first['file_path'] as String,
      createdAt: '2026-10-03T11:00:00Z',
    ));
    return [files.last];
  }

  @override
  Future<void> removeStockAttachment(String id) async {
    if (refuse != null) throw ApiException(refuse!);
    removed = id;
    files.removeWhere((StockAttachmentRecord f) => f.id == id);
  }
}

Future<List<XFile>> _twoFiles() async => [
      XFile('slip.pdf'),
      XFile('shelf.png'),
    ];

void _bigWindow(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('the picker emits each file with its caption', (tester) async {
    _bigWindow(tester);
    List<Json> latest = const [];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: StockEvidencePicker(
            pickFiles: _twoFiles,
            onChanged: (files) => latest = files,
          ),
        ),
      ),
    ));
    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    expect(latest.length, 2);
    expect(latest.first['file_name'], 'slip.pdf');
    expect(latest.first['mime_type'], 'application/pdf');
    expect(latest.first['file_path'], 'slip.pdf');
    expect(latest.first.containsKey('caption'), isFalse);

    await tester.enterText(find.byType(TextField).first, 'Delivery slip');
    await tester.pump();
    expect(latest.first['caption'], 'Delivery slip');

    await tester.tap(find.byTooltip('Remove').last);
    await tester.pump();
    expect(latest.length, 1);
  });

  Future<Json> writeOff(WidgetTester tester, {required bool attach}) async {
    _bigWindow(tester);
    Json? saved;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<Object>(
            context: context,
            builder: (context) => Dialog(
              child: StockActionDialog(
                action: StockAction.writeOff,
                productLabel: 'Detergent',
                warehouseLabel: 'North',
                sourceWarehouseId: 'wh-north',
                available: 12,
                quarantined: 0,
                warehouses: const [],
                pickFiles: _twoFiles,
                onSave: (Json values) async => saved = values,
              ),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '2');
    if (attach) {
      await tester.tap(find.text('Attach photo or document'));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('Write off').last);
    await tester.pumpAndSettle();
    return stockActionBody(
      action: StockAction.writeOff,
      draft: saved!,
      branchId: 'b',
      warehouseId: 'w',
      productId: 'p',
    );
  }

  testWidgets('a write-off body omits attachments when none were attached',
      (tester) async {
    final Json body = await writeOff(tester, attach: false);
    expect(body.containsKey('attachments'), isFalse);
  });

  testWidgets('a write-off body carries the attachments that were picked',
      (tester) async {
    final Json body = await writeOff(tester, attach: true);
    expect((body['attachments'] as List).length, 2);
  });

  testWidgets('the evidence dialog lists, adds and removes', (tester) async {
    _bigWindow(tester);
    final _EvidenceApi api = _EvidenceApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StockEvidenceDialog(
          api: api,
          transactionId: 'tx-1',
          subtitle: 'WO-1',
          pickFiles: () async => [XFile('slip.pdf')],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('damage.jpg'), findsOneWidget);
    expect(find.textContaining('Crushed cartons'), findsOneWidget);

    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save files'));
    await tester.pumpAndSettle();
    expect(api.attached!.single['file_name'], 'slip.pdf');
    expect(find.text('slip.pdf'), findsOneWidget);

    await tester.tap(find.byTooltip('Remove').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove').last);
    await tester.pumpAndSettle();
    expect(api.removed, 'a-1');
    expect(find.text('damage.jpg'), findsNothing);
  });

  testWidgets('a refusal is shown and the dialog stays open', (tester) async {
    _bigWindow(tester);
    final _EvidenceApi api = _EvidenceApi()..refuse = 'The period is closed.';
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StockEvidenceDialog(
          api: api,
          transactionId: 'tx-1',
          subtitle: 'WO-1',
          pickFiles: () async => [XFile('slip.pdf')],
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Attach photo or document'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save files'));
    await tester.pumpAndSettle();
    expect(find.text('The period is closed.'), findsOneWidget);
    expect(find.text('slip.pdf'), findsOneWidget);
  });
}
