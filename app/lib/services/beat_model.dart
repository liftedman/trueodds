import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Global store for the "Beat the Model" game: the user's picks, graded history
/// vs the model, and the running head-to-head. Persisted locally.
final beatModel = BeatModelStore();

String _key(String home, String away) => '$home␟$away';

/// Human label for an H/D/A code given the two team names.
String outcomeLabel(String code, String home, String away) =>
    code == 'H' ? home : (code == 'A' ? away : 'Draw');

class BeatModelStore extends ChangeNotifier {
  final Map<String, Map<String, dynamic>> _pending = {};
  final List<Map<String, dynamic>> _history = [];

  List<Map<String, dynamic>> get pending => _pending.values.toList();
  List<Map<String, dynamic>> get history => _history.reversed.toList();
  bool get hasActivity => _pending.isNotEmpty || _history.isNotEmpty;

  int get graded => _history.length;
  int get userRight => _history.where((h) => h['userRight'] == true).length;
  int get modelRight => _history.where((h) => h['modelRight'] == true).length;
  int get userBeatModel =>
      _history.where((h) => h['userRight'] == true && h['modelRight'] != true).length;
  int get modelBeatUser =>
      _history.where((h) => h['modelRight'] == true && h['userRight'] != true).length;

  /// Consecutive correct user picks from most recent backwards.
  int get streak {
    var s = 0;
    for (final h in history) {
      if (h['userRight'] == true) {
        s++;
      } else {
        break;
      }
    }
    return s;
  }

  /// The pending pick or graded record for a match, if any.
  Map<String, dynamic>? recordFor(String home, String away) {
    final k = _key(home, away);
    if (_pending.containsKey(k)) return _pending[k];
    for (final h in _history) {
      if (h['home'] == home && h['away'] == away) return h;
    }
    return null;
  }

  Future<void> makePick({
    required String sport,
    required String home,
    required String away,
    required String user,
    required String model,
    String? date,
  }) async {
    // can't change a pick once the match has been graded
    if (_history.any((h) => h['home'] == home && h['away'] == away)) return;
    _pending[_key(home, away)] = {
      'sport': sport, 'home': home, 'away': away,
      'user': user, 'model': model, 'date': date,
    };
    await _save();
    notifyListeners();
  }

  /// Grade any pending picks whose result has arrived in the snapshot.
  void grade(List? results) {
    if (results == null) return;
    var changed = false;
    for (final r in results.cast<Map>()) {
      final k = _key(r['home'] as String, r['away'] as String);
      final p = _pending[k];
      if (p == null) continue;
      final res = r['result'] as String; // H / D / A
      _history.add({
        'sport': p['sport'], 'home': p['home'], 'away': p['away'],
        'user': p['user'], 'model': p['model'], 'result': res,
        'score': r['score'],
        'userRight': p['user'] == res, 'modelRight': p['model'] == res,
      });
      _pending.remove(k);
      changed = true;
    }
    if (changed) {
      _save();
      notifyListeners();
    }
  }

  Future<void> load() async {
    try {
      final p = await SharedPreferences.getInstance();
      final pend = p.getString('btm_pending_v1');
      final hist = p.getString('btm_history_v1');
      if (pend != null) {
        (jsonDecode(pend) as Map).forEach(
            (k, v) => _pending[k as String] = Map<String, dynamic>.from(v));
      }
      if (hist != null) {
        for (final h in (jsonDecode(hist) as List)) {
          _history.add(Map<String, dynamic>.from(h));
        }
      }
    } catch (_) {/* start fresh */}
  }

  Future<void> _save() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString('btm_pending_v1', jsonEncode(_pending));
      await p.setString('btm_history_v1', jsonEncode(_history));
    } catch (_) {/* best effort */}
  }
}

/// The pick control shown on a match: tap to call it, then it's tracked vs the
/// model and graded when the result lands.
class BeatModelPick extends StatelessWidget {
  final String home, away, sport, modelPick;
  final bool allowDraw;
  final Color accent;
  const BeatModelPick({
    required this.home,
    required this.away,
    required this.sport,
    required this.modelPick,
    required this.accent,
    this.allowDraw = true,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final muted = cs.onSurface.withOpacity(.6);
    final options = allowDraw
        ? [('H', home), ('D', 'Draw'), ('A', away)]
        : [('H', home), ('A', away)];

    return ListenableBuilder(
      listenable: beatModel,
      builder: (context, _) {
        final rec = beatModel.recordFor(home, away);
        final userPick = rec?['user'] as String?;
        final graded = rec != null && rec.containsKey('result');
        final result = rec?['result'] as String?;

        return Container(
          margin: const EdgeInsets.only(top: 16),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: cs.surfaceContainerHighest.withOpacity(.5),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: cs.onSurface.withOpacity(.06)),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(Icons.sports_esports_outlined, size: 16, color: accent),
              const SizedBox(width: 6),
              Text('BEAT THE MODEL',
                  style: TextStyle(
                      fontSize: 11,
                      letterSpacing: 1.2,
                      fontWeight: FontWeight.w700,
                      color: accent)),
            ]),
            const SizedBox(height: 4),
            Text(
                userPick == null
                    ? 'Make your call. The model picked ${outcomeLabel(modelPick, home, away)} — can you do better?'
                    : graded
                        ? 'Full time: ${outcomeLabel(result!, home, away)}  (${rec['score'] ?? ''})'
                        : 'Locked in. We\'ll grade it against the model when it finishes.',
                style: TextStyle(fontSize: 12, color: muted, height: 1.35)),
            const SizedBox(height: 12),
            Row(
              children: [
                for (final o in options) ...[
                  Expanded(
                    child: _OptionButton(
                      label: o.$2,
                      selected: userPick == o.$1,
                      isModel: modelPick == o.$1,
                      // colour after grading: green if this outcome happened
                      correct: graded ? (result == o.$1) : null,
                      accent: accent,
                      onTap: graded
                          ? null
                          : () => beatModel.makePick(
                                sport: sport,
                                home: home,
                                away: away,
                                user: o.$1,
                                model: modelPick,
                              ),
                    ),
                  ),
                  if (o != options.last) const SizedBox(width: 8),
                ],
              ],
            ),
            if (userPick != null) ...[
              const SizedBox(height: 10),
              Row(children: [
                Expanded(
                    child: _tag(context, 'You',
                        outcomeLabel(userPick, home, away), accent)),
                const SizedBox(width: 8),
                Expanded(
                    child: _tag(context, 'Model',
                        outcomeLabel(modelPick, home, away),
                        cs.onSurface.withOpacity(.5))),
              ]),
              if (graded) ...[
                const SizedBox(height: 6),
                Text(userPick == result ? '✓ you called it' : '✗ missed',
                    style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: userPick == result
                            ? const Color(0xFF16B364)
                            : const Color(0xFFE5484D))),
              ],
            ],
          ]),
        );
      },
    );
  }

  Widget _tag(BuildContext c, String who, String pick, Color color) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('$who: ',
              style: TextStyle(fontSize: 12, color: Theme.of(c).colorScheme.onSurface.withOpacity(.6))),
          Flexible(
            child: Text(pick,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
          ),
        ],
      );
}

class _OptionButton extends StatelessWidget {
  final String label;
  final bool selected, isModel;
  final bool? correct; // null = not graded
  final Color accent;
  final VoidCallback? onTap;
  const _OptionButton({
    required this.label,
    required this.selected,
    required this.isModel,
    required this.correct,
    required this.accent,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Color border = cs.onSurface.withOpacity(.18);
    Color? fill;
    if (selected) {
      border = accent;
      fill = accent.withOpacity(.14);
    }
    if (correct == true) {
      border = const Color(0xFF16B364);
      fill = const Color(0xFF16B364).withOpacity(.14);
    }
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 6),
        decoration: BoxDecoration(
          color: fill,
          border: Border.all(color: border, width: selected || correct == true ? 1.5 : 1),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(children: [
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? accent : null)),
          if (isModel)
            Padding(
              padding: const EdgeInsets.only(top: 3),
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
