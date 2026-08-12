import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:flutter_test/flutter_test.dart';

/// The assignment selector used to fetch a single page of 100. With 163 seeded
/// permissions that silently hid 63 of them, so those permissions could not be
/// granted to a role through the UI at all.
class _PagedApi extends ApiClient {
  _PagedApi(this.total)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final int total;
  final List<int> requestedPages = [];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async {
    final int page = int.parse(query!['page']!);
    final int pageSize = int.parse(query['page_size']!);
    requestedPages.add(page);
    final int start = (page - 1) * pageSize;
    final int end = (start + pageSize).clamp(0, total);
    return {
      'data': [
        for (int index = start; index < end; index++)
          {'id': 'id-$index', 'code': 'PERMISSION_$index'},
      ],
      'pagination': {'total_records': total},
    };
  }
}

void main() {
  test('every option is loaded when the catalogue exceeds one page', () async {
    final api = _PagedApi(163);
    final List<AssignmentOption> options = await api.options('permissions');

    expect(options.length, 163, reason: '63 were previously unreachable');
    expect(options.first.label, 'PERMISSION_0');
    expect(options.last.label, 'PERMISSION_162');
    expect(api.requestedPages, [1, 2]);
  });

  test('a single-page catalogue costs exactly one request', () async {
    final api = _PagedApi(16);
    final List<AssignmentOption> options = await api.options('roles');

    expect(options.length, 16);
    expect(api.requestedPages, [1]);
  });

  test('an exactly-full page costs no wasted follow-up request', () async {
    final api = _PagedApi(100);
    final List<AssignmentOption> options = await api.options('permissions');

    expect(options.length, 100);
    // The reported total already accounts for everything, so page 2 is never
    // requested even though page 1 came back full.
    expect(api.requestedPages, [1]);
  });

  test('an empty catalogue returns nothing without looping', () async {
    final api = _PagedApi(0);
    expect(await api.options('permissions'), isEmpty);
    expect(api.requestedPages, [1]);
  });

  test('an option carries the category the API names, and null when absent',
      () async {
    final api = _CategorisedApi();
    final List<AssignmentOption> options =
        await api.options('business-framework/features');

    expect(options.first.group, 'TRACEABILITY');
    expect(
      options.last.group,
      isNull,
      reason: 'permissions have no category and must fall back to the code',
    );
  });
}

/// Two rows, one categorised and one not, as a mixed catalogue would be.
class _CategorisedApi extends ApiClient {
  _CategorisedApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async =>
      {
        'data': [
          {
            'id': 'id-1',
            'code': 'BATCH_TRACKING',
            'category': 'TRACEABILITY',
          },
          {'id': 'id-2', 'code': 'CUSTOMER_VIEW'},
        ],
        'pagination': {'total_records': 2},
      };
}
