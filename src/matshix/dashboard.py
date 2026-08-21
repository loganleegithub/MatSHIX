from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plotly.offline import get_plotlyjs


def export_dashboard(*, dashboard_data: Path, output: Path) -> Path:
    payload: dict[str, Any] = json.loads(dashboard_data.read_text(encoding="utf-8"))
    days = payload.get("days", [])
    if not days:
        raise ValueError("dashboard data has no market days")
    template = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MatSHIX 上交所期权市场天气</title>
<script>__PLOTLY__</script>
<style>
:root{--bg:#07101c;--panel:#101c2c;--panel2:#15243a;--ink:#eef4fb;--muted:#91a4bb;--line:#253853;--cyan:#45d7d1;--amber:#f5b942;--red:#ff6b6b;--green:#56d68b;--purple:#ae8bff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% -10%,#17314a 0,#07101c 40%);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.shell{max-width:1480px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}.eyebrow{color:var(--cyan);letter-spacing:.14em;font-size:12px}.title{font-size:29px;font-weight:720;margin:4px 0}.subtitle,.muted{color:var(--muted)}.warning{background:#3a2b11;border:1px solid #72541d;color:#ffd780;padding:10px 14px;border-radius:10px;margin:14px 0 18px}
.controls{display:flex;gap:8px;align-items:center;background:#0c1726;padding:9px;border:1px solid var(--line);border-radius:12px}.controls button,.controls select{background:#16263b;color:var(--ink);border:1px solid #314764;border-radius:8px;padding:8px 10px}.controls button{cursor:pointer}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.panel{background:linear-gradient(145deg,rgba(21,36,58,.96),rgba(12,24,39,.96));border:1px solid var(--line);border-radius:14px;padding:16px;min-width:0}.hero{grid-column:span 8}.summary{grid-column:span 4}.full{grid-column:1/-1}.half{grid-column:span 6}.third{grid-column:span 4}.panel h2{font-size:14px;color:#b6c7d9;text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px}.headline{font-size:24px;line-height:1.35;margin:8px 0 16px}.phase{display:inline-block;border-radius:999px;padding:5px 10px;background:#213755;color:#dfeaff;font-weight:650}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.kpi{background:#0a1625;border-radius:10px;padding:11px}.kpi .v{font-size:22px;font-weight:700;margin-top:3px}.answers{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.answer{border-left:3px solid var(--cyan);background:#0b1726;padding:9px 11px;border-radius:6px}.answer span{display:block;color:var(--muted);font-size:11px}.segments{display:flex;gap:10px}.segment{flex:1;text-align:center;padding:13px 6px;border-radius:10px;background:#0b1726;border:1px solid var(--line)}.segment.on{border-color:var(--red);color:#ffaaaa}.segment.unknown{border-style:dashed;color:var(--muted)}
.evidence{margin:0;padding-left:19px}.evidence li{margin:7px 0;overflow-wrap:anywhere}.prob-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.prob{padding:12px;border-radius:10px;background:#0b1726;border-top:3px solid var(--purple)}.prob .num{font-size:22px;font-weight:700}.tag{display:inline-block;font-size:11px;padding:2px 6px;border-radius:4px;background:#283b55;color:#c5d6e8}.tag.model{background:#2a4f42;color:#a8f0cb}.tag.na{background:#3b3444;color:#cabbd4}.definition{color:var(--muted);font-size:11px;margin-top:8px}.chart{height:330px}.footer{color:var(--muted);font-size:12px;margin:18px 2px}.empty{color:var(--muted)}
@media(max-width:950px){.hero,.summary,.half,.third{grid-column:1/-1}.prob-grid{grid-template-columns:1fr 1fr}.top{display:block}.controls{margin-top:12px}.kpis{grid-template-columns:1fr 1fr}}
</style>
</head>
<body><main class="shell">
<div class="top"><div><div class="eyebrow">MATSHIX · SSE ETF OPTIONS</div><div class="title">上交所期权市场天气</div><div class="subtitle">四经济指数 · 三风险段 · 七坐标 · 五个未来状态事件</div></div><div class="controls"><button id="prev">←</button><select id="dateSelect"></select><button id="next">→</button><button id="play">播放</button></div></div>
<div class="warning">研究证据层：真实 14:56 分钟收盘，不是同步 bid/ask，也不构成正式可成交盘口或交易建议。</div>
<section class="grid">
<article class="panel hero"><h2>一句话天气</h2><span id="phase" class="phase"></span><div id="headline" class="headline"></div><div class="kpis"><div class="kpi"><span class="muted">Pressure</span><div id="pressure" class="v"></div></div><div class="kpi"><span class="muted">强度</span><div id="level" class="v"></div></div><div class="kpi"><span class="muted">方向</span><div id="direction" class="v"></div></div><div class="kpi"><span class="muted">置信</span><div id="confidence" class="v"></div></div></div></article>
<article class="panel summary"><h2>六答案与未来判断</h2><div id="answers" class="answers"></div></article>
<article class="panel full"><h2>历史压力与 phase</h2><div id="historyChart" class="chart"></div></article>
<article class="panel half"><h2>四指数风险坐标</h2><div id="indexChart" class="chart"></div></article>
<article class="panel half"><h2>四载体期限结构</h2><div id="termChart" class="chart"></div></article>
<article class="panel third"><h2>三段宽度</h2><div id="segments" class="segments"></div><div id="breadthMeta" class="definition"></div></article>
<article class="panel third"><h2>主要驱动 / 反向证据</h2><div id="evidence"></div></article>
<article class="panel third"><h2>什么会改变判断</h2><ul id="changes" class="evidence"></ul></article>
<article class="panel full"><h2>未来状态概率（与当前 Score 分离）</h2><div id="probabilities" class="prob-grid"></div></article>
</section>
<div class="footer">MatSHIX v1 · 科创50正式载体仅 588000 · 缺失值保持 UNKNOWN · 不输出仓位、买卖箭头或策略收益</div>
</main>
<script>
const DATA=__DATA__;
const days=DATA.days;
const labels={level:'保险价格',shock:'重定价',tail:'尾部方向',term:'期限扩散',breadth:'跨段宽度',repair:'修复',outlook:'未来判断'};
const events={cross_market_iv_jump_1d:['1日跨市场IV跳升','未来1个交易日内跨段IV跳升且Shock确认'],broad_pressure_onset_5d:['5日广泛压力形成','未来5日内Broad且Pressure≥65'],systemic_acute_stress_5d:['5日系统性急压','未来5日内进入系统性急性压力'],persistent_cross_market_stress_20d:['20日持续压力','未来20日内形成跨市场持续压力'],fast_repair_5d:['5日快速修复','高压条件下未来5日内Repair确认']};
const select=document.getElementById('dateSelect');days.forEach((d,i)=>{const o=document.createElement('option');o.value=i;o.textContent=d.session_date;select.appendChild(o)});select.value=days.length-1;
let timer=null;function fmt(v,d=1){return v===null||v===undefined?'—':Number(v).toFixed(d)}function list(items){return items.length?'<ul class="evidence">'+items.map(x=>'<li>'+x.meaning+'</li>').join('')+'</ul>':'<div class="empty">无高分位证据</div>'}
function render(i){select.value=i;const d=days[i];document.getElementById('phase').textContent=d.primary_phase;document.getElementById('headline').textContent=d.headline;document.getElementById('pressure').textContent=fmt(d.pressure_score);document.getElementById('level').textContent=d.pressure_level;document.getElementById('direction').textContent=d.direction;document.getElementById('confidence').textContent=d.confidence;
document.getElementById('answers').innerHTML=Object.entries(labels).map(([k,v])=>'<div class="answer"><span>'+v+'</span>'+d.answers[k]+'</div>').join('');
const seg=d.breadth.segment_stressed;document.getElementById('segments').innerHTML=[['large','大盘'],['mid','中盘'],['tech','科创']].map(([k,n])=>'<div class="segment '+(seg[k]===true?'on':seg[k]===null?'unknown':'')+'">'+n+'<br><b>'+(seg[k]===true?'承压':seg[k]===false?'未确认':'未知')+'</b></div>').join('');document.getElementById('breadthMeta').textContent='已确认风险段 '+(d.breadth.stressed_segment_count??'—')+'/3；名义指数 '+(d.breadth.stressed_index_count??'—')+'/4';
const proxies=d.research_proxies.length?'<b>研究代理</b><ul class="evidence">'+d.research_proxies.map(x=>'<li>'+x.economic_index_id+'.'+x.metric+' · '+x.method+'</li>').join('')+'</ul>':'';document.getElementById('evidence').innerHTML='<b>驱动</b>'+list(d.drivers)+'<b>反向</b>'+list(d.counter_evidence)+'<b>修复</b>'+list(d.repair_evidence)+proxies;document.getElementById('changes').innerHTML=d.what_changes_the_view.map(x=>'<li>'+x+'</li>').join('');
document.getElementById('probabilities').innerHTML=Object.entries(events).map(([id,meta])=>{const p=d.probabilities[id];const shown=p.probability===null?'—':(100*p.probability).toFixed(1)+'%';const tag=p.model_status==='CALIBRATED_MODEL'?'model':p.event_status==='NOT_APPLICABLE'?'na':'';return '<div class="prob"><b>'+meta[0]+'</b><div class="num">'+shown+'</div><span class="tag '+tag+'">'+p.model_status+'</span><div class="definition">'+meta[1]+'<br>'+p.interpretation+'</div></div>'}).join('');
const axes=['insurance_level','shock','down_tail','up_tail','persistence','repair','index_pressure'];const axisNames=['Level','Shock','DownTail','UpTail','Term','Repair','Pressure'];const colors=['#45d7d1','#f5b942','#ff6b6b','#ae8bff'];const indexTraces=Object.entries(d.economic_indices).map(([name,x],j)=>({type:'bar',name:name,x:axisNames,y:axes.map(a=>x.scores[a]),marker:{color:colors[j]}}));Plotly.react('indexChart',indexTraces,{barmode:'group',paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:'#cbd8e7'},yaxis:{range:[0,100],gridcolor:'#253853'},margin:{l:42,r:12,t:8,b:42}},{displayModeBar:false,responsive:true});
const tenor=Object.entries(d.economic_indices).map(([name,x],j)=>({type:'scatter',mode:'lines+markers',name:name,x:['30D','60D','90D'],y:[x.surface.iv30_mf,x.surface.iv60_mf,x.surface.iv90_mf],line:{color:colors[j],width:2}}));Plotly.react('termChart',tenor,{paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:'#cbd8e7'},yaxis:{title:'IV %',gridcolor:'#253853'},margin:{l:50,r:12,t:8,b:42}},{displayModeBar:false,responsive:true});
const xs=days.map(x=>x.session_date),ys=days.map(x=>x.pressure_score);Plotly.react('historyChart',[{type:'scatter',mode:'lines',x:xs,y:ys,line:{color:'#45d7d1',width:2},name:'Pressure'},{type:'scatter',mode:'markers',x:[d.session_date],y:[d.pressure_score],marker:{size:11,color:'#f5b942'},name:'当前选择'}],{paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{color:'#cbd8e7'},yaxis:{range:[0,100],gridcolor:'#253853'},xaxis:{gridcolor:'#17263a'},margin:{l:42,r:12,t:8,b:42},showlegend:false},{displayModeBar:false,responsive:true});}
select.addEventListener('change',()=>render(Number(select.value)));document.getElementById('prev').onclick=()=>render(Math.max(0,Number(select.value)-1));document.getElementById('next').onclick=()=>render(Math.min(days.length-1,Number(select.value)+1));document.getElementById('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;document.getElementById('play').textContent='播放';return}document.getElementById('play').textContent='暂停';timer=setInterval(()=>{let n=Number(select.value)+1;if(n>=days.length)n=0;render(n)},650)};render(days.length-1);
</script></body></html>"""
    html = template.replace("__PLOTLY__", get_plotlyjs()).replace(
        "__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
