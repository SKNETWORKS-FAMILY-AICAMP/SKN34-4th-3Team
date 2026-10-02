"""Trace saved policy misses with read-only retrieval; no router/reranker/generation."""

from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from src.core.config import get_settings
from src.evaluation.run_evaluation import validate_holdout_database
from src.models.factory import get_embedding_model
from src.rag.discovery import build_policy_initial_search_queries
from src.vectorstores.elasticsearch import ElasticsearchBM25Search
from src.vectorstores.nori_hybrid import source_level_rrf
from src.vectorstores.postgres import PostgresVectorSearch


def hit(row):
    return bool(set(row['gold']) & set(row['top5']))


def main():
    if 'default_transaction_read_only=on' not in os.environ.get('PGOPTIONS', ''):
        raise RuntimeError('Require read-only database transactions')
    settings = get_settings()
    baseline_path = Path('evaluation/results/policy63_pre_answer_20261001_200558.json')
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    weighted = json.loads(Path('evaluation/results/policy63_pre_answer_20261001_204940.json').read_text(encoding='utf-8'))
    weighted_rows = {r['case_id']: r for r in weighted['cases']}
    database = validate_holdout_database(settings=settings)
    if database != baseline['database']:
        raise RuntimeError('Database verification differs from baseline')
    dense_search = PostgresVectorSearch(get_embedding_model(settings), settings)
    bm25_search = ElasticsearchBM25Search(settings)
    stamp = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d_%H%M%S')
    prefix = Path('evaluation/results') / f'policy_rrf_trace_{stamp}'
    report = {'baseline': str(baseline_path), 'db_read_only': True, 'database': database,
              'started_at_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
              'pool_k': 40, 'rrf_k': 60, 'diagnostic_rank_depth': 200, 'cases': []}
    cases = [r for r in baseline['cases'] if not hit(r) or not hit(weighted_rows[r['case_id']])]
    print('TRACE_STAMP', stamp, 'CASES', len(cases), flush=True)
    for row in cases:
        queries = build_policy_initial_search_queries(row['search_query'])
        if row['personalized_search_query']:
            queries.append(row['personalized_search_query'])
        rankings, traces, contributions = [], [], defaultdict(list)
        for query_index, query in enumerate(queries):
            for backend, search in [('dense', dense_search), ('bm25', bm25_search)]:
                result = search.search(query, source_types=('policy', 'announcement'),
                                       require_policy_id=True, unique_policy_ids=True, top_k=200)
                pool = result[:40]
                rankings.append(pool)
                ordered = [int(d['policy_id']) for d in result]
                traces.append({'query_index': query_index, 'backend': backend, 'query': query,
                               'gold_ranks': {str(g): ordered.index(g)+1 if g in ordered else None for g in row['gold']},
                               'ranking': [{'policy_id': int(d['policy_id']), 'title': d['title'], 'score': d['score']} for d in result]})
                for rank, document in enumerate(pool, 1):
                    contributions[int(document['policy_id'])].append({'query_index': query_index,
                        'backend': backend, 'rank': rank, 'contribution': 1/(60+rank)})
        fused = source_level_rrf(rankings, unit='policy', rrf_k=60, top_k=10000)
        fused_ids = [int(d['policy_id']) for d in fused]
        cutoff = sum(x['contribution'] for x in contributions[fused_ids[19]]) if len(fused_ids) >= 20 else 0
        candidates = [{'policy_id': int(d['policy_id']), 'title': d['title'], 'rrf_rank': i,
                       'raw_score': sum(x['contribution'] for x in contributions[int(d['policy_id'])]),
                       'contributions': contributions[int(d['policy_id'])]} for i, d in enumerate(fused, 1)]
        item = {'case_id': row['case_id'], 'question': row['question'], 'gold': row['gold'],
                'baseline_hit': hit(row), 'weighted_hit': hit(weighted_rows[row['case_id']]),
                'queries': queries, 'traces': traces, 'rrf_cutoff_score': cutoff, 'candidates': candidates,
                'replay_top20': fused_ids[:20], 'saved_top20': row['rrf'],
                'same_top20_set': set(fused_ids[:20]) == set(row['rrf']),
                'gold_rrf_ranks': {str(g): fused_ids.index(g)+1 if g in fused_ids else None for g in row['gold']}}
        report['cases'].append(item)
        prefix.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('TRACE', len(report['cases']), '/', len(cases), row['case_id'],
              'queries', len(queries), 'gold_rrf', item['gold_rrf_ranks'],
              'same_top20_set', item['same_top20_set'], flush=True)
    report['finished_at_kst'] = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    report['status'] = 'complete'
    prefix.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('COMPLETE', str(prefix.with_suffix('.json')), flush=True)


if __name__ == '__main__':
    main()
