// MST-3: the warning before a duplicate customer or supplier is saved, and the
// dialog that folds one into another.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/workspace/party_merge.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeApi extends ApiClient {
  _FakeApi({this.candidates = const [], this.checkFails = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> candidates;
  final bool checkFails;
  final List<Json> created = [];
  Json? customerMergeBody;
  Json? vendorMergeBody;
  String? customerSurvivor;
  String? vendorSurvivor;

  @override
  Future<List<Json>> customerDuplicates({
    String name = '',
    String phone = '',
    String gstin = '',
    String? excluding,
  }) async {
    if (checkFails) throw const ApiException('down');
    return candidates;
  }

  @override
  Future<Customer> createCustomer(Json data) async {
    created.add(data);
    return Customer.fromJson(<String, dynamic>{
      'id': 'c-new',
      'version': 1,
      'firm_id': 'firm-1',
      'code': 'CUS-9',
      'customer_type': 'BUSINESS',
      'name': data['name'],
      'display_name': data['name'],
      'currency_code': 'INR',
      'status': 'ACTIVE',
      'addresses': <dynamic>[],
      'contacts': <dynamic>[],
    });
  }

  @override
  Future<Json> mergeCustomer(String survivorId, Json body) async {
    customerSurvivor = survivorId;
    customerMergeBody = body;
    return {'rows_moved': 7};
  }

  @override
  Future<Json> mergeVendor(String survivorId, Json body) async {
    vendorSurvivor = survivorId;
    vendorMergeBody = body;
    return {'rows_moved': 3};
  }
}

const Json _dup = <String, dynamic>{
  'id': 'c-old',
  'code': 'CUS-1',
  'name': 'Anand Agencies',
  'reasons': <String>['same GSTIN'],
};

Future<void> _pumpSaveButton(WidgetTester tester, _FakeApi api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            key: const ValueKey<String>('go'),
            onPressed: () => saveUnlessDuplicate<Customer?>(
              context,
              noun: 'customer',
              check: () => api.customerDuplicates(name: 'Anand Agencies'),
              save: () => api.createCustomer({'name': 'Anand Agencies'}),
            ).catchError((Object _) => null),
            child: const Text('go'),
          ),
        ),
      ),
    ),
  );
}

Future<void> _pumpMerge(
  WidgetTester tester, {
  required Future<Json> Function(Json body) merge,
  String noun = 'customer',
}) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            key: const ValueKey<String>('open'),
            onPressed: () => showPartyMergeDialog(
              context,
              noun: noun,
              survivorId: 'c-keep',
              survivorLabel: 'Anand Agencies',
              likely: () async => [_dup],
              search: (text) async => const [],
              merge: merge,
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.byKey(const ValueKey<String>('open')));
  await tester.pumpAndSettle();
}

Future<void> _pickAndConfirm(WidgetTester tester) async {
  expect(find.byKey(const ValueKey<String>('merge-warning')), findsOneWidget);
  await tester.tap(find.byKey(const ValueKey<String>('merge-option-c-old')));
  await tester.enterText(
    find.byKey(const ValueKey<String>('merge-reason')),
    'entered twice',
  );
  await tester.pump();
  await tester.tap(find.byKey(const ValueKey<String>('merge-confirm')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a duplicate shows the warning and Save anyway still saves',
      (tester) async {
    final _FakeApi api = _FakeApi(candidates: const [_dup]);
    await _pumpSaveButton(tester, api);
    await tester.tap(find.byKey(const ValueKey<String>('go')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('duplicate-warning')),
      findsOneWidget,
    );
    expect(find.textContaining('CUS-1'), findsOneWidget);
    expect(find.textContaining('same GSTIN'), findsOneWidget);
    expect(api.created, isEmpty);

    await tester
        .tap(find.byKey(const ValueKey<String>('duplicate-save-anyway')));
    await tester.pumpAndSettle();
    expect(api.created, hasLength(1));
  });

  testWidgets('Cancel at the warning saves nothing', (tester) async {
    final _FakeApi api = _FakeApi(candidates: const [_dup]);
    await _pumpSaveButton(tester, api);
    await tester.tap(find.byKey(const ValueKey<String>('go')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey<String>('duplicate-cancel')));
    await tester.pumpAndSettle();
    expect(api.created, isEmpty);
  });

  testWidgets('without candidates it saves directly', (tester) async {
    final _FakeApi api = _FakeApi();
    await _pumpSaveButton(tester, api);
    await tester.tap(find.byKey(const ValueKey<String>('go')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('duplicate-warning')),
      findsNothing,
    );
    expect(api.created, hasLength(1));
  });

  testWidgets('a failed check does not block the save', (tester) async {
    final _FakeApi api = _FakeApi(checkFails: true);
    await _pumpSaveButton(tester, api);
    await tester.tap(find.byKey(const ValueKey<String>('go')));
    await tester.pumpAndSettle();
    expect(api.created, hasLength(1));
  });

  testWidgets('the merge dialog sends duplicate_id and reason to mergeCustomer',
      (tester) async {
    final _FakeApi api = _FakeApi();
    await _pumpMerge(
      tester,
      merge: (body) => api.mergeCustomer('c-keep', body),
    );
    // Nothing can be sent before a duplicate and a reason are chosen.
    expect(
      tester
          .widget<FilledButton>(
            find.byKey(const ValueKey<String>('merge-confirm')),
          )
          .onPressed,
      isNull,
    );
    await _pickAndConfirm(tester);

    expect(api.customerSurvivor, 'c-keep');
    expect(
      api.customerMergeBody,
      {'duplicate_id': 'c-old', 'reason': 'entered twice'},
    );
    expect(
      find.byKey(const ValueKey<String>('party-merge-dialog')),
      findsNothing,
    );
  });

  testWidgets('the supplier merge calls mergeVendor', (tester) async {
    final _FakeApi api = _FakeApi();
    await _pumpMerge(
      tester,
      noun: 'supplier',
      merge: (body) => api.mergeVendor('v-keep', body),
    );
    await _pickAndConfirm(tester);

    expect(api.vendorSurvivor, 'v-keep');
    expect(
      api.vendorMergeBody,
      {'duplicate_id': 'c-old', 'reason': 'entered twice'},
    );
    expect(mergeSummary({'rows_moved': 3}), 'Merged: 3 rows moved');
  });

  testWidgets('a refusal keeps the dialog open with the server message',
      (tester) async {
    await _pumpMerge(
      tester,
      merge: (body) async =>
          throw const ApiException('A financial year is locked.'),
    );
    await _pickAndConfirm(tester);
    expect(
      find.byKey(const ValueKey<String>('party-merge-dialog')),
      findsOneWidget,
    );
    expect(find.text('A financial year is locked.'), findsOneWidget);
  });
}
