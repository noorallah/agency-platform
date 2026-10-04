import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../core/branding/agency_branding_cache.dart';
import '../core/branding/branding_config.dart';
import '../core/design/design_tokens.dart';
import 'sign_in_screen.dart';

/// Below this width only the agency's logo is drawn in the header.
const double agencyHeaderBreakpoint = 820;

/// From this width the tagline sits under the agency's name too; between the
/// two the name and firm alone keep the areas of the menu bar from folding
/// into More.
const double agencyTaglineBreakpoint = 1280;

/// Who the header says the agency is: the server's record when this PC has
/// one cached, else the package's own `branding.json`.
///
/// Read once from [AgencyBrandingCache] -- which sign-in already refreshed --
/// so the header makes no request of its own, on any screen or navigation.
class AgencyIdentity {
  const AgencyIdentity({
    required this.name,
    this.tagline = '',
    this.logo,
    this.logoFile,
  });

  final String name;
  final String tagline;
  final Uint8List? logo;
  final File? logoFile;

  /// The cached agency for [server], or the branding file's name and logo.
  factory AgencyIdentity.resolve({
    required AgencyBrandingCache cache,
    required String server,
    required BrandingConfig branding,
  }) =>
      AgencyIdentity.from(cache.readSync(server), branding);

  /// [cached] when it names an agency, else the branding file's name and logo.
  factory AgencyIdentity.from(
    CachedAgencyBranding? cached,
    BrandingConfig branding,
  ) {
    if (cached != null && cached.branding.agencyName.isNotEmpty) {
      return AgencyIdentity(
        name: cached.branding.agencyName,
        tagline: cached.branding.tagline,
        logo: cached.logo,
        logoFile: branding.logoFile,
      );
    }
    return AgencyIdentity(name: branding.appName, logoFile: branding.logoFile);
  }
}

/// The window title: "Agency > Firm", or the agency alone with no firm.
String windowTitleFor(String agency, String? firm) =>
    firm == null || firm.isEmpty ? agency : '$agency > $firm';

/// The left end of the phase 2 menu bar: the agency's logo, name and tagline,
/// then the selected firm as plain text. Clicking it goes Home. It adds no
/// height -- it lives in the 44 px strip the areas already have.
class AgencyHeader extends StatelessWidget {
  const AgencyHeader({
    super.key,
    required this.agency,
    required this.onHome,
    this.firmName,
  });

  final AgencyIdentity agency;

  /// The selected firm, or null when none is selected.
  final String? firmName;
  final VoidCallback onHome;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final TextTheme text = Theme.of(context).textTheme;
    final double width = MediaQuery.sizeOf(context).width;
    final bool full = width >= agencyHeaderBreakpoint;
    final bool tagline = width >= agencyTaglineBreakpoint &&
        agency.tagline.isNotEmpty;
    final String firm = firmName ?? '';
    final Widget mark = ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 96),
      child: AgencyMark(
        name: agency.name,
        logo: agency.logo,
        logoFile: agency.logoFile,
        size: 28,
      ),
    );
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Tooltip(
        message: full ? 'Home' : agency.name,
        child: InkWell(
          key: const ValueKey('agency-header'),
          onTap: onHome,
          borderRadius: BorderRadius.circular(5),
          hoverColor: colors.chromeActive,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              mark,
              if (full) ...[
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 150),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        agency.name,
                        key: const ValueKey('agency-header-name'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: text.bodyMedium?.copyWith(
                          color: colors.onChrome,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (tagline)
                        Text(
                          agency.tagline,
                          key: const ValueKey('agency-header-tagline'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: text.bodySmall?.copyWith(
                            color: colors.onChromeMuted,
                            fontSize: 11,
                            height: 1.1,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ]),
          ),
        ),
      ),
      if (full && firm.isNotEmpty) ...[
        const SizedBox(width: 4),
        Text('>',
            style: text.bodyMedium?.copyWith(color: colors.onChromeMuted)),
        const SizedBox(width: 6),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 120),
          child: Text(
            firm,
            key: const ValueKey('agency-header-firm'),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: text.bodyMedium?.copyWith(color: colors.onChromeMuted),
          ),
        ),
      ],
    ]);
  }
}

/// Our product at the right end of the status line: its logo (or a small
/// neutral placeholder), name, version and maker. Hover says it in full; a
/// click does nothing -- Help > About is parked.
class ProductOnStatusBar extends StatelessWidget {
  const ProductOnStatusBar({super.key, required this.branding});

  final BrandingConfig branding;

  @override
  Widget build(BuildContext context) {
    final TextStyle style = DefaultTextStyle.of(context).style.copyWith(
          fontSize: Theme.of(context).textTheme.bodySmall?.fontSize,
        );
    final String line =
        '${branding.productName} ${branding.version} by ${branding.companyName}';
    return Tooltip(
      message: '${branding.productName}\nVersion ${branding.version}\n'
          'by ${branding.companyName}',
      child: ConstrainedBox(
        key: const ValueKey('status-product'),
        constraints: const BoxConstraints(maxWidth: 280),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          ProductMark(branding: branding, size: 16),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              line,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
          ),
        ]),
      ),
    );
  }
}
