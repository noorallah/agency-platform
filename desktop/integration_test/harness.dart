import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/main_phase2.dart' as app;
import 'package:agency_desktop/phase2/indian_format.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Who the flows sign in as; override with `--dart-define=IT_EMAIL=...`.
const String itEmail = String.fromEnvironment('IT_EMAIL',
    defaultValue: 'whole01.admin@agency.local');
const String itPassword =
    String.fromEnvironment('IT_PASSWORD', defaultValue: 'DemoAdmin@12345');

/// Every piece of text on screen, in paint order.
///
/// A screenshot of this app comes out blank on Windows, so this is how a flow
/// says what it was looking at when it gave up.
List<String> textOnScreen(WidgetTester tester) => <String>[
      for (final Text text in tester.widgetList<Text>(find.byType(Text)))
        if ((text.data ?? text.textSpan?.toPlainText() ?? '').trim().isNotEmpty)
          (text.data ?? text.textSpan!.toPlainText()).trim(),
      // Notifications are SelectableText, which is not a Text.
      for (final SelectableText text
          in tester.widgetList<SelectableText>(find.byType(SelectableText)))
        if ((text.data ?? text.textSpan?.toPlainText() ?? '').trim().isNotEmpty)
          (text.data ?? text.textSpan!.toPlainText()).trim(),
    ];

/// Pump real frames until [finder] matches, or fail naming what was on screen.
///
/// `pumpAndSettle` cannot be used against a live server: a spinner never
/// settles, and a request takes as long as it takes.
Future<void> pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
  String? waitingFor,
}) async {
  final DateTime deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('Timed out waiting for ${waitingFor ?? finder.describeMatch(Plurality.one)}.'
      '\nOn screen: ${textOnScreen(tester).take(80).join(' | ')}');
}

/// The field whose label reads [label].
Finder fieldLabelled(String label) => find.ancestor(
      of: find.text(label),
      matching: find.byType(TextField),
    );

/// Start the real phase 2 app and sign in through its own sign-in screen.
Future<void> startAndSignIn(WidgetTester tester) async {
  // The app installs its own error handlers at startup. The test framework
  // reports failures through these two and checks at the end that they are the
  // ones it set, so they go back as soon as the app is up.
  final FlutterExceptionHandler? reportError = FlutterError.onError;
  final ErrorWidgetBuilder errorWidget = ErrorWidget.builder;
  await app.main();
  await pumpUntil(tester, find.text('Username / Email'),
      waitingFor: 'the sign-in screen');
  FlutterError.onError = reportError;
  ErrorWidget.builder = errorWidget;
  await tester.enterText(fieldLabelled('Username / Email').first, itEmail);
  await tester.enterText(fieldLabelled('Password').first, itPassword);
  await tester.pump();
  await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
  await pumpUntil(tester, find.textContaining('Search or jump to'),
      waitingFor: 'the signed-in frame');
}

// ---------------------------------------------------------------------------
// Helpers for the module flows (selling, buying, pricing).
// ---------------------------------------------------------------------------

/// A decoded JSON object.
typedef Json = Map<String, dynamic>;

/// Pump real frames for [duration] without waiting for anything to settle.
Future<void> pumpFor(WidgetTester tester, Duration duration) async {
  final DateTime end = DateTime.now().add(duration);
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// A flow that records what went wrong and carries on, so one broken screen
/// does not hide the screens after it.
///
/// Every line it prints starts `FLOW:`, which is what `run.sh` greps for.
class FlowLog {
  FlowLog(this.name);

  final String name;
  final List<String> failures = <String>[];
  int passed = 0;
  int skipped = 0;

  /// What the screen showed in the step running now; a step sets it so the
  /// result line says what was seen, not only that nothing threw.
  String? saw;

  /// A finding that is an observation, not a failure.
  void info(String label, String detail) {
    // ignore: avoid_print
    print('FLOW: INFO [$name] $label :: ${detail.replaceAll('\n', ' | ')}');
  }

  /// Run [body] as one named step; a thrown error is recorded, not rethrown.
  /// A label that starts with a case id (`SC-SO-014 ...`) is what
  /// `docs/qa/tools/stamp_screen_results.py` files the result under.
  Future<bool> step(String label, Future<void> Function() body) async {
    saw = null;
    try {
      await body();
      passed++;
      // ignore: avoid_print
      print('FLOW: PASS [$name] $label'
          '${saw == null ? '' : ' :: ${saw!.replaceAll('\n', ' | ')}'}');
      return true;
    } catch (error) {
      final String text = '$error'.replaceAll('\n', ' | ');
      failures.add('$label: $text');
      // ignore: avoid_print
      print('FLOW: FAIL [$name] $label: '
          '${text.length > 1800 ? text.substring(0, 1800) : text}');
      return false;
    }
  }

  /// Record a step that could not be tried because an earlier one failed.
  void skip(String label, String because) {
    skipped++;
    // ignore: avoid_print
    print('FLOW: SKIP [$name] $label (because $because)');
  }

  /// Record something the screen got wrong without stopping the step.
  void defect(String label, String detail) {
    failures.add('$label: $detail');
    // ignore: avoid_print
    print('FLOW: DEFECT [$name] $label: $detail');
  }

  /// The closing line, and the failure the test framework reports.
  void finish() {
    // ignore: avoid_print
    print('FLOW: SUMMARY [$name] passed $passed, failed ${failures.length}, '
        'not run $skipped');
    if (failures.isNotEmpty) {
      fail('${failures.length} step(s) failed in $name:\n'
          '${failures.join('\n')}');
    }
  }
}

/// Open a screen from the menu bar: the area's drop-down, then the item. The
/// drop-down shows every screen of its area (since 2026-10-09); a build that
/// still has the "All ... screens" link is given a click on it.
Future<void> openMenu(WidgetTester tester, String area, String path) async {
  await closeOpenEditor(tester);
  await tester.tap(find.byKey(ValueKey<String>('menu-area-$area')));
  await pumpFor(tester, const Duration(milliseconds: 600));
  final Finder item = find.byKey(ValueKey<String>('menu-item-$path'));
  final Finder showAll = find.byKey(const ValueKey<String>('menu-show-all'));
  if (item.evaluate().isEmpty && showAll.evaluate().isNotEmpty) {
    await tester.tap(showAll);
    await pumpFor(tester, const Duration(milliseconds: 600));
  }
  await pumpUntil(tester, item, waitingFor: 'menu item $path');
  await tester.tap(item.first);
  await pumpFor(tester, const Duration(seconds: 3));
}

/// Open a Settings card (a set-up list such as Price Lists).
Future<void> openSetUp(WidgetTester tester, String path,
    {String section = 'Pricing'}) async {
  await closeOpenEditor(tester);
  await tester.tap(find.byKey(const ValueKey<String>('menu-area-settings')));
  final Finder tile = find.byKey(ValueKey<String>('setup-section-$section'));
  await pumpUntil(tester, tile, waitingFor: 'settings section $section');
  await tester.tap(tile);
  await pumpFor(tester, const Duration(milliseconds: 500));
  final Finder card = find.byKey(ValueKey<String>('setup-card-$path'));
  await pumpUntil(tester, card, waitingFor: 'settings card $path');
  await tester.ensureVisible(card);
  await pumpFor(tester, const Duration(milliseconds: 300));
  await tester.tap(card);
  await pumpFor(tester, const Duration(seconds: 3));
}

/// Tap the widget with [key], waiting for it to appear first.
Future<void> tapKey(WidgetTester tester, String key,
    {Duration timeout = const Duration(seconds: 20)}) async {
  final Finder finder = find.byKey(ValueKey<String>(key));
  await pumpUntil(tester, finder, timeout: timeout, waitingFor: 'key $key');
  await tester.ensureVisible(finder.first);
  await tester.tap(finder.first);
  await pumpFor(tester, const Duration(milliseconds: 500));
}

/// Tap the button whose label is exactly [label] (a toolbar step, a dialog
/// button), waiting for it to be enabled.
Future<void> tapButton(WidgetTester tester, String label,
    {Duration timeout = const Duration(seconds: 20)}) async {
  final Finder finder = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate(
        (Widget w) => w is ButtonStyleButton && w.onPressed != null),
  );
  await pumpUntil(tester, finder,
      timeout: timeout, waitingFor: 'enabled button "$label"');
  await tester.ensureVisible(finder.first);
  await tester.tap(finder.first);
  await pumpFor(tester, const Duration(milliseconds: 800));
}

/// Tap the first enabled button whose label starts with [prefix] ("New ").
Future<void> tapButtonStarting(WidgetTester tester, String prefix,
    {Duration timeout = const Duration(seconds: 20)}) async {
  final Finder finder = find.ancestor(
    of: find.byWidgetPredicate((Widget w) =>
        w is Text && (w.data ?? '').startsWith(prefix)),
    matching: find.byWidgetPredicate(
        (Widget w) => w is ButtonStyleButton && w.onPressed != null),
  );
  await pumpUntil(tester, finder,
      timeout: timeout, waitingFor: 'enabled button "$prefix..."');
  // The last match is the one in front: a dialog sits over its screen.
  await tester.tap(finder.last);
  await pumpFor(tester, const Duration(milliseconds: 800));
}

/// Type [text] into the box whose key is a string starting with [prefix]
/// (keys that carry a record id the flow cannot know).
Future<void> typeInKeyed(
    WidgetTester tester, String prefix, String text) async {
  final Finder box = find.byWidgetPredicate((Widget w) {
    final Key? key = w.key;
    return key is ValueKey<String> && key.value.startsWith(prefix);
  });
  await pumpUntil(tester, box, waitingFor: 'a box keyed $prefix...');
  final Finder inner = find.descendant(
      of: box.first, matching: find.byType(EditableText));
  await tester.enterText(
      inner.evaluate().isEmpty ? box.first : inner.first, text);
  await pumpFor(tester, const Duration(milliseconds: 500));
}

/// Pick [label] from the picker with [key]: open it, tap the entry.
Future<void> chooseIn(WidgetTester tester, String key, String label) async {
  final Finder keyed = find.byKey(ValueKey<String>(key));
  if (keyed.evaluate().isNotEmpty) {
    await tester.ensureVisible(keyed.first);
    await pumpFor(tester, const Duration(milliseconds: 300));
  }
  await tapKey(tester, key);
  await pumpFor(tester, const Duration(milliseconds: 500));
  final Finder entry = find.textContaining(label);
  await pumpUntil(tester, entry, waitingFor: 'picker entry "$label"');
  await tester.tap(entry.last);
  await pumpFor(tester, const Duration(milliseconds: 600));
}

/// Type [text] into the [index]th text box inside the widget with [key]
/// (box 0 of a line is the product picker, 1 the quantity).
Future<void> typeIn(
    WidgetTester tester, String key, int index, String text) async {
  final Finder boxes = find.descendant(
      of: find.byKey(ValueKey<String>(key)),
      matching: find.byType(EditableText));
  await pumpUntil(tester, boxes, waitingFor: 'text boxes in $key');
  await tester.enterText(boxes.at(index), text);
  await pumpFor(tester, const Duration(milliseconds: 500));
}

/// Type into the form field labelled [label] (dialogs with plain labels).
Future<void> typeLabelled(
    WidgetTester tester, String label, String text) async {
  final Finder box = fieldLabelled(label);
  await pumpUntil(tester, box, waitingFor: 'field "$label"');
  await tester.ensureVisible(box.first);
  await tester.enterText(box.first, text);
  await pumpFor(tester, const Duration(milliseconds: 300));
}

/// True when some text on screen contains [needle].
bool screenHas(WidgetTester tester, String needle) =>
    textOnScreen(tester).any((String t) => t.contains(needle));

/// True when the screen shows [value] the way the phase 2 screens write an
/// amount (Indian grouping, two decimals).
bool screenShowsAmount(WidgetTester tester, double value) =>
    screenHas(tester, indianAmount(value, full: true));

/// Wait for a snackbar, and return its text.
Future<String> waitForNotice(WidgetTester tester,
    {Duration timeout = const Duration(seconds: 15)}) async {
  final Finder bar = find.byType(SnackBar);
  await pumpUntil(tester, bar, timeout: timeout, waitingFor: 'a notification');
  return <String>[
    for (final Text t in tester.widgetList<Text>(
        find.descendant(of: bar, matching: find.byType(Text))))
      t.data ?? '',
    for (final SelectableText t in tester.widgetList<SelectableText>(
        find.descendant(of: bar, matching: find.byType(SelectableText))))
      t.data ?? '',
  ].join(' ');
}

/// Confirm a dialog that is asking something, by its filled button.
Future<bool> confirmIfAsked(WidgetTester tester) async {
  await pumpFor(tester, const Duration(milliseconds: 700));
  final Finder dialog = find.byType(Dialog);
  if (dialog.evaluate().isEmpty) return false;
  final Finder yes = find.descendant(
      of: dialog,
      matching: find.byWidgetPredicate(
          (Widget w) => w is FilledButton && w.onPressed != null));
  if (yes.evaluate().isEmpty) return false;
  await tester.tap(yes.last);
  await pumpFor(tester, const Duration(seconds: 2));
  return true;
}

/// Tap the grid row showing [text] (a document number).
Future<void> selectRow(WidgetTester tester, String text) async {
  // A grid shows the number alone; the list view puts it first in a line.
  final Finder row = find.textContaining(text);
  await pumpUntil(tester, row, waitingFor: 'a row showing $text');
  await tester.tap(row.first);
  await pumpFor(tester, const Duration(milliseconds: 600));
}

/// A decimal out of whatever the server sent.
double num2(dynamic value) => double.tryParse('$value') ?? double.nan;

/// Compare two money figures to the paisa.
bool sameMoney(double a, double b) => (a - b).abs() < 0.005;

/// The server's own record of what the flows raise: a second opinion on the
/// figures the screen shows, read over HTTP as the same user.
class Server {
  Server._(this._client, this._token, this.firmId);

  final HttpClient _client;
  final String _token;
  final String firmId;

  static const String _base = String.fromEnvironment('API_BASE_URL',
      defaultValue: 'http://127.0.0.1:8000');

  /// The backend sometimes drops a connection ("Connection closed before
  /// full header was received"); a read that is only a second opinion is
  /// tried again rather than failing the step it is checking.
  static Future<Json> _send(HttpClient client, String method, String path,
      {Json? body, String? token, String? firm}) async {
    for (int attempt = 1;; attempt++) {
      try {
        return await _sendOnce(client, method, path,
            body: body, token: token, firm: firm);
      } on HttpException {
        if (attempt >= 3 || method != 'GET') rethrow;
        await Future<void>.delayed(const Duration(seconds: 1));
      }
    }
  }

  static Future<Json> _sendOnce(HttpClient client, String method, String path,
      {Json? body, String? token, String? firm}) async {
    final HttpClientRequest request =
        await client.openUrl(method, Uri.parse('$_base$path'));
    request.headers.contentType = ContentType.json;
    if (token != null) request.headers.set('Authorization', 'Bearer $token');
    if (firm != null) request.headers.set('X-Firm-ID', firm);
    if (body != null) request.write(jsonEncode(body));
    final HttpClientResponse response = await request.close();
    final String text = await utf8.decoder.bind(response).join();
    if (response.statusCode >= 400) {
      throw StateError('$method $path answered ${response.statusCode}: $text');
    }
    return jsonDecode(text) as Json;
  }

  /// Sign in as [itEmail] and find the firm the account belongs to.
  static Future<Server> connect() => connectAs(itEmail, itPassword);

  /// Sign in as somebody else, over HTTP only (no screen). With [firm] given
  /// the account need not belong to one (a platform administrator).
  static Future<Server> connectAs(String email, String password,
      {String? firm}) async {
    final HttpClient client = HttpClient();
    final Json login = await _send(client, 'POST', '/api/v1/auth/login',
        body: <String, dynamic>{'email': email, 'password': password});
    if (firm != null) {
      return Server._(client,
          (login['data'] as Map<String, dynamic>)['access_token'] as String, firm);
    }
    final String token =
        (login['data'] as Map<String, dynamic>)['access_token'] as String;
    final Json firms =
        await _send(client, 'GET', '/api/v1/me/firms', token: token);
    final dynamic data = firms['data'];
    final List<dynamic> list = data is List
        ? data
        : (data as Map<String, dynamic>)['firms'] as List<dynamic>;
    return Server._(
        client, token, (list.first as Map<String, dynamic>)['id'] as String);
  }

  /// GET [path] and return the `data` member.
  Future<dynamic> get(String path) async =>
      (await _send(_client, 'GET', path, token: _token, firm: firmId))['data'];

  /// The newest record of [collection] (by creation time), or null.
  Future<Json?> newest(String collection) async {
    final dynamic rows = await get('/api/v1/$collection?page_size=100');
    final List<Json> list = <Json>[
      for (final dynamic row in rows as List<dynamic>) row as Json,
    ];
    if (list.isEmpty) return null;
    String stamp(Json r) {
      if (r['created_at'] != null) return '${r['created_at']}';
      for (final MapEntry<String, dynamic> e in r.entries) {
        if (e.key.endsWith('_number') && e.value != null) return '${e.value}';
      }
      return '';
    }

    list.sort((Json a, Json b) => stamp(b).compareTo(stamp(a)));
    return list.first;
  }

  /// Send a write ([method] POST or PUT) and return the `data` member.
  Future<dynamic> write(String method, String path, Json body) async =>
      (await _send(_client, method, path,
          body: body, token: _token, firm: firmId))['data'];

  /// The total a list reports in its pagination block.
  Future<int> total(String path) async {
    final Json body = await _send(_client, 'GET',
        '$path${path.contains('?') ? '&' : '?'}page_size=1',
        token: _token, firm: firmId);
    final dynamic pagination = body['pagination'];
    if (pagination is Map && pagination['total_records'] != null) {
      return (pagination['total_records'] as num).toInt();
    }
    return (body['data'] as List<dynamic>).length;
  }

  /// A write that may be refused: returns the status and body instead of
  /// throwing (a 409 or 403 is what a case is looking for).
  Future<({int status, String text})> attempt(
      String method, String path, Json? body) async {
    final HttpClientRequest request =
        await _client.openUrl(method, Uri.parse('$_base$path'));
    request.headers.contentType = ContentType.json;
    request.headers.set('Authorization', 'Bearer $_token');
    request.headers.set('X-Firm-ID', firmId);
    if (body != null) request.write(jsonEncode(body));
    final HttpClientResponse response = await request.close();
    final String text = await utf8.decoder.bind(response).join();
    return (status: response.statusCode, text: text);
  }

  /// One record read back whole.
  Future<Json> one(String collection, String id) async =>
      (await get('/api/v1/$collection/$id')) as Json;
}

/// The subtotal, tax and grand total of a document as the server holds it.
({double sub, double tax, double grand}) figuresOf(Json doc) => (
      sub: num2(
          doc['subtotal'] ?? doc['taxable_amount'] ?? doc['taxable_total']),
      tax: num2(doc['tax_total'] ?? doc['tax_amount']),
      grand: num2(doc['grand_total'] ?? doc['total_amount']),
    );

/// The document's own arithmetic: a grand total that is not the taxable value
/// plus the tax, or a quantity that is not the one typed, is a defect in the
/// server or the screen. Returns what is wrong, or null.
String? arithmeticFault(Json doc, {double? quantity}) {
  final ({double sub, double tax, double grand}) f = figuresOf(doc);
  final List<String> faults = <String>[];
  if (f.grand.isNaN || f.sub.isNaN) {
    return 'no figures on the record (keys: ${doc.keys.take(40).join(',')})';
  }
  final double tax = f.tax.isNaN ? 0 : f.tax;
  final double freight = num2(doc['freight_amount'] ?? 0);
  final double round = num2(doc['round_off'] ?? doc['rounding_amount'] ?? 0);
  final double expected = f.sub + tax + (freight.isNaN ? 0 : freight);
  if ((f.grand - expected).abs() > 1.0 + (round.isNaN ? 0 : round.abs())) {
    faults.add('grand ${f.grand} is not taxable ${f.sub} + tax $tax '
        '(+ freight $freight)');
  }
  final dynamic lines = doc['lines'];
  if (quantity != null && lines is List && lines.isNotEmpty) {
    final Json first = lines.first as Json;
    final double got =
        num2(first['quantity'] ?? first['ordered_quantity']);
    if (got != quantity) faults.add('line 1 quantity is $got, typed $quantity');
  }
  return faults.isEmpty ? null : faults.join('; ');
}

/// Whether the screen shows [value] as an amount, in either spelling the
/// grids use (grouped, or plain with two decimals).
bool screenShowsMoney(WidgetTester tester, double value) =>
    screenShowsAmount(tester, value) ||
    screenHas(tester, value.toStringAsFixed(2));

/// Whether the screen shows [status] (any capitalisation) as a whole text.
bool screenShowsStatus(WidgetTester tester, String status) =>
    textOnScreen(tester)
        .any((String t) => t.toLowerCase() == status.toLowerCase());

/// A document's own number, whatever its collection calls the field.
String docNumber(Json doc) {
  for (final String key in const <String>[
    'quotation_number',
    'order_number',
    'delivery_note_number',
    'grn_number',
    'invoice_number',
    'receipt_number',
    'goods_receipt_number',
    'return_number',
    'document_number',
  ]) {
    final dynamic value = doc[key];
    if (value != null && '$value'.isNotEmpty) return '$value';
  }
  for (final MapEntry<String, dynamic> entry in doc.entries) {
    if (entry.key.endsWith('_number') &&
        !entry.key.startsWith('supplier') &&
        !entry.key.startsWith('customer') &&
        '${entry.value}'.isNotEmpty) {
      return '${entry.value}';
    }
  }
  throw StateError('no document number on the record '
      '(keys: ${doc.keys.take(40).join(',')})');
}

/// Tap the toolbar's New button, however the screen words it ("New",
/// "New Order", "+ New").
Future<void> tapNew(WidgetTester tester) async {
  final Finder finder = find.ancestor(
    of: find.byWidgetPredicate((Widget w) =>
        w is Text &&
        ((w.data ?? '').startsWith('New') || (w.data ?? '') == '+ New')),
    matching: find.byWidgetPredicate(
        (Widget w) => w is ButtonStyleButton && w.onPressed != null),
  );
  await pumpUntil(tester, finder, waitingFor: 'a New button');
  await tester.tap(finder.first);
  await pumpFor(tester, const Duration(seconds: 2));
}

/// Pick [label] from the picker whose key starts with [prefix].
Future<void> chooseInKeyed(
    WidgetTester tester, String prefix, String label) async {
  final Finder picker = find.byWidgetPredicate((Widget w) {
    final Key? key = w.key;
    return key is ValueKey<String> && key.value.startsWith(prefix);
  });
  await pumpUntil(tester, picker, waitingFor: 'a picker keyed $prefix...');
  await tester.tap(picker.first);
  await pumpFor(tester, const Duration(milliseconds: 500));
  final Finder entry = find.textContaining(label);
  await pumpUntil(tester, entry, waitingFor: 'picker entry "$label"');
  await tester.tap(entry.last);
  await pumpFor(tester, const Duration(milliseconds: 600));
}

/// Tap an editor's save button and wait for the editor to close. A save the
/// server or the form refused leaves the editor open, so that is a failure,
/// and the messages on screen say why.
Future<void> saveEditor(WidgetTester tester, String key) async {
  await tapKey(tester, key);
  final Finder button = find.byKey(ValueKey<String>(key));
  final DateTime deadline = DateTime.now().add(const Duration(seconds: 12));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (button.evaluate().isEmpty) {
      await pumpFor(tester, const Duration(seconds: 1));
      return;
    }
  }
  final RegExp complaint = RegExp(
      r'must|need|choose|required|select|pick|add a|cannot|can.t|not |refus|invalid|enter',
      caseSensitive: false);
  throw StateError('the editor stayed open after $key. Messages: '
      '${textOnScreen(tester).where(complaint.hasMatch).take(12).join(' | ')}'
      ' Screen: ${textOnScreen(tester).skip(14).take(90).join(' | ')}');
}

/// Leave a document editor a failed step left open, so the next step starts
/// from a list rather than from somebody else's form.
Future<void> closeOpenEditor(WidgetTester tester) async {
  for (int i = 0; i < 3; i++) {
    final Finder dialog = find.byType(Dialog);
    if (dialog.evaluate().isEmpty) break;
    final Finder sure =
        find.descendant(of: dialog.last, matching: find.text('Discard and close'));
    if (sure.evaluate().isNotEmpty) {
      await tester.tap(sure.first);
      await pumpFor(tester, const Duration(milliseconds: 700));
      continue;
    }
    Finder out = find.descendant(of: dialog.last, matching: find.text('Cancel'));
    if (out.evaluate().isEmpty) {
      out = find.descendant(of: dialog.last, matching: find.text('Close'));
    }
    if (out.evaluate().isEmpty) break;
    await tester.tap(out.first);
    await pumpFor(tester, const Duration(milliseconds: 700));
  }
  final Finder band = find.byKey(const ValueKey<String>('document-band-actions'));
  if (band.evaluate().isEmpty) return;
  final Finder cancel =
      find.descendant(of: band, matching: find.text('Cancel'));
  if (cancel.evaluate().isEmpty) return;
  await tester.tap(cancel.first);
  await pumpFor(tester, const Duration(milliseconds: 800));
  final Finder discard = find.byKey(const ValueKey<String>('document-discard'));
  if (discard.evaluate().isNotEmpty) {
    await tester.tap(discard.first);
    await pumpFor(tester, const Duration(seconds: 1));
  }
}

/// What a snackbar or an open dialog on screen is saying right now.
String noticeText(WidgetTester tester) {
  final Finder holder = find.byWidgetPredicate(
      (Widget w) => w is SnackBar || w is Dialog);
  return <String>[
    for (final Text t in tester
        .widgetList<Text>(find.descendant(of: holder, matching: find.byType(Text))))
      t.data ?? '',
    for (final SelectableText t in tester.widgetList<SelectableText>(
        find.descendant(of: holder, matching: find.byType(SelectableText))))
      t.data ?? t.textSpan?.toPlainText() ?? '',
  ].where((String t) => t.isNotEmpty).join(' | ');
}
