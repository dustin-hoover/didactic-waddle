#!/usr/bin/env python3
"""Build the crew PWA from one source (shell.html + app.js), two ways (doc 23):

  python3 make_pwa.py                       -> index.html (production: served by dispatch.py at /crew,
                                               registers sw.js, loads app.js)
  python3 make_pwa.py preview <runsheet.json> <out.html>
                                            -> single-file artifact preview: app.js inlined, lake +
                                               a real planner run sheet embedded, no network (demo mode)
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
shell = open(os.path.join(HERE, "shell.html")).read()
app = open(os.path.join(HERE, "app.js")).read()

def production():
    head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            '<meta name="theme-color" content="#1C5E88">\n<link rel="manifest" href="manifest.webmanifest">\n'
            '<link rel="icon" href="icon.svg">\n<meta name="apple-mobile-web-app-capable" content="yes">\n')
    title_end = shell.index("</style>") + len("</style>")
    html = (head + shell[:title_end] + "\n</head>\n<body>\n" + shell[title_end:] +
            '\n<script src="app.js"></script>\n<script>if("serviceWorker" in navigator){navigator.serviceWorker.register("sw.js").catch(function(){});}</script>\n</body>\n</html>\n')
    open(os.path.join(HERE, "index.html"), "w").write(html)
    return os.path.join(HERE, "index.html")

def preview(runsheet_path, out):
    lake = json.load(open(os.path.join(REPO, "data", "gis", "outputs", "lake.geojson")))
    rs = json.load(open(runsheet_path))
    demo = {"crew": rs["crew_id"], "day": rs["day"], "runsheet": rs, "lake": lake,
            "note": "Preview with a real planner run on the real lake and example members. Actions here stay on "
                    "this device; the crew app in DockOS syncs them to dispatch and billing."}
    js = "window.BDN_DEMO=" + json.dumps(demo, separators=(",", ":")) + ";"
    open(out, "w").write(shell + "\n<script>" + js.replace("</", "<\\/") + "</script>\n<script>" + app + "</script>\n")
    return out

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        print(preview(sys.argv[2], sys.argv[3]))
    else:
        print(production())
