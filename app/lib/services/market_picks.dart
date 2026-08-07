import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sports_model_app/services/config.dart';

/// "You vs the model" for Markets mode.
///
/// The point of this is not entertainment. Someone new to trading has no way to
/// find out whether their intuition beats a coin flip, and every incentive in
/// the industry is against them finding out. Fifty logged calls answers it for
/// free, and it is the one lesson that reliably changes behaviour.
///
/// HOW GRADING STAYS HONEST
///
/// A pick is keyed to (symbol, timeframe, made_at_ts) — the exact bar the
/// forward test logged its own forecast against. So the user and the model are
/// settled from the SAME resolved row in `paper_predictions`, by identical
/// arithmetic. No separate price lookup, no approximation, and no way for the
/// two sides of the comparison to disagree.
///
/// A pick can only be made while the forecast window is still open, which is the
/// same guard the logger uses. That means the outcome cannot already be known at
/// the moment of picking.
final marketPicks = MarketPicksStore();

String _pickKey(String symbol, String timeframe, int madeAtTs) =>
    '$symbol␟$timeframe␟$madeAtTs';

/// Who called it right.
///
/// A DOWN call that comes off is a win — scoring only UP calls would flatter or
/// punish either side depending on which way the market happened to drift. The
/// model is credited with UP whenever p_up > 0.5, matching exactly how the
/// backtest and the forward test score it, so the three numbers a user sees can
/// never disagree with each other.
({bool userRight, bool modelRight}) scorePick({
  required bool userUp,
  required double modelPUp,
  required bool actualUp,
}) =>
    (userRight: userUp == actualUp, modelRight: (modelPUp > 0.5) == actualUp);

class MarketPicksStore extends ChangeNotifier {
  static const _pendingKey = 'mkt_picks_pending_v1';
  static const _historyKey = 'mkt_picks_history_v1';

  final Map<String, Map<String, dynamic>> _pending = {};
  final List<Map<String, dynamic>> _history = [];

  List<Map<String, dynamic>> get pending => _pending.values.toList();
  List<Map<String, dynamic>> get history => _history.reversed.toList();
  bool get hasActivity => _pending.isNotEmpty || _history.isNotEmpty;

  int get graded => _history.length;
  int get userRight => _history.where((h) => h['userRight'] == true).length;
  int get modelRight => _history.where((h) => h['modelRight'] == true).length;
  int get userBeatModel => _history
      .where((h) => h['userRight'] == true && h['modelRight'] != true)
      .length;
  int get modelBeatUser => _history
      .where((h) => h['modelRight'] == true && h['userRight'] != true)
      .length;

  double? get userHitRate => graded == 0 ? null : userRight / graded;
  double? get modelHitRate => graded == 0 ? null : modelRight / graded;

  /// Consecutive correct calls, most recent backwards.
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

  Map<String, dynamic>? recordFor(String symbol, String timeframe, int madeAtTs) {
    final k = _pickKey(symbol, timeframe, madeAtTs);
    if (_pending.containsKey(k)) return _pending[k];
    for (final h in _history) {
      if (h['symbol'] == symbol &&
          h['timeframe'] == timeframe &&
          h['made_at_ts'] == madeAtTs) {
        return h;
      }
    }
    return null;
  }

  Future<void> makePick({
    required String symbol,
    required String name,
    required String timeframe,
    required int madeAtTs,
    required int settlesAt,
    required double refClose,
    required bool userUp,
    required double modelPUp,
  }) async {
    final k = _pickKey(symbol, timeframe, madeAtTs);
    // Never let a graded call be rewritten — that would turn the record into
    // a story rather than a measurement.
    if (_history.any((h) =>
        h['symbol'] == symbol &&
        h['timeframe'] == timeframe &&
        h['made_at_ts'] == madeAtTs)) {
      return;
    }
    _pending[k] = {
      'symbol': symbol,
      'name': name,
      'timeframe': timeframe,
      'made_at_ts': madeAtTs,
      'settles_at': settlesAt,
      'ref_close': refClose,
      'userUp': userUp,
      'modelPUp': modelPUp,
    };
    await _save();
    notifyListeners();
  }

  /// Grade pending picks whose logged row has been resolved upstream.
  ///
  /// Reads `paper_predictions` with the anon key (public SELECT). Only rows the
  /// forward test has already settled are returned, so this cannot grade
  /// anything early.
  Future<void> grade() async {
    if (_pending.isEmpty) return;

    final due = _pending.values.where((p) {
      final s = p['settles_at'];
      return s is int &&
          (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000) >= s;
    }).toList();
    if (due.isEmpty) return;

    final symbols = due.map((p) => p['symbol'] as String).toSet().toList();
    final cutoffs = due.map((p) => p['made_at_ts'] as int).toSet().toList();

    late final List rows;
    try {
      // Fetched WITHOUT filtering on actual_up, deliberately. We need to tell
      // "the row exists but hasn't settled" apart from "the row is gone" — only
      // the second means the pick can never be graded, and treating the first as
      // the second would silently discard live calls.
      final uri = Uri.parse('${Config.supabaseUrl}/rest/v1/paper_predictions'
          '?select=symbol,timeframe,made_at_ts,actual_up,settle_close'
          '&symbol=in.(${symbols.join(',')})'
          '&made_at_ts=in.(${cutoffs.join(',')})');
      final resp = await http.get(uri, headers: {
        'apikey': Config.supabaseAnonKey,
        'Authorization': 'Bearer ${Config.supabaseAnonKey}',
      }).timeout(const Duration(seconds: 25));
      if (resp.statusCode != 200) return;
      rows = jsonDecode(resp.body) as List;
    } catch (_) {
      return; // offline or table absent — try again next refresh
    }

    var changed = false;
    final seenUpstream = <String>{};

    for (final r in rows.cast<Map>()) {
      final k = _pickKey(
          r['symbol'] as String, r['timeframe'] as String, r['made_at_ts'] as int);
      seenUpstream.add(k);
      final p = _pending[k];
      if (p == null) continue;
      if (r['actual_up'] == null) continue; // logged, not yet settled

      final actualUp = r['actual_up'] == true;
      final s = scorePick(
        userUp: p['userUp'] == true,
        modelPUp: (p['modelPUp'] as num).toDouble(),
        actualUp: actualUp,
      );

      _history.add({
        ...p,
        'actualUp': actualUp,
        'settle_close': r['settle_close'],
        'userRight': s.userRight,
        'modelRight': s.modelRight,
      });
      _pending.remove(k);
      changed = true;
    }

    // Void: long overdue AND no upstream row at all. A forecast logged just
    // before a market closes targets a bar that never forms (FX stops on Friday
    // evening), so it can never settle. Dropping it is the honest handling —
    // scoring it either way would put a coin flip into a record whose entire
    // value is that it contains only real outcomes.
    final nowSecs = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
    for (final p in due) {
      final k = _pickKey(
          p['symbol'] as String, p['timeframe'] as String, p['made_at_ts'] as int);
      if (seenUpstream.contains(k) || !_pending.containsKey(k)) continue;
      final grace = 3 * _barSeconds(p['timeframe'] as String);
      if (nowSecs - (p['settles_at'] as int) > grace) {
        _pending.remove(k);
        changed = true;
      }
    }

    if (changed) {
      await _save();
      notifyListeners();
    }
  }

  static int _barSeconds(String timeframe) => switch (timeframe) {
        '1m' => 60,
        '5m' => 300,
        '15m' => 900,
        '1h' => 3600,
        '4h' => 14400,
        '1d' => 86400,
        _ => 3600,
      };

  Future<void> load() async {
    try {
      final p = await SharedPreferences.getInstance();
      final pend = p.getString(_pendingKey);
      final hist = p.getString(_historyKey);
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
      await p.setString(_pendingKey, jsonEncode(_pending));
      await p.setString(_historyKey, jsonEncode(_history));
    } catch (_) {/* best effort */}
  }
}
