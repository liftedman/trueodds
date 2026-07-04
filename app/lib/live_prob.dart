import 'package:flutter/material.dart';
import 'predict.dart';
import 'widgets.dart';

const _liveRed = Color(0xFFE5484D);

/// Live win probability for an in-play match — updates with the score and the
/// clock, and shows how it has moved from the pre-match number.
class LiveWinProbability extends StatelessWidget {
  final String home, away;
  final double lh, la; // pre-match expected goals
  final double preHome, preDraw, preAway; // pre-match probabilities
  final int homeGoals, awayGoals, minute;
  final Color accent;
  const LiveWinProbability({
    required this.home,
    required this.away,
    required this.lh,
    required this.la,
    required this.preHome,
    required this.preDraw,
    required this.preAway,
    required this.homeGoals,
    required this.awayGoals,
    required this.minute,
    required this.accent,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final live = Predict.inPlay(lh, la, homeGoals, awayGoals, minute);
    final curve = Predict.inPlayHomeCurve(lh, la, homeGoals, awayGoals, minute);
    final fav = [live.home, live.draw, live.away].reduce((a, b) => a > b ? a : b);

    String delta(String label, double pre, double now) {
      final d = ((now - pre) * 100).round();
      final arrow = d > 0 ? '▲' : (d < 0 ? '▼' : '–');
      return '$label ${(now * 100).round()}% $arrow${d.abs()}';
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _liveRed.withOpacity(.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _liveRed.withOpacity(.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const _Pulse(),
          const SizedBox(width: 8),
          Text("LIVE  ·  $minute'",
              style: const TextStyle(
                  color: _liveRed, fontWeight: FontWeight.w800, fontSize: 13)),
          const Spacer(),
          Text('$homeGoals – $awayGoals',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        ]),
        const SizedBox(height: 4),
        Text('Live win probability — updates with the score and the clock',
            style: TextStyle(fontSize: 12, color: muted)),
        const SizedBox(height: 12),
        ProbBar(home, live.home, live.home == fav, accent),
        ProbBar('Draw', live.draw, live.draw == fav, accent),
        ProbBar(away, live.away, live.away == fav, accent),
        const SizedBox(height: 12),
        // forward projection: how P(home) firms up if the score holds
        Row(children: [
          Text('If score holds',
              style: TextStyle(fontSize: 11, color: muted)),
          const SizedBox(width: 10),
          Expanded(
            child: SizedBox(
              height: 34,
              child: CustomPaint(
                painter: _CurvePainter(curve, accent, cs.onSurface.withOpacity(.12)),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text('FT', style: TextStyle(fontSize: 11, color: muted)),
        ]),
        const SizedBox(height: 12),
        // pre-match vs now
        Text(
            'Pre-match → now:   ${delta(home, preHome, live.home)}   ·   '
            '${delta('Draw', preDraw, live.draw)}   ·   ${delta(away, preAway, live.away)}',
            style: TextStyle(fontSize: 11.5, color: muted, height: 1.4)),
      ]),
    );
  }
}

/// A small pulsing live dot.
class _Pulse extends StatefulWidget {
  const _Pulse();
  @override
  State<_Pulse> createState() => _PulseState();
}

class _PulseState extends State<_Pulse> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
        ..repeat(reverse: true);
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: 0.4, end: 1.0).animate(_c),
        child: Container(
          width: 9,
          height: 9,
          decoration: const BoxDecoration(color: _liveRed, shape: BoxShape.circle),
        ),
      );
}

class _CurvePainter extends CustomPainter {
  final List<double> pts; // P(home win) over remaining time, 0..1
  final Color line;
  final Color grid;
  _CurvePainter(this.pts, this.line, this.grid);

  @override
  void paint(Canvas canvas, Size size) {
    // 50% reference line
    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    final midY = size.height * 0.5;
    canvas.drawLine(Offset(0, midY), Offset(size.width, midY), gridPaint);

    if (pts.length < 2) return;
    final path = Path();
    for (var i = 0; i < pts.length; i++) {
      final x = size.width * i / (pts.length - 1);
      final y = size.height * (1 - pts[i].clamp(0.0, 1.0));
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = line
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
    // end dot
    final lastX = size.width;
    final lastY = size.height * (1 - pts.last.clamp(0.0, 1.0));
    canvas.drawCircle(Offset(lastX, lastY), 3.5, Paint()..color = line);
  }

  @override
  bool shouldRepaint(_CurvePainter old) => old.pts != pts;
}
