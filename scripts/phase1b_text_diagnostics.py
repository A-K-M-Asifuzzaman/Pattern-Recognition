"""Unfitted question-endpoint text probes and task/operation descriptive strata."""
import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from phase1b_audit import auc,binary,table,save

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('outputs/phase1b'))
out=parser.parse_args().output
rs=list(csv.DictReader((out/'edited_question_features.csv').open()))
for r in rs:
    r['relevant']=int(r['relevant'])
    r['source_lexical_code']=256*ord(r['source'][0])+ord(r['source'][1])
    r['target_lexical_code']=256*ord(r['target'][0])+ord(r['target'][1])
rules=[('source_lexically_before_target',lambda r:r['source']<r['target']),
       ('source_initial_A_to_M',lambda r:r['source'][0]<='M'),
       ('target_initial_A_to_M',lambda r:r['target'][0]<='M'),
       ('same_endpoint_initial',lambda r:r['source'][0]==r['target'][0])]
result=[]; ranks=[]
for split in ['train','validation','test']:
    sample=[r for r in rs if r['split']==split]
    for name,predicate in rules: result.append({'split':split,'rule':name,**binary(sample,predicate)})
    for key in ['source_lexical_code','target_lexical_code']:
        rng=random.Random(20261027); gids=sorted({r['group_id'] for r in sample});scores=[]
        for _ in range(300):
            draws=rng.choices(gids,k=len(gids));drawn=[r for gid in draws for r in sample if r['group_id']==gid]
            value=auc(drawn,key)
            if value is not None:scores.append(value)
        scores.sort()
        ranks.append({'split':split,'feature':key,'auroc_increasing_feature':auc(sample,key),
                      'group_bootstrap_95_low':scores[int(.025*(len(scores)-1))],'group_bootstrap_95_high':scores[int(.975*(len(scores)-1))]})
strata=[]
for split in ['train','validation','test']:
    for task in ['reachability','shortest_path','direct_edge']:
        for operation in ['addition','deletion','reversal']:
            sample=[r for r in rs if r['split']==split and r['task']==task and r['operation']==operation]
            if sample:strata.append({'split':split,'task':task,'operation':operation,'relevant':sum(r['relevant'] for r in sample),
                                    'irrelevant':sum(not r['relevant'] for r in sample),'change_rate':sum(r['relevant'] for r in sample)/len(sample)})
table(out/'shortcut_endpoint_rules.csv',result)
table(out/'shortcut_endpoint_ranks.csv',ranks)
table(out/'shortcut_task_operation_rates.csv',strata)
save(out/'text_probe_protocol.json',{'fitting':'none','split_unit':'original group, existing train/validation/test assignments',
                                    'all_rules_reported':True,'endpoint_rank_direction':'increasing lexical code only','bootstrap':'300 whole-group resamples per split',
                                    'scope':'Template/task, character length, endpoint initials and lexical ordering. No exhaustive n-gram search or trained text model.'})
