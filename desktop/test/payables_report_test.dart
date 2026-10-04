import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/branch_warehouse.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/phase2/payables_report_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// PG-2: payables by supplier and month, with the books check.
class _Api extends ApiClient {
  _Api({this.difference = '0.00'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String difference;
  final List<Map<String, String?>> asked = [];

  Json _row(String? id, String name, List<String> amounts, String total) => {
        'vendor_id': id,
        'vendor_code': id == null ? '' : 'V1',
        'vendor_name': name,
        'older': '10.00',
        'amounts': amounts,
        'later': '0.00',
        'credits': '-5.00',
        'total': total,
        'counts': [1, 1],
        'documents': 2,
      };

  @override
  Future<Json> purchasePayables({
    String? asOf,
    String basis = 'invoice',
    int months = 6,
    String? vendorId,
    String? branchId,
    String view = 'owed',
  }) async {
    asked.add({'view': view, 'branch': branchId});
    return {
      'as_of': asOf,
      'basis': basis,
      'view': view,
      'months': ['2026-09', '2026-10'],
      'rows': [_row('v-1', 'Acme Traders', ['100.00', '200.00'], '305.00')],
      'total': _row(null, 'Total', ['100.00', '200.00'], '305.00'),
      'books_check': {
        'ledger_balance': '305.00',
        'difference': difference,
        'note': 'Compared with 2100.',
      },
    };
  }

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult(items: [
        Vendor.fromJson({'id': 'v-1', 'name': 'Acme Traders'}),
      ], total: 1);

  @override
  Future<PagedResult<BranchRecord>> branches({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    BranchQuery filters = const BranchQuery(),
  }) async =>
      PagedResult(items: const [], total: 0);
}

Future<void> _open(WidgetTester tester, _Api api, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: PayablesReportPage(api: api, onOpenBills: () {}),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows suppliers, a total row and an agreeing books check',
      (tester) async {
    await _open(tester, _Api(), const Size(1366, 768));
    expect(find.text('Acme Traders'), findsWidgets);
    expect(find.byKey(const ValueKey('payables-total-row')), findsOneWidget);
    expect(find.text('Total'), findsOneWidget);
    expect(find.textContaining('Agrees with the books'), findsOneWidget);
    expect(find.byKey(const ValueKey('payables-chart')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('warns when the grid and the books differ', (tester) async {
    await _open(tester, _Api(difference: '12.50'), const Size(1366, 768));
    expect(find.textContaining('Does not agree with the books'),
        findsOneWidget);
  });

  testWidgets('the Paid switch asks for the paid view', (tester) async {
    final _Api api = _Api();
    await _open(tester, api, const Size(1366, 768));
    await tester.tap(find.text('Paid'));
    await tester.pumpAndSettle();
    expect(api.asked.last['view'], 'paid');
    expect(find.text('Credits'), findsNothing);
    expect(find.byKey(const ValueKey('payables-total-row')), findsOneWidget);
  });

  testWidgets('does not overflow at 800x600', (tester) async {
    await _open(tester, _Api(difference: '12.50'), const Size(800, 600));
    expect(find.byKey(const ValueKey('payables-grid')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
