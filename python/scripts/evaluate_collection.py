"""Fixed-seed economy benchmark; no account files or live balances are touched.

Run from repository root: PYTHONPATH=python python python/scripts/evaluate_collection.py
Reports independent new accounts that stay in one category until collection completes.
Includes board movement, special cells, both pity counters and three initial tickets.
"""
import json
import random
from statistics import mean, median
from morning_bloom import gacha_board as board


def evaluate(trials=500):
    output = {}
    for category, tiers in board.REWARDS.items():
        totals, targets = [], []
        target = 'rose' if category == 'pot' else 'lavender' if category == 'garden' else 'catalog_plant_000'
        expected = {key for pool in tiers.values() for key in pool}
        for trial in range(trials):
            rng = random.Random(20261103 + trial)
            state, seen, first = board.initial_state(), set(), None
            while seen != expected:
                result = board._next(state, rng.randrange)
                pool = tiers[result['rarity']]
                item = pool[rng.randrange(len(pool))]
                seen.add(item)
                if item == target and first is None:
                    first = state['total']
            totals.append(state['total'])
            targets.append(first)
        ordered = sorted(totals)
        output[category] = {
            'trials': trials, 'pool': len(expected), 'target': target,
            'target_mean_draws': round(mean(targets), 2),
            'collection_mean_draws': round(mean(totals), 2),
            'collection_median_draws': median(totals),
            'collection_p90_draws': ordered[int(.9 * trials) - 1],
            'mean_sunlight_after_initial_tickets': round(mean(max(0, n - 3) * board.PRICE for n in totals), 2),
        }
    return output


if __name__ == '__main__':
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
