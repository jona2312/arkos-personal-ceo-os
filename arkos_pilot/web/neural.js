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
    const defs=make('defs',{});
    for(const [name,color] of [['gold','#ffb72f'],['red','#ff302c']]){
      const gradient=make('radialGradient',{id:'arkos-neural-'+name});
      for(const [offset,opacity] of [['0%','0.8'],['16%','0.5'],['48%','0.13'],['100%','0']])gradient.append(make('stop',{offset,'stop-color':color,'stop-opacity':opacity}));
      defs.append(gradient);
    }
    const links=make('g',{class:'neural-links'}),branches=make('g',{class:'neural-red-links'}),signals=make('g',{class:'neural-signals'}),halos=make('g',{class:'neural-halos'}),nodes=make('g',{class:'neural-nodes'}),stars=make('g',{class:'neural-stars'});
    let seed=37;const rand=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
    const points=[];
    for(let y=0;y<12;y++)for(let x=0;x<19;x++)points.push({x:x*89+(rand()-.5)*86,y:y*91+(rand()-.5)*84});
    const segments=[];
    for(let i=0;i<points.length;i++){
      const a=points[i];
      const nearest=points.map((b,j)=>({j,d:Math.hypot(a.x-b.x,a.y-b.y)})).filter(b=>b.j>i&&b.d<180).sort((a,b)=>a.d-b.d).slice(0,4);
      for(const n of nearest){const b=points[n.j];segments.push(`M${a.x.toFixed(1)} ${a.y.toFixed(1)}L${b.x.toFixed(1)} ${b.y.toFixed(1)}`);}
      const hub=i%3===0,red=i%4===0;
      nodes.append(make('circle',{cx:a.x.toFixed(1),cy:a.y.toFixed(1),r:hub?'3.1':'1.1',class:hub?'neural-hub '+(red?'hub-red':'hub-gold'):'neural-node'}));
      if(hub){
        halos.append(make('circle',{cx:a.x.toFixed(1),cy:a.y.toFixed(1),r:red?'31':'25',fill:'url(#arkos-neural-'+(red?'red':'gold')+')',class:'neural-halo'}));
        stars.append(make('path',{d:`M${a.x-11} ${a.y}h22 M${a.x} ${a.y-11}v22`,class:red?'star-red':'star-gold'}));
      }
    }
    links.append(make('path',{d:segments.join(' ')}));
    branches.append(make('path',{d:segments.filter((_,i)=>i%5===0).join(' ')}));
    signals.append(make('path',{d:segments.filter((_,i)=>i%4===0).join(' ')}));
    svg.append(defs,links,branches,signals,halos,stars,nodes);container.append(svg);
  }
  const api={activity,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ArkosNeural=api;
})(typeof window!=='undefined'?window:globalThis);
