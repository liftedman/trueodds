import 'package:flutter/material.dart';
import 'favorites.dart';
import 'team_avatar.dart';

const _label = {
  'clubs': 'Club', 'wc': 'World Cup', 'nba': 'NBA', 'tennis': 'Tennis', 'cl': 'UCL'
};

/// Search every team/player across sports; follow with the star.
class TeamSearch extends SearchDelegate<String?> {
  final List<({String name, String sport})> _items;

  TeamSearch(Map data) : _items = _collect(data);

  static List<({String name, String sport})> _collect(Map data) {
    final seen = <String>{};
    final out = <({String name, String sport})>[];
    void add(String sport, Iterable names) {
      for (final n in names) {
        final key = '$sport|$n';
        if (seen.add(key)) out.add((name: n as String, sport: sport));
      }
    }
    (data['leagues'] as Map?)?.forEach((_, lg) =>
        add('clubs', (lg['teams'] as List).map((t) => t['name'])));
    add('wc', ((data['wc'] as Map?)?['teams'] as List? ?? []).map((t) => t['name']));
    add('cl', ((data['cl'] as Map?)?['teams'] as List? ?? []).map((t) => t['name']));
    add('nba', ((data['nba'] as Map?)?['teams'] as List? ?? []).map((t) => t['name']));
    add('tennis',
        ((data['tennis'] as Map?)?['players'] as List? ?? []).map((t) => t['name']));
    out.sort((a, b) => a.name.compareTo(b.name));
    return out;
  }

  @override
  List<Widget> buildActions(BuildContext context) => [
        if (query.isNotEmpty)
          IconButton(icon: const Icon(Icons.clear), onPressed: () => query = ''),
      ];

  @override
  Widget buildLeading(BuildContext context) => IconButton(
      icon: const Icon(Icons.arrow_back), onPressed: () => close(context, null));

  @override
  Widget buildResults(BuildContext context) => _list(context);

  @override
  Widget buildSuggestions(BuildContext context) => _list(context);

  Widget _list(BuildContext context) {
    final q = query.trim().toLowerCase();
    final results = q.isEmpty
        ? _items.where((e) => favorites.contains(e.name)).toList()
        : _items.where((e) => e.name.toLowerCase().contains(q)).take(60).toList();
    if (results.isEmpty) {
      return Center(
        child: Text(q.isEmpty ? 'Type a team or player' : 'No matches',
            style: TextStyle(
                color: Theme.of(context).colorScheme.onSurface.withOpacity(.6))),
      );
    }
    return ListView(
      children: results
          .map((e) => ListTile(
                leading: TeamAvatar(e.name, size: 34),
                title: Text(e.name),
                subtitle: Text(_label[e.sport] ?? e.sport),
                trailing: FavStar(e.sport, e.name),
              ))
          .toList(),
    );
  }
}
