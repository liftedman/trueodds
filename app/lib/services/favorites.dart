import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Followed teams/players, persisted on-device. Key = "sport|name".
class FavoritesStore extends ChangeNotifier {
  final Set<String> _keys = {};

  static String _k(String sport, String name) => '$sport|$name';

  bool isFav(String sport, String name) => _keys.contains(_k(sport, name));
  bool contains(String name) => _keys.any((k) => k.split('|').last == name);
  List<String> get all => _keys.toList();

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    _keys
      ..clear()
      ..addAll(p.getStringList('favs') ?? const []);
    notifyListeners();
  }

  Future<void> toggle(String sport, String name) async {
    final k = _k(sport, name);
    if (!_keys.add(k)) _keys.remove(k);
    notifyListeners();
    final p = await SharedPreferences.getInstance();
    await p.setStringList('favs', _keys.toList());
  }
}

/// Global instance (loaded in main()).
final favorites = FavoritesStore();

/// A follow/unfollow star that reflects and toggles favourite state.
class FavStar extends StatelessWidget {
  final String sport;
  final String name;
  final double size;
  const FavStar(this.sport, this.name, {this.size = 22, super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: favorites,
      builder: (context, _) {
        final on = favorites.isFav(sport, name);
        return IconButton(
          visualDensity: VisualDensity.compact,
          tooltip: on ? 'Following $name' : 'Follow $name',
          icon: Icon(on ? Icons.star_rounded : Icons.star_border_rounded,
              size: size, color: on ? const Color(0xFFE8A33D) : null),
          onPressed: () => favorites.toggle(sport, name),
        );
      },
    );
  }
}
