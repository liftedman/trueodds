part of '../predictors.dart';

// ------------------------------------------------- Club friendlies (exhibition)
/// Pre-season / mid-season friendlies, rated with the cross-league club Elo and
/// clearly flagged as a low-confidence exhibition (squads rotate). Fixtures are
/// tappable into the full prediction, like every other sport tab.
class FriendliesTab extends StatelessWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  const FriendliesTab(this.data, {required this.onRefresh, super.key});

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    final fr = (data['friendlies'] as Map?) ?? const {};
    final fixtures = (fr['fixtures'] as List?) ?? const [];
    final dropped = (fr['dropped'] as num?)?.toInt() ?? 0;

    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          _exhibitionBanner(context),
          _card(context,
              _fixturesSection(context, fixtures, accent,
                  data: data, sportKey: 'friendlies')),
          if (dropped > 0) _droppedNote(context, dropped),
          const ResponsibleNote(),
        ],
      ),
    );
  }

  Widget _exhibitionBanner(BuildContext c) {
    final cs = Theme.of(c).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest.withOpacity(.5),
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: cs.primary, width: 3)),
      ),
      child: Row(children: [
        Icon(Icons.info_outline, size: 18, color: cs.onSurface.withOpacity(.6)),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'Exhibition — pre-season friendlies. Squads rotate heavily and the '
            'result rarely reflects true strength, so treat these as '
            'low-confidence. Rated as neutral-venue games.',
            style: TextStyle(
                fontSize: 12, height: 1.35, color: cs.onSurface.withOpacity(.7)),
          ),
        ),
      ]),
    );
  }

  Widget _droppedNote(BuildContext c, int n) {
    final muted = Theme.of(c).colorScheme.onSurface.withOpacity(.6);
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Text(
        '$n more ${n == 1 ? 'friendly is' : 'friendlies are'} on the calendar '
        'against clubs we don\'t rate (lower divisions, tour sides). We leave '
        'them out rather than guess at a matchup we can\'t model honestly.',
        style: TextStyle(fontSize: 12, height: 1.35, color: muted),
      ),
    );
  }
}
