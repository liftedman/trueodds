import 'package:flutter/material.dart';

/// A single plain-language reason behind a prediction.
class Reason {
  final IconData icon;
  final String text;
  const Reason(this.icon, this.text);
}

/// "Why this prediction" — shows the model's reasoning in plain language so the
/// number is never a black box.
class WhyThis extends StatelessWidget {
  final List<Reason> reasons;
  const WhyThis(this.reasons, {super.key});

  @override
  Widget build(BuildContext context) {
    if (reasons.isEmpty) return const SizedBox.shrink();
    final c = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(top: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.surfaceContainerHighest.withOpacity(.5),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: c.onSurface.withOpacity(.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(Icons.lightbulb_outline, size: 16, color: c.primary),
            const SizedBox(width: 6),
            Text('WHY THIS PREDICTION',
                style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 1.2,
                    fontWeight: FontWeight.w700,
                    color: c.primary)),
          ]),
          const SizedBox(height: 10),
          ...reasons.map((r) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(r.icon, size: 16, color: c.onSurface.withOpacity(.55)),
                  const SizedBox(width: 10),
                  Expanded(child: Text(r.text, style: const TextStyle(height: 1.35))),
                ]),
              )),
        ],
      ),
    );
  }
}

/// One honest sentence explaining what the confidence level actually means.
class ConfidenceNote extends StatelessWidget {
  final double topProb;
  const ConfidenceNote(this.topProb, {super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    final text = topProb >= .65
        ? 'The model leans clearly one way here — but upsets still happen.'
        : topProb >= .45
            ? 'A moderate lean. Treat it as a tilt, not a certainty.'
            : 'This is close to a coin-flip. No outcome is reliably favoured.';
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(text,
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: muted, fontStyle: FontStyle.italic)),
    );
  }
}

/// The honest footer shown on every prediction.
class ResponsibleNote extends StatelessWidget {
  const ResponsibleNote({super.key});

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(top: 20),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: c.surfaceContainerHighest.withOpacity(.4),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.shield_outlined, size: 18, color: c.onSurface.withOpacity(.5)),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'These are statistical estimates, not tips. No model beats the '
            'bookmakers over time — if it could, we would not give it away. '
            'Never bet more than you can afford to lose.',
            style: TextStyle(
                fontSize: 11.5,
                height: 1.4,
                color: c.onSurface.withOpacity(.6)),
          ),
        ),
      ]),
    );
  }
}
