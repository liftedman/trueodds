import 'package:flutter/material.dart';

/// Stable, crest-like initials avatar. Each team/player gets a consistent
/// colour derived from its name, so no image assets are needed.
class TeamAvatar extends StatelessWidget {
  final String name;
  final double size;
  const TeamAvatar(this.name, {this.size = 34, super.key});

  static Color colorFor(String name) {
    var h = 0;
    for (final c in name.codeUnits) {
      h = (h * 31 + c) & 0x7fffffff;
    }
    final hue = (h % 360).toDouble();
    return HSLColor.fromAHSL(1, hue, .52, .46).toColor();
  }

  static String initialsFor(String name) {
    final parts =
        name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) {
      final w = parts.first;
      return (w.length >= 2 ? w.substring(0, 2) : w).toUpperCase();
    }
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final color = colorFor(name);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(
            color: Theme.of(context).colorScheme.surface, width: size * .06),
      ),
      alignment: Alignment.center,
      child: Text(
        initialsFor(name),
        style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w800,
            fontSize: size * .38,
            letterSpacing: -.5),
      ),
    );
  }
}

/// Home + away monograms shown as a small overlapping pair (away behind).
class DuoAvatar extends StatelessWidget {
  final String home, away;
  final double size;
  const DuoAvatar(this.home, this.away, {this.size = 30, super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size * 1.55,
      height: size,
      child: Stack(children: [
        Positioned(right: 0, child: TeamAvatar(away, size: size)),
        Positioned(left: 0, child: TeamAvatar(home, size: size)),
      ]),
    );
  }
}
