import 'package:flutter/material.dart';
import 'package:sports_model_app/widgets/theme.dart';

/// Shared pieces for Markets mode.
///
/// The centrepiece is [PayoffCard]. Every other trading app shows you a
/// confident arrow; this one shows the arrow next to the hit rate you would
/// actually need for that arrow to make money, and the hit rate this model has
/// actually achieved on this instrument. Those three numbers together are the
/// entire product.

String pctM(double v) => '${(v * 100).toStringAsFixed(1)}%';

/// Formats a price without pretending to more precision than the instrument has.
String priceStr(num? v) {
  if (v == null) return '—';
  final a = v.abs();
  if (a >= 1000) return v.toStringAsFixed(2);
  if (a >= 10) return v.toStringAsFixed(3);
  if (a >= 1) return v.toStringAsFixed(4);
  return v.toStringAsFixed(5);
}

/// Colour for a signed change: green up, red down, muted flat.
Color changeColor(BuildContext c, double v) {
  if (v > 0.0005) return AppTheme.hi;
  if (v < -0.0005) return const Color(0xFFE5484D);
  return Theme.of(c).colorScheme.onSurface.withOpacity(.5);
}

/// True once the bar a forecast referred to has already closed.
///
/// The snapshot is rebuilt on a schedule, so short-horizon forecasts inside it
/// go out of date long before the next build. A 5-minute forecast from this
/// morning is not a prediction any more — it is history with the answer already
/// known. Showing it as though it were current would be the single easiest way
/// for this mode to mislead someone, so every surface checks this first.
bool isExpired(Map horizon) {
  final t = settleTime(horizon);
  if (t == null) return false;
  return (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000) > t;
}

/// When the forecast is actually decided.
///
/// `settles_at` is the settling bar's CLOSE. `target` is only its OPEN, so
/// reading `target` as the deadline marks a forecast expired a full bar early —
/// an hour early on the 1h horizon, a day early on 1d. Older snapshots predate
/// the `settles_at` field, so fall back to target plus one bar length inferred
/// from the gap between cutoff and target.
int? settleTime(Map horizon) {
  final s = horizon['settles_at'];
  if (s is int) return s;
  final target = horizon['target'];
  final cutoff = horizon['cutoff'];
  if (target is! int) return null;
  if (cutoff is int && target > cutoff) return target + (target - cutoff);
  return target;
}

/// How long ago a forecast's window closed, e.g. '3h ago'. Empty if still open.
///
/// Worth showing rather than a bare "closed": a window that shut two minutes ago
/// means the snapshot is mid-refresh, while one that shut two days ago means the
/// upstream data itself is lagging. Those deserve different reactions, and only
/// the age distinguishes them.
String expiredAgo(Map horizon) {
  final t = settleTime(horizon);
  if (t == null) return '';
  final secs = (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000) - t;
  if (secs <= 0) return '';
  if (secs < 3600) return '${(secs / 60).floor()}m ago';
  if (secs < 86400) return '${(secs / 3600).floor()}h ago';
  return '${(secs / 86400).floor()}d ago';
}

/// Human age of an epoch-seconds timestamp, e.g. '12m ago'. '' if absent.
///
/// Prices are refreshed on a much shorter cycle than the models, so the app now
/// has two different freshness clocks. Showing the price one explicitly is what
/// stops a ticking price from implying a ticking forecast.
String ageOf(dynamic epochSecs) {
  if (epochSecs is! num) return '';
  final secs =
      (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000) - epochSecs.toInt();
  if (secs < 0) return 'just now';
  if (secs < 90) return '${secs}s ago';
  if (secs < 3600) return '${(secs / 60).floor()}m ago';
  if (secs < 86400) return '${(secs / 3600).floor()}h ago';
  return '${(secs / 86400).floor()}d ago';
}

/// The honest verdict for one instrument/horizon, derived from its track record.
///
/// Returns (label, colour, explanation). Kept in one place so the list chip and
/// the detail page can never disagree with each other.
(String, Color, String) marketVerdict(Map? track, double breakeven) {
  if (track == null) {
    return (
      'Untested',
      AppTheme.lo,
      'No measured track record for this instrument and horizon yet, so there '
          'is nothing to justify acting on the estimate.'
    );
  }
  if (track['enough'] != true) {
    return (
      'Too few tests',
      AppTheme.lo,
      'Only ${track['n']} out-of-sample predictions have been scored here. '
          'That is too small a sample to mean anything either way.'
    );
  }
  final hit = (track['hit'] as num).toDouble();
  if (track['clears_breakeven'] == true) {
    return (
      'Clears breakeven',
      AppTheme.hi,
      'Measured ${pctM(hit)} over ${track['n']} out-of-sample predictions, and '
          'even the low end of the confidence range stays above the '
          '${pctM(breakeven)} needed. Treat this with suspicion rather than '
          'excitement — verify it holds on other periods before believing it.'
    );
  }
  if (track['beats_base'] == true) {
    return (
      'Signal, not profit',
      AppTheme.med,
      'The model is better calibrated than simply guessing the long-run drift, '
          'but its ${pctM(hit)} hit rate does not reach the ${pctM(breakeven)} '
          'a trade at this payout requires. Informative, not tradable.'
    );
  }
  return (
    'No edge',
    const Color(0xFFE5484D),
    'Measured ${pctM(hit)} over ${track['n']} out-of-sample predictions, '
        'against the ${pctM(breakeven)} needed to break even. Acting on this '
        'loses money over time.'
  );
}

/// Small pill showing the verdict label.
class VerdictChip extends StatelessWidget {
  final String label;
  final Color color;
  final bool dense;
  const VerdictChip(this.label, this.color, {this.dense = false, super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
          horizontal: dense ? 7 : 9, vertical: dense ? 3 : 4),
      decoration: BoxDecoration(
        color: color.withOpacity(.14),
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: color.withOpacity(.5)),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: dense ? 10 : 11,
              fontWeight: FontWeight.w700,
              color: color)),
    );
  }
}

/// THE card. Model confidence vs the bar it has to clear, side by side.
///
/// `pSide` is the model's confidence in whichever direction it leans (always
/// >= 0.5), which is the number a user would actually be staking on — not the
/// raw P(up), which understates confidence whenever the lean is "down".
class PayoffCard extends StatelessWidget {
  final double pSide;
  final String side; // 'UP' / 'DOWN'
  final double breakeven;
  final double payout;
  final Map? track;

  /// When true the forecast's settlement bar has already closed, so the lean is
  /// suppressed. The measured track record below it stays valid and on show —
  /// that part does not expire.
  final bool expired;

  /// Human age of a closed window, e.g. '3h ago'. Only used when [expired].
  final String expiredSince;
  const PayoffCard({
    required this.pSide,
    required this.side,
    required this.breakeven,
    required this.payout,
    this.track,
    this.expired = false,
    this.expiredSince = '',
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final (label, color, explain) = marketVerdict(track, breakeven);

    // Expected value per unit staked, using the MEASURED hit rate where we have
    // one. Falling back to this single forecast's confidence would be the
    // dishonest version: it assumes the model is right about being right.
    final measured =
        (track != null && track!['enough'] == true) ? (track!['hit'] as num).toDouble() : null;
    final evBasis = measured ?? pSide;
    final ev = evBasis * payout - (1 - evBasis);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text('THE NUMBER THAT MATTERS',
                  style: TextStyle(
                      fontSize: 11, letterSpacing: 1.2, color: muted)),
            ),
            VerdictChip(label, color),
          ]),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
                child: _stat(
                    context,
                    expired ? 'Model leaned' : 'Model leans',
                    expired ? 'expired' : '$side ${pctM(pSide)}',
                    expired ? muted : cs.primary)),
            Expanded(
                child: _stat(context, 'Needed to break even', pctM(breakeven),
                    cs.onSurface)),
            Expanded(
              child: _stat(
                  context,
                  'Actually achieved',
                  measured == null ? '—' : pctM(measured),
                  measured == null
                      ? muted
                      : (measured >= breakeven ? AppTheme.hi : const Color(0xFFE5484D))),
            ),
          ]),
          if (expired) ...[
            const SizedBox(height: 10),
            Row(children: [
              Icon(Icons.history_toggle_off,
                  size: 14, color: muted),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                    'This forecast\'s window closed${expiredSince.isEmpty ? '' : ' $expiredSince'}'
                    ' — the lean is no longer a prediction. The track record '
                    'below still applies.',
                    style: TextStyle(fontSize: 11.5, height: 1.4, color: muted)),
              ),
            ]),
          ],
          const SizedBox(height: 14),
          _breakevenBar(context, measured, breakeven),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withOpacity(.08),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: color.withOpacity(.25)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(explain,
                  style: TextStyle(fontSize: 12.5, height: 1.45, color: cs.onSurface)),
              if (measured != null) ...[
                const SizedBox(height: 8),
                Text(
                    'At a ${(payout * 100).round()}% payout that is '
                    '${ev >= 0 ? '+' : ''}${(ev * 100).toStringAsFixed(2)}% '
                    'expected return per unit staked.',
                    style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        color: ev >= 0 ? AppTheme.hi : const Color(0xFFE5484D))),
              ],
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _stat(BuildContext c, String label, String value, Color color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 10,
                  height: 1.3,
                  color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
          const SizedBox(height: 3),
          Text(value,
              style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: color,
                  fontFeatures: const [FontFeature.tabularFigures()])),
        ],
      );

  /// A single track from 45% to 65% with the breakeven line marked, and the
  /// measured hit rate placed against it. Shows the gap at a glance.
  Widget _breakevenBar(BuildContext c, double? measured, double be) {
    const lo = 0.45, hi = 0.65;
    double at(double v) => ((v - lo) / (hi - lo)).clamp(0.0, 1.0);
    final cs = Theme.of(c).colorScheme;

    return LayoutBuilder(builder: (_, box) {
      final w = box.maxWidth;
      return SizedBox(
        height: 34,
        child: Stack(children: [
          Positioned(
            top: 12,
            child: Container(
              width: w,
              height: 8,
              decoration: BoxDecoration(
                color: cs.onSurface.withOpacity(.08),
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
          // Everything at or above breakeven is the profitable zone.
          Positioned(
            left: w * at(be),
            top: 12,
            child: Container(
              width: w * (1 - at(be)),
              height: 8,
              decoration: BoxDecoration(
                color: AppTheme.hi.withOpacity(.18),
                borderRadius: const BorderRadius.horizontal(
                    right: Radius.circular(4)),
              ),
            ),
          ),
          // Breakeven marker.
          Positioned(
            left: (w * at(be)) - 1,
            top: 6,
            child: Container(width: 2, height: 20, color: cs.onSurface.withOpacity(.55)),
          ),
          Positioned(
            left: (w * at(be)) - 16,
            top: 0,
            child: Text('need',
                style: TextStyle(fontSize: 9, color: cs.onSurface.withOpacity(.55))),
          ),
          // Measured hit rate.
          if (measured != null)
            Positioned(
              left: (w * at(measured)) - 6,
              top: 8,
              child: Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: measured >= be ? AppTheme.hi : const Color(0xFFE5484D),
                  shape: BoxShape.circle,
                  border: Border.all(color: cs.surface, width: 2),
                ),
              ),
            ),
        ]),
      );
    });
  }
}

/// Whole-model scoreboard, shown above every instrument list.
///
/// This exists to defeat the most natural misreading of the list below it. Scan
/// 115 measured combinations and you WILL find one that looks profitable; the
/// honest response is to say how many chance alone would have produced. Without
/// that number a lone winner reads as a discovery instead of as noise.
class MarketsSummaryCard extends StatelessWidget {
  final Map data;
  const MarketsSummaryCard(this.data, {super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final s = data['summary'] as Map;
    final measured = (s['measured'] as num).toInt();
    if (measured == 0) return const SizedBox.shrink();

    final cleared = (s['cleared_breakeven'] as num).toInt();
    final expected = (s['expected_false_positives'] as num?)?.toDouble();
    final meanHit = (s['mean_hit'] as num?)?.toDouble();
    final breakeven = (data['breakeven'] as num).toDouble();

    // The headline. Anything other than "beaten fair and square" says so.
    final (verdict, vColor) = (expected != null && cleared <= expected)
        ? (
            cleared == 0
                ? 'No edge found anywhere'
                : 'Within chance — no real edge',
            const Color(0xFFE5484D)
          )
        : ('More winners than chance predicts', AppTheme.med);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text('HOW THIS MODEL IS ACTUALLY DOING',
                  style: TextStyle(
                      fontSize: 11, letterSpacing: 1.2, color: muted)),
            ),
            VerdictChip(verdict, vColor, dense: true),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
                child: _mini(context, 'Combinations tested', '$measured', null)),
            Expanded(
                child: _mini(
                    context,
                    'Mean hit rate',
                    meanHit == null ? '—' : pctM(meanHit),
                    meanHit != null && meanHit >= breakeven
                        ? AppTheme.hi
                        : const Color(0xFFE5484D))),
            Expanded(
                child: _mini(context, 'Cleared breakeven',
                    '$cleared of $measured', null)),
          ]),
          const SizedBox(height: 12),
          Text(
            expected == null
                ? 'Measured out-of-sample across every instrument and horizon.'
                : 'Testing $measured combinations, roughly '
                    '${expected.toStringAsFixed(0)} would clear the '
                    '${pctM(breakeven)} bar by luck alone. '
                    '${cleared <= expected ? "We found $cleared — at or below what chance produces, so this is not evidence of an edge." : "We found $cleared, more than chance predicts. Worth investigating, but assume a data problem before believing it."}',
            style: TextStyle(fontSize: 12, height: 1.45, color: muted),
          ),
        ]),
      ),
    );
  }

  Widget _mini(BuildContext c, String label, String value, Color? color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 9.5,
                  height: 1.3,
                  color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.w800,
                  color: color,
                  fontFeatures: const [FontFeature.tabularFigures()])),
        ],
      );
}

/// The forward test: predictions logged before the outcome existed.
///
/// Kept visually distinct from [MarketsSummaryCard] on purpose. That card
/// reports a backtest, which is only as trustworthy as the person who wrote the
/// harness. This one reports forecasts that were written down in advance and
/// never edited — a weaker sample for a long time, but a much stronger kind of
/// claim. Conflating the two would let backtest confidence borrow credibility
/// it hasn't earned.
class LiveRecordCard extends StatelessWidget {
  final Map data;
  const LiveRecordCard(this.data, {super.key});

  @override
  Widget build(BuildContext context) {
    final rec = data['live_record'];
    if (rec is! Map) return const SizedBox.shrink();

    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final overall = rec['overall'] as Map? ?? const {};
    final n = (overall['n'] as num?)?.toInt() ?? 0;
    final pending = (rec['pending'] as num?)?.toInt() ?? 0;
    final breakeven = (rec['breakeven'] as num).toDouble();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(Icons.fact_check_outlined, size: 15, color: muted),
            const SizedBox(width: 6),
            Expanded(
              child: Text('FORWARD TEST — LOGGED BEFORE THE OUTCOME',
                  style: TextStyle(
                      fontSize: 11, letterSpacing: 1.1, color: muted)),
            ),
          ]),
          const SizedBox(height: 10),
          if (n == 0) ...[
            Text(
                pending == 0
                    ? 'Nothing logged yet. Once the scheduled job runs, every '
                        'forecast is written down before its window closes and '
                        'graded afterwards.'
                    : '$pending forecast${pending == 1 ? '' : 's'} logged and '
                        'waiting to settle. Results appear here once their '
                        'windows close — nothing is scored early.',
                style: TextStyle(fontSize: 12.5, height: 1.45, color: muted)),
          ] else ...[
            Row(children: [
              Expanded(child: _cell(context, 'Graded', '$n', null)),
              Expanded(
                  child: _cell(
                      context,
                      'Hit rate',
                      pctM((overall['hit'] as num).toDouble()),
                      (overall['hit'] as num).toDouble() >= breakeven
                          ? AppTheme.hi
                          : const Color(0xFFE5484D))),
              Expanded(
                  child: _cell(context, 'Need', pctM(breakeven), null)),
              Expanded(child: _cell(context, 'Pending', '$pending', null)),
            ]),
            const SizedBox(height: 10),
            _ciLine(context, overall, breakeven, muted),
            if (rec['by_timeframe'] is Map &&
                (rec['by_timeframe'] as Map).isNotEmpty) ...[
              const SizedBox(height: 10),
              for (final e in (rec['by_timeframe'] as Map).entries)
                if (((e.value as Map)['n'] as num?) != null &&
                    ((e.value as Map)['n'] as num) > 0)
                  _tfRow(context, e.key as String, e.value as Map, breakeven, muted),
            ],
          ],
        ]),
      ),
    );
  }

  Widget _ciLine(BuildContext c, Map o, double breakeven, Color muted) {
    final ci = (o['ci'] as List).cast<num>();
    final enough = o['enough'] == true;
    final clears = o['clears_breakeven'] == true;
    final ev = (o['ev'] as num).toDouble();

    final String verdict;
    final Color color;
    if (!enough) {
      verdict = 'Too few to claim anything yet — the range is still too wide '
          'to separate this from a coin flip.';
      color = AppTheme.lo;
    } else if (clears) {
      verdict = 'Clears breakeven even at the low end of the range. Verify '
          'before believing it.';
      color = AppTheme.hi;
    } else {
      verdict = 'Below breakeven — acting on these would have lost '
          '${(ev * 100).abs().toStringAsFixed(1)}% per unit staked.';
      color = const Color(0xFFE5484D);
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('95% range ${pctM(ci[0].toDouble())} – ${pctM(ci[1].toDouble())}',
          style: TextStyle(fontSize: 11.5, color: muted)),
      const SizedBox(height: 6),
      Text(verdict,
          style: TextStyle(
              fontSize: 12.5, height: 1.4, fontWeight: FontWeight.w600, color: color)),
    ]);
  }

  Widget _tfRow(BuildContext c, String tf, Map s, double breakeven, Color muted) {
    final hit = (s['hit'] as num).toDouble();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        SizedBox(width: 38, child: Text(tf, style: TextStyle(fontSize: 11.5, color: muted))),
        Text('n=${s['n']}',
            style: TextStyle(fontSize: 11.5, color: muted)),
        const Spacer(),
        Text(pctM(hit),
            style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                fontFeatures: const [FontFeature.tabularFigures()],
                color: hit >= breakeven ? AppTheme.hi : const Color(0xFFE5484D))),
      ]),
    );
  }

  Widget _cell(BuildContext c, String label, String value, Color? color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 9.5,
                  color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.w800,
                  color: color,
                  fontFeatures: const [FontFeature.tabularFigures()])),
        ],
      );
}

/// The standing disclosure for Markets mode. Stronger than the sports one,
/// because the money at risk is larger and the products involved are riskier.
class MarketsDisclosure extends StatelessWidget {
  const MarketsDisclosure({super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Analysis, not advice',
            style: TextStyle(
                fontSize: 11, letterSpacing: 1.2, color: muted)),
        const SizedBox(height: 6),
        Text(
          'These are statistical estimates with a published track record, not '
          'trade recommendations. Nothing here is financial advice. '
          'Fixed-time ("binary") products carry a built-in house edge and are '
          'banned for retail clients in the UK, EU and Australia. Most retail '
          'traders lose money. Never risk money you cannot afford to lose.',
          style: TextStyle(fontSize: 11.5, height: 1.5, color: muted),
        ),
      ]),
    );
  }
}
