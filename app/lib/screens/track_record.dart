import 'package:flutter/material.dart';
import 'package:sports_model_app/widgets/theme.dart';

int _pct(num v) => (v * 100).round();

/// "The Receipts" — our out-of-sample track record, shown openly. The point is
/// radical honesty: how our past predictions actually did, market comparison
/// and all.
class TrackRecordScreen extends StatelessWidget {
  final Map data;
  const TrackRecordScreen(this.data, {super.key});

  @override
  Widget build(BuildContext context) {
    final r = data['receipts'] as Map?;
    final wc = data['wc_receipts'] as Map?;
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);

    return Scaffold(
      appBar: AppBar(title: const Text('Our track record')),
      body: (r == null && wc == null)
          ? _empty(context, muted)
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                Text('The receipts',
                    style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.5,
                        color: cs.onSurface)),
                const SizedBox(height: 4),
                Text(
                    'How our predictions actually did — graded on games the '
                    'model never trained on. No cherry-picking.',
                    style: TextStyle(color: muted, height: 1.4)),
                if (r != null) ...[
                  const SizedBox(height: 18),
                  _bandTitle(context, 'Club football'),
                  const SizedBox(height: 12),
                  _headline(context, r),
                  const SizedBox(height: 24),
                  _calibration(context, r),
                  const SizedBox(height: 24),
                  _examples(context, r),
                  const SizedBox(height: 20),
                  _honestNote(context, r),
                ],
                if (wc != null) ...[
                  const SizedBox(height: 28),
                  _bandTitle(context, 'World Cup & internationals'),
                  const SizedBox(height: 12),
                  _wcHeadline(context, wc),
                  const SizedBox(height: 24),
                  _calibration(context, wc),
                  const SizedBox(height: 24),
                  _examples(context, wc),
                ],
              ],
            ),
    );
  }

  Widget _bandTitle(BuildContext c, String t) {
    final cs = Theme.of(c).colorScheme;
    return Row(children: [
      Container(width: 4, height: 20, decoration: BoxDecoration(
          color: cs.primary, borderRadius: BorderRadius.circular(2))),
      const SizedBox(width: 8),
      Text(t, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
    ]);
  }

  // Single hit-rate stat for internationals (no betting market to compare to).
  Widget _wcHeadline(BuildContext c, Map wc) {
    final cs = Theme.of(c).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.4),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(children: [
        Text('${_pct(wc['hit_rate'] as num)}%',
            style: TextStyle(
                fontSize: 44,
                height: 1,
                fontWeight: FontWeight.w800,
                color: cs.primary)),
        const SizedBox(height: 6),
        Text('of our World Cup / international picks were correct',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13, color: cs.onSurface.withOpacity(.6))),
        const SizedBox(height: 8),
        Text('across ${wc['n']} matches · out-of-sample · no betting market',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.55))),
      ]),
    );
  }

  // Big paired stat: our pick hit-rate vs the bookmaker's.
  Widget _headline(BuildContext c, Map r) {
    final cs = Theme.of(c).colorScheme;
    final model = r['model'] as Map;
    final book = r['bookmaker'] as Map;
    final n = r['n'];
    Widget stat(String label, num rate, bool primary) => Expanded(
          child: Column(children: [
            Text('${_pct(rate)}%',
                style: TextStyle(
                    fontSize: 40,
                    fontWeight: FontWeight.w800,
                    height: 1,
                    color: primary ? cs.primary : cs.onSurface.withOpacity(.75))),
            const SizedBox(height: 6),
            Text(label,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 12, color: cs.onSurface.withOpacity(.6))),
          ]),
        );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 16),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.4),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(children: [
        Row(children: [
          stat('Our picks won', model['hit_rate'] as num, true),
          Container(width: 1, height: 54, color: cs.onSurface.withOpacity(.12)),
          stat("Bookmaker's picks won", book['hit_rate'] as num, false),
        ]),
        const SizedBox(height: 14),
        Text(
            'across $n matches · ${r['season'] ?? ''} · out-of-sample',
            style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.55))),
      ]),
    );
  }

  // The crown jewel: predicted vs actual per confidence band.
  Widget _calibration(BuildContext c, Map r) {
    final cs = Theme.of(c).colorScheme;
    final rows = (r['calibration'] as List?)?.cast<Map>() ?? const [];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _sectionTitle(c, 'Are our percentages honest?'),
      const SizedBox(height: 4),
      Text(
          'When we say a number, does it happen that often? Closer bars = more '
          'trustworthy probabilities.',
          style: TextStyle(fontSize: 13, color: cs.onSurface.withOpacity(.6), height: 1.4)),
      const SizedBox(height: 14),
      ...rows.map((b) => _calibRow(c, b)),
    ]);
  }

  Widget _calibRow(BuildContext c, Map b) {
    final cs = Theme.of(c).colorScheme;
    final predicted = (b['predicted'] as num).toDouble();
    final actual = (b['actual'] as num).toDouble();
    Widget bar(double v, Color color, String tag) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(children: [
            SizedBox(
                width: 62,
                child: Text(tag,
                    style: TextStyle(
                        fontSize: 10, color: cs.onSurface.withOpacity(.5)))),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(5),
                child: Container(
                  height: 16,
                  color: cs.onSurface.withOpacity(.07),
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: v.clamp(0.0, 1.0),
                    child: Container(color: color),
                  ),
                ),
              ),
            ),
            SizedBox(
                width: 42,
                child: Text('${_pct(v)}%',
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                        fontSize: 12,
                        fontFeatures: [FontFeature.tabularFigures()]))),
          ]),
        );
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('When we said ${b['label']}',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
          const Spacer(),
          Text('${b['n']} games',
              style: TextStyle(fontSize: 11, color: cs.onSurface.withOpacity(.5))),
        ]),
        const SizedBox(height: 4),
        bar(predicted, cs.primary.withOpacity(.45), 'we said'),
        bar(actual, cs.primary, 'happened'),
      ]),
    );
  }

  Widget _examples(BuildContext c, Map r) {
    final cs = Theme.of(c).colorScheme;
    final ex = (r['examples'] as List?)?.cast<Map>() ?? const [];
    if (ex.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _sectionTitle(c, 'Receipts, not promises'),
      const SizedBox(height: 4),
      Text('Real calls from the graded season — including one we got wrong.',
          style: TextStyle(fontSize: 13, color: cs.onSurface.withOpacity(.6))),
      const SizedBox(height: 12),
      ...ex.map((e) {
        final hit = e['hit'] == true;
        final color = hit ? AppTheme.hi : const Color(0xFFE5484D);
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: cs.surfaceContainerHighest.withOpacity(.35),
            borderRadius: BorderRadius.circular(10),
            border: Border(left: BorderSide(color: color, width: 3)),
          ),
          child: Row(children: [
            Icon(hit ? Icons.check_circle : Icons.cancel, color: color, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(e['match'] as String? ?? '',
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                Text(
                    'We picked ${e['pick']} (${_pct(e['prob'] as num)}%)  ·  '
                    'ended ${e['score']}',
                    style: TextStyle(
                        fontSize: 12, color: cs.onSurface.withOpacity(.6))),
              ]),
            ),
          ]),
        );
      }),
    ]);
  }

  Widget _honestNote(BuildContext c, Map r) {
    final cs = Theme.of(c).colorScheme;
    final model = (r['model'] as Map)['hit_rate'] as num;
    final book = (r['bookmaker'] as Map)['hit_rate'] as num;
    final behind = _pct(book) - _pct(model);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: cs.primary, width: 3)),
        color: cs.primary.withOpacity(.07),
      ),
      child: Text(
        'The honest read: our picks land about $behind% behind the bookmaker — '
        'nobody reliably beats the market, and we won\'t pretend to. What we '
        'can promise is that our percentages mean what they say. Use them as '
        'insight, not a betting system.',
        style: const TextStyle(fontWeight: FontWeight.w600, height: 1.45),
      ),
    );
  }

  Widget _sectionTitle(BuildContext c, String t) => Text(t,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800));

  Widget _empty(BuildContext c, Color muted) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.receipt_long_outlined, size: 40, color: muted),
            const SizedBox(height: 12),
            Text('Track record is being prepared',
                style: TextStyle(fontWeight: FontWeight.w700, color: muted)),
            const SizedBox(height: 6),
            Text('It appears once the backend publishes a snapshot with graded '
                'results. Pull to refresh shortly.',
                textAlign: TextAlign.center, style: TextStyle(color: muted)),
          ]),
        ),
      );
}
