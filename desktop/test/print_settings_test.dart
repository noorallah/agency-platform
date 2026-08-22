// How many copies a bill prints is a firm's own preference, and it has to be
// changeable by the person who discovers it is wrong.
//
// The renderer has printed one page set per copy label since it was written,
// and `document_print_templates.copy_labels` has stored them — but nothing in
// the desktop could set one, so every firm printed a single unlabelled copy
// whether that suited it or not. This is the screen that closes that, opened
// from beside the Print button because that is where somebody stands when they
// find out.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/workspace/print_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(List<String> permissions) {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': permissions,
      })))
      .replaceAll('=', '');
  return 'header.$claims.sig';
}

PermissionService _permissions({bool mayManage = true}) => PermissionService()
  ..applyAccessToken(_accessToken(
    mayManage
        ? const <String>['PLATFORM_VIEW', 'PLATFORM_SETTINGS']
        : const <String>['PLATFORM_VIEW'],
  ));

class _TemplateApi extends ApiClient {
  _TemplateApi({this.stored})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// What the firm has saved, or null for a firm that has saved nothing.
  final Json? stored;
  Json? saved;

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
    if (method == 'PUT') {
      saved = Map<String, dynamic>.from(body ?? const <String, dynamic>{});
      return {'data': {...saved!, 'document_type': 'SALES_INVOICE', 'is_customised': true}};
    }
    return {
      'data': stored ??
          <String, dynamic>{
            'document_type': 'SALES_INVOICE',
            'title_text': 'TAX INVOICE',
            'accent_color': '#0B3D6B',
            'show_bank_details': true,
            'show_discount_column': true,
            'show_batch_column': false,
            'show_expiry_column': false,
            'copy_labels': <String>[],
            'page_size': 'A4',
            'margin_mm': '12',
            'is_customised': false,
          },
    };
  }
}

Future<void> _open(
  WidgetTester tester,
  _TemplateApi api, {
  bool mayManage = true,
}) async {
  tester.view.physicalSize = const Size(1400, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PrintSettingsDialog(
        api: api,
        permissions: _permissions(mayManage: mayManage),
        documentType: 'SALES_INVOICE',
        documentLabel: 'sales invoice',
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('the copies are a preference, saved and changeable', () {
    testWidgets('a firm that has saved nothing prints one, and is told so',
        (tester) async {
      await _open(tester, _TemplateApi());

      expect(find.text('One, unlabelled'), findsOneWidget);
      expect(
        find.textContaining('these are the platform defaults'),
        findsOneWidget,
        reason: 'empty boxes with no explanation read as broken',
      );
    });

    testWidgets('choosing three names them without anybody typing',
        (tester) async {
      final _TemplateApi api = _TemplateApi();
      await _open(tester, api);

      await tester.tap(find.byType(DropdownButton<int>).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('3, labelled').last);
      await tester.pumpAndSettle();

      expect(find.text('ORIGINAL FOR RECIPIENT'), findsOneWidget);
      expect(find.text('DUPLICATE FOR TRANSPORTER'), findsOneWidget);
      expect(find.text('TRIPLICATE FOR SUPPLIER'), findsOneWidget);
    });

    testWidgets('the choice is what gets saved', (tester) async {
      final _TemplateApi api = _TemplateApi();
      await _open(tester, api);

      await tester.tap(find.byType(DropdownButton<int>).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('2, labelled').last);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved, isNotNull);
      expect(api.saved!['copy_labels'], <String>[
        'ORIGINAL FOR RECIPIENT',
        'DUPLICATE FOR TRANSPORTER',
      ]);
    });

    testWidgets('a saved preference comes back on the next open',
        (tester) async {
      final _TemplateApi api = _TemplateApi(stored: <String, dynamic>{
        'document_type': 'SALES_INVOICE',
        'title_text': 'TAX INVOICE',
        'accent_color': '#0B3D6B',
        'show_bank_details': true,
        'show_discount_column': false,
        'show_batch_column': false,
        'show_expiry_column': false,
        'copy_labels': <String>['ORIGINAL', 'OFFICE COPY'],
        'page_size': 'A5',
        'margin_mm': '10',
        'is_customised': true,
      });
      await _open(tester, api);

      expect(find.text('2, labelled'), findsOneWidget);
      expect(find.text('ORIGINAL'), findsOneWidget);
      expect(find.text('OFFICE COPY'), findsOneWidget,
          reason: 'a firm names its copies whatever it likes');
      expect(find.textContaining('platform defaults'), findsNothing);
    });

    testWidgets('a copy left unnamed is not sent as a blank banner',
        (tester) async {
      final _TemplateApi api = _TemplateApi();
      await _open(tester, api);

      await tester.tap(find.byType(DropdownButton<int>).first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('2, labelled').last);
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'DUPLICATE FOR TRANSPORTER'), '   ');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(api.saved!['copy_labels'], <String>['ORIGINAL FOR RECIPIENT']);
    });
  });

  group('who may change it', () {
    testWidgets('somebody who may only view can read but not save',
        (tester) async {
      await _open(tester, _TemplateApi(), mayManage: false);

      final FilledButton save = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Save'),
      );
      expect(save.onPressed, isNull);
      final DropdownButton<int> copies =
          tester.widget<DropdownButton<int>>(find.byType(DropdownButton<int>).first);
      expect(copies.onChanged, isNull);
    });
  });
}
