import sys, re, subprocess, xml.etree.ElementTree as ET, os
root = sys.argv[1]
files = subprocess.run(["git","-C",root,"ls-files","*.svg"],capture_output=True,text=True).stdout.split()
files = [f for f in files if not f.startswith("assets/archive")]
def ln(t): return t.rsplit("}",1)[-1] if isinstance(t,str) else ""
for f in files:
    src = open(os.path.join(root,f),encoding="utf-8",errors="replace").read()
    try:
        r = ET.fromstring(src)
    except Exception as e:
        print(f, "PARSE ERROR", e); continue
    titles=[n for n in r if ln(n.tag)=="title"]; descs=[n for n in r if ln(n.tag)=="desc"]
    texts=[n for n in r.iter() if ln(n.tag)=="text"]
    sizes=[]
    for m in re.finditer(r'font-size[=:]\s*"?([0-9.]+)(px|pt)?', src):
        sizes.append(float(m.group(1)))
    bg = None
    has_media = "prefers-color-scheme" in src
    paths = sum(1 for n in r.iter() if ln(n.tag)=="path")
    print(f"{f}\n   bytes={len(src)} role={r.get('role')} labelledby={bool(r.get('aria-labelledby'))} title={len(titles)} desc={len(descs)} w={r.get('width')} h={r.get('height')} vb={r.get('viewBox')} texts={len(texts)} paths={paths} minfont={min(sizes) if sizes else None} media={has_media}")
    if titles: print("   T:", " ".join("".join(titles[0].itertext()).split())[:160])
    if descs: print("   D:", " ".join("".join(descs[0].itertext()).split())[:300])
