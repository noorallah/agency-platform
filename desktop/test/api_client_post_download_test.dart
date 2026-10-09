// What a POST download puts on the wire (D-UI-90).
//
// `downloadBytes` wrote its body before it set the sign-in and firm headers.
// Writing sends the headers, so setting one afterwards threw: the pick list,
// the loading sheet and a print run each reached the server with no token and
// a body that never ended, and the screen said it could not connect. Every
// widget test overrides `downloadBytes`, so none could see it; these talk to a
// real loopback server and read what actually arrived.
//
// No `testWidgets` here, deliberately: that binding answers every request
// with 400 and makes no real connection.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

class _Arrived {
  String method = '';
  String path = '';
  String? authorization;
  String? firm;
  String? contentType;
  String body = '';
}

Future<(ApiClient, _Arrived)> _start() async {
  final HttpServer server =
      await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final _Arrived arrived = _Arrived();
  server.listen((HttpRequest request) async {
    arrived
      ..method = request.method
      ..path = request.uri.path
      ..authorization = request.headers.value(HttpHeaders.authorizationHeader)
      ..firm = request.headers.value('X-Firm-ID')
      ..contentType = request.headers.contentType?.mimeType
      ..body = await utf8.decoder.bind(request).join();
    request.response
      ..statusCode = 200
      ..headers.contentType = ContentType('application', 'pdf')
      ..add(<int>[37, 80, 68, 70]);
    await request.response.close();
  });
  addTearDown(() => server.close(force: true));
  return (
    ApiClient(
      baseUrl: 'http://127.0.0.1:${server.port}',
      accessToken: () => 'token-1',
      refreshAccessToken: () async => false,
      activeFirmId: () => 'firm-1',
    ),
    arrived,
  );
}

void main() {
  test('a print run arrives signed in, for its firm, with its ids', () async {
    final (ApiClient api, _Arrived arrived) = await _start();

    final List<int> pdf = await api.salesInvoicesPdf(<String>['a', 'b']);

    expect(pdf, <int>[37, 80, 68, 70]);
    expect(arrived.method, 'POST');
    expect(arrived.path, '/api/v1/sales-invoices/bulk-print');
    expect(arrived.authorization, 'Bearer token-1');
    expect(arrived.firm, 'firm-1');
    expect(arrived.contentType, 'application/json');
    expect(jsonDecode(arrived.body), <String, dynamic>{
      'invoice_ids': <String>['a', 'b'],
    });
  });

  test('every download that posts a body arrives whole', () async {
    final (ApiClient api, _Arrived arrived) = await _start();
    final Map<String, Future<List<int>> Function()> calls =
        <String, Future<List<int>> Function()>{
      '/api/v1/delivery-notes/bulk-print': () =>
          api.deliveryChallansPdf(<String>['n']),
      '/api/v1/delivery-notes/pick-list': () =>
          api.deliveryPickListPdf(<String>['n']),
      '/api/v1/delivery-notes/loading-sheet': () =>
          api.deliveryLoadingSheetPdf(<String>['n']),
    };

    for (final MapEntry<String, Future<List<int>> Function()> call
        in calls.entries) {
      await call.value();
      expect(arrived.path, call.key);
      expect(arrived.authorization, 'Bearer token-1', reason: call.key);
      expect(arrived.firm, 'firm-1', reason: call.key);
      expect(jsonDecode(arrived.body), <String, dynamic>{
        'note_ids': <String>['n'],
      });
    }
  });

  test('a download with no body still arrives signed in', () async {
    final (ApiClient api, _Arrived arrived) = await _start();

    await api.salesInvoicePdf('inv-1');

    expect(arrived.method, 'GET');
    expect(arrived.authorization, 'Bearer token-1');
    expect(arrived.firm, 'firm-1');
    expect(arrived.body, isEmpty);
  });
}
