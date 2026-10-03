import 'package:agency_desktop/core/theme/theme_manager.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/ui/reports/report_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// STK-14: Home's to-do list carries the stock alerts, and the stock ageing
/// report shows how fast each item turns over.
class _Source implements HomeSource {
  _Source(this.alerts, {this.fail = false});

  final Map<String, dynamic> alerts;
  final bool fail;

  @override
  Future<Map<String, dynamic>> stockAlerts() async {
    if (fail) throw StateError('refused');
    return alerts;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) {
    final String name = invocation.memberName.toString();
    if (name.contains('invoiceRegister') ||
        name.contains('customerOutstanding') ||
        name.contains('taxCalendar')) {
      return Future.value(<Map<String, dynamic>>[]);
    }
    if (name.contains('receiptsOn')) return Future.value(0.0);
    if (name.contains('summary')) return Future.value(<String, dynamic>{});
    return Future.value(0);
  }
}

const Set<String> _storeman = {
  'inventory/inventory',
  'inventory/expiry-monitor',
  'inventory/physical-counts',
};

Future<List<String>> _pump(WidgetTester tester, HomeSource source,
    {Set<String> allowed = _storeman}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final List<String> opened = [];
  await tester.pumpWidget(MaterialApp(
    theme: ThemeRegistry.themeFor(
      palette: AppPalette.neutral,
      brightness: Brightness.light,
    ),
    home: Scaffold(
      body: Phase2HomePage(
        firmName: 'QA01',
        userName: 'Owner',
        today: DateTime.utc(2026, 10, 3),
        allowed: allowed.contains,
        source: source,
        onOpen: (item) => opened.add(item.path),
      ),
    ),
  ));
  await tester.pump();
  await tester.pump();
  expect(tester.takeException(), isNull);
  return opened;
}

void main() {
  testWidgets('Home lists the non-zero stock counts and opens the screen',
      (tester) async {
    final List<String> opened = await _pump(
      tester,
      _Source({
        'out': 3,
        'low': 5,
        'near_expiry': 2,
        'over_maximum': 1,
        'in_transit': 0,
        'open_counts': 1,
      }),
    );
    expect(find.text('3 products out of stock'), findsOneWidget);
    expect(find.text('5 below reorder level'), findsOneWidget);
    expect(find.text('2 batches near expiry'), findsOneWidget);
    expect(find.text('1 over maximum'), findsOneWidget);
    expect(find.text('1 count sheet open'), findsOneWidget);
    // A zero count draws no line.
    expect(find.textContaining('in transit'), findsNothing);

    await tester.tap(find.text('1 count sheet open'));
    await tester.pump();
    expect(opened, ['inventory/physical-counts']);
  });

  testWidgets('a failed read hides the stock lines without a trace',
      (tester) async {
    await _pump(tester, _Source(const {}, fail: true));
    expect(find.textContaining('out of stock'), findsNothing);
    expect(find.textContaining('below reorder level'), findsNothing);
  });

  testWidgets('a user without stock access gets no stock lines',
      (tester) async {
    await _pump(tester, _Source({'out': 3}), allowed: const {});
    expect(find.textContaining('out of stock'), findsNothing);
  });

  test('stock ageing lists issued last year and turnover', () {
    final ReportDefinition ageing =
        reportCatalog.firstWhere((r) => r.id == 'stock-ageing');
    final Map<String, String> columns = {
      for (final ReportColumn c in ageing.columns) c.key: c.label,
    };
    expect(columns['issued_last_year'], 'Issued (last year)');
    expect(columns['turnover'], 'Turnover');
  });
}
