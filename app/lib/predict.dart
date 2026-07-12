import 'dart:math';

/// Prediction math — the Dart port of the models. Operates on the snapshot maps.

final List<double> _fact = () {
  final f = <double>[1];
  for (var k = 1; k <= 40; k++) {
    f.add(f[k - 1] * k);
  }
  return f;
}();

double _pois(int k, double lam) => pow(lam, k) * exp(-lam) / _fact[k];

double _d(dynamic v) => (v as num).toDouble();

/// Result of a scoreline-grid prediction (clubs, World Cup, UCL).
class GridResult {
  final double home, draw, away, lh, la;
  final Map<String, double> goals; // Over 0.5/1.5/2.5/3.5 + BTTS
  final Map<String, double> result; // double chance / DNB / handicap / CS / TT
  final List<MapEntry<String, double>> scorelines;
  GridResult(this.home, this.draw, this.away, this.lh, this.la, this.goals,
      this.result, this.scorelines);
}

GridResult _grid(double lh, double la) {
  const maxG = 10;
  final ph = <double>[], pa = <double>[];
  for (var k = 0; k <= maxG; k++) {
    ph.add(_pois(k, lh));
    pa.add(_pois(k, la));
  }
  double sum = 0;
  final mat = <List<double>>[];
  for (var i = 0; i <= maxG; i++) {
    final row = <double>[];
    for (var j = 0; j <= maxG; j++) {
      final p = ph[i] * pa[j];
      row.add(p);
      sum += p;
    }
    mat.add(row);
  }
  double h = 0, d = 0, a = 0, o05 = 0, o15 = 0, o25 = 0, o35 = 0, btts = 0;
  double hcapH = 0, hcapA = 0, csH = 0, csA = 0, ttH = 0, ttA = 0;
  final scores = <MapEntry<String, double>>[];
  for (var i = 0; i <= maxG; i++) {
    for (var j = 0; j <= maxG; j++) {
      final p = mat[i][j] / sum;
      if (i > j) {
        h += p;
      } else if (i == j) {
        d += p;
      } else {
        a += p;
      }
      if (i + j > 0) o05 += p;
      if (i + j > 1) o15 += p;
      if (i + j > 2) o25 += p;
      if (i + j > 3) o35 += p;
      if (i >= 1 && j >= 1) btts += p;
      if (i - j >= 2) hcapH += p;
      if (j - i >= 2) hcapA += p;
      if (j == 0) csH += p; // home clean sheet (away scores 0)
      if (i == 0) csA += p;
      if (i >= 2) ttH += p;
      if (j >= 2) ttA += p;
      scores.add(MapEntry('$i–$j', p));
    }
  }
  scores.sort((x, y) => y.value.compareTo(x.value));
  final ha = (h + a) == 0 ? 1 : (h + a);
  return GridResult(h, d, a, lh, la, {
    'Over 0.5': o05, 'Over 1.5': o15, 'Over 2.5': o25, 'Over 3.5': o35,
    'BTTS': btts,
  }, {
    '1X': h + d, '12': h + a, 'X2': d + a,
    'DNB home': h / ha, 'DNB away': a / ha,
    'Home -1.5': hcapH, 'Away -1.5': hcapA,
    'Home CS': csH, 'Away CS': csA,
    'Home o1.5': ttH, 'Away o1.5': ttA,
  }, scores.take(5).toList());
}

double _poisOver(double lam, double line) {
  double cum = 0;
  for (var k = 0; k <= line.floor(); k++) {
    cum += _pois(k, lam);
  }
  return 1 - cum;
}

/// Standard-normal CDF (Abramowitz-Stegun approximation) for NBA spread/totals.
double _ncdf(double x) {
  final t = 1 / (1 + 0.2316419 * x.abs());
  final dd = 0.3989423 * exp(-x * x / 2);
  final p = dd *
      t *
      (0.3193815 +
          t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}

/// Corners & cards markets for a club matchup, from the two teams' rates.
/// Returns null if the rate data isn't present (older snapshot).
({double corners, double cards, Map<String, double> cornerO, Map<String, double> cardO})?
    clubCounts(Map h, Map a) {
  if (h['cf'] == null || a['cf'] == null) return null;
  double r(Map m, String k) => (m[k] as num).toDouble();
  final corners = (r(h, 'cf') + r(a, 'ca')) / 2 + (r(a, 'cf') + r(h, 'ca')) / 2;
  final cards = (r(h, 'kf') + r(a, 'ka')) / 2 + (r(a, 'kf') + r(h, 'ka')) / 2;
  return (
    corners: corners,
    cards: cards,
    cornerO: {for (final l in [8.5, 9.5, 10.5, 11.5]) 'O$l': _poisOver(corners, l)},
    cardO: {for (final l in [2.5, 3.5, 4.5, 5.5]) 'O$l': _poisOver(cards, l)},
  );
}

/// Recent form (W/D/L, newest first) from the embedded match log.
List<String> teamForm(List log, String team, [int n = 5]) {
  final res = <String>[];
  for (final m in log) {
    final hg = (m[3] as num), ag = (m[4] as num);
    if (m[1] == team) {
      res.add(hg > ag ? 'W' : (hg == ag ? 'D' : 'L'));
    } else if (m[2] == team) {
      res.add(ag > hg ? 'W' : (ag == hg ? 'D' : 'L'));
    }
  }
  final last = res.length > n ? res.sublist(res.length - n) : res;
  return last.reversed.toList();
}

/// Recent head-to-head meetings (newest first) as "date: H x-y A".
List<String> h2hMeetings(List log, String home, String away, [int n = 5]) {
  final out = <String>[];
  for (final m in log) {
    if ((m[1] == home && m[2] == away) || (m[1] == away && m[2] == home)) {
      out.add('${m[0]}: ${m[1]} ${m[3]}-${m[4]} ${m[2]}');
    }
  }
  final last = out.length > n ? out.sublist(out.length - n) : out;
  return last.reversed.toList();
}

class Predict {
  /// Clubs — Dixon-Coles on attack/defence.
  static GridResult club(Map league, String home, String away,
      {int outHome = 0, int outAway = 0}) {
    final teams = (league['teams'] as List).cast<Map>();
    Map find(String n) => teams.firstWhere((t) => t['name'] == n,
        orElse: () => {'attack': 0.0, 'defence': 0.0});
    final h = find(home), a = find(away);
    final adv = _d(league['home_adv']);
    final lh = exp((_d(h['attack']) - 0.07 * outHome) +
        (_d(a['defence']) + 0.05 * outAway) + adv);
    final la = exp((_d(a['attack']) - 0.07 * outAway) +
        (_d(h['defence']) + 0.05 * outHome));
    return _grid(lh, la);
  }

  /// World Cup / UCL — Elo with goals derived from the rating gap.
  static GridResult elo(Map sport, double eloH, double eloA, bool neutral,
      {int outHome = 0, int outAway = 0}) {
    final adv = neutral ? 0.0 : _d(sport['home_adv']);
    final dr = (eloH - 40 * outHome) - (eloA - 40 * outAway) + adv;
    final total = max(1.2, _d(sport['total_base']) + _d(sport['total_gap']) * dr.abs());
    final sup = _d(sport['sup_slope']) * dr;
    return _grid(max(0.12, (total + sup) / 2), max(0.12, (total - sup) / 2));
  }

  /// In-play result probabilities: given the pre-match expected goals [lh]/[la],
  /// the current score, and minutes played, project the FINAL result. Remaining
  /// goals follow Poisson over the fraction of the match still to play — so as
  /// time runs down with a lead, the leader's probability firms toward certainty.
  static ({double home, double draw, double away}) inPlay(
      double lh, double la, int homeGoals, int awayGoals, int minute) {
    final remaining = (90 - minute).clamp(0, 90) / 90.0;
    final rlh = lh * remaining, rla = la * remaining; // expected remaining goals
    const maxG = 10;
    final ph = [for (var k = 0; k <= maxG; k++) _pois(k, rlh)];
    final pa = [for (var k = 0; k <= maxG; k++) _pois(k, rla)];
    double h = 0, d = 0, a = 0, sum = 0;
    for (var i = 0; i <= maxG; i++) {
      for (var j = 0; j <= maxG; j++) {
        final p = ph[i] * pa[j];
        sum += p;
        final fh = homeGoals + i, fa = awayGoals + j;
        if (fh > fa) {
          h += p;
        } else if (fh == fa) {
          d += p;
        } else {
          a += p;
        }
      }
    }
    return (home: h / sum, draw: d / sum, away: a / sum);
  }

  /// P(home win) sampled from [fromMinute] to full time (holding the current
  /// score) — the forward curve that visualises how the result firms up.
  static List<double> inPlayHomeCurve(
      double lh, double la, int homeGoals, int awayGoals, int fromMinute) {
    final pts = <double>[];
    for (var m = fromMinute.clamp(0, 90); m <= 90; m += 5) {
      pts.add(inPlay(lh, la, homeGoals, awayGoals, m).home);
    }
    return pts;
  }

  /// NBA — win probability + projected score.
  static ({double homeWin, double awayWin, double projHome, double projAway})
      nba(Map nba, double eloH, double eloA, bool neutral,
          {int outHome = 0, int outAway = 0}) {
    final adv = neutral ? 0.0 : _d(nba['home_adv']);
    final dr = (eloH - 40 * outHome) - (eloA - 40 * outAway) + adv;
    final pHome = 1 / (1 + pow(10, -dr / 400));
    final margin = _d(nba['margin_slope']) * dr;
    final mt = _d(nba['mean_total']);
    return (
      homeWin: pHome.toDouble(),
      awayWin: (1 - pHome).toDouble(),
      projHome: (mt + margin) / 2,
      projAway: (mt - margin) / 2,
    );
  }

  /// NBA point-spread cover probabilities (home perspective).
  static Map<String, double> nbaSpread(
      Map nba, double eloH, double eloA, bool neutral,
      {int outHome = 0, int outAway = 0}) {
    final adv = neutral ? 0.0 : _d(nba['home_adv']);
    final dr = (eloH - 40 * outHome) - (eloA - 40 * outAway) + adv;
    final margin = _d(nba['margin_slope']) * dr;
    final std = _d(nba['margin_std']);
    double cover(double line) => 1 - _ncdf((line - margin) / std);
    return {
      'Home -5.5': cover(5.5),
      'Home -10.5': cover(10.5),
      'Home +5.5': cover(-5.5),
    };
  }

  /// NBA total-points over probabilities.
  static Map<String, double> nbaTotals(Map nba) {
    final mt = _d(nba['mean_total']);
    final std = _d(nba['total_std']);
    double over(double line) => 1 - _ncdf((line - mt) / std);
    return {
      'Over 215.5': over(215.5),
      'Over 225.5': over(225.5),
      'Over 235.5': over(235.5),
    };
  }

  /// In-play win probability for a basketball game. Projects the final margin
  /// as (current margin + expected remaining margin) and firms up as the clock
  /// winds down (spread shrinks with the square root of time left).
  static ({double home, double away}) inPlayBasketball(Map m, double eloH,
      double eloA, int homeScore, int awayScore, double fracLeft) {
    final dr = eloH - eloA + _d(m['home_adv']);
    final expMargin = _d(m['margin_slope']) * dr;
    final curMargin = (homeScore - awayScore).toDouble();
    if (fracLeft <= 0.0) {
      final h = curMargin > 0 ? 1.0 : (curMargin < 0 ? 0.0 : 0.5);
      return (home: h, away: 1 - h);
    }
    final proj = curMargin + expMargin * fracLeft;
    final sd = _d(m['margin_std']) * sqrt(fracLeft);
    final pHome = (1 - _ncdf((0 - proj) / sd)).clamp(0.0, 1.0);
    return (home: pHome, away: 1 - pHome);
  }

  /// P(home win) sampled from now (fracLeft) to full time, holding the current
  /// score — the "if the lead holds" curve for the live block.
  static List<double> inPlayBasketballCurve(Map m, double eloH, double eloA,
      int homeScore, int awayScore, double fracLeft) {
    const steps = 8;
    return [
      for (var i = 0; i <= steps; i++)
        inPlayBasketball(m, eloH, eloA, homeScore, awayScore,
                fracLeft * (1 - i / steps))
            .home,
    ];
  }

  /// Total-points over lines derived from a league's own average total, so the
  /// same code gives sensible lines for the NBA (~225) and the WNBA (~160).
  static Map<String, double> totalsAround(Map m) {
    final mt = _d(m['mean_total']);
    final std = _d(m['total_std']);
    final base = mt.floorToDouble() + 0.5; // an x.5 line near the mean
    double over(double line) => 1 - _ncdf((line - mt) / std);
    return {
      for (final l in [base - 5, base, base + 5]) 'Over ${l.toStringAsFixed(1)}': over(l),
    };
  }

  /// Per-team points over/under. A team's score ~ Normal(projected, σ) where
  /// σ = total_std/√2 (splitting the total's spread between the two teams).
  /// Labels use each team's short name (e.g. "Aces o84.5").
  static Map<String, double> teamTotals(Map m, double eloH, double eloA,
      bool neutral, String home, String away,
      {int outHome = 0, int outAway = 0}) {
    final res = nba(m, eloH, eloA, neutral, outHome: outHome, outAway: outAway);
    final std = _d(m['total_std']) / sqrt(2);
    double over(double proj, double line) => 1 - _ncdf((line - proj) / std);
    String short(String n) => n.split(' ').last;
    double base(double p) => p.floorToDouble() + 0.5;
    final hb = base(res.projHome), ab = base(res.projAway);
    return {
      '${short(home)} o${(hb - 4).toStringAsFixed(1)}': over(res.projHome, hb - 4),
      '${short(home)} o${(hb + 4).toStringAsFixed(1)}': over(res.projHome, hb + 4),
      '${short(away)} o${(ab - 4).toStringAsFixed(1)}': over(res.projAway, ab - 4),
      '${short(away)} o${(ab + 4).toStringAsFixed(1)}': over(res.projAway, ab + 4),
    };
  }

  /// NFL — win prob + projected score. Same Elo-margin model as the NBA one.
  static ({double homeWin, double awayWin, double projHome, double projAway})
      nfl(Map nfl, double eloH, double eloA, bool neutral,
          {int outHome = 0, int outAway = 0}) =>
          nba(nfl, eloH, eloA, neutral, outHome: outHome, outAway: outAway);

  /// NFL point-spread cover probabilities (home perspective).
  static Map<String, double> nflSpread(
      Map nfl, double eloH, double eloA, bool neutral,
      {int outHome = 0, int outAway = 0}) {
    final adv = neutral ? 0.0 : _d(nfl['home_adv']);
    final dr = (eloH - 40 * outHome) - (eloA - 40 * outAway) + adv;
    final margin = _d(nfl['margin_slope']) * dr;
    final std = _d(nfl['margin_std']);
    double cover(double line) => 1 - _ncdf((line - margin) / std);
    return {
      'Home -3.5': cover(3.5),
      'Home -7.5': cover(7.5),
      'Home +3.5': cover(-3.5),
    };
  }

  /// NFL total-points over probabilities.
  static Map<String, double> nflTotals(Map nfl) {
    final mt = _d(nfl['mean_total']);
    final std = _d(nfl['total_std']);
    double over(double line) => 1 - _ncdf((line - mt) / std);
    return {
      'Over 41.5': over(41.5),
      'Over 44.5': over(44.5),
      'Over 47.5': over(47.5),
    };
  }

  /// Tennis — surface-aware blended Elo.
  static double tennis(Map t, Map a, Map b, String surface) {
    double blend(Map p) {
      final ov = _d(p['elo']);
      final sv = _d(surface == 'Clay'
          ? p['clay']
          : surface == 'Grass'
              ? p['grass']
              : p['hard']);
      final w = _d(t['surface_weight']);
      return w * sv + (1 - w) * ov;
    }
    final ra = blend(a), rb = blend(b);
    return (1 / (1 + pow(10, -(ra - rb) / 400))).toDouble();
  }
}
