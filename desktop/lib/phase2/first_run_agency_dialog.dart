import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import '../models/agency_branding.dart';
import 'agency_branding_form.dart';

/// First-run setup, step 1, "Your agency" (backlog 71, U5): opened once after
/// the first administrator signs in, while the server holds no branding.
///
/// It is the same [AgencyBrandingForm] as Settings > Platform > Branding,
/// pre-filled with whatever exists. It closes with `true` once saved and with
/// `false` on **Skip for now** (or Escape); the shell remembers a skip so the
/// dialog does not open again by itself. It makes no request until Save.
class FirstRunAgencyDialog extends StatelessWidget {
  const FirstRunAgencyDialog({
    super.key,
    required this.api,
    required this.product,
    required this.initial,
    required this.onChanged,
    this.initialLogo,
    this.pickFile,
  });

  final ApiClient api;
  final BrandingConfig product;
  final AgencyBranding initial;
  final Uint8List? initialLogo;
  final void Function(AgencyBranding saved, Uint8List? logo) onChanged;
  final Future<XFile?> Function()? pickFile;

  /// Shows the dialog; true when saved, false when skipped or dismissed.
  static Future<bool> show(
    BuildContext context, {
    required ApiClient api,
    required BrandingConfig product,
    required AgencyBranding initial,
    required void Function(AgencyBranding saved, Uint8List? logo) onChanged,
    Uint8List? initialLogo,
    Future<XFile?> Function()? pickFile,
  }) async =>
      await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) => FirstRunAgencyDialog(
          api: api,
          product: product,
          initial: initial,
          initialLogo: initialLogo,
          onChanged: onChanged,
          pickFile: pickFile,
        ),
      ) ??
      false;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Size screen = MediaQuery.sizeOf(context);
    return Dialog(
      key: const ValueKey('first-run-agency'),
      insetPadding: const EdgeInsets.all(AppSpacing.lg),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 860,
          maxHeight: screen.height - 2 * AppSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xl,
                AppSpacing.lg,
                AppSpacing.xl,
                0,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Set up your agency',
                      style: theme.textTheme.titleLarge),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'Your name and logo show on the sign-in screen and at the '
                    'top of every screen, on every PC. You can change them '
                    'later in Settings > Platform > Branding.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              height: (screen.height - 160).clamp(260.0, 480.0),
              child: AgencyBrandingForm(
                api: api,
                product: product,
                initial: initial,
                initialLogo: initialLogo,
                onChanged: onChanged,
                pickFile: pickFile,
                secondaryLabel: 'Skip for now',
                onSecondary: () => Navigator.of(context).pop(false),
                onDone: () => Navigator.of(context).pop(true),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
