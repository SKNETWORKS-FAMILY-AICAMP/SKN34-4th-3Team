"""Read-only lexical diagnostics for saved pre-answer results; no model calls."""
import json
from pathlib import Path
from elasticsearch import Elasticsearch
from src.core.config import get_settings
from src.rag.discovery import build_policy_initial_search_queries

def main():
    prefix = Path('evaluation/results/policy63_pre_answer_20261001_200558')
    report = json.loads(prefix.with_suffix('.json').read_text(encoding='utf-8'))
    settings = get_settings()
    es = Elasticsearch(settings.elasticsearch_url)
    index = settings.elasticsearch_index_alias
    diagnostics = []
    for row in report['cases']:
        if set(row['gold']) & set(row['top5']):
            continue
        ids = list(set(row['gold'] + row['top5']))
        hits = es.search(index=index, size=100, query={'terms': {'policy_id': ids}})['hits']['hits']
        documents = {str(pid): [h['_source'] for h in hits if h['_source']['policy_id'] == pid] for pid in ids}
        queries = build_policy_initial_search_queries(row['search_query'])
        if row['personalized_search_query']:
            queries.append(row['personalized_search_query'])
        ranks = []
        for query in queries:
            result = es.search(index=index, size=200, collapse={'field':'policy_id'}, query={'bool':{'must':[{'multi_match':{'query':query,'fields':['title','content'],'type':'cross_fields','minimum_should_match':'25%'}}], 'filter':[{'exists':{'field':'policy_id'}},{'terms':{'source_type':['policy','announcement']}}]}})['hits']['hits']
            ordered = [h['_source']['policy_id'] for h in result]
            tokens = es.indices.analyze(index=index, field='content', text=query)['tokens']
            ranks.append({'query':query,'tokens':[t['token'] for t in tokens], 'gold_ranks':{str(g):ordered.index(g)+1 if g in ordered else None for g in row['gold']}})
        title_tokens = {str(g): [t['token'] for t in es.indices.analyze(index=index,field='title',text=documents[str(g)][0]['title'])['tokens']] if documents[str(g)] else [] for g in row['gold']}
        category = 'retrieval_missing' if not (set(row['gold']) & (set(row['dense'])|set(row['bm25']))) else 'rrf_dropped' if not set(row['gold']) & set(row['rrf']) else 'rerank_below_top5'
        item = {'case_id':row['case_id'],'question':row['question'],'gold':row['gold'],'category':category,'ranks':{k:{str(g):row[k].index(g)+1 if g in row[k] else None for g in row['gold']} for k in ['dense','bm25','rrf','rerank','top5']},'queries':ranks,'gold_title_tokens':title_tokens,'documents':documents}
        diagnostics.append(item)
        print(json.dumps({'case':row['case_id'],'category':category,'gold':[(g,documents[str(g)][0]['title'] if documents[str(g)] else 'MISSING') for g in row['gold']],'ranks':item['ranks'],'lexical_ranks':[r['gold_ranks'] for r in ranks]},ensure_ascii=False),flush=True)
    Path(str(prefix)+'_diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    main()
