/// Global team-name → crest-URL lookup, populated from the snapshot on load.
/// Teams without a crest fall back to the monogram avatar.
final Map<String, String> teamCrests = {};

void loadTeamCrests(Map data) {
  teamCrests.clear();
  (data['leagues'] as Map?)?.forEach((_, lg) {
    for (final t in (lg['teams'] as List? ?? const [])) {
      final c = t['crest'];
      if (c is String && c.isNotEmpty) {
        teamCrests[t['name'] as String] = c;
      }
    }
  });
}
