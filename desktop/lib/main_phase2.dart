import 'main.dart';

/// The phase 2 app: the same application with the phase 2 frame
/// (`lib/phase2/`, docs/UI_PHASE_2_DESIGN.md).
///
/// Its own entry point by the owner's choice (2026-09-26), so phase 1 stays
/// exactly as it is while phase 2 is built beside it. Run it with
///
///     flutter run -d windows -t lib/main_phase2.dart
///
/// When phase 2 has every screen, it becomes `main.dart` and phase 1's frame
/// is deleted.
Future<void> main() => startAgencyApp(phase2: true);
