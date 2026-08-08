import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sports_model_app/services/config.dart';

/// Loads the Markets snapshot from Supabase.
///
/// Deliberately a separate row (id='markets') and a separate cache key from the
/// sports snapshot, so the two modes fail independently: a broken or stale
/// Markets build never stops Sports from loading, and vice versa.
class MarketsApi {
  static const _cacheKey = 'markets_cache_v1';

  /// Three rows, one request.
  ///
  /// `markets` is the full snapshot, rebuilt daily. `markets_prices` and
  /// `markets_record` are written far more often by the 15-minute job. They are
  /// separate rows on purpose: when the frequent writers patched the main blob
  /// instead, a concurrent full rebuild was silently reverted by whichever
  /// read-modify-write landed last. One row per writer removes the race, at the
  /// cost of this merge on read.
  static String get _url =>
      '${Config.supabaseUrl}/rest/v1/snapshot'
      '?select=id,data,updated_at'
      '&id=in.(markets,markets_prices,markets_record)';

  /// Fetches the latest snapshot and caches it. Throws on network/auth error.
  static Future<Map<String, dynamic>> fetch() async {
    final resp = await http.get(
      Uri.parse(_url),
      headers: {
        'apikey': Config.supabaseAnonKey,
        'Authorization': 'Bearer ${Config.supabaseAnonKey}',
      },
    ).timeout(const Duration(seconds: 30));

    if (resp.statusCode != 200) {
      throw Exception('Supabase ${resp.statusCode}: ${resp.body}');
    }
    final list = jsonDecode(resp.body) as List;
    final rows = {
      for (final r in list.cast<Map<String, dynamic>>()) r['id'] as String: r
    };
    final base = rows['markets'];
    if (base == null) {
      throw Exception(
          'No markets snapshot yet — run `python -m markets_model.main push`.');
    }

    final merged = _merge(
      base: base['data'] as Map<String, dynamic>,
      prices: rows['markets_prices']?['data'] as Map<String, dynamic>?,
      record: rows['markets_record']?['data'] as Map<String, dynamic>?,
    );

    // Newest of the three, so "last updated" reflects the freshest part.
    final updatedAt = list
        .map((r) => (r as Map)['updated_at'] as String)
        .reduce((a, b) => a.compareTo(b) >= 0 ? a : b);

    final row = {'data': merged, 'updated_at': updatedAt};
    await _save(row);
    return {'data': merged, 'updated_at': updatedAt};
  }

  /// Overlay the frequently-written rows onto the daily snapshot.
  ///
  /// Prices overwrite only price fields — never anything under `horizons`, so a
  /// minutes-old price can't make an hours-old forecast look current.
  static Map<String, dynamic> _merge({
    required Map<String, dynamic> base,
    Map<String, dynamic>? prices,
    Map<String, dynamic>? record,
  }) {
    if (prices != null) {
      final bySymbol = prices['prices'];
      if (bySymbol is Map) {
        for (final inst in (base['instruments'] as List? ?? const [])) {
          final p = bySymbol[(inst as Map)['symbol']];
          if (p is! Map) continue;
          inst['last'] = p['last'];
          inst['change'] = p['change'];
          inst['change_tf'] = p['change_tf'];
          inst['spark'] = p['spark'];
          inst['price_as_of'] = p['as_of'];
        }
      }
      if (prices['prices_updated'] != null) {
        base['prices_updated'] = prices['prices_updated'];
      }
    }
    if (record != null && record['live_record'] != null) {
      base['live_record'] = record['live_record'];
    }
    return base;
  }

  /// The last successfully fetched snapshot, or null if none cached yet.
  static Future<Map<String, dynamic>?> cached() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_cacheKey);
      if (raw == null) return null;
      final row = jsonDecode(raw) as Map<String, dynamic>;
      return {
        'data': row['data'] as Map<String, dynamic>,
        'updated_at': row['updated_at'],
      };
    } catch (_) {
      return null;
    }
  }

  static Future<void> _save(Map<String, dynamic> row) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_cacheKey, jsonEncode(row));
    } catch (_) {
      // Best-effort cache.
    }
  }
}
