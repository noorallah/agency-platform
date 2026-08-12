// The profile configuration form offers business features as checkboxes. All
// 21 in one flat list is hard to read and hard to reason about, so the picker
// groups them — but it could only group by the leading word of the code, which
// suits permissions (`CUSTOMER_VIEW` under "Customer") and is useless for
// features: `BARCODE` and `IMEI` have no underscore at all, and `BATCH_TRACKING`
// and `EXPIRY_TRACKING` would each land in a bucket of one.
//
// Features carry a category, so the picker now groups by that when the API
// names one and falls back to the old behaviour when it does not.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Row {
  const _Row(this.id, this.code);
  final String id, code;
}

/// Serves a catalogue of options, with or without categories.
class _OptionsApi extends ApiClient {
  _OptionsApi({required this.catalogue})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// code -> category, where a null category models a catalogue without one.
  final Map<String, String?> catalogue;

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    if (path.contains('features') || path.contains('permissions')) {
      return {
        'data': [
          for (final MapEntry<String, String?> entry in catalogue.entries)
            {
              'id': 'id-${entry.key}',
              'code': entry.key,
              if (entry.value != null) 'category': entry.value,
            },
        ],
        'pagination': {'total_records': catalogue.length},
      };
    }
    return {
      'data': const <dynamic>[],
      'pagination': {'total_records': 0},
    };
  }
}

ResourceDefinition<_Row> _definition(String optionsResource) =>
    ResourceDefinition<_Row>(
      title: 'Things',
      resource: 'things',
      showFrame: false,
      headers: const ['Code'],
      cells: (row) => [row.code],
      id: (row) => row.id,
      load: ({int page = 1, String search = '', String? sortBy,
              bool descending = false, Map<String, String?> filters = const {}}) async =>
          const PagedResult<_Row>(items: <_Row>[], total: 0),
      fields: [
        FieldSpec(
          key: 'option_ids',
          label: 'Enabled features',
          optionsResource: optionsResource,
        ),
      ],
      initialValues: (row) => const {},
      payload: (values, isCreating) => const {},
    );

Future<void> _openCreateForm(
  WidgetTester tester,
  _OptionsApi api,
  String optionsResource,
) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ResourceManagementPage<_Row>(
          api: api,
          definition: _definition(optionsResource),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('features are grouped under the categories the API names',
      (tester) async {
    final api = _OptionsApi(catalogue: const {
      'BATCH_TRACKING': 'TRACEABILITY',
      'EXPIRY_TRACKING': 'TRACEABILITY',
      'SERIAL_NUMBER': 'TRACEABILITY',
      'DRUG_LICENSE': 'COMPLIANCE',
      'BARCODE': 'CATALOGUE',
      'IMEI': 'TRACEABILITY',
    });

    await _openCreateForm(tester, api, 'business-framework/features');

    expect(find.text('Traceability'), findsOneWidget);
    expect(find.text('Compliance'), findsOneWidget);
    expect(find.text('Catalogue'), findsOneWidget);
    // The old heuristic would have produced these one-row buckets instead,
    // and dropped BARCODE and IMEI — which have no underscore — into a
    // catch-all. ("General" itself is not asserted on: the form's own first
    // section is called that.)
    for (final String derived in ['Batch', 'Expiry', 'Serial', 'Drug']) {
      expect(find.text(derived), findsNothing);
    }
  });

  testWidgets('a short catalogue is still grouped when categories are named',
      (tester) async {
    // Fewer than the nine that used to be required before grouping kicked in:
    // a named category is a decision, not a crowd-control measure.
    final api = _OptionsApi(catalogue: const {
      'BARCODE': 'CATALOGUE',
      'QR_CODE': 'CATALOGUE',
      'COMMISSION': 'SALES',
    });

    await _openCreateForm(tester, api, 'business-framework/features');

    expect(find.text('Catalogue'), findsOneWidget);
    expect(find.text('Sales'), findsOneWidget);
  });

  testWidgets('a catalogue without categories keeps the old grouping',
      (tester) async {
    final api = _OptionsApi(catalogue: const {
      'CUSTOMER_VIEW': null,
      'CUSTOMER_CREATE': null,
      'CUSTOMER_UPDATE': null,
      'CUSTOMER_DELETE': null,
      'VENDOR_VIEW': null,
      'VENDOR_CREATE': null,
      'VENDOR_UPDATE': null,
      'VENDOR_DELETE': null,
      'PRODUCT_VIEW': null,
    });

    await _openCreateForm(tester, api, 'permissions');

    expect(find.text('Customer'), findsOneWidget);
    expect(find.text('Vendor'), findsOneWidget);
    expect(find.text('Product'), findsOneWidget);
  });
}
