import 'entities.dart';

/// How far one step of a Settings subject has got, as the server reads it
/// from the firm's own records.
class SettingsStepState {
  const SettingsStepState({
    required this.code,
    required this.state,
    required this.detail,
  });

  static const String done = 'DONE';
  static const String todo = 'TODO';
  static const String optional = 'OPTIONAL';

  /// The step's code, e.g. `rates-and-profiles`.
  final String code;

  /// [done], [todo] or [optional].
  final String state;

  /// What the server found, in words: "5 profiles, from the GST template".
  final String detail;

  bool get isTodo => state == todo;

  factory SettingsStepState.fromJson(Json json) => SettingsStepState(
        code: stringValue(json['code']),
        state: stringValue(json['state']).toUpperCase(),
        detail: stringValue(json['detail']),
      );
}

/// The steps of one Settings subject (Tax) for the firm in hand: one answer
/// from `GET /api/v1/settings-sections/{section}/state`.
class SettingsSectionState {
  const SettingsSectionState({
    required this.section,
    required this.todoCount,
    required this.steps,
  });

  final String section;
  final int todoCount;
  final List<SettingsStepState> steps;

  /// The state of the step with [code], or null when the server named none.
  SettingsStepState? step(String code) {
    for (final SettingsStepState step in steps) {
      if (step.code == code) return step;
    }
    return null;
  }

  factory SettingsSectionState.fromJson(Json json) {
    final dynamic steps = json['steps'];
    final List<SettingsStepState> parsed = [
      if (steps is List)
        for (final dynamic step in steps)
          if (step is Map)
            SettingsStepState.fromJson(Map<String, dynamic>.from(step)),
    ];
    final dynamic count = json['todo_count'];
    return SettingsSectionState(
      section: stringValue(json['section']),
      todoCount: count is num
          ? count.toInt()
          : parsed.where((step) => step.isTodo).length,
      steps: parsed,
    );
  }
}
