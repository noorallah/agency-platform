// `refusalMessage` lives beside the client it reads, in `core/api`, so
// that the session controller can show a refused forced password change
// rule by rule without `core` importing `ui` (BL-31.16). Everything under
// `ui/` goes on importing it from here, and from the framework barrel.
export '../../core/api/api_refusal.dart';
