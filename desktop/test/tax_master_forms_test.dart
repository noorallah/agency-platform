// D-DLG-4: the tax masters were one generic dialog of raw text boxes labelled
// by API keys, with a rule's conditions and a profile's components typed as
// JSON, that closed before the save ran and so could not report a refusal.
//
// These cases drive the real forms and read what they send.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/tax_framework.dart';
import 'package:agency_desktop/ui/tax/tax_master_dialogs.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> sent = <Json>[];

  /// When set, the next save is refused with this message.
  String? refuse;

  Future<void> _record(Json data) async {
    final String? message = refuse;
    if (message != null) {
      refuse = null;
      throw ApiException(message, statusCode: 422);
    }
    sent.add(data);
  }

  @override
  Future<PagedResult<TaxSystemRecord>> taxSystems({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? status,
    bool includeDeleted = false,
  }) async =>
      PagedResult<TaxSystemRecord>(
        items: [
          TaxSystemRecord.fromJson(
              {'id': 'sys-gst', 'code': 'GST', 'name': 'GST'}),
          TaxSystemRecord.fromJson(
              {'id': 'sys-vat', 'code': 'VAT', 'name': 'VAT'}),
        ],
        total: 2,
      );

  @override
  Future<PagedResult<TaxComponentRecord>> taxComponents({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
    bool includeDeleted = false,
  }) async =>
      PagedResult<TaxComponentRecord>(
        items: [
          TaxComponentRecord.fromJson(
              {'id': 'cmp-cgst', 'code': 'CGST', 'name': 'Central GST'}),
        ],
        total: 1,
      );

  @override
  Future<PagedResult<TaxProfileRecord>> taxProfiles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    String? taxSystemId,
    bool includeDeleted = false,
  }) async =>
      PagedResult<TaxProfileRecord>(
        items: [
          TaxProfileRecord.fromJson(
              {'id': 'prf-18', 'code': 'GST18', 'name': 'GST 18%'}),
        ],
        total: 1,
      );

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      <GeoPlaceRecord>[
        GeoPlaceRecord.fromJson(
            level, {'id': 'cty-in', 'name': 'India', 'code': 'IN'}),
      ];

  @override
  Future<PagedResult<BusinessProfileRecord>> businessProfiles({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      const PagedResult<BusinessProfileRecord>(items: [], total: 0);

  @override
  Future<TaxComponentRecord> createTaxComponent(Json data) async {
    await _record(data);
    return TaxComponentRecord.fromJson({'id': 'new'});
  }

  @override
  Future<TaxProfileRecord> createTaxProfile(Json data) async {
    await _record(data);
    return TaxProfileRecord.fromJson({'id': 'new'});
  }

  @override
  Future<TaxRuleRecord> createTaxRule(Json data) async {
    await _record(data);
    return TaxRuleRecord.fromJson({'id': 'new'});
  }

  @override
  Future<TaxRuleRecord> updateTaxRule(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    await _record(data);
    return TaxRuleRecord.fromJson({'id': id});
  }

  @override
  Future<TaxCountryMappingRecord> createTaxCountryMapping(Json data) async {
    await _record(data);
    return TaxCountryMappingRecord.fromJson({'id': 'new'});
  }
}

Future<void> _open(
  WidgetTester tester,
  Future<bool?> Function(BuildContext, ApiClient) show,
  _Api api,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => show(context, api),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _type(WidgetTester tester, String label, String text,
    {bool last = false}) async {
  final Finder finder = find.widgetWithText(TextFormField, label);
  await tester.ensureVisible(last ? finder.last : finder.first);
  await tester.enterText(last ? finder.last : finder.first, text);
}

Future<void> _choose(
  WidgetTester tester,
  Finder dropdown,
  String item,
) async {
  await tester.ensureVisible(dropdown);
  await tester.tap(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(find.text(item).last);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a component asks in words, with a drop-down for its system',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxComponentForm(c, a, null), api);

    expect(find.text('Tax system *'), findsOneWidget);
    expect(find.text('Rate (%) *'), findsOneWidget);
    expect(find.text('tax_system_id'), findsNothing,
        reason: 'no API key is shown as a label');
    expect(find.byType(Switch), findsNWidgets(2));

    await _type(tester, 'Code *', 'sgst');
    await _type(tester, 'Name *', 'State GST');
    await _type(tester, 'Rate (%) *', '9');
    await _choose(
      tester,
      find.byKey(const ValueKey('tax-field-tax_system_id')),
      'VAT - VAT',
    );
    await tester.tap(find.byKey(const ValueKey('tax-field-recoverable')));
    await _save(tester);

    expect(find.byType(AlertDialog), findsNothing, reason: 'saved, so closed');
    expect(api.sent, hasLength(1));
    final Json body = api.sent.single;
    expect(body['tax_system_id'], 'sys-vat');
    expect(body['code'], 'SGST');
    expect(body['percentage'], '9');
    expect(body['recoverable'], true);
    expect(body['included_in_price'], false);
    // Only keys the server's TaxComponentWrite declares.
    expect(
      body.keys.toSet().difference({
        'tax_system_id',
        'code',
        'name',
        'label',
        'short_label',
        'display_order',
        'calculation_order',
        'percentage',
        'included_in_price',
        'recoverable',
        'status',
      }),
      isEmpty,
    );
  });

  testWidgets('a refusal keeps the form open, with what was typed',
      (tester) async {
    final _Api api = _Api()..refuse = 'Code SGST already exists.';
    await _open(tester, (c, a) => showTaxComponentForm(c, a, null), api);
    await _type(tester, 'Code *', 'sgst');
    await _type(tester, 'Name *', 'State GST');
    await _type(tester, 'Rate (%) *', '9');
    await _save(tester);

    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('Code SGST already exists.'), findsOneWidget);
    expect(find.text('sgst'), findsOneWidget, reason: 'typing kept');
    expect(api.sent, isEmpty);

    await _save(tester);
    expect(find.byType(AlertDialog), findsNothing);
    expect(api.sent, hasLength(1));
  });

  testWidgets('a missing required field is named and nothing is sent',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxComponentForm(c, a, null), api);
    await _save(tester);
    expect(find.text('Required'), findsWidgets);
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(api.sent, isEmpty);
  });

  testWidgets('a profile builds its components from rows, not JSON',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxProfileForm(c, a, null), api);
    expect(find.textContaining('[]'), findsNothing);

    await _type(tester, 'Code *', 'gst18');
    await _type(tester, 'Name *', 'GST 18%');
    await tester.ensureVisible(find.text('Add component'));
    await tester.tap(find.text('Add component'));
    await tester.pumpAndSettle();
    await _choose(
      tester,
      find.widgetWithText(DropdownButtonFormField<String>, 'Component *'),
      'CGST - Central GST',
    );
    await _type(tester, 'Rate (%) *', '9', last: true);
    await tester.ensureVisible(find.text('Add component'));
    await tester.tap(find.text('Add component'));
    await tester.pumpAndSettle();
    expect(find.text('Component *', skipOffstage: false), findsNWidgets(2));
    await tester.ensureVisible(
      find.byKey(const ValueKey('tax-row-remove-components-1')),
    );
    await tester.tap(find.byKey(const ValueKey('tax-row-remove-components-1')));
    await tester.pumpAndSettle();
    expect(find.text('Component *', skipOffstage: false), findsOneWidget);
    await _save(tester);

    final Json body = api.sent.single;
    expect(body['tax_system_id'], 'sys-gst');
    expect(body['components'], [
      {
        'tax_component_id': 'cmp-cgst',
        'calculation_order': 0,
        'percentage': '9',
        'included_in_price': false,
        'recoverable': false,
      },
    ]);
  });

  testWidgets('a rule builds conditions and actions from rows', (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxRuleForm(c, a, null), api);

    await _type(tester, 'Code *', 'inward');
    await _type(tester, 'Name *', 'Inward');

    await tester.ensureVisible(find.text('Add condition'));
    await tester.tap(find.text('Add condition'));
    await tester.pumpAndSettle();
    await _type(tester, 'Field *', 'transaction_type');
    await _choose(
      tester,
      find.widgetWithText(DropdownButtonFormField<String>, 'Operator *'),
      'Is one of',
    );
    await _type(
      tester,
      'Values (comma separated) *',
      'PURCHASE, PURCHASE_INVOICE',
    );

    await tester.ensureVisible(find.text('Add condition'));
    await tester.tap(find.text('Add condition'));
    await tester.pumpAndSettle();
    await _type(tester, 'Field *', 'invoice_value', last: true);
    await _choose(
      tester,
      find.widgetWithText(DropdownButtonFormField<String>, 'Operator *').last,
      'Greater than',
    );
    await _type(tester, 'Value *', '50000', last: true);

    await tester.ensureVisible(find.text('Add action'));
    await tester.tap(find.text('Add action'));
    await tester.pumpAndSettle();
    await _choose(
      tester,
      find.widgetWithText(DropdownButtonFormField<String>, 'Tax profile *'),
      'GST18 - GST 18%',
    );
    await _save(tester);

    expect(find.byType(AlertDialog), findsNothing);
    final Json body = api.sent.single;
    expect(body['code'], 'INWARD');
    expect(body['priority'], '100');
    expect(body['status'], 'DRAFT');
    expect(body['conditions'], [
      {
        'sequence': 1,
        'field_key': 'transaction_type',
        'operator': 'IN',
        'value_json': {
          'values': ['PURCHASE', 'PURCHASE_INVOICE'],
        },
      },
      {
        'sequence': 2,
        'field_key': 'invoice_value',
        'operator': 'GREATER_THAN',
        'value_number': '50000',
      },
    ]);
    expect(body['actions'], [
      {
        'sequence': 1,
        'action_type': 'APPLY_TAX_PROFILE',
        'target_tax_profile_id': 'prf-18',
      },
    ]);
  });

  testWidgets('a country mapping picks its country and a date', (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxCountryMappingForm(c, a, null), api);
    expect(find.text('Country *'), findsOneWidget);
    expect(find.text('country_id'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('tax-field-effective_from')));
    await tester.pumpAndSettle();
    expect(find.byType(DatePickerDialog), findsOneWidget);
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await _save(tester);

    final Json body = api.sent.single;
    expect(body['country_id'], 'cty-in');
    expect(body['tax_system_id'], 'sys-gst');
    expect(body['is_default'], true);
    expect(body['effective_from'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a rule with many rows scrolls instead of overflowing',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, (c, a) => showTaxRuleForm(c, a, null), api);
    for (int i = 0; i < 8; i++) {
      await tester.ensureVisible(find.text('Add condition'));
      await tester.tap(find.text('Add condition'));
      await tester.pumpAndSettle();
    }
    expect(tester.takeException(), isNull);
    expect(
      tester.getSize(find.byType(AlertDialog)).height,
      lessThanOrEqualTo(768),
    );
  });

  testWidgets('editing a rule keeps its list conditions and sends them back',
      (tester) async {
    final _Api api = _Api();
    final TaxRuleRecord rule = TaxRuleRecord.fromJson({
      'id': 'r-1',
      'code': 'INWARD',
      'name': 'Inward',
      'priority': 30,
      'status': 'ACTIVE',
      'version': 3,
      'conditions': [
        {
          'sequence': 1,
          'field_key': 'transaction_type',
          'operator': 'IN',
          'value_json': {
            'values': ['PURCHASE', 'PURCHASE_RETURN'],
          },
        },
      ],
      'actions': [
        {'sequence': 1, 'action_type': 'INPUT_CREDIT_ALLOWED'},
      ],
    });
    await _open(tester, (c, a) => showTaxRuleForm(c, a, rule), api);
    expect(find.text('PURCHASE, PURCHASE_RETURN'), findsOneWidget);
    await _save(tester);

    final Json body = api.sent.single;
    expect(body['conditions'], [
      {
        'sequence': 1,
        'field_key': 'transaction_type',
        'operator': 'IN',
        'value_json': {
          'values': ['PURCHASE', 'PURCHASE_RETURN'],
        },
      },
    ]);
    expect(body['actions'], [
      {'sequence': 1, 'action_type': 'INPUT_CREDIT_ALLOWED'},
    ]);
  });
}
