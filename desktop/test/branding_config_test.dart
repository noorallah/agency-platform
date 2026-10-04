// The package's own branding file: older files still load, the new optional
// fields parse, a malformed strength is skipped, and the shipped file is sound.
//
// A file with no `testWidgets` gets no HTTP overrides, so the api_client
// branding calls talk to a real loopback server here.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/branding/branding_config.dart';
import 'package:agency_desktop/models/agency_branding.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _oldFile() => <String, dynamic>{
      'app_name': 'Ledger Desk',
      'window_name': 'Ledger Desk Window',
      'product_name': 'Ledger Desk',
      'company_name': 'Example Co',
      'logo_path': 'logo.png',
      'splash_path': 'splash.png',
      'version': '2.0.0',
      'support_email': 'support@example.test',
      'support_website': 'https://example.test/support',
      'copyright': '© Example Co',
      'login_background_color': '#F0F0F0',
      'login_accent_color': '#001122',
    };

void main() {
  test('a file without the new keys still loads, with them empty', () {
    final BrandingConfig config = BrandingConfig.fromJson(_oldFile());

    expect(config.supportEmail, 'support@example.test');
    expect(config.tagline, '');
    expect(config.supportPhone, '');
    expect(config.companyLogoPath, '');
    expect(config.strengths, isEmpty);
  });

  test('support email and website may be empty or missing', () {
    final Map<String, dynamic> json = _oldFile()
      ..['support_email'] = ''
      ..remove('support_website');
    final BrandingConfig config = BrandingConfig.fromJson(json);

    expect(config.supportEmail, '');
    expect(config.supportWebsite, '');
  });

  test('the existing required keys are still required', () {
    final Map<String, dynamic> json = _oldFile()..remove('app_name');
    expect(() => BrandingConfig.fromJson(json), throwsFormatException);
  });

  test('the new keys parse and withWindowName carries every one', () {
    final BrandingConfig config = BrandingConfig.fromJson(_oldFile()
      ..['tagline'] = 'Many lights.'
      ..['company_logo_path'] = 'c.png'
      ..['product_logo_path'] = 'p.png'
      ..['support_phone'] = '+91 90000 00000'
      ..['support_whatsapp'] = '+91 90000 00001'
      ..['support_hours'] = 'Mon-Sat'
      ..['strengths'] = <dynamic>[
        <String, dynamic>{
          'kicker': 'TAX',
          'headline': 'Ready when you bill.',
          'text': 'Built from the bills.',
          'points': <dynamic>['one', 'two', 3],
          'examples': <dynamic>[
            <String, dynamic>{'label': 'CGST', 'value': '38,115.00'},
          ],
          'find_it': 'Accounts > GST returns',
        },
      ]);
    final BrandingConfig copy = config.withWindowName('Sign in');

    expect(copy.windowName, 'Sign in');
    expect(copy.tagline, 'Many lights.');
    expect(copy.companyLogoPath, 'c.png');
    expect(copy.productLogoPath, 'p.png');
    expect(copy.supportPhone, '+91 90000 00000');
    expect(copy.supportWhatsapp, '+91 90000 00001');
    expect(copy.supportHours, 'Mon-Sat');
    expect(copy.strengths, hasLength(1));
    final BrandingStrength slide = copy.strengths.single;
    expect(slide.points, <String>['one', 'two']);
    expect(slide.examples.single.value, '38,115.00');
    expect(slide.findIt, 'Accounts > GST returns');
  });

  test('a malformed strength is skipped, not fatal', () {
    final BrandingConfig config = BrandingConfig.fromJson(_oldFile()
      ..['strengths'] = <dynamic>[
        'not an object',
        <String, dynamic>{'kicker': 'NO HEADLINE'},
        <String, dynamic>{'headline': 'Good one'},
      ]);

    expect(config.strengths.map((BrandingStrength s) => s.headline),
        <String>['Good one']);
  });

  test('the shipped branding.json loads with eight strengths', () {
    final dynamic decoded =
        jsonDecode(File('config/branding.json').readAsStringSync());
    final BrandingConfig config =
        BrandingConfig.fromJson(decoded as Map<String, dynamic>);

    expect(config.strengths, hasLength(8));
    for (final BrandingStrength slide in config.strengths) {
      expect(slide.headline, isNotEmpty);
      expect(slide.points, isNotEmpty);
      expect(slide.examples, isNotEmpty);
      expect(slide.findIt, isNotEmpty);
    }
    expect(config.supportEmail, '');
    expect(config.supportWebsite, '');
  });

  group('the branding calls', () {
    late List<String> seen;
    late ApiClient api;

    Future<void> serve(
      int status,
      List<int> body, {
      String type = 'application/json',
    }) async {
      final HttpServer server =
          await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      seen = <String>[];
      server.listen((HttpRequest request) async {
        seen.add('${request.method} ${request.uri.path} '
            'auth=${request.headers.value(HttpHeaders.authorizationHeader)} '
            'if-match=${request.headers.value(HttpHeaders.ifMatchHeader)}');
        await request.drain<void>();
        request.response
          ..statusCode = status
          ..headers.contentType = ContentType.parse(type)
          ..add(body);
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));
      api = ApiClient(
        baseUrl: 'http://127.0.0.1:${server.port}',
        accessToken: () => null,
        refreshAccessToken: () async => false,
      );
    }

    final List<int> brandingJson = utf8.encode(jsonEncode(<String, dynamic>{
      'data': <String, dynamic>{
        'is_set': true,
        'agency_name': 'Sri Lakshmi Agencies',
        'tagline': 'Wholesale',
        'accent_color': '#155EEF',
        'has_logo': true,
        'version': 3,
      },
    }));

    test('getBranding works signed out and parses', () async {
      await serve(200, brandingJson);
      final AgencyBranding branding = await api.getBranding();

      expect(branding.isSet, isTrue);
      expect(branding.agencyName, 'Sri Lakshmi Agencies');
      expect(branding.version, 3);
      expect(seen.single, startsWith('GET /api/v1/branding auth=null'));
    });

    test('getBrandingLogo returns the bytes, and null on 404', () async {
      await serve(200, <int>[1, 2, 3], type: 'image/png');
      expect(await api.getBrandingLogo(), Uint8List.fromList(<int>[1, 2, 3]));

      await serve(404, utf8.encode('{"message":"none"}'));
      expect(await api.getBrandingLogo(), isNull);
    });

    test('writes send If-Match as a quoted version', () async {
      await serve(200, brandingJson);
      await api.updateBranding(
        agencyName: 'A',
        tagline: '',
        accentColor: '',
        expectedVersion: 3,
      );
      await api.uploadBrandingLogo(
          fileName: 'l.png', bytes: <int>[1], expectedVersion: 4);
      await api.deleteBrandingLogo(expectedVersion: 5);
      await api.deleteBrandingLogo();

      expect(seen[0], contains('PUT /api/v1/branding '));
      expect(seen[0], endsWith('if-match="3"'));
      expect(seen[1], contains('PUT /api/v1/branding/logo '));
      expect(seen[1], endsWith('if-match="4"'));
      expect(seen[2], contains('DELETE /api/v1/branding/logo '));
      expect(seen[2], endsWith('if-match="5"'));
      expect(seen[3], endsWith('if-match=null'));
    });
  });
}
