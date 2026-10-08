/* Local decorative network. Task states drive signals; no model telemetry. */
(function(root){
  'use strict';
  function activity(tasks,online){
    if(!online)return 'offline';
    if(tasks.some(t=>t.state==='running'))return 'running';
    if(tasks.some(t=>t.state==='queued'))return 'queued';
    if(tasks.some(t=>['awaiting_approval','blocked'].includes(t.state)))return 'review';
    return 'idle';
  }
  function mount(container){
    const ns='http://www.w3.org/2000/svg';
    const make=(tag,attrs)=>{const n=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
    const svg=make('svg',{viewBox:'0 0 1600 1000',preserveAspectRatio:'xMidYMid slice',class:'neural-network','aria-hidden':'true',focusable:'false'});
    const links=make('g',{class:'neural-links'}),signals=make('g',{class:'neural-signals'}),nodes=make('g',{class:'neural-nodes'});
    let seed=37;const rand=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
    const points=[];
    for(let y=0;y<7;y++)for(let x=0;x<11;x++)points.push({x:x*160+(rand()-.5)*100,y:y*167+(rand()-.5)*85});
    const segments=[];
    for(let i=0;i<points.length;i++){
      const a=points[i];
      const nearest=points.map((b,j)=>({j,d:Math.hypot(a.x-b.x,a.y-b.y)})).filter(b=>b.j>i&&b.d<255).sort((a,b)=>a.d-b.d).slice(0,3);
      for(const n of nearest){const b=points[n.j];segments.push(`M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`);}
      nodes.append(make('circle',{cx:a.x.toFixed(1),cy:a.y.toFixed(1),r:i%7===0?'4':'1.8',class:i%7===0?'neural-hub':'neural-node'}));
      if(i%7===0)nodes.append(make('circle',{cx:a.x.toFixed(1),cy:a.y.toFixed(1),r:'11',class:'neural-halo'}));
    }
    links.append(make('path',{d:segments.join(' ')}));
    signals.append(make('path',{d:segments.filter((_,i)=>i%4===0).join(' ')}));
    svg.append(links,signals,nodes);container.append(svg);
  }
  const api={activity,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ArkosNeural=api;
})(typeof window!=='undefined'?window:globalThis);
