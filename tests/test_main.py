import pandas as pd

from sports_model import __version__, config
from sports_model.betting import staking, value
from sports_model.ingest import football
from sports_model.models import dixon_coles, elo, markets, nba_elo, tennis_elo


def test_version():
    assert __version__ == "0.1.0"


def test_leagues_configured():
    # The top-5 European leagues we start with.
    assert set(config.FOOTBALL_LEAGUES) == {"E0", "SP1", "D1", "I1", "F1"}


def test_odds_candidates_cover_all_outcomes():
    # Every odds family has home/draw/away fields with at least one candidate.
    expected = {
        f"{fam}{out}"
        for fam in ("b365", "avg")
        for out in ("h", "d", "a")
    } | {
        f"{fam}_{out}"
        for fam in ("max", "pso", "psc")
        for out in ("h", "d", "a")
    } | {
        f"{fam}_{out}"
        for fam in ("pso", "psc", "max")
        for out in ("ov", "un")
    }
    assert set(football._ODDS_CANDIDATES) == expected
    for candidates in football._ODDS_CANDIDATES.values():
        assert len(candidates) >= 1


def _toy_matches():
    # A tiny synthetic league where 'Strong' beats 'Weak' a lot at home.
    rows = []
    for _ in range(20):
        rows.append({"date": "2023-01-01", "home": "Strong", "away": "Weak",
                     "fthg": 3, "ftag": 0})
        rows.append({"date": "2023-01-01", "home": "Weak", "away": "Strong",
                     "fthg": 0, "ftag": 2})
    return pd.DataFrame(rows)


def test_model_predict_is_a_probability_distribution():
    model = dixon_coles.fit(_toy_matches())
    p = model.predict("Strong", "Weak")
    assert set(p) == {"H", "D", "A"}
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_model_learns_team_strength():
    # Strong at home should be favoured over Weak.
    model = dixon_coles.fit(_toy_matches())
    p = model.predict("Strong", "Weak")
    assert p["H"] > p["A"]


def test_unknown_team_falls_back_to_mean():
    # A promoted team never seen in training still yields a valid prediction.
    model = dixon_coles.fit(_toy_matches())
    p = model.predict("Strong", "BrandNewTeam")
    assert abs(sum(p.values()) - 1.0) < 1e-9


def test_xg_model_fits_and_disables_rho():
    # Build the same toy league but with xG columns instead of goals.
    df = _toy_matches()
    df["xg_h"] = df["fthg"].astype(float)
    df["xg_a"] = df["ftag"].astype(float)
    model = dixon_coles.fit(df, use_xg=True)
    assert model.rho == 0.0  # rho correction disabled for xG
    p = model.predict("Strong", "Weak")
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert p["H"] > p["A"]


def test_predict_totals_is_a_distribution():
    model = dixon_coles.fit(_toy_matches())
    p = model.predict_totals("Strong", "Weak")
    assert set(p) == {"OV", "UN"}
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_goal_markets_are_consistent():
    model = dixon_coles.fit(_toy_matches())
    mat = model.score_matrix("Strong", "Weak")
    m = markets.goal_markets(mat)
    # Over lines must be monotonically decreasing as the line rises.
    assert m["over_0.5"] >= m["over_1.5"] >= m["over_2.5"] >= m["over_3.5"]
    # Over + Under = 1 for each line; BTTS yes + no = 1.
    for line in ("0.5", "1.5", "2.5", "3.5"):
        assert abs(m[f"over_{line}"] + m[f"under_{line}"] - 1.0) < 1e-9
    assert abs(m["btts_yes"] + m["btts_no"] - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in m.values())


def test_result_markets_consistent():
    model = dixon_coles.fit(_toy_matches())
    mat = model.score_matrix("Strong", "Weak")
    r = markets.result_markets(mat)
    assert abs(r["dnb_home"] + r["dnb_away"] - 1.0) < 1e-9
    # Double chance 1X = 1 - away win; all probabilities valid.
    assert all(0.0 <= v <= 1.0 for v in r.values())
    # Strong (favoured) covers -1.5 more often than Weak does.
    assert r["home_hcap_15"] > r["away_hcap_15"]


def test_nba_spread_and_total_probs():
    model = nba_elo.fit(_toy_nba())  # AAA wins 120-100 repeatedly
    # AAA strongly favoured at home -> good chance to cover -5.5.
    assert model.cover_prob("AAA", "BBB", -5.5) > 0.5
    # Total over a very low line is near-certain; over a huge line near-zero.
    assert model.total_over_prob("AAA", "BBB", 50) > 0.95
    assert model.total_over_prob("AAA", "BBB", 400) < 0.05


def test_tennis_elo_surface_aware():
    import pandas as pd
    rows = []
    # AAA wins on Hard; BBB wins on Clay -> surface ratings should diverge.
    for i in range(30):
        rows.append({"date": f"2024-01-{i%28+1:02d}", "surface": "Hard",
                     "winner": "AAA", "loser": "BBB"})
        rows.append({"date": f"2024-06-{i%28+1:02d}", "surface": "Clay",
                     "winner": "BBB", "loser": "AAA"})
    model = tennis_elo.fit(pd.DataFrame(rows))
    hard = model.predict("AAA", "BBB", "Hard")
    clay = model.predict("AAA", "BBB", "Clay")
    assert abs(hard["a_win"] + hard["b_win"] - 1.0) < 1e-9
    # AAA stronger on hard than on clay.
    assert hard["a_win"] > clay["a_win"]


def test_value_bet_detected_only_with_positive_edge():
    probs = {"H": 0.55, "D": 0.25, "A": 0.20}
    # H: 0.55*2.10-1 = +0.155 (value). D: 0.25*3.0-1 = -0.25. A: 0.20*4.0-1=-0.20.
    odds = {"H": 2.10, "D": 3.0, "A": 4.0}
    bets = value.find_value_bets(probs, odds, min_edge=0.0)
    assert [b.outcome for b in bets] == ["H"]
    assert bets[0].edge > 0.15


def test_no_value_when_odds_too_short():
    probs = {"H": 0.55, "D": 0.25, "A": 0.20}
    odds = {"H": 1.50, "D": 3.0, "A": 4.0}  # 0.55*1.5-1 = -0.175
    assert value.find_value_bets(probs, odds, min_edge=0.0) == []


def test_kelly_zero_without_edge_and_capped():
    # No edge -> stake nothing.
    assert staking.kelly_fraction(0.40, 2.0) == 0.0
    # Huge edge -> still capped at the cap.
    assert staking.kelly_fraction(0.99, 5.0, fraction=1.0, cap=0.05) == 0.05


def _toy_internationals():
    import pandas as pd
    # Brazil beats Chile repeatedly; both also play draws elsewhere.
    rows = []
    for i in range(30):
        rows.append({"date": f"2000-01-{i%28+1:02d}", "home": "Brazil",
                     "away": "Chile", "home_score": 2, "away_score": 0,
                     "tournament": "Friendly", "neutral": 0})
    return pd.DataFrame(rows)


def test_elo_predict_distribution_and_favourite():
    model = elo.fit(_toy_internationals())
    p = model.predict("Brazil", "Chile", neutral=True)
    assert abs(p["H"] + p["D"] + p["A"] - 1.0) < 1e-9
    assert all(0.0 <= p[k] <= 1.0 for k in ("H", "D", "A"))
    # Brazil has won every meeting -> should be favoured.
    assert p["H"] > p["A"]
    assert model.rating("Brazil") > model.rating("Chile")


def test_elo_unknown_team_uses_default():
    model = elo.fit(_toy_internationals())
    p = model.predict("Brazil", "Atlantis", neutral=True)
    assert abs(p["H"] + p["D"] + p["A"] - 1.0) < 1e-9


def _toy_nba():
    import pandas as pd
    rows = []
    for i in range(40):
        rows.append({"date": f"2023-11-{i%28+1:02d}", "season": "2023-24",
                     "home": "AAA", "away": "BBB",
                     "home_pts": 120, "away_pts": 100})
    return pd.DataFrame(rows)


def test_nba_elo_predicts_win_prob_and_score():
    model = nba_elo.fit(_toy_nba())
    p = model.predict("AAA", "BBB")
    assert abs(p["home_win"] + p["away_win"] - 1.0) < 1e-9
    assert p["home_win"] > p["away_win"]          # AAA always wins
    assert model.rating("AAA") > model.rating("BBB")
    assert p["proj_home"] > p["proj_away"]         # projected to outscore
