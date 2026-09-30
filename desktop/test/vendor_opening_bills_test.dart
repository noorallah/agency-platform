// Supplier opening bills: what the firm owed each supplier on day one,
// entered once at cutover so the supplier's balance here matches the old
// books without re-keying every historical purchase invoice.
//
// The section lives on the phase 2 vendor editor, copying the shape the
// Licences section already established (backlog 54): a nullable loader
// hides the section for a new vendor or somebody without `VENDOR_VIEW`, and
// "Add opening bill" and "Cancel" show only with `VENDOR_UPDATE`.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/models/vendor_opening_bill.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson() => <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'addresses': const <Json>[],
      'contacts': const <Json>[],
      'bank_accounts': const <Json>[],
      'tax_details': const <Json>[],
      'notes': const <Json>[],
    };

const Json _openBill = {
  'id': 'ob-1',
  'version': 1,
  'vendor_id': 'v-1',
  'vendor_code': 'V001',
  'vendor_name': 'Supplier One',
  'bill_number': 'OB-00001',
  'reference_number': 'INV-OLD-1',
  'bill_date': '2026-04-01',
  'due_date': '2026-05-01',
  'posting_date': '2026-04-01',
  'amount': '5000.00',
  'paid_amount': '0.00',
  'outstanding_amount': '5000.00',
  'narration': 'Opening balance',
  'status': 'POSTED',
  'cancellation_reason': null,
};

const Json _paidBill = {
  'id': 'ob-2',
  'version': 1,
  'vendor_id': 'v-1',
  'vendor_code': 'V001',
  'vendor_name': 'Supplier One',
  'bill_number': 'OB-00002',
  'reference_number': 'INV-OLD-2',
  'bill_date': '2026-04-05',
  'due_date': '2026-05-05',
  'posting_date': '2026-04-05',
  'amount': '3000.00',
  'paid_amount': '1000.00',
  'outstanding_amount': '2000.00',
  'narration': null,
  'status': 'POSTED',
  'cancellation_reason': null,
};

class _VendorApi extends ApiClient {
  _VendorApi({this.rows = const <Json>[], this.bills = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  List<Json> bills;
  final List<Json> createdBodies = <Json>[];
  final List<String> openingBillReads = <String>[];
  String? cancelledBillId;
  String? cancelReason;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[for (final Json row in rows) Vendor.fromJson(row)],
        total: rows.length,
      );

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<List<VendorOpeningBill>> vendorOpeningBills(String vendorId) async {
    openingBillReads.add(vendorId);
    return [for (final Json row in bills) VendorOpeningBill.fromJson(row)];
  }

  @override
  Future<VendorOpeningBill> createVendorOpeningBill(
    String vendorId,
    Json data,
  ) async {
    createdBodies.add(data);
    final Json row = {
      'id': 'ob-new',
      'version': 1,
      'vendor_id': vendorId,
      'vendor_code': 'V001',
      'vendor_name': 'Supplier One',
      'bill_number': 'OB-00003',
      'reference_number': data['reference_number'],
      'bill_date': data['bill_date'],
      'due_date': data['due_date'],
      'posting_date': data['posting_date'] ?? '2026-09-30',
      'amount': data['amount'],
      'paid_amount': '0.00',
      'outstanding_amount': data['amount'],
      'narration': data['narration'],
      'status': 'POSTED',
      'cancellation_reason': null,
    };
    bills = [...bills, row];
    return VendorOpeningBill.fromJson(row);
  }

  @override
  Future<VendorOpeningBill> cancelVendorOpeningBill(
    String billId,
    String reason,
  ) async {
    cancelledBillId = billId;
    cancelReason = reason;
    final Json updated = {
      ...bills.firstWhere((row) => row['id'] == billId),
      'status': 'CANCELLED',
      'cancellation_reason': reason,
    };
    bills = [
      for (final Json row in bills)
        if (row['id'] == billId) updated else row,
    ];
    return VendorOpeningBill.fromJson(updated);
  }
}

Future<void> _pump(WidgetTester tester, _VendorApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: VendorManagementPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openVendor(WidgetTester tester) async {
  await tester.tap(find.text('V001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the section is hidden while a vendor is still being created',
      (tester) async {
    final _VendorApi api = _VendorApi();
    await _pump(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'New vendor'));
    await tester.pumpAndSettle();

    expect(find.text('Opening bills'), findsNothing);
    expect(find.text('Add opening bill'), findsNothing);
  });

  testWidgets('lists what the supplier was owed at cutover, and what is '
      'still owed', (tester) async {
    final _VendorApi api = _VendorApi(
      rows: [_vendorJson()],
      bills: const [_openBill, _paidBill],
    );
    await _pump(tester, api);
    await _openVendor(tester);

    expect(find.text('Opening bills'), findsWidgets);
    expect(find.text('OB-00001'), findsOneWidget);
    expect(find.text('OB-00002'), findsOneWidget);
    expect(find.text('INV-OLD-1'), findsOneWidget);
    // The open bill shows the same figure in Amount and Owed (nothing has
    // been paid against it), so this one is not unique on the row.
    expect(find.text('5000.00'), findsWidgets);
    // The paid bill's amount (3000.00) and what is still owed (2000.00) and
    // what has been paid (1000.00) all differ, so each is unique.
    expect(find.text('3000.00'), findsOneWidget);
    expect(find.text('2000.00'), findsOneWidget);
    expect(find.text('1000.00'), findsOneWidget);
    expect(api.openingBillReads, ['v-1']);
  });

  testWidgets('add posts only the fields the write schema declares',
      (tester) async {
    final _VendorApi api = _VendorApi(rows: [_vendorJson()]);
    await _pump(tester, api);
    await _openVendor(tester);

    final Finder addButton =
        find.widgetWithText(OutlinedButton, 'Add opening bill');
    await tester.ensureVisible(addButton);
    await tester.pumpAndSettle();
    await tester.tap(addButton);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Supplier reference'),
      'REF-9',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Amount'),
      '2500.00',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Narration'),
      'Carried over from the old books',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.createdBodies, hasLength(1));
    final Json body = api.createdBodies.single;
    // Bill date is always sent (it is required); due date and posting date
    // were left blank, so they must be absent rather than sent as null --
    // an absent posting date is what makes the server default it to today.
    expect(
      body.keys.toSet(),
      {'bill_date', 'reference_number', 'amount', 'narration'},
    );
    expect(body['reference_number'], 'REF-9');
    expect(body['amount'], '2500.00');
    expect(body['narration'], 'Carried over from the old books');
    expect(body['bill_date'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
  });

  testWidgets('cancel asks for a reason and sends it', (tester) async {
    final _VendorApi api = _VendorApi(
      rows: [_vendorJson()],
      bills: const [_openBill],
    );
    await _pump(tester, api);
    await _openVendor(tester);

    final Finder cancelButton =
        find.byKey(const ValueKey('opening-bill-cancel-ob-1'));
    await tester.ensureVisible(cancelButton);
    await tester.pumpAndSettle();
    await tester.tap(cancelButton);
    await tester.pumpAndSettle();

    expect(find.text('Cancel OB-00001'), findsOneWidget);
    await tester.enterText(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.byType(TextField),
      ),
      'Entered twice',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel bill'));
    await tester.pumpAndSettle();

    expect(api.cancelledBillId, 'ob-1');
    expect(api.cancelReason, 'Entered twice');
  });

  testWidgets('cancel is not offered once anything has been paid',
      (tester) async {
    final _VendorApi api = _VendorApi(
      rows: [_vendorJson()],
      bills: const [_paidBill],
    );
    await _pump(tester, api);
    await _openVendor(tester);

    expect(find.text('OB-00002'), findsOneWidget);
    expect(find.byKey(const ValueKey('opening-bill-cancel-ob-2')),
        findsNothing);
  });
}
