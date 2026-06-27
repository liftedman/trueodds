import 'package:flutter/material.dart';

/// TrueOdds brand: a distinct teal accent (separate from the per-sport colours),
/// a logo mark, and a launch/splash view.
const Color kBrand = Color(0xFF0EA5A4);

/// The TrueOdds mark + wordmark. Use [compact] for the app bar.
class BrandMark extends StatelessWidget {
  final bool compact;
  const BrandMark({this.compact = false, super.key});

  @override
  Widget build(BuildContext context) {
    final size = compact ? 26.0 : 56.0;
    final text = Theme.of(context).colorScheme.onSurface;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: kBrand,
          borderRadius: BorderRadius.circular(size * .28),
          boxShadow: [BoxShadow(color: kBrand.withOpacity(.35), blurRadius: size * .35)],
        ),
        child: Icon(Icons.insights_rounded, color: Colors.white, size: size * .62),
      ),
      SizedBox(width: compact ? 8 : 12),
      RichText(
        text: TextSpan(
          style: TextStyle(
              fontSize: compact ? 18 : 30,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.5,
              color: text),
          children: const [
            TextSpan(text: 'True'),
            TextSpan(text: 'Odds', style: TextStyle(color: kBrand)),
          ],
        ),
      ),
    ]);
  }
}

/// Branded launch screen shown while the first snapshot loads.
class SplashView extends StatelessWidget {
  const SplashView({super.key});
  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const BrandMark(),
        const SizedBox(height: 14),
        Text('Honest predictions across every sport',
            style: TextStyle(color: muted)),
        const SizedBox(height: 32),
        SizedBox(
          width: 26,
          height: 26,
          child: CircularProgressIndicator(strokeWidth: 2.2, color: kBrand),
        ),
      ]),
    );
  }
}
