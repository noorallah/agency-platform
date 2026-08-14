import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/physical_count.dart';
import 'package:agency_desktop/ui/inventory/physical_count_page.dart';
import 'package:agency_desktop/ui/inventory/physical_count_sheet_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Counting a warehouse.
///
/// The sheet is walked over hours, so what has been counted so far belongs on
/// the server rather than in a form somebody might close. Posting is the
/// irreversible step that turns every difference into a stock adjustment.
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _CountApi extends ApiClient {
  _CountApi({this.sheets = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<PhysicalCountSheet> sheets;
  Json? recorded;
  String? posted;

  @override
  Future<PagedResult<PhysicalCountSheet>> physicalCounts({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async =>
      PagedResult<PhysicalCountSheet>(items: sheets, total: sheets.length);

  /// What the server would hand back. The tests that care pass one in; the
  /// rest only care what was sent.
  PhysicalCountSheet get _echo => sheets.isEmpty ? _sheet() : sheets.first;

  @override
  Future<PhysicalCountSheet> physicalCount(String id) async => _echo;

  @override
  Future<PhysicalCountSheet> recordPhysicalCount(String id, Json data) async {
    recorded = data;
    return _echo;
  }

  @override
  Future<PhysicalCountSheet> postPhysicalCount(String id) async {
    posted = id;
    return _echo;
  }
}

Json _line({
  required String id,
  required String expected,
  String counted = '',
  String variance = '',
}) =>
    {
      'id': id,
      'line_number': int.parse(id.split('-').last),
      'product_id': 'p-$id',
      'batch_id': '',
      'expected_quantity': expected,
      'counted_quantity': counted,
      'variance_quantity': variance,
      'transaction_id': '',
      'remarks': '',
    };

PhysicalCountSheet _sheet({
  String status = 'DRAFT',
  List<Json> lines = const [],
}) =>
    PhysicalCountSheet.fromJson({
      'id': 'pc-1',
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'count_number': 'PC-2026-2027-000001',
      'count_date': '2027-03-31',
      'status': status,
      'remarks': '',
      'posted_at': '',
      'lines': lines,
    });

Future<void> _pumpSheet(
  WidgetTester tester,
  _CountApi api,
  PhysicalCountSheet sheet, {
  bool canCount = true,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PhysicalCountSheetDialog(
          api: api,
          sheet: sheet,
          canCount: canCount,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('reading a sheet', () {
    test('how much of it has been walked', () {
      final PhysicalCountSheet sheet = _sheet(lines: [
        _line(id: 'l-1', expected: '10', counted: '9'),
        _line(id: 'l-2', expected: '5'),
        _line(id: 'l-3', expected: '7', counted: '7'),
      ]);
      expect(sheet.countedLines, 2);
      expect(sheet.lines.length, 3);
    });

    test('an uncounted line is not a line that found nothing', () {
      // Blank and zero are different answers, and the server treats them so.
      final PhysicalCountLine blank =
          PhysicalCountLine.fromJson(_line(id: 'l-1', expected: '10'));
      final PhysicalCountLine zero = PhysicalCountLine.fromJson(
        _line(id: 'l-2', expected: '10', counted: '0'),
      );
      expect(blank.isCounted, isFalse);
      expect(zero.isCounted, isTrue);
    });
  });

  group('filling one in', () {
    testWidgets('the difference shows while it is being typed', (tester) async {
      // So a fat-fingered digit is visible before it posts, not after.
      await _pumpSheet(
        tester,
        _CountApi(),
        _sheet(lines: [_line(id: 'l-1', expected: '10.0000')]),
      );

      await tester.enterText(find.byType(TextField).first, '7');
      await tester.pumpAndSettle();

      expect(find.text('-3.0000'), findsOneWidget);
    });

    testWidgets('a blank line is sent as no count rather than as zero',
        (tester) async {
      final _CountApi api = _CountApi();
      await _pumpSheet(
        tester,
        api,
        _sheet(lines: [
          _line(id: 'l-1', expected: '10'),
          _line(id: 'l-2', expected: '5'),
        ]),
      );

      await tester.enterText(find.byType(TextField).first, '8');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(OutlinedButton, 'Save progress'));
      await tester.pumpAndSettle();

      final List<dynamic> lines = api.recorded!['lines'] as List<dynamic>;
      expect(lines, hasLength(2));
      expect((lines[0] as Map)['counted_quantity'], '8');
      expect((lines[1] as Map).containsKey('counted_quantity'), isFalse,
          reason: 'nobody walked it, so it is not a count of nothing');
    });

    testWidgets('posting warns about the lines nobody walked', (tester) async {
      final _CountApi api = _CountApi();
      await _pumpSheet(
        tester,
        api,
        _sheet(lines: [
          _line(id: 'l-1', expected: '10', counted: '9'),
          _line(id: 'l-2', expected: '5'),
        ]),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'Post count'));
      await tester.pumpAndSettle();

      expect(find.textContaining('1 line(s) have not been counted'),
          findsOneWidget);
      expect(find.textContaining('cannot be changed'), findsOneWidget);
    });

    testWidgets('a posted sheet cannot be edited', (tester) async {
      await _pumpSheet(
        tester,
        _CountApi(),
        _sheet(
          status: 'POSTED',
          lines: [_line(id: 'l-1', expected: '10', counted: '9', variance: '-1')],
        ),
      );

      expect(find.widgetWithText(FilledButton, 'Post count'), findsNothing);
      final TextField counted = tester.widget<TextField>(find.byType(TextField));
      expect(counted.enabled, isFalse);
      expect(find.text('-1'), findsOneWidget, reason: 'the variance it wrote');
    });

    testWidgets('without INVENTORY_ADJUST it is read only', (tester) async {
      await _pumpSheet(
        tester,
        _CountApi(),
        _sheet(lines: [_line(id: 'l-1', expected: '10')]),
        canCount: false,
      );

      expect(find.widgetWithText(FilledButton, 'Post count'), findsNothing);
      final TextField counted = tester.widget<TextField>(find.byType(TextField));
      expect(counted.enabled, isFalse);
    });
  });

  group('the list', () {
    testWidgets('says how far along each sheet is', (tester) async {
      final _CountApi api = _CountApi(sheets: [
        _sheet(lines: [
          _line(id: 'l-1', expected: '10', counted: '9'),
          _line(id: 'l-2', expected: '5'),
        ]),
      ]);
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PhysicalCountPage(
              api: api,
              permissions: _permissionsFor(
                const ['INVENTORY_VIEW', 'INVENTORY_ADJUST'],
              ),
              hasActiveFirm: true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('1 of 2 lines counted'), findsOneWidget);
      expect(find.text('DRAFT'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Open Count'), findsOneWidget);
    });

    testWidgets('without INVENTORY_ADJUST there is nothing to open',
        (tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PhysicalCountPage(
              api: _CountApi(),
              permissions: _permissionsFor(const ['INVENTORY_VIEW']),
              hasActiveFirm: true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Open Count'), findsNothing);
    });
  });
}
