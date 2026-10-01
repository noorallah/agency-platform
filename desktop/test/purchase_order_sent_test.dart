// "Sent to supplier" on a purchase order (backlog 69 row 6): the call the
// Mark as sent action makes, and what the order says afterwards.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  String? path;
  Json? body;

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
    this.path = '$method $path';
    this.body = body;
    return {
      'data': <String, dynamic>{
        'id': 'po-1',
        'po_number': 'PO-1',
        'status': 'APPROVED',
        'sent_at': '2026-10-01T10:00:00Z',
        'sent_via': 'WHATSAPP',
        'lines': const <Json>[],
      },
    };
  }
}

void main() {
  test('marking sent posts how, and the order says so', () async {
    final _Api api = _Api();
    final order = await api.markPurchaseOrderSent('po-1', 'WHATSAPP');

    expect(api.path, 'POST /api/v1/purchases/po-1/mark-sent');
    expect(api.body, {'via': 'WHATSAPP'});
    expect(order.sentVia, 'WHATSAPP');
    expect(order.sentAt, isNotEmpty);
    expect(order.isSendable, isTrue);
  });
}
