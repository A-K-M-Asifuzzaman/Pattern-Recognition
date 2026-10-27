import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(prog='python -m topodelta_qa.live')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--source',type=Path,default=Path('outputs/phase2a'));p.add_argument('--output',type=Path,default=Path('outputs/phase2b'))
    for name in ('preflight','execute','score'):
        p=sub.add_parser(name);p.add_argument('--output',type=Path,default=Path('outputs/phase2b'))
        if name=='execute':p.add_argument('--approve-proposal',required=True)
        if name=='score':p.add_argument('--stage',choices=('smoke','full'),required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        from .plan import prepare
        prepare(args.source,args.output)
    else:
        from .control import preflight,execute,score_saved
        if args.command=='preflight':print(json.dumps(preflight(args.output.resolve())))
        elif args.command=='execute':execute(args.output.resolve(),args.approve_proposal)
        else:score_saved(args.output.resolve(),args.stage)


if __name__=='__main__':main()
