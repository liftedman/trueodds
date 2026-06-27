import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'config.dart';

/// Loads the latest prediction snapshot from Supabase, with a local cache so
/// the app opens instantly and keeps working with no signal.
class SnapshotApi {
  static const _cacheKey = 'snapshot_cache_v1';

  /// Returns the `data` object (leagues / wc / nba / tennis / cl) plus
  /// `updated_at`. On success the result is written to the local cache.
  /// Throws on network or auth error.
  static Future<Map<String, dynamic>> fetch() async {
    final resp = await http.get(
      Uri.parse(Config.snapshotUrl),
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
      throw Exception('No snapshot found — run `python -m sports_model.main push`.');
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
      // Caching is best-effort; ignore write failures.
    }
  }
}
