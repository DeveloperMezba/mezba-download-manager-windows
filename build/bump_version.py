import json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
old=(root/'VERSION').read_text().strip()
if len(sys.argv)!=2 or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',sys.argv[1]):raise SystemExit('Usage: python build/bump_version.py 0.1.1')
new=sys.argv[1]
if tuple(map(int,new.split('.')))<=tuple(map(int,old.split('.'))):raise SystemExit('Choose a higher version')
(root/'VERSION').write_text(new+'\n');(root/'source/mdm/__init__.py').write_text('__version__ = '+repr(new)+'\n')
for browser in ('chromium','firefox'):
 p=root/f'source/extension/{browser}/manifest.json';data=json.loads(p.read_text());data['version']=new;p.write_text(json.dumps(data,indent=2)+'\n')
p=root/'build/installer.nsi';s=p.read_text().replace('"'+old+'"','"'+new+'"').replace('"'+old+'.0"','"'+new+'.0"');p.write_text(s)
p=root/'build/launcher.rc';s=p.read_text().replace(old+'.0',new+'.0').replace(old.replace('.',',')+',0',new.replace('.',',')+',0').replace('"'+old+'"','"'+new+'"');p.write_text(s)
p=root/'build/app.manifest';p.write_text(p.read_text().replace(old+'.0',new+'.0'))
print('Version set to '+new+'. Update the changelog, test, and publish tag v'+new+'.')
