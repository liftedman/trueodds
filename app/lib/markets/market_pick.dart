import 'package:flutter/material.dart';
import 'package:sports_model_app/markets/market_widgets.dart';
import 'package:sports_model_app/services/market_picks.dart';
import 'package:sports_model_app/widgets/theme.dart';

/// The pick control: call it UP or DOWN before the window closes, then it is
/// graded against the model from the same settled row.
///
/// Deliberately shows the model's lean BEFORE you choose. Hiding it would make a
/// better game; showing it makes a better lesson, because the interesting
/// question is not whether you can guess, it is whether you can beat a
/// well-built model that is itself losing money at this payout.
class MarketPickCard extends StatelessWidget {
  final String symbol;
  final String name;
  final String timeframe;
  final int madeAtTs;
  final int settlesAt;
  final double refClose;
  final double modelPUp;
  final double breakeven;
  final Color accent;

  /// False once the window has closed — picking is no longer possible because
  /// the outcome is already determined.
  final bool open;

  const MarketPickCard({
    required this.symbol,
    required this.name,
    required this.timeframe,
    required this.madeAtTs,
    required this.settlesAt,
    required this.refClose,
    required this.modelPUp,
    required this.breakeven,
    required this.accent,
    required this.open,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final modelUp = modelPUp > 0.5;

    return ListenableBuilder(
      listenable: marketPicks,
      builder: (context, _) {
        final rec = marketPicks.recordFor(symbol, timeframe, madeAtTs);
        final picked = rec?['userUp'] as bool?;
        final graded = rec != null && rec.containsKey('actualUp');
        final actualUp = rec?['actualUp'] as bool?;

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(Icons.sports_esports_outlined, size: 16, color: accent),
                    const SizedBox(width: 6),
                    Text('YOU VS THE MODEL',
                        style: TextStyle(
                            fontSize: 11,
                            letterSpacing: 1.2,
                            fontWeight: FontWeight.w700,
                            color: accent)),
                  ]),
                  const SizedBox(height: 6),
                  Text(_blurb(picked, graded, actualUp),
                      style:
                          TextStyle(fontSize: 12.5, height: 1.4, color: muted)),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: _btn(
                        context,
                        label: 'UP',
                        icon: Icons.trending_up,
                        selected: picked == true,
                        isModel: modelUp,
                        correct: graded ? actualUp == true : null,
                        onTap: (!open || graded || picked != null)
                            ? null
                            : () => _pick(true),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _btn(
                        context,
                        label: 'DOWN',
                        icon: Icons.trending_down,
                        selected: picked == false,
                        isModel: !modelUp,
                        correct: graded ? actualUp == false : null,
                        onTap: (!open || graded || picked != null)
                            ? null
                            : () => _pick(false),
                      ),
                    ),
                  ]),
                  if (graded) ...[
                    const SizedBox(height: 12),
                    _outcomeRow(context, picked == actualUp,
                        (modelPUp > 0.5) == actualUp),
                  ] else if (picked != null) ...[
                    const SizedBox(height: 10),
                    Text(
                        'Locked in. It grades itself once the '
                        '$timeframe bar closes — nothing is scored early.',
                        style: TextStyle(fontSize: 11.5, color: muted)),
                  ],
                ]),
          ),
        );
      },
    );
  }

  void _pick(bool up) => marketPicks.makePick(
        symbol: symbol,
        name: name,
        timeframe: timeframe,
        madeAtTs: madeAtTs,
        settlesAt: settlesAt,
        refClose: refClose,
        userUp: up,
        modelPUp: modelPUp,
      );

  String _blurb(bool? picked, bool graded, bool? actualUp) {
    if (graded) {
      return 'Settled: price went ${actualUp == true ? 'UP' : 'DOWN'}.';
    }
    if (picked != null) return 'Your call is recorded.';
    if (!open) {
      return 'This window has closed, so there is nothing left to predict.';
    }
    final side = modelPUp > 0.5 ? 'UP' : 'DOWN';
    final conf = modelPUp > 0.5 ? modelPUp : 1 - modelPUp;
    return 'The model leans $side at ${pctM(conf)} — barely off a coin flip. '
        'Call it yourself and find out, over many tries, whether your read beats '
        'that. You need ${pctM(breakeven)} to profit at this payout.';
  }

  Widget _outcomeRow(BuildContext c, bool userRight, bool modelRight) {
    Widget tag(String who, bool right) => Expanded(
          child: Row(children: [
            Icon(right ? Icons.check_circle : Icons.cancel,
                size: 15,
                color: right ? AppTheme.hi : const Color(0xFFE5484D)),
            const SizedBox(width: 5),
            Text(who,
                style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: right ? AppTheme.hi : const Color(0xFFE5484D))),
          ]),
        );
    return Row(children: [tag('You', userRight), tag('Model', modelRight)]);
  }

  Widget _btn(
    BuildContext context, {
    required String label,
    required IconData icon,
    required bool selected,
    required bool isModel,
    required bool? correct,
    VoidCallback? onTap,
  }) {
    final cs = Theme.of(context).colorScheme;
    Color border = cs.onSurface.withOpacity(.18);
    Color? fill;
    if (selected) {
      border = accent;
      fill = accent.withOpacity(.14);
    }
    if (correct == true) {
      border = AppTheme.hi;
      fill = AppTheme.hi.withOpacity(.14);
    }
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(
          color: fill,
          border: Border.all(
              color: border, width: selected || correct == true ? 1.5 : 1),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(children: [
          Icon(icon,
              size: 18,
              color: selected
                  ? accent
                  : (correct == true ? AppTheme.hi : cs.onSurface.withOpacity(.7))),
          const SizedBox(height: 3),
          Text(label,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                  color: selected ? accent : null)),
          if (isModel)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text('model',
                  style: TextStyle(
                      fontSize: 9,
                      letterSpacing: .5,
                      color: cs.onSurface.withOpacity(.45))),
            ),
        ]),
      ),
    );
  }
}

/// Compact entry point to the scoreboard, shown above the instrument list.
///
/// Always visible, even with no calls yet — it is the invitation. Once there is
/// a record it leads with the comparison that matters: your rate against the
/// breakeven bar, not against the model.
class MarketScoreboardTile extends StatelessWidget {
  final double breakeven;
  final double payout;
  const MarketScoreboardTile(
      {required this.breakeven, required this.payout, super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);

    return ListenableBuilder(
      listenable: marketPicks,
      builder: (context, _) {
        final n = marketPicks.graded;
        final you = marketPicks.userHitRate;
        return Card(
          child: InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) =>
                    MarketScoreboard(breakeven: breakeven, payout: payout))),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(children: [
                Icon(Icons.sports_esports_outlined,
                    size: 18, color: cs.primary),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('You vs the model',
                            style: TextStyle(
                                fontSize: 13.5, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 2),
                        Text(
                            n == 0
                                ? 'Call any instrument UP or DOWN — find out for '
                                    'free whether your read beats a coin flip.'
                                : '$n settled · you ${pctM(you!)} · '
                                    'need ${pctM(breakeven)}',
                            style: TextStyle(fontSize: 11.5, color: muted)),
                      ]),
                ),
                if (n > 0)
                  Text(pctM(you!),
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: you >= breakeven
                              ? AppTheme.hi
                              : const Color(0xFFE5484D))),
                Icon(Icons.chevron_right, size: 18, color: muted),
              ]),
            ),
          ),
        );
      },
    );
  }
}

/// Your record against the model, and against the bar that actually matters.
class MarketScoreboard extends StatelessWidget {
  final double breakeven;
  final double payout;
  const MarketScoreboard(
      {required this.breakeven, required this.payout, super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);

    return Scaffold(
      appBar: AppBar(title: const Text('You vs the model')),
      body: ListenableBuilder(
        listenable: marketPicks,
        builder: (context, _) {
          final n = marketPicks.graded;
          final pend = marketPicks.pending.length;

          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
            children: [
              if (n == 0)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Text(
                        pend == 0
                            ? 'No calls yet. Open any instrument on a '
                                'forward-tested horizon and call it UP or DOWN — '
                                'your record builds here.'
                            : '$pend call${pend == 1 ? '' : 's'} waiting to '
                                'settle. Results appear once their bars close.',
                        style: TextStyle(
                            fontSize: 13, height: 1.45, color: muted)),
                  ),
                )
              else ...[
                _headline(context, n),
                const SizedBox(height: 12),
                _verdict(context, n),
              ],
              const SizedBox(height: 12),
              if (marketPicks.pending.isNotEmpty) ...[
                _sectionLabel(context, 'Waiting to settle'),
                for (final p in marketPicks.pending) _pendingRow(context, p),
                const SizedBox(height: 12),
              ],
              if (marketPicks.history.isNotEmpty) ...[
                _sectionLabel(context, 'Settled'),
                for (final h in marketPicks.history.take(40))
                  _historyRow(context, h),
              ],
              const MarketsDisclosure(),
            ],
          );
        },
      ),
    );
  }

  Widget _headline(BuildContext c, int n) {
    final you = marketPicks.userHitRate!;
    final model = marketPicks.modelHitRate!;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(children: [
          Row(children: [
            Expanded(
                child: _big(c, 'You', '${marketPicks.userRight}/$n',
                    pctM(you), you >= breakeven)),
            Container(
                width: 1,
                height: 54,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.12)),
            Expanded(
                child: _big(c, 'Model', '${marketPicks.modelRight}/$n',
                    pctM(model), model >= breakeven)),
          ]),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
                child: _mini(c, 'You beat it', '${marketPicks.userBeatModel}')),
            Expanded(
                child: _mini(c, 'It beat you', '${marketPicks.modelBeatUser}')),
            Expanded(child: _mini(c, 'Streak', '${marketPicks.streak}')),
            Expanded(child: _mini(c, 'Need', pctM(breakeven))),
          ]),
        ]),
      ),
    );
  }

  /// The honest reading of the numbers above. Small samples get told so, loudly,
  /// because a hot start is exactly what convinces someone to risk real money.
  Widget _verdict(BuildContext c, int n) {
    final you = marketPicks.userHitRate!;
    final cs = Theme.of(c).colorScheme;

    final String text;
    final Color color;
    if (n < 30) {
      text = 'Far too few calls to mean anything. At $n picks, a run of luck '
          'looks identical to skill — that is exactly why the app will not '
          'congratulate you yet. Keep going.';
      color = AppTheme.lo;
    } else if (n < 100) {
      text = 'Still a small sample. Your ${pctM(you)} could easily swing several '
          'points either way from here. Treat it as a rough read, not a result.';
      color = AppTheme.lo;
    } else if (you >= breakeven) {
      text = 'Over $n calls you are at ${pctM(you)}, above the ${pctM(breakeven)} '
          'breakeven. That is genuinely interesting — and the first thing to do '
          'with an interesting result is doubt it. Keep logging before you '
          'conclude anything, and remember this costs nothing while real trades '
          'cost spread.';
      color = AppTheme.hi;
    } else {
      text = 'Over $n calls you are at ${pctM(you)}, short of the '
          '${pctM(breakeven)} needed. On a real ${(payout * 100).round()}% payout '
          'that is ${((you * payout - (1 - you)) * 100).toStringAsFixed(1)}% per '
          'trade. Worth knowing for free rather than paying to find out.';
      color = const Color(0xFFE5484D);
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withOpacity(.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(.3)),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 12.5, height: 1.45, color: cs.onSurface)),
    );
  }

  Widget _big(BuildContext c, String who, String tally, String pct, bool good) =>
      Column(children: [
        Text(who,
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.1,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
        const SizedBox(height: 4),
        Text(pct,
            style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                color: good ? AppTheme.hi : const Color(0xFFE5484D),
                fontFeatures: const [FontFeature.tabularFigures()])),
        Text(tally,
            style: TextStyle(
                fontSize: 11,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
      ]);

  Widget _mini(BuildContext c, String label, String value) => Column(
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  fontFeatures: [FontFeature.tabularFigures()])),
          Text(label,
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 9.5,
                  color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
        ],
      );

  Widget _sectionLabel(BuildContext c, String t) => Padding(
        padding: const EdgeInsets.only(top: 6, bottom: 6),
        child: Text(t.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.2,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
      );

  Widget _pendingRow(BuildContext c, Map p) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Expanded(
              child: Text('${p['name']} · ${p['timeframe']}',
                  style: const TextStyle(fontSize: 13))),
          Text(p['userUp'] == true ? 'UP' : 'DOWN',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: Theme.of(c).colorScheme.primary)),
          const SizedBox(width: 8),
          Text(ageOf(p['settles_at']).isEmpty
                  ? 'pending'
                  : 'due ${ageOf(p['settles_at'])}',
              style: TextStyle(
                  fontSize: 11,
                  color: Theme.of(c).colorScheme.onSurface.withOpacity(.5))),
        ]),
      );

  Widget _historyRow(BuildContext c, Map h) {
    final userRight = h['userRight'] == true;
    final modelRight = h['modelRight'] == true;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Icon(userRight ? Icons.check_circle : Icons.cancel,
            size: 15, color: userRight ? AppTheme.hi : const Color(0xFFE5484D)),
        const SizedBox(width: 8),
        Expanded(
            child: Text('${h['name']} · ${h['timeframe']}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13))),
        Text(h['userUp'] == true ? 'UP' : 'DOWN',
            style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600)),
        const SizedBox(width: 8),
        Text(modelRight ? 'model ✓' : 'model ✗',
            style: TextStyle(
                fontSize: 10.5,
                color: Theme.of(c).colorScheme.onSurface.withOpacity(.55))),
      ]),
    );
  }
}
