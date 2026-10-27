import argparse
import json
from pathlib import Path
from .boundary import verify_exports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);a=p.parse_args()
    print(json.dumps(verify_exports(a.dataset,a.dataset/'reports'),indent=2))
