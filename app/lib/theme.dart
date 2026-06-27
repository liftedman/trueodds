import 'package:flutter/material.dart';

/// Design tokens from docs/DESIGN.md — neutral light/dark base + per-sport accent.
class AppTheme {
  // Per-sport accent colors (your palette).
  static const Map<String, Color> sportAccent = {
    'clubs': Color(0xFF16B364),   // green
    'wc': Color(0xFF2E7DF6),      // blue
    'nba': Color(0xFF8B5CF6),     // purple
    'tennis': Color(0xFF84CC16),  // lime
    'cl': Color(0xFFE5484D),      // red
  };

  // Confidence colors.
  static const Color hi = Color(0xFF16B364);
  static const Color med = Color(0xFFE8A33D);
  static const Color lo = Color(0xFF8B95A4);

  static ThemeData _base(Brightness b, Color accent) {
    final dark = b == Brightness.dark;
    final ground = dark ? const Color(0xFF0E1117) : const Color(0xFFF6F7F9);
    final surface = dark ? const Color(0xFF171C24) : Colors.white;
    final text = dark ? const Color(0xFFE9EDF3) : const Color(0xFF131722);
    final line = dark ? const Color(0xFF242B35) : const Color(0xFFE4E8EE);
    return ThemeData(
      useMaterial3: true,
      brightness: b,
      scaffoldBackgroundColor: ground,
      colorScheme: ColorScheme.fromSeed(
        seedColor: accent, brightness: b,
      ).copyWith(surface: surface, primary: accent),
      cardTheme: CardThemeData(
        color: surface,
        elevation: dark ? 0 : 1,
        shape: RoundedRectangleBorder(
          side: BorderSide(color: line),
          borderRadius: BorderRadius.circular(14),
        ),
      ),
      dividerColor: line,
      fontFamily: 'Roboto',
      textTheme: Typography.material2021(platform: TargetPlatform.android)
          .black
          .apply(bodyColor: text, displayColor: text),
    );
  }

  static ThemeData light(Color accent) => _base(Brightness.light, accent);
  static ThemeData dark(Color accent) => _base(Brightness.dark, accent);
}
