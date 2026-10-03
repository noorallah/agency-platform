/// How the screens write a date: the signed-in person's own format, chosen in
/// My preferences (backlog 73) and kept on the server as `date_format`.
///
/// One holder rather than a parameter threaded through every screen, because
/// [documentDate] is called from some forty places that have no session to
/// ask. Set when the preferences arrive at sign-in and again when they are
/// saved; the screens built after that write the new format.
abstract final class DisplayDates {
  /// The Indian convention, and how the phase 2 screens wrote every date
  /// before there was a choice.
  static const String defaultFormat = 'dd-MM-yyyy';

  /// What the server accepts, as My preferences offers it.
  static const List<String> formats = [
    'dd-MM-yyyy',
    'dd/MM/yyyy',
    'yyyy-MM-dd',
    'MM/dd/yyyy',
  ];

  static String _format = defaultFormat;

  /// The format in use.
  static String get format => _format;

  /// Use [format] from now on; anything unknown falls back to the default.
  static void use(String? format) =>
      _format = formats.contains(format) ? format! : defaultFormat;

  /// [day] in [format], or in the one in use.
  static String write(DateTime day, [String? format]) {
    final String dd = day.day.toString().padLeft(2, '0');
    final String mm = day.month.toString().padLeft(2, '0');
    final String yyyy = day.year.toString().padLeft(4, '0');
    return switch (format ?? _format) {
      'dd/MM/yyyy' => '$dd/$mm/$yyyy',
      'yyyy-MM-dd' => '$yyyy-$mm-$dd',
      'MM/dd/yyyy' => '$mm/$dd/$yyyy',
      _ => '$dd-$mm-$yyyy',
    };
  }
}
