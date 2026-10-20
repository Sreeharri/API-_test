#!/usr/bin/env python3
"""Re-evaluate an old ZIP report locally. Does not call an API or overwrite the original."""
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import uuid
import zipfile
import benchmark as b


def rescore_zip(path,output):
    fixtures=json.loads((b.ROOT/'data'/'legal_radar_cases.json').read_text(encoding='utf-8'))
    by_id={c['id']:c for c in fixtures}
    with zipfile.ZipFile(path) as z:
        summaries=[n for n in z.namelist() if n.endswith('/summary.json')]
        top=min(summaries,key=lambda n:n.count('/'))
        metadata=json.loads(z.read(top))['metadata']
        prefix=top.rsplit('/',1)[0]+'/'
        rows=[json.loads(line) for line in z.read(prefix+'results.jsonl').decode('utf-8-sig').splitlines() if line.strip()]
    original=copy.deepcopy(metadata)
    run_id=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-rescored-'+uuid.uuid4().hex[:6]
    metadata.update({'run_id':run_id,'status':'retrospectively_rescored','original_run_id':original['run_id'],
                     'original_metadata':original,'scorer_version':b.SCORER_VERSION,
                     'rescore_note':'No new model requests. Allowed aliases were developed after reviewing earlier outputs; this is a retrospective diagnostic, not held-out evidence.',
                     'alias_fixture_sha256':hashlib.sha256((b.ROOT/'data'/'legal_radar_cases.json').read_bytes()).hexdigest()})
    reports=b.Reports(output/run_id,b.API({'models':[]}))
    for row in rows:
        if row['suite'] in ('quality','stability') and row['case_id'] in by_id:
            row['original_score']=copy.deepcopy(row.get('score'))
            row['score']=b.score(row['result'],by_id[row['case_id']])
        reports.add(row)
    b.dump(reports.path/'run.json',metadata)
    summary=reports.finish(metadata)
    return reports.path,summary


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_zip',type=Path)
    parser.add_argument('--output',type=Path,default=b.ROOT/'reports')
    args=parser.parse_args()
    path,_=rescore_zip(args.report_zip,args.output)
    print('Retrospective report (no new API calls): '+str(path.resolve()))

if __name__=='__main__':cli()
