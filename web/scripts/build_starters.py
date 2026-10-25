from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
for name,files in [('python',[('bot.py',root.parent/'lab/bots/baseline.py'),('common.py',root.parent/'lab/bots/common.py')]),('cpp',[('main.cpp',root/'examples/cpp/main.cpp')])]:
    with zipfile.ZipFile(root/'public'/f'sample-{name}.zip','w') as archive:
        for target,path in files:
            info=zipfile.ZipInfo(target,date_time=(2026,10,25,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())
