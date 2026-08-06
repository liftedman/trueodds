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

  static String get _url =>
      '${Config.supabaseUrl}/rest/v1/snapshot?select=data,updated_at&id=eq.markets';

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
    if (list.isEmpty) {
      throw Exception(
          'No markets snapshot yet — run `python -m markets_model.main push`.');
    }
    final row = list.first as Map<String, dynamic>;
    final result = {
      'data': row['data'] as Map<String, dynamic>,
      'updated_at': row['updated_at'],
    };
    await _save(row);
    return result;
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
