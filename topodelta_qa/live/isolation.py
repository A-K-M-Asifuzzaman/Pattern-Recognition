"""macOS Seatbelt: deny by default; only staged inputs/code/runtime and private outputs."""
import json
import os
import subprocess
import sys
from pathlib import Path


def profile(stage, network=False):
    stage=stage.resolve()
    runtime=Path(sys.base_prefix).resolve()
    reads=[str(runtime),'/System/Library','/System/Cryptexes','/System/Volumes/Preboot','/usr/lib','/usr/share','/opt/homebrew/Cellar','/opt/homebrew/opt','/opt/homebrew/lib','/opt/homebrew/etc/openssl@3','/opt/homebrew/etc/ca-certificates',
           '/private/etc','/Library/Apple','/private/var/db/dyld',str(stage/'code'),str(stage/'inputs')]
    literals=['/','/dev/null','/dev/random','/dev/urandom','/dev/zero']
    parts=['(version 1)','(deny default)','(allow process-fork)','(allow sysctl-read)','(allow mach-lookup)',
           '(allow process-exec (literal '+json.dumps(str(Path(sys.executable).resolve()))+'))',
           '(allow file-read* '+' '.join('(subpath '+json.dumps(x)+')' for x in reads)+' '+
           ' '.join('(literal '+json.dumps(x)+')' for x in literals)+')',
           '(allow file-read* file-write* (subpath '+json.dumps(str(stage/'results'))+') (subpath '+json.dumps(str(stage/'tmp'))+'))']
    if network:parts.append('(allow network-outbound)')
    return '\n'.join(parts)+'\n'


def launch(stage, mode, args=(), network=False, credential=False):
    stage=stage.resolve()
    env={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','HOME':str(stage/'tmp'),'TMPDIR':str(stage/'tmp'),
         'PYTHONDONTWRITEBYTECODE':'1'}
    if credential and os.environ.get('OPENAI_API_KEY'):
        env['OPENAI_API_KEY']=os.environ['OPENAI_API_KEY']
    script=stage/'code/bootstrap.py'
    cmd=['/usr/bin/sandbox-exec','-p',profile(stage,network),str(Path(sys.executable).resolve()),'-I','-S',str(script),mode,*map(str,args)]
    return subprocess.run(cmd,env=env,cwd=stage/'tmp',capture_output=True,text=True)
