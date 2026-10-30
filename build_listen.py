"""Regenerate listen.html from bfxr-samples/index.txt so the static page never
goes stale relative to what the generator actually produced."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
IDX = os.path.join(HERE, "bfxr-samples", "index.txt")

GROUPS = {
    "A": "A · 从刺耳到软（同一个音，逐步处理）",
    "B": "B · 六套音色",
    "C": "C · 句子演示",
    "D": "D · 多层叠加（这就是新加的功能）",
    "W": "W · 12 种内置波形",
}

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>对话音效试听 · 静态</title>
<style>
  :root{{--bg:#12141a;--card:#1a1d26;--card2:#20242f;--line:#2b3040;
        --fg:#e8ebf2;--dim:#8d95a8;--accent:#5ee0c0}}
  *{{box-sizing:border-box}}
  body{{margin:0;padding:34px 20px 90px;background:var(--bg);color:var(--fg);
       font:15px/1.6 "Microsoft YaHei UI","Segoe UI",system-ui,sans-serif;
       max-width:900px;margin-inline:auto}}
  h1{{font-size:20px;margin:0 0 6px}}
  .sub{{color:var(--dim);font-size:13px;margin-bottom:24px}}
  h2{{font-size:14px;color:var(--accent);margin:32px 0 10px;font-weight:600;
      padding-bottom:6px;border-bottom:1px solid var(--line)}}
  .row{{display:flex;align-items:center;gap:13px;padding:10px 14px;margin-bottom:6px;
       background:var(--card);border:1px solid var(--line);border-radius:10px;
       cursor:pointer;transition:background .12s,border-color .12s}}
  .row:hover{{background:var(--card2);border-color:#3a4256}}
  .row.playing{{background:#16302c;border-color:var(--accent)}}
  .play{{flex:0 0 30px;height:30px;border-radius:50%;background:#2b3040;
        display:grid;place-items:center;font-size:11px;color:var(--dim)}}
  .row.playing .play{{background:var(--accent);color:#0b1512}}
  .label{{flex:1;min-width:0}}
  .label b{{font-weight:600;font-size:14px}}
  .note{{display:block;color:var(--dim);font-size:11.5px;margin-top:1px}}
  .opts{{display:flex;gap:20px;align-items:center;color:var(--dim);font-size:12.5px;
        margin-bottom:10px;flex-wrap:wrap}}
  .opts label{{display:flex;gap:6px;align-items:center;cursor:pointer}}
</style>
</head>
<body>
<h1>对话音效试听 · 静态</h1>
<div class="sub">全部由 bfxr 合成器生成。第三方声明见工程目录；想自己调参数用控制台。</div>
<div class="opts">
  <label><input type="checkbox" id="rep" checked> 短音连播 ×3</label>
  <label><input type="checkbox" id="auto"> 播完自动下一个</label>
</div>
{body}
<script>
let current = null;
let selection = 0, timer = null;
document.querySelectorAll(".row").forEach(row => {{
  const audio = new Audio("bfxr-samples/" + row.dataset.file);
  audio.preload = "auto";
  let token = 0, repeatsLeft = 0;
  function play() {{
    if (token !== selection || current !== audio) return;
    audio.currentTime = 0;
    audio.play().catch(e => {{
      row.classList.remove("playing");
      console.warn("播放失败", row.dataset.file, e);
    }});
  }}
  audio.addEventListener("ended", () => {{
    if (token !== selection || current !== audio) return;
    if (repeatsLeft > 0 && audio.duration < 0.25) {{
      repeatsLeft--;
      timer = setTimeout(play, Math.max(0, 260 - audio.duration * 1000));
      return;
    }}
    row.classList.remove("playing");
    if (document.getElementById("auto").checked) {{
      const all = [...document.querySelectorAll(".row")];
      const i = all.indexOf(row);
      if (i >= 0 && i < all.length - 1) timer = setTimeout(() => {{
        if (token === selection) all[i + 1].click();
      }}, 420);
    }}
  }});
  row.addEventListener("click", () => {{
    clearTimeout(timer);
    token = ++selection;
    if (current) current.pause();
    current = audio;
    repeatsLeft = document.getElementById("rep").checked ? 2 : 0;
    document.querySelectorAll(".row").forEach(r => r.classList.remove("playing"));
    row.classList.add("playing");
    play();
  }});
}});
</script>
</body>
</html>
"""


def main():
    rows = []
    with open(IDX, encoding="utf-8-sig") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))

    body = []
    current = None
    for name, label, note in rows:
        g = name[0]
        if g != current and g in GROUPS:
            if current is not None:
                body.append("</div>")
            body.append(f"<h2>{GROUPS[g]}</h2>\n<div>")
            current = g
        body.append(
            f'<div class="row" data-file="{name}">'
            f'<div class="play">▶</div>'
            f'<div class="label"><b>{label}</b><span class="note">{note}</span></div>'
            f'</div>'
        )
    if current is not None:
        body.append("</div>")

    out = TEMPLATE.format(body="\n".join(body))
    path = os.path.join(HERE, "listen.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"listen.html 已重建：{len(rows)} 行")


if __name__ == "__main__":
    main()
