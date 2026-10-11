"""Local practice app; browser runs on the student's own computer.

Teacher evaluator can read /state independently of the agent's claims.
No model tool is allowed to call /state directly.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

STATE = {"form_success": False, "canvas_success": False}
HTML = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>COMMA Practice</title>
<style>body{font:20px system-ui;background:#f4f6f7;color:#172b37;max-width:760px;margin:40px auto;padding:0 30px}h1{font-size:30px}section{background:white;padding:24px;margin:20px 0;border:1px solid #d5dfe2;border-radius:12px}label{display:block;margin:15px 0}input,select,button{font:inherit;padding:8px}button{cursor:pointer}canvas{border:1px solid #bcc8d0;max-width:100%}#result,#canvas-result{color:#11664d;min-height:26px}</style>
<h1>COMMA Practice</h1><p>本机 Computer Use 练习 · 切换模型或观察方式前重置</p>
<section><h2>报名表</h2><form id="form"><label>姓名 <input name="name" autocomplete="off"></label><label>类别 <select name="category"><option>请选择</option><option>Research</option><option>Teaching</option></select></label><label><input type="checkbox" name="agree"> 同意</label><button>提交</button></form><p id="result" role="status"></p></section>
<section><h2>画布定位</h2><p>点击橙色圆形。</p><canvas id="canvas" width="650" height="180" aria-label="图形练习画布"></canvas><p id="canvas-result" role="status"></p></section>
<button id="reset">重置全部练习</button>
<script>
const f=document.querySelector('#form'),c=document.querySelector('#canvas'),ctx=c.getContext('2d');
ctx.fillStyle='#2764b3';ctx.fillRect(55,50,90,85);ctx.fillStyle='#ee8c25';ctx.beginPath();ctx.arc(340,90,40,0,Math.PI*2);ctx.fill();ctx.fillStyle='#239d83';ctx.beginPath();ctx.moveTo(540,45);ctx.lineTo(595,135);ctx.lineTo(485,135);ctx.closePath();ctx.fill();
async function save(data){await fetch('/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
f.onsubmit=async e=>{e.preventDefault();let ok=f.elements.name.value==='Lin'&&f.elements.category.value==='Research'&&f.elements.agree.checked;await save({form_success:ok});document.querySelector('#result').textContent=ok?'提交成功：Lin / Research':'信息不符合要求，请检查。';};
c.onclick=async e=>{let r=c.getBoundingClientRect(),x=(e.clientX-r.left)*650/r.width,y=(e.clientY-r.top)*180/r.height;let ok=Math.hypot(x-340,y-90)<=40;await save({canvas_success:ok});document.querySelector('#canvas-result').textContent=ok?'成功：已选中橙色圆形':'未选中目标，请重试。';};
document.querySelector('#reset').onclick=async()=>{await save({form_success:false,canvas_success:false});f.reset();document.querySelector('#result').textContent='';document.querySelector('#canvas-result').textContent='';};
</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/state":
            body, content_type = json.dumps(STATE).encode(), "application/json"
        else:
            body, content_type = HTML.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/state":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 2048:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            for key in STATE:
                if key in data and type(data[key]) is bool:
                    STATE[key] = data[key]
        except (ValueError, TypeError):
            self.send_error(400)
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"用本机浏览器打开 http://127.0.0.1:{args.port}；Ctrl+C 停止。", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
