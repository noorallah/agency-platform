// A document lifecycle action always carries a JSON body.
//
// Cancel and close on five document types declare a body (with an optional
// reason), and the shared action call sent none, so the server answered 422
// "body: Field required" to Cancel and Close on sales orders, sales invoices,
// delivery notes, purchase invoices and purchase returns. Found at plan item
// 9.9 on 2026-09-13 cancelling a draft order.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

class _RecordingApi extends ApiClient {
  _RecordingApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<({String method, String path, Json? body})> calls = [];

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
    calls.add((method: method, path: path, body: body));
    return <String, dynamic>{'success': true, 'data': <String, dynamic>{}};
  }
}

void main() {
  test('cancel and close send a JSON object, not an empty request', () async {
    final _RecordingApi api = _RecordingApi();
    for (final String resource in const [
      'sales-orders',
      'sales-invoices',
      'delivery-notes',
      'purchase-invoices',
      'purchase-returns',
    ]) {
      await api.documentAction(resource, 'doc-1', '/cancel');
      await api.documentAction(resource, 'doc-1', 'close');
    }
    expect(api.calls, hasLength(10));
    for (final call in api.calls) {
      expect(call.method, 'POST');
      expect(call.body, isNotNull, reason: '${call.path} was sent no body');
    }
    expect(api.calls.first.path, '/api/v1/sales-orders/doc-1/cancel');
    expect(api.calls[1].path, '/api/v1/sales-orders/doc-1/close');
  });
}
