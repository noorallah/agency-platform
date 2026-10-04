import 'dart:async';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import '../models/agency_branding.dart';
import 'sign_in_screen.dart';

/// The largest logo the server accepts.
const int agencyLogoLimitBytes = 1024 * 1024;

/// The agency's branding form, shared by Settings > Platform > Branding and the
/// first-run "Set up your agency" dialog (backlog 71, U5 and U7).
///
/// One implementation, so the two cannot disagree about what is asked or how it
/// is checked: the agency's name (required), its tagline and its logo, with a
/// live preview of the sign-in card and the header strip beside them. The
/// accent colour is not asked -- the stored value goes back unchanged.
///
/// **The form runs its own save** and stays open with the server's message on a
/// refusal, every typed value kept (D-DLG-1). A save is `PUT /branding`, then
/// -- only when the logo changed -- `PUT /branding/logo` or `DELETE
/// /branding/logo`, each carrying the version the last answer gave as
/// `If-Match`. It makes no read of its own: the answers carry the data.
class AgencyBrandingForm extends StatefulWidget {
  const AgencyBrandingForm({
    super.key,
    required this.api,
    required this.product,
    required this.initial,
    required this.onChanged,
    this.initialLogo,
    this.onDone,
    this.pickFile,
    this.secondaryLabel,
    this.onSecondary,
    this.saveLabel = 'Save',
  });

  final ApiClient api;

  /// Our product's identity, shown read-only: set by the installer.
  final BrandingConfig product;

  /// What the server holds now (or [AgencyBranding.notSet]) and its logo.
  final AgencyBranding initial;
  final Uint8List? initialLogo;

  /// The server accepted a change, wholly or in part: the caller updates its
  /// cache and header from the answer and the logo bytes held here.
  final void Function(AgencyBranding saved, Uint8List? logo) onChanged;

  /// Everything was saved; a dialog closes here, a page just says so.
  final VoidCallback? onDone;

  /// Replaced in tests; the platform's file chooser by default.
  final Future<XFile?> Function()? pickFile;

  /// An extra button beside Save ("Skip for now"), disabled while saving.
  final String? secondaryLabel;
  final VoidCallback? onSecondary;
  final String saveLabel;

  @override
  State<AgencyBrandingForm> createState() => _AgencyBrandingFormState();
}

enum _LogoChange { none, replaced, removed }

class _AgencyBrandingFormState extends State<AgencyBrandingForm> {
  late final TextEditingController _name =
      TextEditingController(text: widget.initial.agencyName);
  late final TextEditingController _tagline =
      TextEditingController(text: widget.initial.tagline);

  late AgencyBranding _baseline = widget.initial;
  late Uint8List? _baselineLogo = widget.initialLogo;
  late Uint8List? _logo = widget.initialLogo;
  _LogoChange _change = _LogoChange.none;
  String _logoFileName = 'logo.png';

  bool _saving = false;
  bool _saved = false;
  String? _nameError;
  String? _logoError;
  String? _saveError;

  @override
  void dispose() {
    _name.dispose();
    _tagline.dispose();
    super.dispose();
  }

  bool get _hasLogo => _logo != null;

  Future<XFile?> _choose() => (widget.pickFile ??
      () => openFile(acceptedTypeGroups: const <XTypeGroup>[
            XTypeGroup(
              label: 'Pictures',
              extensions: <String>['png', 'jpg', 'jpeg'],
            ),
          ]))();

  Future<void> _pickLogo() async {
    final XFile? file = await _choose();
    if (file == null || !mounted) return;
    final String lower = file.name.toLowerCase();
    if (!(lower.endsWith('.png') ||
        lower.endsWith('.jpg') ||
        lower.endsWith('.jpeg'))) {
      setState(() => _logoError = 'Choose a PNG or JPG picture.');
      return;
    }
    final Uint8List bytes = await file.readAsBytes();
    if (!mounted) return;
    if (bytes.length > agencyLogoLimitBytes) {
      final String size = (bytes.length / agencyLogoLimitBytes)
          .toStringAsFixed(1);
      setState(() => _logoError =
          'That picture is $size MB; the limit is 1 MB. Choose a smaller one.');
      return;
    }
    setState(() {
      _logo = bytes;
      _logoFileName = file.name;
      _change = _LogoChange.replaced;
      _logoError = null;
      _saved = false;
    });
  }

  void _removeLogo() {
    setState(() {
      _logo = null;
      // Removing a logo that was only just chosen needs no call at all.
      _change = _baselineLogo == null && !_baseline.hasLogo
          ? _LogoChange.none
          : _LogoChange.removed;
      _logoError = null;
      _saved = false;
    });
  }

  Future<void> _save() async {
    if (_saving) return;
    final String name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _nameError = 'Give your agency a name.');
      return;
    }
    setState(() {
      _nameError = null;
      _saveError = null;
      _saving = true;
      _saved = false;
    });
    int? version = _baseline.version;
    AgencyBranding latest = _baseline;
    try {
      latest = await widget.api.updateBranding(
        agencyName: name,
        tagline: _tagline.text.trim(),
        accentColor: _baseline.accentColor,
        expectedVersion: version,
      );
      version = latest.version;
      // The name and tagline are on the server now; say so before the logo,
      // so a refused logo leaves the header right and the version current.
      _baseline = latest;
      widget.onChanged(latest, _baselineLogo);
      if (_change == _LogoChange.replaced) {
        latest = await widget.api.uploadBrandingLogo(
          fileName: _logoFileName,
          bytes: _logo!,
          expectedVersion: version,
        );
      } else if (_change == _LogoChange.removed && latest.hasLogo) {
        latest = await widget.api.deleteBrandingLogo(expectedVersion: version);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saveError = error.message;
      });
      return;
    }
    _baseline = latest;
    _baselineLogo = _logo;
    _change = _LogoChange.none;
    widget.onChanged(latest, _logo);
    if (!mounted) return;
    setState(() {
      _saving = false;
      _saved = true;
    });
    widget.onDone?.call();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: LayoutBuilder(builder: (context, constraints) {
            final Widget fields = _fields(context);
            final Widget preview = _preview(context);
            if (constraints.maxWidth < 640) {
              return SingleChildScrollView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    fields,
                    const SizedBox(height: AppSpacing.lg),
                    preview,
                  ],
                ),
              );
            }
            return SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 3, child: fields),
                  const SizedBox(width: AppSpacing.xl),
                  Expanded(flex: 2, child: preview),
                ],
              ),
            );
          }),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.md,
          ),
          child: Row(children: [
            if (_saveError != null)
              Expanded(child: _banner(context, _saveError!))
            else if (_saved)
              Expanded(
                child: Row(children: [
                  Icon(Icons.check_circle_outline,
                      size: 18, color: context.semanticColors.success),
                  const SizedBox(width: AppSpacing.sm),
                  Text('Saved.', key: const ValueKey('branding-saved')),
                ]),
              )
            else
              const Spacer(),
            const SizedBox(width: AppSpacing.md),
            if (widget.secondaryLabel != null) ...[
              TextButton(
                key: const ValueKey('branding-secondary'),
                onPressed: _saving ? null : widget.onSecondary,
                child: Text(widget.secondaryLabel!),
              ),
              const SizedBox(width: AppSpacing.sm),
            ],
            FilledButton(
              key: const ValueKey('branding-save'),
              onPressed: _saving ? null : () => unawaited(_save()),
              child: _saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(widget.saveLabel),
            ),
          ]),
        ),
      ],
    );
  }

  Widget _banner(BuildContext context, String message) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Container(
      key: const ValueKey<String>('save-error-banner'),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: colors.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Icon(Icons.error_outline, color: colors.onErrorContainer, size: 18),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            message,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: colors.onErrorContainer),
          ),
        ),
      ]),
    );
  }

  Widget _fields(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? muted = theme.textTheme.bodySmall
        ?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: const ValueKey('branding-name'),
          controller: _name,
          maxLength: 150,
          enabled: !_saving,
          onChanged: (_) => setState(() {
            _nameError = null;
            _saved = false;
          }),
          decoration: InputDecoration(
            labelText: 'Agency name *',
            counterText: '',
            errorText: _nameError,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        TextField(
          key: const ValueKey('branding-tagline'),
          controller: _tagline,
          maxLength: 200,
          enabled: !_saving,
          onChanged: (_) => setState(() => _saved = false),
          decoration: const InputDecoration(
            labelText: 'Tagline (optional)',
            counterText: '',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        Text('Logo', style: theme.textTheme.labelLarge),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.md,
          runSpacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 56,
              height: 56,
              child: Center(
                child: AgencyMark(
                  key: const ValueKey('branding-logo-preview'),
                  name: _name.text,
                  logo: _logo,
                  logoFile: null,
                  size: 48,
                ),
              ),
            ),
            OutlinedButton.icon(
              key: const ValueKey('branding-choose-logo'),
              onPressed: _saving ? null : () => unawaited(_pickLogo()),
              icon: const Icon(Icons.image_outlined, size: 18),
              label: Text(_hasLogo ? 'Change logo' : 'Choose logo'),
            ),
            if (_hasLogo)
              TextButton(
                key: const ValueKey('branding-remove-logo'),
                onPressed: _saving ? null : _removeLogo,
                child: const Text('Remove logo'),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        if (_logoError != null)
          Text(
            _logoError!,
            key: const ValueKey('branding-logo-error'),
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.error),
          )
        else
          Text(
            'A PNG or JPG up to 1 MB. Without one, the initials of the name '
            'show instead.',
            style: muted,
          ),
        const SizedBox(height: AppSpacing.xl),
        _productBlock(context),
      ],
    );
  }

  Widget _productBlock(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Container(
      key: const ValueKey('branding-product'),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppSpacing.xs),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(children: [
        ProductMark(branding: widget.product, size: 32),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${widget.product.productName} by ${widget.product.companyName}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              Text(
                'Our product and company. Set by the installer; changed only '
                'by an update.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ]),
    );
  }

  Widget _preview(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final AppSemanticColors colors = context.semanticColors;
    final String typed = _name.text.trim();
    final String name = typed.isEmpty ? 'Your agency' : typed;
    final String tagline = _tagline.text.trim();
    final TextStyle? muted = theme.textTheme.bodySmall
        ?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Column(
      key: const ValueKey('branding-preview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Preview', style: theme.textTheme.labelLarge),
        const SizedBox(height: AppSpacing.sm),
        Text('Sign-in screen', style: muted),
        const SizedBox(height: AppSpacing.xs),
        Container(
          padding: const EdgeInsets.all(AppSpacing.lg),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(AppSpacing.sm),
            border: Border.all(color: theme.colorScheme.outlineVariant),
          ),
          child: Row(children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 120),
              child: AgencyMark(
                key: const ValueKey('branding-preview-signin-mark'),
                name: name,
                logo: _logo,
                logoFile: null,
                size: 44,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    key: const ValueKey('branding-preview-signin-name'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  if (tagline.isNotEmpty)
                    Text(
                      tagline,
                      key: const ValueKey('branding-preview-signin-tagline'),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: muted,
                    ),
                ],
              ),
            ),
          ]),
        ),
        const SizedBox(height: AppSpacing.lg),
        Text('Top of every screen', style: muted),
        const SizedBox(height: AppSpacing.xs),
        Container(
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          decoration: BoxDecoration(
            color: colors.chrome,
            borderRadius: BorderRadius.circular(AppSpacing.xs),
          ),
          child: Row(children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 96),
              child: AgencyMark(
                key: const ValueKey('branding-preview-header-mark'),
                name: name,
                logo: _logo,
                logoFile: null,
                size: 28,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    key: const ValueKey('branding-preview-header-name'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: colors.onChrome,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (tagline.isNotEmpty)
                    Text(
                      tagline,
                      key: const ValueKey('branding-preview-header-tagline'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colors.onChromeMuted,
                        fontSize: 11,
                        height: 1.1,
                      ),
                    ),
                ],
              ),
            ),
          ]),
        ),
      ],
    );
  }
}
