// STK-15, the desktop half: kits and combo packs.
//
//   * the product record shows a Components section for a BUNDLE and not for
//     a stock item;
//   * saving it sends `{"components": [...]}` with the declared keys, and the
//     server's refusal stays on the section;
//   * assembling sends branch, warehouse, quantity, date and remarks, and a
//     refusal keeps the dialog open;
//   * the client reaches the four endpoints.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/kit.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/repack.dart';
import 'package:agency_desktop/ui/inventory/repack_dialog.dart'
    show RepackOption;
import 'package:agency_desktop/ui/products/kit_components_section.dart';
import 'package:agency_desktop/ui/products/product_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const ProductMetadataRecord _metadata = ProductMetadataRecord(
  profileCode: 'WHOLESALE',
  features: [],
  categories: [],
  taxProfiles: [],
  requiredAttributeDefinitionIds: [],
  optionalAttributeDefinitionIds: [],
);

Product _product(String id, String type, {String code = 'P', String? name}) =>
    Product.fromJson({
      'id': id,
      'code': code,
      'name': name ?? 'Product $id',
      'product_type': type,
      'status': 'ACTIVE',
      'unit': 'NOS',
      'purchase_price': '80',
      'selling_price': '100',
      'mrp': '120',
      'stock_on_hand': '4',
    });

const RepackRecord _repack = RepackRecord(
  id: 'rp-1',
  repackNumber: 'RPK-0007',
  repackDate: '2026-10-03',
);

class _Recorder {
  final List<Json> replaced = [];
  final List<Json> assembled = [];
  final List<Json> disassembled = [];
  String? refuseReplace;
  String? refuseAssemble;

  KitActions get actions => KitActions(
        load: (productId) async => const [
          KitComponent(
            componentProductId: 'p-soap',
            componentCode: 'SOAP',
            componentName: 'Soap',
            quantity: '2.0000',
          ),
        ],
        replace: (productId, body) async {
          if (refuseReplace != null) throw ApiException(refuseReplace!);
          replaced.add(body);
          return const [];
        },
        products: () async => [
          _product('p-soap', 'STOCK_ITEM', code: 'SOAP', name: 'Soap'),
          _product('p-towel', 'STOCK_ITEM', code: 'TWL', name: 'Towel'),
          _product('kit-1', 'BUNDLE', code: 'KIT', name: 'Gift pack'),
          _product('kit-2', 'BUNDLE', code: 'KIT2', name: 'Other pack'),
        ],
        assemble: (productId, body) async {
          if (refuseAssemble != null) throw ApiException(refuseAssemble!);
          assembled.add(body);
          return _repack;
        },
        disassemble: (productId, body) async {
          disassembled.add(body);
          return _repack;
        },
      );
}

Future<void> _pumpEditor(
  WidgetTester tester,
  Product product,
  _Recorder recorder,
) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: ProductWorkspaceDialog(
        mode: ProductDialogMode.edit,
        product: product,
        categories: const [],
        uoms: const [],
        definitions: const [],
        metadata: _metadata,
        initialTab: 'general',
        onMetadataForCategory: (_) async => _metadata,
        onSave: (payload) async => product,
        onTabChanged: (_) {},
        kits: recorder.actions,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpStockDialog(
  WidgetTester tester,
  _Recorder recorder, {
  required bool assemble,
  bool kitTracksBatch = false,
  bool kitTracksExpiry = false,
  List<KitComponent> batchParts = const [],
}) async {
  tester.view.physicalSize = const Size(1200, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final KitActions actions = recorder.actions;
  await tester.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () => showDialog<dynamic>(
            context: context,
            builder: (context) => KitStockDialog(
              kitName: 'Gift pack',
              assemble: assemble,
              kitTracksBatch: kitTracksBatch,
              kitTracksExpiry: kitTracksExpiry,
              batchParts: batchParts,
              branches: const [RepackOption(id: 'b-1', label: 'BR1 - Main')],
              warehouses: const [
                RepackOption(id: 'w-1', label: 'WH1 - Store', parentId: 'b-1'),
              ],
              onSave: (body) => assemble
                  ? actions.assemble('kit-1', body)
                  : actions.disassemble('kit-1', body),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

class _PathApi extends ApiClient {
  _PathApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> calls = [];
  final List<Json?> bodies = [];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    calls.add('$method $path');
    bodies.add(body);
    if (method == 'GET') return {'data': <dynamic>[]};
    if (path.endsWith('/components')) return {'data': <dynamic>[]};
    return {
      'data': {
        'id': 'rp-1',
        'repack_number': 'RPK-0007',
        'repack_date': '2026-10-03',
      },
    };
  }
}

void main() {
  testWidgets('a kit shows the Components section with its saved rows',
      (tester) async {
    await _pumpEditor(tester, _product('kit-1', 'BUNDLE'), _Recorder());
    expect(find.byKey(const ValueKey('kit-components')), findsOneWidget);
    expect(find.textContaining('SOAP - Soap'), findsWidgets);
    expect(find.byKey(const ValueKey('product-section-components')),
        findsOneWidget);
  });

  testWidgets('a stock item has no Components section', (tester) async {
    await _pumpEditor(tester, _product('p-1', 'STOCK_ITEM'), _Recorder());
    expect(find.byKey(const ValueKey('kit-components')), findsNothing);
    expect(find.byKey(const ValueKey('product-section-components')),
        findsNothing);
  });

  testWidgets('saving sends the components with the declared keys',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpEditor(tester, _product('kit-1', 'BUNDLE'), recorder);
    final Finder add = find.byKey(const ValueKey('kit-component-add'));
    await tester.ensureVisible(add);
    await tester.tap(add);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('kit-component-product-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('TWL - Towel').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('kit-component-quantity-1')), '3');
    final Finder save = find.byKey(const ValueKey('kit-components-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(recorder.replaced, [
      {
        'components': [
          {'component_product_id': 'p-soap', 'quantity': '2.0000'},
          {'component_product_id': 'p-towel', 'quantity': '3'},
        ],
      },
    ]);
    expect(find.text('Components saved.'), findsOneWidget);
  });

  testWidgets('the picker offers neither kits nor the kit itself',
      (tester) async {
    await _pumpEditor(tester, _product('kit-1', 'BUNDLE'), _Recorder());
    final Finder add = find.byKey(const ValueKey('kit-component-add'));
    await tester.ensureVisible(add);
    await tester.tap(add);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('kit-component-product-1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('TWL - Towel'), findsOneWidget);
    expect(find.textContaining('Gift pack'), findsNothing);
    expect(find.textContaining('Other pack'), findsNothing);
  });

  testWidgets("the server's refusal stays on the section", (tester) async {
    final _Recorder recorder = _Recorder()
      ..refuseReplace = 'A kit cannot hold another kit.';
    await _pumpEditor(tester, _product('kit-1', 'BUNDLE'), recorder);
    final Finder save = find.byKey(const ValueKey('kit-components-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(find.text('A kit cannot hold another kit.'), findsOneWidget);
  });

  testWidgets('assembling sends branch, warehouse, quantity, date, remarks',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder, assemble: true);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '5');
    await tester.enterText(find.byKey(const ValueKey('kit-remarks')), 'Diwali');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    expect(recorder.assembled, hasLength(1));
    final Json body = recorder.assembled.single;
    expect(body.keys.toSet(),
        {'branch_id', 'warehouse_id', 'quantity', 'on', 'remarks'});
    expect(body['branch_id'], 'b-1');
    expect(body['warehouse_id'], 'w-1');
    expect(body['quantity'], '5');
    expect(body['remarks'], 'Diwali');
    expect(body['on'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    expect(find.byType(KitStockDialog), findsNothing);
  });

  testWidgets('a refusal naming the short component keeps the dialog open',
      (tester) async {
    final _Recorder recorder = _Recorder()
      ..refuseAssemble = 'Not enough Soap in stock.';
    await _pumpStockDialog(tester, recorder, assemble: true);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '5');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    expect(find.text('Not enough Soap in stock.'), findsOneWidget);
    expect(find.byType(KitStockDialog), findsOneWidget);
  });

  testWidgets('disassembling calls disassemble, not assemble', (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder, assemble: false);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '2');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    expect(recorder.disassembled, hasLength(1));
    expect(recorder.assembled, isEmpty);
    expect(recorder.disassembled.single['remarks'], isNull);
  });

  testWidgets('a kit kept in batches is assembled into the batch typed',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder,
        assemble: true, kitTracksBatch: true, kitTracksExpiry: true);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '1');
    await tester.enterText(find.byKey(const ValueKey('kit-batch')), 'KB1');
    await tester.enterText(find.byKey(const ValueKey('kit-expiry')), '2027-13');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    expect(find.text('Enter the expiry date as YYYY-MM-DD.'), findsOneWidget);
    expect(recorder.assembled, isEmpty);
    await tester.enterText(
        find.byKey(const ValueKey('kit-expiry')), '2027-12-31');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    final Json body = recorder.assembled.single;
    expect(body['batch_number'], 'KB1');
    expect(body['expiry_date'], '2027-12-31');
    expect(body.containsKey('part_batches'), isFalse);
  });

  testWidgets('a plain kit is offered no batch box, assembling or breaking',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder, assemble: true);
    expect(find.byKey(const ValueKey('kit-batch')), findsNothing);
    expect(find.byKey(const ValueKey('kit-expiry')), findsNothing);
    expect(find.byKey(const ValueKey('kit-part-batch-0')), findsNothing);
  });

  testWidgets('breaking a kit names the batch a batch-tracked part goes into',
      (tester) async {
    const List<KitComponent> parts = [
      KitComponent(
          componentProductId: 'p-med',
          componentCode: 'MED',
          componentName: 'Syrup',
          trackBatch: true),
      KitComponent(
          componentProductId: 'p-pill',
          componentCode: 'PILL',
          componentName: 'Tablets',
          trackBatch: true),
    ];
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder,
        assemble: false, kitTracksBatch: true, batchParts: parts);
    // The kit's own batch is asked for when kits are made, not broken.
    expect(find.byKey(const ValueKey('kit-batch')), findsNothing);
    expect(find.text('Batch for MED - Syrup'), findsOneWidget);
    expect(find.text('Batch for PILL - Tablets'), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '1');
    await tester.enterText(
        find.byKey(const ValueKey('kit-part-batch-1')), ' B77 ');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    final Json body = recorder.disassembled.single;
    expect(body['part_batches'], [
      {'product_id': 'p-pill', 'batch_number': 'B77'},
    ]);
    expect(body.containsKey('batch_number'), isFalse);
  });

  testWidgets('breaking with every batch box blank sends no part_batches',
      (tester) async {
    final _Recorder recorder = _Recorder();
    await _pumpStockDialog(tester, recorder, assemble: false, batchParts: const [
      KitComponent(componentProductId: 'p-med', trackBatch: true),
    ]);
    await tester.enterText(find.byKey(const ValueKey('kit-quantity')), '1');
    await tester.tap(find.byKey(const ValueKey('kit-save')));
    await tester.pumpAndSettle();
    expect(recorder.disassembled.single.keys.toSet(),
        {'branch_id', 'warehouse_id', 'quantity', 'on', 'remarks'});
  });

  test('a component says whether it is kept in batches', () {
    expect(
        KitComponent.fromJson(const {
          'component_product_id': 'p',
          'track_batch': true,
        }).trackBatch,
        isTrue);
    expect(
        KitComponent.fromJson(const {'component_product_id': 'p'}).trackBatch,
        isFalse);
  });

  test('the client reaches the four endpoints', () async {
    final _PathApi api = _PathApi();
    await api.kitComponents('k1');
    await api.replaceKitComponents('k1', {'components': <Json>[]});
    final RepackRecord made = await api.assembleKits('k1', {'quantity': '1'});
    await api.disassembleKits('k1', {'quantity': '1'});
    expect(api.calls, [
      'GET /api/v1/products/k1/components',
      'PUT /api/v1/products/k1/components',
      'POST /api/v1/products/k1/assemble',
      'POST /api/v1/products/k1/disassemble',
    ]);
    expect(made.repackNumber, 'RPK-0007');
  });
}
