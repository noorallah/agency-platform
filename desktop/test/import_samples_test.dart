// Every file-based importer offers a sample file: the headings it reads and
// one example row. The sample is built from the importer's own column list,
// so these tests hold each one to a single question -- does the importer
// accept the file it hands out? -- rather than to a copied list of names.
//
// And every import dialog shows its messages through `CopyableMessage`, so a
// refusal from the server can be selected and pasted rather than retyped.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_territory.dart';
import 'package:agency_desktop/ui/branches/branch_warehouse_import_dialog.dart';
import 'package:agency_desktop/ui/inventory/inventory_import_samples.dart';
import 'package:agency_desktop/ui/inventory/inventory_import_wizard.dart';
import 'package:agency_desktop/ui/purchases/purchase_import_sample.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/sales/territory_import_dialog.dart';
import 'package:agency_desktop/ui/sales/territory_import_sample.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api({this.refuseWith})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuseWith;

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
    if (refuseWith != null) {
      throw ApiException(refuseWith!, statusCode: 409);
    }
    final List<dynamic> records =
        (body?['records'] as List<dynamic>?) ?? const <dynamic>[];
    return <String, dynamic>{
      'success': true,
      'data': [
        for (final dynamic record in records)
          <String, dynamic>{
            'id': 'id-${records.indexOf(record)}',
            'code': (record as Json)['code'],
            'name': record['name'],
          },
      ],
    };
  }

  @override
  Future<List<SalesTerritory>> importTerritories({
    required String fileName,
    required List<int> bytes,
  }) async {
    if (refuseWith != null) throw ApiException(refuseWith!);
    return const <SalesTerritory>[];
  }
}

/// A saved sample, captured instead of written through a native dialog.
class _Saved {
  String? name;
  String? content;

  Future<void> save(String suggestedName, String text) async {
    name = suggestedName;
    content = text;
  }
}

/// A real file on disk: the branch importer picks its format from the
/// extension, and `XFile.fromData` leaves `name` and `path` empty.
XFile _onDisk(String name, String content) {
  final Directory dir = Directory.systemTemp.createTempSync('import-sample');
  final File file = File('${dir.path}/$name')..writeAsStringSync(content);
  return XFile(file.path);
}

void _desktopSurface(WidgetTester tester) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 1200);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);
}

/// Intercept the platform clipboard and hand back whatever was copied.
String? Function() _captureClipboard(WidgetTester tester) {
  String? copied;
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    SystemChannels.platform,
    (MethodCall call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String?;
      }
      return null;
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null),
  );
  return () => copied;
}

/// Pump until the branch dialog has counted the rows it just read.
Future<void> _waitForParse(WidgetTester tester) async {
  final Stopwatch elapsed = Stopwatch()..start();
  while (find.textContaining('rows ').evaluate().isEmpty &&
      elapsed.elapsed < const Duration(seconds: 10)) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pumpAndSettle();
  }
}

void main() {
  group('ImportSample', () {
    test('writes a header row and one example row, quoted where needed', () {
      const ImportSample sample = ImportSample(
        fileName: 'x.csv',
        columns: ['code', 'name', 'notes'],
        example: ['A1', 'Plain', 'has, a comma and "quotes"'],
      );
      expect(
        sample.csv,
        'code,name,notes\r\n'
        'A1,Plain,"has, a comma and ""quotes"""\r\n',
      );
    });

    test('every shipped sample has one example value per column', () {
      final List<ImportSample> samples = [
        branchImportSample(BranchImportTarget.branches),
        branchImportSample(BranchImportTarget.warehouses),
        territoryImportSample,
        purchaseImportSample,
        for (final InventoryImportType type in InventoryImportType.values)
          inventoryImportSample(type),
      ];
      for (final ImportSample sample in samples) {
        expect(
          sample.example,
          hasLength(sample.columns.length),
          reason: sample.fileName,
        );
        // Reading it is what asserts the lengths agree in debug builds.
        expect(sample.csv, contains('\r\n'), reason: sample.fileName);
      }
    });
  });

  group('branches and warehouses', () {
    for (final BranchImportTarget target in BranchImportTarget.values) {
      testWidgets('${target.name}: the sample it hands out is a file it accepts',
          (tester) async {
      _desktopSurface(tester);
        final _Saved saved = _Saved();
        // Choose file is wired to hand back whatever the sample wrote, so
        // the dialog is asked to read its own output.
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: BranchWarehouseImportDialog(
                api: _Api(),
                target: target,
                saveSampleOverride: saved.save,
                pickFileOverride: () async =>
                    _onDisk(saved.name!, saved.content!),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.widgetWithText(OutlinedButton, 'Sample file'));
        await tester.pumpAndSettle();

        expect(saved.name, '${target.name}_sample.csv');
        final ImportSample sample = branchImportSample(target);
        expect(
          saved.content!.split('\r\n').first,
          sample.columns.join(','),
          reason: 'the header row is the column list the parser reads',
        );
        expect(find.textContaining('Sample saved.'), findsOneWidget);

        await tester.runAsync(() async {
          await tester.tap(find.widgetWithText(OutlinedButton, 'Choose file'));
        });
        await _waitForParse(tester);

        expect(
          find.text('1 rows ready.'),
          findsOneWidget,
          reason: 'the example row passes every client-side check',
        );
      });
    }

    testWidgets('a refusal can be copied', (tester) async {
      _desktopSurface(tester);
      final String? Function() copied = _captureClipboard(tester);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: BranchWarehouseImportDialog(
              api: _Api(refuseWith: 'Branch code already exists in this firm.'),
              target: BranchImportTarget.branches,
              pickFileOverride: () async =>
                  _onDisk('b.csv', 'code,name\r\nBR_1,One\r\n'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.runAsync(() async {
        await tester.tap(find.widgetWithText(OutlinedButton, 'Choose file'));
      });
      await _waitForParse(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Import'));
      await tester.pumpAndSettle();

      expect(
        find.byWidgetPredicate(
          (widget) =>
              widget is SelectableText &&
              (widget.data ?? '').contains('Nothing was imported'),
        ),
        findsOneWidget,
        reason: 'the refusal is rendered selectable',
      );
      await tester.ensureVisible(find.byTooltip('Copy message'));
      await tester.tap(find.byTooltip('Copy message'));
      await tester.pumpAndSettle();
      expect(copied(), contains('Branch code already exists in this firm.'));
      expect(copied(), contains('Nothing was imported'));
    });
  });

  group('territories', () {
    testWidgets('offers a sample with the headings the server reads',
        (tester) async {
      _desktopSurface(tester);
      final _Saved saved = _Saved();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TerritoryImportDialog(
              api: _Api(),
              saveSampleOverride: saved.save,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Sample file'));
      await tester.pumpAndSettle();

      expect(saved.name, 'territories_sample.csv');
      // The spelling `TerritoryService.import_csv` reads; the backend's
      // `test_import_samples_match_the_server.py` holds the Dart file to it.
      expect(
        saved.content!.split('\r\n').first,
        'Code,Name,Level,ParentCode,Status,CustomerCodes',
      );
      expect(find.textContaining('Sample saved.'), findsOneWidget);
    });

    testWidgets('a refusal can be copied', (tester) async {
      _desktopSurface(tester);
      final String? Function() copied = _captureClipboard(tester);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TerritoryImportDialog(
              api: _Api(refuseWith: 'Unknown hierarchy level: Zone.'),
              pickFileOverride: () async => XFile.fromData(
                utf8.encode('Code,Name,Level\nRT01,North,Zone\n'),
                name: 'routes.csv',
                path: 'routes.csv',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose file'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Import'));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byTooltip('Copy message'));
      await tester.tap(find.byTooltip('Copy message'));
      await tester.pumpAndSettle();
      expect(copied(), 'Unknown hierarchy level: Zone. Nothing was imported.');
    });
  });

  group('purchase orders', () {
    testWidgets('the sample it hands out previews with no missing column',
        (tester) async {
      _desktopSurface(tester);
      final _Saved saved = _Saved();
      const List<String> required = [
        'branchid',
        'warehouseid',
        'vendorid',
        'productid',
        'purchasedate',
        'orderedqty',
        'unitprice',
      ];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PurchaseImportWizard(
              api: _Api(),
              requiredHeaders: required,
              onImported: () async {},
              saveSampleOverride: saved.save,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Sample file'));
      await tester.pumpAndSettle();

      expect(saved.name, 'purchase_orders_sample.csv');
      expect(
        saved.content!.split('\r\n').first,
        purchaseImportSample.columns.join(','),
      );

      // Feed the sample back through the same path a chosen file takes.
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PurchaseImportWizard(
              api: _Api(),
              requiredHeaders: required,
              onImported: () async {},
              initialFileName: saved.name,
              initialFileBytes: utf8.encode(saved.content!),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Missing required column'), findsNothing);
      expect(find.text('Start Import'), findsOneWidget);
      final Finder issues = find.text('Issues');
      expect(issues, findsOneWidget);
    });
  });

  group('inventory', () {
    for (final InventoryImportType type in InventoryImportType.values) {
      test('${type.name}: the sample carries every required column', () {
        final ImportSample sample = inventoryImportSample(type);
        final List<Map<String, String>> rows =
            InventoryImportFileParser.parseBytes(
          fileName: sample.fileName,
          bytes: utf8.encode(sample.csv),
        );
        expect(rows, hasLength(1));
        for (final String column in inventoryImportRequiredColumns(type)) {
          expect(rows.single.keys, contains(column), reason: column);
          expect(
            rows.single[column],
            isNotEmpty,
            reason: 'the example fills in $column',
          );
        }
      });
    }

    testWidgets('offers the sample for the selected import type',
        (tester) async {
      _desktopSurface(tester);
      final Directory temp = Directory.systemTemp.createTempSync('inv-sample');
      final _Saved saved = _Saved();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: InventoryImportWizard(
              api: _Api(),
              preferences: DesktopPreferencesService(directory: temp),
              branches: const [],
              warehouses: const [],
              products: const [],
              initialType: InventoryImportType.inventoryAdjustment,
              onViewImportedRecords: (_) async {},
              saveTextOverride: saved.save,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Sample file'));
      await tester.pumpAndSettle();

      expect(saved.name, 'inventory_adjustment_sample.csv');
      expect(
        saved.content,
        inventoryImportSample(InventoryImportType.inventoryAdjustment).csv,
      );
      expect(find.textContaining('Sample saved.'), findsOneWidget);
    });
  });
}
