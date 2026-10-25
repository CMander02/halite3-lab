import json,sys,collections
d=json.load(open(sys.argv[1]))
fr=d['full_frames']
spawn=collections.Counter(); wreck=collections.Counter(); lost=collections.Counter()
for i,f in enumerate(fr):
    for e in f.get('events',[]):
        if e['type']=='spawn': spawn[e['owner_id']]+=1
        if e['type']=='shipwreck':
            for s in e['ships']: wreck[s['owner_id']]+=1
    if i in (50,100,150,199):
        en=f.get('entities',{})
        print(i,{p:(len(v), sum(x['energy'] for x in v.values())) for p,v in en.items()}, {p:e for p,e in f.get('energy',{}).items()})
print('spawn',dict(spawn),'wrecked',dict(wreck))
print(d['game_statistics']['player_statistics'][0].keys() if 'game_statistics' in d else '')
