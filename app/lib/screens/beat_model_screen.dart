import 'package:flutter/material.dart';
import 'package:sports_model_app/services/beat_model.dart';

/// You vs the algorithm — running head-to-head, streak, and graded history.
class BeatModelScreen extends StatelessWidget {
  const BeatModelScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    return Scaffold(
      appBar: AppBar(title: const Text('Beat the Model')),
      body: ListenableBuilder(
        listenable: beatModel,
        builder: (context, _) {
          if (!beatModel.hasActivity) {
            return _empty(context, muted);
          }
          final history = beatModel.history;
          final pending = beatModel.pending;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
            children: [
              _scoreCard(context),
              if (beatModel.graded > 0) ...[
                const SizedBox(height: 20),
                _verdict(context),
              ],
              if (pending.isNotEmpty) ...[
                const SizedBox(height: 24),
                _title(context, 'Awaiting result (${pending.length})'),
                const SizedBox(height: 8),
                ...pending.map((p) => _pendingRow(context, p)),
              ],
              if (history.isNotEmpty) ...[
                const SizedBox(height: 24),
                _title(context, 'Graded'),
                const SizedBox(height: 8),
                ...history.map((h) => _gradedRow(context, h)),
              ],
            ],
          );
        },
      ),
    );
  }

  Widget _scoreCard(BuildContext c) {
    final cs = Theme.of(c).colorScheme;
    final you = beatModel.userRight;
    final model = beatModel.modelRight;
    final n = beatModel.graded;
    Widget side(String label, int v, bool primary) => Expanded(
          child: Column(children: [
            Text('$v',
                style: TextStyle(
                    fontSize: 44,
                    height: 1,
                    fontWeight: FontWeight.w800,
                    color: primary ? cs.primary : cs.onSurface.withOpacity(.75))),
            const SizedBox(height: 6),
            Text(label, style: TextStyle(fontSize: 13, color: cs.onSurface.withOpacity(.6))),
          ]),
        );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.4),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(children: [
        Text(n == 0 ? 'No calls graded yet' : 'Correct calls · out of $n',
            style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6))),
        const SizedBox(height: 14),
        Row(children: [
          side('You', you, true),
          Text('vs', style: TextStyle(color: cs.onSurface.withOpacity(.4))),
          side('Model', model, false),
        ]),
        if (beatModel.streak >= 2) ...[
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
                color: cs.primary.withOpacity(.14),
                borderRadius: BorderRadius.circular(999)),
            child: Text('🔥 ${beatModel.streak} correct in a row',
                style: TextStyle(
                    fontWeight: FontWeight.w700, color: cs.primary, fontSize: 13)),
          ),
        ],
      ]),
    );
  }

  Widget _verdict(BuildContext c) {
    final cs = Theme.of(c).colorScheme;
    final youBeat = beatModel.userBeatModel;
    final modelBeat = beatModel.modelBeatUser;
    String msg;
    if (youBeat > modelBeat) {
      msg = 'You\'re ahead — you\'ve out-called the model $youBeat time'
          '${youBeat == 1 ? '' : 's'} to $modelBeat. Impressive; that\'s hard to '
          'keep up over a full season.';
    } else if (modelBeat > youBeat) {
      msg = 'The model\'s ahead $modelBeat–$youBeat on calls only one of you got '
          'right. That\'s the norm — a calibrated model is tough to beat over time.';
    } else {
      msg = 'Dead level ($youBeat–$youBeat) on the calls that split you. '
          'Staying level with the model is genuinely good going.';
    }
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: cs.primary, width: 3)),
        color: cs.primary.withOpacity(.07),
      ),
      child: Text(msg,
          style: const TextStyle(fontWeight: FontWeight.w600, height: 1.45)),
    );
  }

  Widget _pendingRow(BuildContext c, Map p) {
    final cs = Theme.of(c).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.3),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(children: [
        Icon(Icons.schedule, size: 18, color: cs.onSurface.withOpacity(.5)),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${p['home']} v ${p['away']}',
                style: const TextStyle(fontWeight: FontWeight.w600)),
            Text(
                'You: ${outcomeLabel(p['user'] as String, p['home'] as String, p['away'] as String)}'
                '   ·   Model: ${outcomeLabel(p['model'] as String, p['home'] as String, p['away'] as String)}',
                style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6))),
          ]),
        ),
      ]),
    );
  }

  Widget _gradedRow(BuildContext c, Map h) {
    final cs = Theme.of(c).colorScheme;
    final home = h['home'] as String, away = h['away'] as String;
    final youRight = h['userRight'] == true;
    final modelRight = h['modelRight'] == true;
    Widget chip(String who, bool right) => Container(
          margin: const EdgeInsets.only(right: 6),
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(
            color: (right ? const Color(0xFF16B364) : const Color(0xFFE5484D))
                .withOpacity(.14),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text('$who ${right ? '✓' : '✗'}',
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: right ? const Color(0xFF16B364) : const Color(0xFFE5484D))),
        );
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.3),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text('$home v $away',
                style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
          Text('${outcomeLabel(h['result'] as String, home, away)} (${h['score'] ?? ''})',
              style: TextStyle(fontSize: 12, color: cs.onSurface.withOpacity(.6))),
        ]),
        const SizedBox(height: 6),
        Row(children: [chip('You', youRight), chip('Model', modelRight)]),
      ]),
    );
  }

  Widget _title(BuildContext c, String t) => Text(t,
      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800));

  Widget _empty(BuildContext c, Color muted) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.sports_esports_outlined, size: 44, color: muted),
            const SizedBox(height: 14),
            Text('Think you can beat the algorithm?',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
            const SizedBox(height: 8),
            Text(
                'Open any match and make your call. We\'ll track it against the '
                'model and grade you both when the result comes in.',
                textAlign: TextAlign.center,
                style: TextStyle(color: muted, height: 1.4)),
          ]),
        ),
      );
}
