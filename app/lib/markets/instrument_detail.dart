import 'package:flutter/material.dart';
import 'package:sports_model_app/markets/market_widgets.dart';
import 'package:sports_model_app/widgets/live_prob.dart' show Sparkline;
import 'package:sports_model_app/widgets/theme.dart';

/// Plain-language names for the model's features, so "why" is readable by
/// someone who has never seen a logistic regression. Keys match
/// markets_model/features.py FEATURE_NAMES.
const _featureLabels = {
  'ret_1': 'last bar\'s move',
  'ret_3': 'move over 3 bars',
  'ret_5': 'move over 5 bars',
  'ret_10': 'move over 10 bars',
  'ret_20': 'move over 20 bars',
  'vol_10': 'recent volatility (10)',
  'vol_30': 'recent volatility (30)',
  'rsi_14': 'overbought / oversold (RSI)',
  'range_pos_20': 'position in the 20-bar range',
  'sma_dist_20': 'distance from the 20-bar average',
  'sma_dist_50': 'distance from the 50-bar average',
  'body_frac': 'candle body direction',
  'hl_range_z': 'bar range vs normal',
  'vol_z_20': 'volume vs normal',
  'hour_sin': 'time of day',
  'hour_cos': 'time of day',
  'dow_sin': 'day of week',
  'dow_cos': 'day of week',
};

/// Full analysis for one instrument: price, the payoff reality check, the
/// measured track record, and what is driving the current lean.
class InstrumentDetail extends StatefulWidget {
  final Map data; // the whole markets snapshot
  final Map instrument;
  final String initialTimeframe;
  const InstrumentDetail(this.data, this.instrument, this.initialTimeframe,
      {super.key});

  @override
  State<InstrumentDetail> createState() => _InstrumentDetailState();
}

class _InstrumentDetailState extends State<InstrumentDetail> {
  late String _tf;

  Map get _horizons => widget.instrument['horizons'] as Map;
  List<String> get _available =>
      [for (final t in widget.data['timeframes'] as List) t as String]
          .where(_horizons.containsKey)
          .toList();

  @override
  void initState() {
    super.initState();
    final avail = _available;
    _tf = avail.contains(widget.initialTimeframe)
        ? widget.initialTimeframe
        : (avail.isNotEmpty ? avail.first : widget.initialTimeframe);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final inst = widget.instrument;
    final accent = AppTheme.sportAccent[inst['asset']] ?? cs.primary;
    final breakeven = (widget.data['breakeven'] as num).toDouble();
    final payout = (widget.data['payout'] as num).toDouble();

    final h = _horizons[_tf] as Map?;
    final pUp = h == null ? 0.5 : (h['p_up'] as num).toDouble();
    final side = pUp >= .5 ? 'UP' : 'DOWN';
    final pSide = pUp >= .5 ? pUp : 1 - pUp;
    final track = h?['track'] as Map?;
    final change = (inst['change'] as num).toDouble();
    final spark = [for (final v in inst['spark'] as List) (v as num).toDouble()];

    return Theme(
      data: Theme.of(context).copyWith(
        colorScheme: cs.copyWith(primary: accent),
      ),
      child: Scaffold(
        appBar: AppBar(
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${inst['name']}',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              Text('${inst['symbol']}',
                  style: TextStyle(fontSize: 11, color: muted)),
            ],
          ),
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
          children: [
            // --- price -----------------------------------------------------
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Text(priceStr(inst['last'] as num?),
                        style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                            fontFeatures: [FontFeature.tabularFigures()])),
                    const SizedBox(width: 10),
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Text(
                          '${change >= 0 ? '+' : ''}${(change * 100).toStringAsFixed(2)}%',
                          style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              color: changeColor(context, change))),
                    ),
                    const Spacer(),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('last ${spark.length} × ${inst['change_tf']}',
                            style: TextStyle(fontSize: 10, color: muted)),
                        if (inst['price_as_of'] != null)
                          Text('price ${ageOf(inst['price_as_of'])}',
                              style: TextStyle(fontSize: 10, color: muted)),
                      ],
                    ),
                  ]),
                  const SizedBox(height: 12),
                  if (spark.length > 2)
                    Sparkline(spark, changeColor(context, change), height: 56),
                ]),
              ),
            ),
            const SizedBox(height: 12),

            // --- horizon ----------------------------------------------------
            if (_available.length > 1) ...[
              Text('HORIZON',
                  style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: muted)),
              const SizedBox(height: 6),
              SegmentedButton<String>(
                segments: [
                  for (final t in _available)
                    ButtonSegment(value: t, label: Text(t)),
                ],
                selected: {_tf},
                showSelectedIcon: false,
                onSelectionChanged: (s) => setState(() => _tf = s.first),
              ),
              const SizedBox(height: 14),
            ],

            if (h == null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Text(
                      'No model for this horizon yet — not enough bars ingested.',
                      style: TextStyle(color: muted)),
                ),
              )
            else ...[
              PayoffCard(
                pSide: pSide,
                side: side,
                breakeven: breakeven,
                payout: payout,
                track: track,
                expired: isExpired(h),
                expiredSince: expiredAgo(h),
              ),
              const SizedBox(height: 12),
              _windowCard(context, h, muted),
              const SizedBox(height: 12),
              _trackCard(context, track, muted, breakeven),
              const SizedBox(height: 12),
              _driversCard(context, h, muted, accent),
            ],
            const MarketsDisclosure(),
          ],
        ),
      ),
    );
  }

  /// What exactly this forecast refers to. Being explicit about the information
  /// cutoff and the settlement bar is what makes the track record auditable.
  Widget _windowCard(BuildContext c, Map h, Color muted) {
    String p(int n) => n.toString().padLeft(2, '0');
    String fmt(int epoch) {
      final d = DateTime.fromMillisecondsSinceEpoch(epoch * 1000, isUtc: true);
      return '${d.year}-${p(d.month)}-${p(d.day)} ${p(d.hour)}:${p(d.minute)} UTC';
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('WHAT THIS FORECAST MEANS',
              style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: muted)),
          const SizedBox(height: 10),
          _kv(c, 'Based on data up to', fmt(h['cutoff'] as int)),
          _kv(c, 'Reference price', priceStr(h['ref_close'] as num?)),
          _kv(c, isExpired(h) ? 'Settled at' : 'Settles at',
              fmt(h['target'] as int)),
          const SizedBox(height: 8),
          Text(
              'The model sees nothing after the cutoff. It is asking one '
              'question: will the close at settlement be above the reference '
              'price?',
              style: TextStyle(fontSize: 12, height: 1.45, color: muted)),
        ]),
      ),
    );
  }

  Widget _trackCard(BuildContext c, Map? track, Color muted, double breakeven) {
    if (track == null) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Text(
              'No walk-forward evaluation has been run for this instrument and '
              'horizon yet.',
              style: TextStyle(color: muted)),
        ),
      );
    }
    final ci = (track['ci'] as List).cast<num>();
    final n = track['n'] as int;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('MEASURED TRACK RECORD',
              style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: muted)),
          const SizedBox(height: 10),
          _kv(c, 'Out-of-sample predictions', '$n'),
          _kv(c, 'Hit rate', pctM((track['hit'] as num).toDouble())),
          _kv(c, '95% confidence range',
              '${pctM(ci[0].toDouble())} – ${pctM(ci[1].toDouble())}'),
          _kv(c, 'Needed to break even', pctM(breakeven)),
          _kv(
              c,
              'Beats drift benchmark',
              track['beats_base'] == true ? 'Yes' : 'No'),
          const SizedBox(height: 8),
          Text(
              'Measured by refitting the model on past bars only and scoring it '
              'on bars it had never seen, in time order. The confidence range '
              'matters more than the headline number: if it reaches below the '
              'breakeven line, the apparent edge could easily be luck.',
              style: TextStyle(fontSize: 12, height: 1.45, color: muted)),
        ]),
      ),
    );
  }

  Widget _driversCard(BuildContext c, Map h, Color muted, Color accent) {
    final drivers = (h['drivers'] as List?) ?? const [];
    if (drivers.isEmpty) return const SizedBox.shrink();
    final maxW = drivers
        .map((d) => ((d['weight'] as num).toDouble()).abs())
        .fold<double>(0, (a, b) => a > b ? a : b);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('WHAT IS DRIVING THE LEAN',
              style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: muted)),
          const SizedBox(height: 10),
          for (final d in drivers) ...[
            _driverRow(c, d as Map, maxW, accent, muted),
            const SizedBox(height: 8),
          ],
          Text(
              'Weights come from the fitted model. A positive weight pushes '
              'towards UP, negative towards DOWN. They are small for a reason — '
              'no single indicator carries much information about the next move.',
              style: TextStyle(fontSize: 12, height: 1.45, color: muted)),
        ]),
      ),
    );
  }

  Widget _driverRow(
      BuildContext c, Map d, double maxW, Color accent, Color muted) {
    final w = (d['weight'] as num).toDouble();
    final label = _featureLabels[d['feature']] ?? d['feature'] as String;
    final frac = maxW > 0 ? (w.abs() / maxW).clamp(0.0, 1.0) : 0.0;
    final up = w >= 0;
    return Row(children: [
      Expanded(
        flex: 5,
        child: Text(label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12.5)),
      ),
      Expanded(
        flex: 4,
        child: Row(children: [
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: FractionallySizedBox(
                widthFactor: up ? 0.0 : frac,
                child: Container(
                    height: 8,
                    decoration: BoxDecoration(
                        color: const Color(0xFFE5484D).withOpacity(.7),
                        borderRadius: BorderRadius.circular(4))),
              ),
            ),
          ),
          Container(width: 1, height: 12, color: muted.withOpacity(.4)),
          Expanded(
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: up ? frac : 0.0,
              child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                      color: accent, borderRadius: BorderRadius.circular(4))),
            ),
          ),
        ]),
      ),
    ]);
  }

  Widget _kv(BuildContext c, String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(children: [
          Expanded(
              child: Text(k,
                  style: TextStyle(
                      fontSize: 12.5,
                      color: Theme.of(c).colorScheme.onSurface.withOpacity(.7)))),
          Text(v,
              style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  fontFeatures: [FontFeature.tabularFigures()])),
        ]),
      );
}
