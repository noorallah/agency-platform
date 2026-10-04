import 'dart:async';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import '../models/agency_branding.dart';
import '../ui/workspace/desktop_framework.dart';
import 'agency_branding_form.dart';

/// Settings > Platform > Branding in the phase 2 app (backlog 71, U7): the
/// agency's name, tagline and logo, with a live preview, and our own product
/// shown read-only.
///
/// **Server calls: one `GET /branding`, and one `GET /branding/logo` only when
/// the record has a logo** -- on opening, never again (no polling, none on
/// navigation). A save is the form's own writes; [onChanged] hands the answer
/// to the shell, which refreshes the cache and the header without a read.
///
/// Offered to whoever holds `PLATFORM_SETTINGS`; the server stays the gate.
class BrandingPage extends StatefulWidget {
  const BrandingPage({
    super.key,
    required this.api,
    required this.product,
    required this.onChanged,
    this.pickFile,
  });

  final ApiClient api;
  final BrandingConfig product;
  final void Function(AgencyBranding saved, Uint8List? logo) onChanged;
  final Future<XFile?> Function()? pickFile;

  @override
  State<BrandingPage> createState() => _BrandingPageState();
}

class _BrandingPageState extends State<BrandingPage> {
  AgencyBranding? _branding;
  Uint8List? _logo;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final AgencyBranding branding = await widget.api.getBranding();
      Uint8List? logo;
      if (branding.isSet && branding.hasLogo) {
        logo = await widget.api.getBrandingLogo();
      }
      if (!mounted) return;
      setState(() {
        _branding = branding;
        _logo = logo;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final AgencyBranding? branding = _branding;
    final Widget body;
    if (branding != null) {
      body = AgencyBrandingForm(
        key: ValueKey('branding-form-${branding.version}'),
        api: widget.api,
        product: widget.product,
        initial: branding,
        initialLogo: _logo,
        onChanged: widget.onChanged,
        pickFile: widget.pickFile,
      );
    } else if (_error != null) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _error!,
              key: const ValueKey('branding-load-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              key: const ValueKey('branding-retry'),
              onPressed: () => unawaited(_load()),
              child: const Text('Try again'),
            ),
          ],
        ),
      );
    } else {
      body = const Center(child: CircularProgressIndicator());
    }
    return phase2Frame(
      title: 'Branding',
      description: "The agency's name, tagline and logo, shown on sign-in "
          'and at the top of every screen on every PC.',
      child: body,
    );
  }
}
