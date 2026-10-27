"""Descriptive shortcut associations; no fitted predictor or model execution."""
import math
from collections import Counter, defaultdict

from .build import records, write
from .reports import counted, table


def image_statistics(image):
    hist=image.convert('L').histogram();total=sum(hist);mean=sum(i*n for i,n in enumerate(hist))/total
    background=image.getpixel((0,0))[0]
    return {'mean_gray':mean,'gray_std':math.sqrt(sum(n*(i-mean)**2 for i,n in enumerate(hist))/total),
            'nonbackground_fraction':1-hist[background]/total}


def bin_value(value,thresholds):
    return str(sum(value>=boundary for boundary in thresholds))


def association(counts):
    rows=Counter();cols=Counter();total=sum(counts.values())
    for (a,b),n in counts.items():rows[a]+=n;cols[b]+=n
    if min(len(rows),len(cols))<2:return 0.0
    chi=sum((counts.get((a,b),0)-r*c/total)**2/(r*c/total) for a,r in rows.items() for b,c in cols.items())
    return math.sqrt(chi/(total*min(len(rows)-1,len(cols)-1)))


def report(root,statistics,out):
    by_variant={r['variant_id']:r for r in statistics};tables=Counter();associations=defaultdict(Counter)
    table(out/'image_statistics.csv',statistics)
    for g in records(root):
        original=g['variants'][0];stats=by_variant[original['id']]
        for v in g['variants'][2:]:
            for q in g['questions']:
                label=str(v['relevance'][q['id']]);split=g['split'];op=v['edit']['operation']
                features={'question_wording_task':q['task'],'operation':op,'style':str(g['coverage']['style']),
                          'layout':g['coverage']['layout'],'nodes':str(g['coverage']['nodes']),
                          'changed_pixel_fraction':bin_value(v['pixel_change']['fraction'],(.0005,.001,.002,.004,.008)),
                          'original_mean_gray':bin_value(stats['mean_gray'],(240,245,250,253)),
                          'original_gray_std':bin_value(stats['gray_std'],(15,20,25,30,35)),
                          'original_ink_fraction':bin_value(stats['nonbackground_fraction'],(.01,.02,.03,.05,.08))}
                for feature,value in features.items():
                    tables[split,q['task'],op,feature,value,label]+=1
                    associations[split,feature][value,label]+=1
    counted(out/'shortcut_contingencies.csv',tables,('split','task','operation','feature','bin_or_value','answer_changed'))
    table(out/'shortcut_associations.csv',[{'split':split,'feature':feature,'cramers_v':association(counts),
          'edit_question_observations':sum(counts.values())} for (split,feature),counts in sorted(associations.items())])
    write(out/'shortcut_diagnostics.json',{'status':'completed','method':'Descriptive split-specific contingency counts and Cramers V; no fitting, training, inference or significance tests.',
          'independence':'Two questions and two edits per base graph are correlated observations; association counts are not independent sample sizes.',
          'numeric_bins':{'changed_pixel_fraction':[.0005,.001,.002,.004,.008],'original_mean_gray':[240,245,250,253],
                          'original_gray_std':[15,20,25,30,35],'original_ink_fraction':[.01,.02,.03,.05,.08]},
          'limitations':'Shortcut diagnostics, not proof of no leakage. Question wording is represented by its fixed task template; arbitrary endpoint labels are not fitted. No items were excluded using diagnostic performance.',
          'grouped_partitions':'Existing group-isolated train/validation/test memberships, with separate descriptive tables; no fitted diagnostic requires an additional split.'})
