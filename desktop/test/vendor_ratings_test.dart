// BUY-15: people rate suppliers, on the phase 2 supplier record.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/models/vendor_rating.dart';
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

Json _rating(String id, String by, int score, {String remark = ''}) =>
    <String, dynamic>{
      'id': id,
      'rated_by': by,
      'rated_on': '2026-10-01',
      'quality': score,
      'delivery': score,
      'price': score,
      'communication': score,
      'paperwork': score,
      'remark': remark,
    };

Json _ratingsJson({bool mine = true}) => <String, dynamic>{
      'count': 2,
      'averages': <String, dynamic>{
        'quality': '4.5',
        'delivery': '4.0',
        'price': '3.5',
        'communication': '4.0',
        'paperwork': null,
      },
      'overall': '4.1',
      'ratings': <Json>[
        if (mine) _rating('r-me', 'u-me', 5, remark: 'Always on time'),
        _rating('r-other', 'u-pri', 4),
      ],
      'mine': mine ? _rating('r-me', 'u-me', 5, remark: 'Always on time') : null,
    };

class _Api extends ApiClient {
  _Api({this.empty = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool empty;
  bool hasMine = true;
  Json? putBody;
  int deletes = 0;
  String? refuse;

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
        items: empty
            ? const <Vendor>[]
            : <Vendor>[
          Vendor.fromJson(<String, dynamic>{
            'id': 'v-1',
            'firm_id': 'firm-1',
            'code': 'V001',
            'name': 'Supplier One',
            'display_name': 'Supplier One',
            'status': 'ACTIVE',
          }),
        ],
        total: empty ? 0 : 1,
      );

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      const <GeoPlaceRecord>[];

  @override
  Future<List<FirmMember>> firmMembers() async => const <FirmMember>[
        FirmMember(userId: 'u-pri', fullName: 'Priya Rao'),
      ];

  @override
  Future<VendorRatings> vendorRatings(String vendorId) async =>
      VendorRatings.fromJson(_ratingsJson(mine: hasMine));

  @override
  Future<VendorRating> saveMyVendorRating(String vendorId, Json body) async {
    if (refuse != null) throw ApiException(refuse!);
    putBody = body;
    hasMine = true;
    return VendorRating.fromJson(_rating('r-me', 'u-me', 5));
  }

  @override
  Future<void> withdrawMyVendorRating(String vendorId) async {
    deletes++;
    hasMine = false;
  }
}

Future<void> _open(WidgetTester tester, _Api api, {bool create = false}) async {
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
  if (create) {
    await tester.tap(find.text('New vendor'));
  } else {
    await tester.tap(find.text('V001').first);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Edit').first);
  }
  await tester.pumpAndSettle();
  final Finder rate = find.byKey(const ValueKey('ratings-rate'));
  if (rate.evaluate().isNotEmpty) {
    await tester.ensureVisible(rate);
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('the supplier record shows the summary and the ratings',
      (tester) async {
    await _open(tester, _Api());
    expect(find.text('4.1 of 5 from 2 people'), findsOneWidget);
    expect(find.text('Quality 4.5'), findsOneWidget);
    expect(find.text('Paperwork -'), findsOneWidget);
    expect(find.textContaining('You · 2026-10-01'), findsOneWidget);
    expect(find.textContaining('Priya Rao · 2026-10-01'), findsOneWidget);
    expect(find.text('Always on time'), findsOneWidget);
    expect(find.textContaining("People's opinion"), findsOneWidget);
    expect(find.text('Change my rating'), findsOneWidget);
  });

  testWidgets('rating sends the five scores and the remark', (tester) async {
    final _Api api = _Api()..hasMine = false;
    await _open(tester, api);
    expect(find.text('Rate this supplier'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('ratings-rate')));
    await tester.pumpAndSettle();
    FilledButton save() => tester
        .widget<FilledButton>(find.byKey(const ValueKey('rating-save')));
    expect(save().onPressed, isNull);
    for (final (String key, String _) in vendorRatingCriteria) {
      await tester.tap(find.byKey(ValueKey('rating-$key-4')));
      await tester.pump();
    }
    await tester.enterText(find.byKey(const ValueKey('rating-remark')), 'Good');
    await tester.tap(find.byKey(const ValueKey('rating-save')));
    await tester.pumpAndSettle();
    expect(api.putBody, <String, dynamic>{
      'quality': 4,
      'delivery': 4,
      'price': 4,
      'communication': 4,
      'paperwork': 4,
      'remark': 'Good',
    });
    expect(find.byKey(const ValueKey('rating-save')), findsNothing);
  });

  testWidgets('a refusal keeps the dialog open with the message',
      (tester) async {
    final _Api api = _Api()..refuse = 'Suppliers cannot be rated today.';
    await _open(tester, api);
    await tester.tap(find.byKey(const ValueKey('ratings-rate')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rating-save')));
    await tester.pumpAndSettle();
    expect(find.text('Suppliers cannot be rated today.'), findsOneWidget);
    expect(find.byKey(const ValueKey('rating-save')), findsOneWidget);
    expect(api.putBody, isNull);
  });

  testWidgets('withdrawing asks first, then deletes', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await tester.tap(find.byKey(const ValueKey('ratings-withdraw')));
    await tester.pumpAndSettle();
    expect(find.text('Withdraw my rating?'), findsOneWidget);
    expect(api.deletes, 0);
    await tester.tap(find.text('Withdraw'));
    await tester.pumpAndSettle();
    expect(api.deletes, 1);
    expect(find.text('Rate this supplier'), findsOneWidget);
  });

  testWidgets('a new supplier says to save it first', (tester) async {
    await _open(tester, _Api(empty: true), create: true);
    expect(find.textContaining('Save the supplier first'), findsOneWidget);
    expect(find.byKey(const ValueKey('ratings-rate')), findsNothing);
  });
}
