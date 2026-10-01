// Proof of delivery on the delivery note (backlog 67 row 6): the dialog that
// records it, the "Not yet delivered" filter on the list, and the action that
// is offered only for goods that left.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_note_management_page.dart';
import 'package:agency_desktop/ui/delivery_notes/delivery_proof_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _note(
  int n,
  String status, {
  bool delivered = false,
}) =>
    <String, dynamic>{
      'id': 'dn-$n',
      'delivery_note_number': 'DN-000$n',
      'customer_name': 'Customer $n',
      'delivery_date': '2026-08-10',
      'status': status,
      'grand_total': '1000.00',
      'is_delivered': delivered,
      'delivered_at': delivered ? '2026-08-12T09:30:00Z' : null,
      'delivery_received_by': delivered ? 'S. Rao' : null,
      'delivery_remarks': null,
      'version': 2,
    };

class _ProofApi extends ApiClient {
  _ProofApi({this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuse;

  /// Every list query the page asked for.
  final List<Map<String, String>> listQueries = <Map<String, String>>[];
  final List<Json> proofBodies = <Json>[];
  final List<String> proofPaths = <String>[];

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
    if (method == 'POST' && path.endsWith('/proof-of-delivery')) {
      if (refuse != null) throw ApiException(refuse!, statusCode: 409);
      proofPaths.add(path);
      proofBodies.add(body!);
      return <String, dynamic>{'data': _note(1, 'COMPLETED', delivered: true)};
    }
    if (method == 'GET' && path == '/api/v1/delivery-notes/summary') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'total': 3,
          'dispatched': 2,
          'draft': 1,
          'awaiting_delivery_proof': 4,
        },
      };
    }
    if (method == 'GET' && path == '/api/v1/delivery-notes') {
      listQueries.add(<String, String>{...?query});
      final List<Json> rows = <Json>[
        _note(1, 'DISPATCHED'),
        _note(2, 'DRAFT'),
        _note(3, 'COMPLETED', delivered: true),
      ];
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

Future<void> _openDialog(
  WidgetTester tester,
  _ProofApi api, {
  Future<XFile?> Function()? pickFile,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<Json>(
            context: context,
            builder: (_) => DeliveryProofDialog(
              api: api,
              noteId: 'dn-1',
              noteNumber: 'DN-0001',
              now: DateTime(2026, 8, 14, 16, 45),
              pickFile: pickFile,
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

Future<void> _pumpPage(WidgetTester tester, _ProofApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory dir = Directory.systemTemp.createTempSync('proof-test');
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: DeliveryNoteManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: dir),
          permissions: _permissions(const <String>['SALES_VIEW', 'SALES_UPDATE']),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('the dialog', () {
    testWidgets('posts when, who, a remark and the signed copy',
        (tester) async {
      final _ProofApi api = _ProofApi();
      await _openDialog(
        tester,
        api,
        pickFile: () async => XFile('signed-copy.pdf'),
      );
      await tester.enterText(
          find.byKey(const ValueKey('proof-received-by')), 'S. Rao');
      await tester.enterText(
          find.byKey(const ValueKey('proof-remarks')), 'Left at the gate');
      await tester.tap(find.byKey(const ValueKey('proof-attach')));
      await tester.pumpAndSettle();
      expect(find.text('signed-copy.pdf'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('proof-save')));
      await tester.pumpAndSettle();

      expect(api.proofPaths.single,
          '/api/v1/delivery-notes/dn-1/proof-of-delivery');
      final Json body = api.proofBodies.single;
      expect(DateTime.parse(body['delivered_at'] as String).isUtc, isTrue);
      expect(DateTime.parse(body['delivered_at'] as String),
          DateTime(2026, 8, 14, 16, 45).toUtc());
      expect(body['received_by'], 'S. Rao');
      expect(body['remarks'], 'Left at the gate');
      expect(body['attachment'], <String, dynamic>{
        'file_name': 'signed-copy.pdf',
        'mime_type': 'application/pdf',
        'file_path': 'signed-copy.pdf',
      });
      // Closed on success.
      expect(find.byType(DeliveryProofDialog), findsNothing);
    });

    testWidgets('with no remark or file those are null', (tester) async {
      final _ProofApi api = _ProofApi();
      await _openDialog(tester, api);
      await tester.enterText(
          find.byKey(const ValueKey('proof-received-by')), 'Gate staff');
      await tester.tap(find.byKey(const ValueKey('proof-save')));
      await tester.pumpAndSettle();
      final Json body = api.proofBodies.single;
      expect(body['remarks'], isNull);
      expect(body['attachment'], isNull);
    });

    testWidgets('says who received it before anything is sent',
        (tester) async {
      final _ProofApi api = _ProofApi();
      await _openDialog(tester, api);
      await tester.tap(find.byKey(const ValueKey('proof-save')));
      await tester.pumpAndSettle();
      expect(api.proofBodies, isEmpty);
      expect(find.text('Say who received the goods.'), findsOneWidget);
    });

    testWidgets('a refusal keeps the dialog open with what was typed',
        (tester) async {
      final _ProofApi api = _ProofApi(refuse: 'Only goods that left.');
      await _openDialog(tester, api);
      await tester.enterText(
          find.byKey(const ValueKey('proof-received-by')), 'S. Rao');
      await tester.tap(find.byKey(const ValueKey('proof-save')));
      await tester.pumpAndSettle();
      expect(find.byType(DeliveryProofDialog), findsOneWidget);
      expect(find.text('Only goods that left.'), findsOneWidget);
      expect(find.text('S. Rao'), findsOneWidget);
    });
  });

  group('the list', () {
    testWidgets('"Not yet delivered" counts, filters and clears',
        (tester) async {
      final _ProofApi api = _ProofApi();
      await _pumpPage(tester, api);
      expect(api.listQueries.last.containsKey('awaiting_delivery_proof'),
          isFalse);
      expect(find.text('Not yet delivered'), findsOneWidget);
      expect(find.text('4'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('view-counter-awaiting-proof')));
      await tester.pumpAndSettle();
      expect(api.listQueries.last['awaiting_delivery_proof'], 'true');

      await tester.tap(find.byKey(const ValueKey('view-counter-awaiting-proof')));
      await tester.pumpAndSettle();
      expect(api.listQueries.last.containsKey('awaiting_delivery_proof'),
          isFalse);
    });

    testWidgets('the list stays overflow-free at 1366 by 768', (tester) async {
      final _ProofApi api = _ProofApi();
      await _pumpPage(tester, api);
      tester.view.physicalSize = const Size(1366, 768);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Not yet delivered'), findsOneWidget);
    });

    testWidgets('a delivered note carries a Delivered badge', (tester) async {
      final _ProofApi api = _ProofApi();
      await _pumpPage(tester, api);
      expect(find.textContaining('Delivered 12-08-2026'), findsOneWidget);
    });

    testWidgets('proof is offered for goods that left, not for a draft',
        (tester) async {
      final _ProofApi api = _ProofApi();
      await _pumpPage(tester, api);
      // The selection bar offers only what the selected note can do now.
      final Finder action =
          find.byKey(const ValueKey('selection-proof-of-delivery'));
      expect(action, findsNothing, reason: 'nothing selected');

      // A tap waits out a possible double-tap before it selects.
      await tester.tap(find.text('DN-0002'));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(action, findsNothing, reason: 'a draft has not left');

      await tester.tap(find.text('DN-0001'));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(action, findsOneWidget);

      await tester.tap(action);
      await tester.pumpAndSettle();
      expect(find.byType(DeliveryProofDialog), findsOneWidget);
    });
  });
}
