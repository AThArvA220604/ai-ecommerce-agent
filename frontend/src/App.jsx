import React from "react";
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

/* ═══════════════════════════════════════════════════════════════════════════
   Nexus AI — E-Commerce Automation Dashboard
   Motion philosophy: every animation has a purpose.
     - Stagger reveals → establish visual hierarchy on load
     - Tab crossfade → spatial continuity between views  
     - Row expand → show/hide relationship (AI reasoning is INSIDE the row)
     - Hover lift → affordance (this is interactive)
     - Button press → haptic feedback substitute on screen
     - Risk gauge sweep → draw attention to the numbe
   Nothing moves just to move. If you can't name WHY it animates, remove it.
   ═══════════════════════════════════════════════════════════════════════════ */

const API_BASE = (typeof window !== "undefined" && window.__API_BASE__) ||
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) ||
  "http://localhost:8000/api";
const HEALTH_POLL_MS = 15_000;

// ─── Demo data (unchanged) ─────────────────────────────────────────────────
const DEMO_PRODUCTS=[{id:"PROD-001",name:"Wireless Bluetooth Headphones",category:"Electronics",price:79.99,stock_quantity:45,reorder_threshold:15,supplier:"TechSupply Co.",stock_status:"normal",supplier_lead_time_days:5},{id:"PROD-002",name:"Organic Cotton T-Shirt",category:"Apparel",price:29.99,stock_quantity:120,reorder_threshold:30,supplier:"GreenTextiles Inc.",stock_status:"normal",supplier_lead_time_days:14},{id:"PROD-003",name:"Stainless Steel Water Bottle",category:"Home & Kitchen",price:24.99,stock_quantity:8,reorder_threshold:20,supplier:"EcoGoods Ltd.",stock_status:"low",supplier_lead_time_days:10},{id:"PROD-004",name:"Mechanical Keyboard",category:"Electronics",price:149.99,stock_quantity:22,reorder_threshold:10,supplier:"TechSupply Co.",stock_status:"normal",supplier_lead_time_days:5},{id:"PROD-005",name:"Yoga Mat Premium",category:"Sports",price:49.99,stock_quantity:3,reorder_threshold:15,supplier:"FitLife Corp.",stock_status:"critical",supplier_lead_time_days:7},{id:"PROD-006",name:"Espresso Machine Deluxe",category:"Home & Kitchen",price:299.99,stock_quantity:12,reorder_threshold:5,supplier:"KitchenPro Ltd.",stock_status:"normal",supplier_lead_time_days:21},{id:"PROD-007",name:"Running Shoes Ultra",category:"Sports",price:129.99,stock_quantity:67,reorder_threshold:20,supplier:"FitLife Corp.",stock_status:"normal",supplier_lead_time_days:7},{id:"PROD-008",name:"Leather Wallet Slim",category:"Accessories",price:44.99,stock_quantity:0,reorder_threshold:25,supplier:"CraftGoods Inc.",stock_status:"out_of_stock",supplier_lead_time_days:14},{id:"PROD-009",name:"USB-C Hub 7-in-1",category:"Electronics",price:39.99,stock_quantity:55,reorder_threshold:15,supplier:"TechSupply Co.",stock_status:"normal",supplier_lead_time_days:5},{id:"PROD-010",name:"Scented Candle Set",category:"Home & Kitchen",price:19.99,stock_quantity:200,reorder_threshold:40,supplier:"HomeVibes Co.",stock_status:"normal",supplier_lead_time_days:10}];
const DEMO_ORDERS=[{id:"ORD-1001",product_id:"PROD-003",quantity:25,unit_price:24.99,total_price:624.75,customer_type:"wholesale",status:"pending",created_at:"2026-04-14T09:15:00Z"},{id:"ORD-1002",product_id:"PROD-005",quantity:2,unit_price:49.99,total_price:99.98,customer_type:"regular",status:"pending",created_at:"2026-04-14T10:30:00Z"},{id:"ORD-1003",product_id:"PROD-008",quantity:50,unit_price:44.99,total_price:2249.50,customer_type:"new",status:"pending",created_at:"2026-04-14T11:00:00Z"},{id:"ORD-1004",product_id:"PROD-001",quantity:1,unit_price:79.99,total_price:79.99,customer_type:"vip",status:"pending",created_at:"2026-04-14T13:45:00Z"},{id:"ORD-1005",product_id:"PROD-004",quantity:3,unit_price:149.99,total_price:449.97,customer_type:"regular",status:"pending",created_at:"2026-04-14T14:20:00Z"},{id:"ORD-1006",product_id:"PROD-006",quantity:10,unit_price:299.99,total_price:2999.90,customer_type:"new",status:"pending",created_at:"2026-04-14T16:00:00Z"},{id:"ORD-1007",product_id:"PROD-002",quantity:5,unit_price:29.99,total_price:149.95,customer_type:"regular",status:"pending",created_at:"2026-04-15T08:10:00Z"},{id:"ORD-1008",product_id:"PROD-010",quantity:1,unit_price:19.99,total_price:19.99,customer_type:"vip",status:"pending",created_at:"2026-04-15T09:00:00Z"}].map(o=>({...o,priority:null,category:null,risk_flag:null,risk_score:null,ai_reasoning:null,ai_engine:null,ai_model:null,ai_latency_ms:null,processed_at:null,product_name:null}));
function demoClassify(o,p){const{quantity:q,total_price:tp,customer_type:ct}=o;const s=p?.stock_quantity??999;const cat=q>=20?"bulk":tp>=500?"high-value":ct==="vip"?"priority":"standard";const pri=(tp>=2000||(ct==="vip"&&tp>=100))?"critical":tp>=500||ct==="wholesale"?"high":q>=5?"medium":"low";const r=[];if(ct==="new"&&tp>=1000)r.push("new customer high-value exposure");if(q>s*2&&s>0)r.push("quantity exceeds available stock");if(q>=50)r.push("unusually large order volume");if(tp>=2500&&ct==="new")r.push("unverified customer large exposure");const rf=r.length>=2?"blocked":r.length===1?"review":"clear";const rs=r.length>=2?Math.min(100,75+r.length*5):r.length===1?45:10;return{category:cat,priority:pri,risk_flag:rf,risk_score:rs,reasoning:`Order of ${q} units totaling $${tp.toFixed(2)} from ${ct} customer. Categorized as '${cat}' with '${pri}' priority. ${r.length?`Risk signals: ${r.join(", ")}.`:"No risk signals — safe to auto-fulfill."}`,risk_factors:r};}

// ─── API (unchanged) ────────────────────────────────────────────────────────
async function apiFetch(path,opts={}){const c=new AbortController();const t=setTimeout(()=>c.abort(),30000);try{const r=await fetch(`${API_BASE}${path}`,{...opts,signal:c.signal,headers:{"Content-Type":"application/json",...(opts.headers||{})}});if(!r.ok)throw new Error(`${r.status}: ${await r.text().catch(()=>"")}`);return await r.json();}finally{clearTimeout(t);}}
const api={health:()=>apiFetch("/health"),getOrders:()=>apiFetch("/orders"),getInventory:()=>apiFetch("/inventory"),getAlerts:()=>apiFetch("/alerts"),getAgentLogs:()=>apiFetch("/agent-logs"),processOrder:id=>apiFetch("/process-order",{method:"POST",body:JSON.stringify({order_id:id})}),processAll:()=>apiFetch("/process-all-orders",{method:"POST"}),acknowledgeAlert:id=>apiFetch("/alerts/acknowledge",{method:"POST",body:JSON.stringify({alert_id:id})})};

// ─── Tokens ─────────────────────────────────────────────────────────────────
const V={bg:"#0c0f14",l1:"#11151c",l2:"#161b25",l3:"#1c222e",border:"#232a38",borderH:"#2e3748",text:"#e8e4de",ts:"#9b9690",tt:"#605c56",gold:"#d4a053",goldD:"#2a2114",goldG:"rgba(212,160,83,0.12)",teal:"#2dd4bf",tealD:"#0d3331",tealG:"rgba(45,212,191,0.10)",rose:"#f43f5e",roseD:"#2a0f15",roseG:"rgba(244,63,94,0.10)",sky:"#38bdf8",skyD:"#0c2135",skyG:"rgba(56,189,248,0.10)",violet:"#a78bfa",mono:"'IBM Plex Mono',monospace",sans:"'Satoshi','General Sans',system-ui,sans-serif"};
const ST={pending:{bg:V.skyD,text:V.sky,label:"Pending"},processing:{bg:V.goldD,text:V.gold,label:"Processing"},processed:{bg:V.tealD,text:V.teal,label:"Processed"},flagged:{bg:V.roseD,text:V.rose,label:"Flagged"}};
const PR={low:{bg:V.l3,text:V.ts},medium:{bg:V.skyD,text:V.sky},high:{bg:V.goldD,text:V.gold},critical:{bg:V.roseD,text:V.rose}};
const RK={clear:{bg:V.tealD,text:V.teal},review:{bg:V.goldD,text:V.gold},blocked:{bg:V.roseD,text:V.rose}};
const SK={normal:{bg:V.tealD,text:V.teal,label:"In Stock"},low:{bg:V.goldD,text:V.gold,label:"Low"},critical:{bg:V.roseD,text:V.rose,label:"Critical"},out_of_stock:{bg:"#1f0a0e",text:"#fda4af",label:"Out of Stock"}};

const CSS=`@import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700&f[]=general-sans@400,500,600&display=swap');@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');@keyframes spin{to{transform:rotate(360deg)}}@keyframes pulseRing{0%,100%{box-shadow:0 0 0 0 rgba(212,160,83,0)}50%{box-shadow:0 0 0 5px rgba(212,160,83,0.12)}}*{box-sizing:border-box;margin:0;padding:0}::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:#2e3748;border-radius:3px}::-webkit-scrollbar-thumb:hover{background:#3d4a5e}`;

// ─── Motion presets — single source of truth for timing feel ───────────────
const M={
  // Stagger children: parent gets this, children get fadeItem
  stagger:{initial:"hidden",animate:"visible",variants:{hidden:{},visible:{transition:{staggerChildren:0.06,delayChildren:0.1}}}},
  fadeItem:{variants:{hidden:{opacity:0,y:14},visible:{opacity:1,y:0,transition:{type:"spring",stiffness:300,damping:28}}},initial:"hidden",animate:"visible"},
  // Tab page crossfade
  page:{initial:{opacity:0,y:8},animate:{opacity:1,y:0},exit:{opacity:0,y:-6},transition:{duration:0.22,ease:[0.25,0.1,0.25,1]}},
  // Expandable panel
  expand:{initial:{height:0,opacity:0},animate:{height:"auto",opacity:1,transition:{height:{type:"spring",stiffness:350,damping:32},opacity:{duration:0.2,delay:0.05}}},exit:{height:0,opacity:0,transition:{height:{duration:0.2},opacity:{duration:0.12}}}},
  // Card hover
  cardHover:{whileHover:{y:-3,borderColor:`${V.gold}33`,boxShadow:`0 8px 30px ${V.goldG}`},transition:{type:"spring",stiffness:400,damping:25}},
  // Button tap
  btnTap:{whileTap:{scale:0.96},whileHover:{scale:1.01},transition:{type:"spring",stiffness:500,damping:20}},
};

// ─── Primitives ─────────────────────────────────────────────────────────────
function Badge({children,bg,color,pill}){return <span style={{display:"inline-flex",alignItems:"center",padding:pill?"3px 10px":"2px 8px",borderRadius:pill?20:6,fontSize:10.5,fontWeight:600,letterSpacing:"0.04em",textTransform:"uppercase",background:bg,color,lineHeight:"16px",whiteSpace:"nowrap"}}>{children}</span>;}
function Spinner({size=16}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{animation:"spin 0.8s linear infinite"}}><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" opacity="0.15"/><path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/></svg>;}

function RiskGauge({score}){
  if(score==null)return<span style={{color:V.tt,fontSize:11}}>—</span>;
  const color=score>=70?V.rose:score>=35?V.gold:V.teal;
  const circ=2*Math.PI*18;const dash=circ*(Math.max(0,Math.min(100,score))/100);
  return(
    <div style={{position:"relative",width:44,height:44,display:"flex",alignItems:"center",justifyContent:"center"}}>
      <svg width="44" height="44" viewBox="0 0 44 44" style={{transform:"rotate(-90deg)",position:"absolute"}}>
        <circle cx="22" cy="22" r="18" fill="none" stroke={V.l3} strokeWidth="3"/>
        <motion.circle cx="22" cy="22" r="18" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
          initial={{strokeDasharray:`0 ${circ}`}}
          animate={{strokeDasharray:`${dash} ${circ}`}}
          transition={{duration:0.8,ease:"easeOut",delay:0.2}}/>
      </svg>
      <motion.span initial={{opacity:0,scale:0.5}} animate={{opacity:1,scale:1}} transition={{delay:0.4,type:"spring",stiffness:300}}
        style={{fontSize:11,fontWeight:700,color,fontFamily:V.mono,position:"relative"}}>{score}</motion.span>
    </div>
  );
}

function Btn({children,variant="primary",disabled,loading,onClick,style:s}){
  const styles={
    primary:{display:"inline-flex",alignItems:"center",gap:6,fontFamily:V.sans,fontSize:12,fontWeight:600,borderRadius:8,border:"none",cursor:disabled?"default":"pointer",padding:"9px 18px",background:`linear-gradient(135deg,${V.gold},#b8862d)`,color:"#0c0f14",boxShadow:`0 1px 8px ${V.goldG}`,opacity:disabled?0.5:1,whiteSpace:"nowrap",...s},
    secondary:{display:"inline-flex",alignItems:"center",gap:6,fontFamily:V.sans,fontSize:12,fontWeight:600,borderRadius:8,border:"none",cursor:disabled?"default":"pointer",padding:"7px 14px",background:V.l3,color:V.ts,opacity:disabled?0.5:1,whiteSpace:"nowrap",...s},
  };
  return <motion.button onClick={onClick} disabled={disabled||loading} style={styles[variant]||styles.secondary} {...M.btnTap}>{loading?<Spinner size={13}/>:null}{children}</motion.button>;
}

// ─── Icons ──────────────────────────────────────────────────────────────────
const IC={orders:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" x2="21" y1="6" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>,inventory:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>,alerts:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>,agent:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>,play:<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg>,check:<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,pulse:<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>,brain:<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/></svg>,chevDown:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>};

// ═══════════════════════════════════════════════════════════════════════════
// APP
// ═══════════════════════════════════════════════════════════════════════════
export default function App(){
  const[tab,setTab]=useState("orders");const[orders,setOrders]=useState(DEMO_ORDERS);const[inventory,setInventory]=useState(DEMO_PRODUCTS);const[alerts,setAlerts]=useState([]);const[agentLogs,setAgentLogs]=useState([]);const[processing,setProcessing]=useState(null);const[processAllRunning,setProcessAllRunning]=useState(false);const[health,setHealth]=useState({connected:false,engine_mode:"demo (offline)",checking:true});const[error,setError]=useState(null);const[expandedOrder,setExpandedOrder]=useState(null);const dc=useRef({log:1,alert:1});

  const probeBackend=useCallback(async()=>{try{const h=await api.health();setHealth({connected:true,checking:false,engine_mode:h.ai?.engine_mode||"unknown",model:h.ai?.model,breaker:h.ai?.circuit_breaker});return true;}catch{setHealth(p=>({...p,connected:false,checking:false,engine_mode:p.engine_mode?.includes("demo")?p.engine_mode:"demo (offline)"}));return false;}},[]);
  const loadAll=useCallback(async()=>{if(!health.connected)return;try{const[o,inv,al,logs]=await Promise.all([api.getOrders(),api.getInventory(),api.getAlerts(),api.getAgentLogs()]);setOrders(o);setInventory(inv);setAlerts(al);setAgentLogs(logs);setError(null);}catch(e){setError(`Load failed: ${e.message}`);}},[health.connected]);
  useEffect(()=>{probeBackend();const t=setInterval(probeBackend,HEALTH_POLL_MS);return()=>clearInterval(t);},[probeBackend]);
  useEffect(()=>{loadAll();},[loadAll]);

  const productMap=useMemo(()=>{const m={};inventory.forEach(p=>{m[p.id]=p;});return m;},[inventory]);
  const stats=useMemo(()=>({total:orders.length,pending:orders.filter(o=>o.status==="pending").length,processed:orders.filter(o=>o.status==="processed").length,flagged:orders.filter(o=>o.status==="flagged").length,lowStock:inventory.filter(p=>p.stock_status==="low"||p.stock_status==="critical").length,outOfStock:inventory.filter(p=>p.stock_status==="out_of_stock").length,unackAlerts:alerts.filter(a=>!a.acknowledged).length,revenue:orders.filter(o=>o.status!=="cancelled").reduce((s,o)=>s+o.total_price,0)}),[orders,inventory,alerts]);

  const processOrderLive=useCallback(async(id)=>{setProcessing(id);try{await api.processOrder(id);await loadAll();}catch(e){setError(`Process failed: ${e.message}`);}finally{setProcessing(null);}},[loadAll]);
  const processOrderDemo=useCallback(async(orderId)=>{setProcessing(orderId);await new Promise(r=>setTimeout(r,400+Math.random()*400));const fx={};setInventory(pi=>{const pm={};pi.forEach(p=>{pm[p.id]=p;});let fo=null;setOrders(po=>{const o=po.find(x=>x.id===orderId);if(o)fo=o;return po;});if(!fo)return pi;const pr=pm[fo.product_id];const cl=demoClassify(fo,pr);fx.cl=cl;fx.order=fo;fx.product=pr;if(cl.risk_flag==="clear"&&pr){const ns=Math.max(0,pr.stock_quantity-fo.quantity);const ss=ns===0?"out_of_stock":ns<=pr.reorder_threshold*0.3?"critical":ns<=pr.reorder_threshold?"low":"normal";fx.newStock=ns;fx.stockStatus=ss;return pi.map(p=>p.id===pr.id?{...p,stock_quantity:ns,stock_status:ss}:p);}return pi;});setOrders(prev=>prev.map(o=>{if(o.id!==orderId||!fx.cl)return o;const s=fx.cl.risk_flag!=="clear"?"flagged":"processed";return{...o,category:fx.cl.category,priority:fx.cl.priority,risk_flag:fx.cl.risk_flag,risk_score:fx.cl.risk_score,ai_reasoning:fx.cl.reasoning,ai_engine:"rules_fallback",ai_model:"",ai_latency_ms:0,status:s,processed_at:new Date().toISOString()};}));if(fx.cl&&fx.order){const{cl,order,product,newStock,stockStatus}=fx;const now=new Date().toISOString();const logs=[{agent_name:"order_processor",action:"classify_order",decision:`${cl.category} / ${cl.priority} / ${cl.risk_flag} (score=${cl.risk_score})`,reasoning:cl.reasoning}];const na=[];if(cl.risk_flag==="clear"&&product&&newStock!=null){logs.push({agent_name:"inventory_manager",action:"deduct_stock",decision:`${product.stock_quantity} → ${newStock}`,reasoning:`Deducted ${order.quantity} from ${product.name}. Status: ${stockStatus}`});if(["low","critical","out_of_stock"].includes(stockStatus)){na.push({alert_type:"low_stock",severity:stockStatus!=="low"?"critical":"warning",title:`${stockStatus==="out_of_stock"?"OUT OF STOCK":"Low Stock"}: ${product.name}`,message:`${product.name} at ${newStock} units (threshold: ${product.reorder_threshold}).`,related_entity_type:"product",related_entity_id:product.id});logs.push({agent_name:"notification_agent",action:"stock_alert",decision:"alert_sent",reasoning:`${product.name} is ${stockStatus}`});}}else if(cl.risk_flag!=="clear"){logs.push({agent_name:"inventory_manager",action:"skip_deduction",decision:"order_blocked",reasoning:`Stock deduction skipped — order ${orderId} blocked.`});}if(cl.priority==="critical"||cl.priority==="high"){na.push({alert_type:"high_priority_order",severity:cl.priority==="critical"?"critical":"warning",title:`High Priority: ${orderId}`,message:`${product?.name} — $${order.total_price.toFixed(2)}, ${cl.priority} priority.`,related_entity_type:"order",related_entity_id:orderId});logs.push({agent_name:"notification_agent",action:"priority_alert",decision:"sent",reasoning:`High-priority notification for ${orderId}`});}if(cl.risk_flag!=="clear"){na.push({alert_type:"fraud_risk",severity:cl.risk_flag==="blocked"?"critical":"warning",title:`Risk Flag: ${orderId}`,message:`Order flagged as '${cl.risk_flag}' (risk score ${cl.risk_score}).`,related_entity_type:"order",related_entity_id:orderId});logs.push({agent_name:"notification_agent",action:"risk_alert",decision:"sent",reasoning:`Risk notification for ${orderId}`});}setAgentLogs(prev=>[...logs.reverse().map(l=>({...l,id:dc.current.log++,created_at:now})),...prev]);setAlerts(prev=>[...na.reverse().map(a=>({...a,id:dc.current.alert++,acknowledged:false,created_at:now})),...prev]);}setProcessing(null);},[]);
  const processOrder=health.connected?processOrderLive:processOrderDemo;
  const processAll=useCallback(async()=>{setProcessAllRunning(true);if(health.connected){try{await api.processAll();await loadAll();}catch(e){setError(`Batch failed: ${e.message}`);}}else{let ids=[];setOrders(p=>{ids=p.filter(o=>o.status==="pending").map(o=>o.id);return p;});await new Promise(r=>setTimeout(r,0));for(const id of ids)await processOrderDemo(id);}setProcessAllRunning(false);},[health.connected,loadAll,processOrderDemo]);
  const acknowledgeAlert=useCallback(async(id)=>{if(health.connected){try{await api.acknowledgeAlert(id);setAlerts(await api.getAlerts());}catch(e){setError(`Acknowledge failed: ${e.message}`);}}else{setAlerts(p=>p.map(a=>a.id===id?{...a,acknowledged:true}:a));}},[health.connected]);

  const TABS=[{id:"orders",label:"Orders",icon:IC.orders},{id:"inventory",label:"Inventory",icon:IC.inventory},{id:"alerts",label:"Alerts",icon:IC.alerts,badge:stats.unackAlerts},{id:"agents",label:"AI Decisions",icon:IC.agent}];

  return(
    <div style={{minHeight:"100vh",background:V.bg,color:V.text,fontFamily:V.sans}}>
      <style>{CSS}</style>

      {/* Header */}
      <motion.header initial={{y:-20,opacity:0}} animate={{y:0,opacity:1}} transition={{duration:0.4,ease:"easeOut"}} style={{borderBottom:`1px solid ${V.border}`,background:"rgba(12,15,20,0.8)",backdropFilter:"blur(16px) saturate(1.4)",position:"sticky",top:0,zIndex:50}}>
        <div style={{maxWidth:1320,margin:"0 auto",padding:"16px 28px",display:"flex",alignItems:"center",justifyContent:"space-between",gap:16,flexWrap:"wrap"}}>
          <div style={{display:"flex",alignItems:"center",gap:14}}>
            <motion.div whileHover={{rotate:12,scale:1.05}} transition={{type:"spring",stiffness:300}} style={{width:38,height:38,borderRadius:12,background:`linear-gradient(145deg,${V.gold},#b8862d)`,display:"flex",alignItems:"center",justifyContent:"center",color:"#0c0f14",boxShadow:`0 2px 12px ${V.goldG}`}}>{IC.pulse}</motion.div>
            <div><div style={{fontSize:18,fontWeight:700,letterSpacing:"-0.03em"}}>Nexus AI</div><div style={{fontSize:11,color:V.ts,fontWeight:500,marginTop:1}}>E-Commerce Automation</div></div>
          </div>
          <EngineBadge health={health} onRefresh={probeBackend}/>
        </div>
        <AnimatePresence>{error&&<motion.div key="err" initial={{height:0,opacity:0}} animate={{height:"auto",opacity:1}} exit={{height:0,opacity:0}} transition={{duration:0.2}} style={{maxWidth:1320,margin:"0 auto",padding:"8px 28px",background:V.roseD,color:V.rose,fontSize:12,borderTop:`1px solid ${V.border}`,display:"flex",alignItems:"center",gap:8,fontWeight:500,overflow:"hidden"}}><span style={{flex:1}}>{error}</span><button onClick={()=>setError(null)} style={{background:"none",border:"none",color:V.rose,cursor:"pointer",fontWeight:600,fontSize:11,textDecoration:"underline"}}>dismiss</button></motion.div>}</AnimatePresence>
      </motion.header>

      <div style={{maxWidth:1320,margin:"0 auto",padding:"24px 28px 48px"}}>
        {/* Stats */}
        <motion.div {...M.stagger} style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:14,marginBottom:28}}>
          {[{l:"Total Orders",v:stats.total,i:IC.orders,t:12},{l:"Pending",v:stats.pending,i:<span style={{fontSize:17}}>&#9711;</span>,c:V.sky,g:V.skyG},{l:"Processed",v:stats.processed,i:IC.check,c:V.teal,g:V.tealG,t:8},{l:"Flagged",v:stats.flagged,i:<span style={{fontSize:16}}>&#9888;</span>,c:V.rose,g:V.roseG},{l:"Low Stock",v:stats.lowStock+stats.outOfStock,i:IC.inventory,c:V.gold,g:V.goldG},{l:"Revenue",v:`$${stats.revenue.toLocaleString(undefined,{minimumFractionDigits:0})}`,i:<span style={{fontSize:17}}>$</span>,c:V.teal,g:V.tealG,t:5}].map((s,i)=>(
            <motion.div key={i} {...M.fadeItem} {...M.cardHover} style={{background:V.l1,border:`1px solid ${V.border}`,borderRadius:16,padding:"20px 22px",cursor:"default"}}>
              <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:12}}>
                <div style={{width:36,height:36,borderRadius:10,background:s.g||V.goldG,display:"flex",alignItems:"center",justifyContent:"center",color:s.c||V.gold,flexShrink:0}}>{s.i}</div>
                {s.t!=null&&<span style={{fontSize:11,fontWeight:600,color:s.t>=0?V.teal:V.rose}}>{s.t>=0?"↑":"↓"}{Math.abs(s.t)}%</span>}
              </div>
              <div style={{fontSize:26,fontWeight:700,lineHeight:1,letterSpacing:"-0.02em"}}>{s.v}</div>
              <div style={{fontSize:12,color:V.ts,marginTop:6,fontWeight:500}}>{s.l}</div>
            </motion.div>
          ))}
        </motion.div>

        {/* Tabs */}
        <div style={{display:"flex",gap:4,marginBottom:24,background:V.l1,borderRadius:8,padding:4,border:`1px solid ${V.border}`,overflowX:"auto",width:"fit-content"}}>
          {TABS.map(t=>{const a=tab===t.id;return(
            <motion.button key={t.id} onClick={()=>setTab(t.id)} whileHover={{backgroundColor:a?undefined:`${V.l3}88`}} whileTap={{scale:0.97}}
              style={{display:"flex",alignItems:"center",gap:7,padding:"9px 18px",fontSize:13,fontWeight:600,color:a?V.text:V.ts,background:a?V.l3:"transparent",border:"none",borderRadius:6,cursor:"pointer",fontFamily:V.sans,whiteSpace:"nowrap",position:"relative",overflow:"hidden"}}>
              <span style={{color:a?V.gold:V.tt,transition:"color 0.2s"}}>{t.icon}</span>{t.label}
              {t.badge>0&&<motion.span initial={{scale:0}} animate={{scale:1}} transition={{type:"spring",stiffness:500}} style={{background:V.rose,color:"#fff",fontSize:10,fontWeight:700,padding:"1px 7px",borderRadius:10,lineHeight:"16px"}}>{t.badge}</motion.span>}
            </motion.button>
          );})}
        </div>

        {/* Tab content with crossfade */}
        <AnimatePresence mode="wait">
          <motion.div key={tab} {...M.page}>
            {tab==="orders"&&<OrdersTab orders={orders} productMap={productMap} processing={processing} processOrder={processOrder} processAll={processAll} processAllRunning={processAllRunning} expandedOrder={expandedOrder} setExpandedOrder={setExpandedOrder}/>}
            {tab==="inventory"&&<InventoryTab inventory={inventory}/>}
            {tab==="alerts"&&<AlertsTab alerts={alerts} acknowledgeAlert={acknowledgeAlert}/>}
            {tab==="agents"&&<AgentsTab logs={agentLogs}/>}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── Engine Badge ────────────────────────────────────────────────────────────
function EngineBadge({health,onRefresh}){
  const isLLM=health.engine_mode==="llm";const isDemo=!health.connected;
  const color=isLLM?V.violet:health.engine_mode==="rules"?V.teal:V.gold;
  const label=isLLM?"AI Engine":health.engine_mode==="rules"?"Rule Engine":isDemo?"Offline Demo":"Connecting...";
  return(
    <div style={{display:"flex",alignItems:"center",gap:8}}>
      <motion.div animate={isLLM?{boxShadow:[`0 0 0 0 ${V.violet}00`,`0 0 0 5px ${V.violet}18`,`0 0 0 0 ${V.violet}00`]}:{}} transition={isLLM?{duration:3,repeat:Infinity,ease:"easeInOut"}:{}} style={{display:"flex",alignItems:"center",gap:8,background:V.l2,borderRadius:8,padding:"7px 14px",border:`1px solid ${color}33`}}>
        <div style={{color,display:"flex"}}>{IC.brain}</div>
        <div style={{display:"flex",flexDirection:"column",gap:1}}>
          <span style={{fontSize:11,fontWeight:700,color,letterSpacing:"0.03em"}}>{label}</span>
          {isLLM&&health.model&&<span style={{fontSize:9,color:V.tt,fontFamily:V.mono}}>{health.model}</span>}
          {health.breaker?.open&&<span style={{fontSize:9,color:V.gold}}>breaker open</span>}
        </div>
      </motion.div>
      <motion.button onClick={onRefresh} whileHover={{borderColor:V.gold}} whileTap={{scale:0.92}} style={{background:V.l2,border:`1px solid ${V.border}`,borderRadius:8,padding:"7px 9px",color:V.ts,cursor:"pointer",display:"flex"}}>
        {health.checking?<Spinner size={13}/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>}
      </motion.button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ORDERS
// ═══════════════════════════════════════════════════════════════════════════
function OrdersTab({orders,productMap,processing,processOrder,processAll,processAllRunning,expandedOrder,setExpandedOrder}){
  const hasPending=orders.some(o=>o.status==="pending");
  const th={padding:"12px 16px",textAlign:"left",fontSize:10.5,fontWeight:600,color:V.tt,textTransform:"uppercase",letterSpacing:"0.06em",whiteSpace:"nowrap",position:"sticky",top:0,background:V.l1,zIndex:2,borderBottom:`1px solid ${V.border}`};
  return(
    <div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:16,gap:12,flexWrap:"wrap"}}>
        <h2 style={{fontSize:17,fontWeight:700,letterSpacing:"-0.01em"}}>Order Queue</h2>
        {hasPending&&<Btn variant="primary" loading={processAllRunning} onClick={processAll}>{IC.play}{processAllRunning?"Processing...":"Process All Pending"}</Btn>}
      </div>
      <div style={{background:V.l1,border:`1px solid ${V.border}`,borderRadius:16,overflow:"hidden"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr>{["Order","Product","Qty","Total","Customer","Status","Priority","Risk","Score","Engine",""].map(h=><th key={h} style={th}>{h}</th>)}</tr></thead>
            <tbody>
              {orders.map((o,i)=>{
                const p=productMap[o.product_id];const isP=processing===o.id;const ss=ST[o.status]||ST.pending;const ps=o.priority?PR[o.priority]:null;const rs=o.risk_flag?RK[o.risk_flag]:null;const isExp=expandedOrder===o.id;const eng=o.ai_engine==="llm"?"LLM":o.ai_engine?.includes("rules")?"Rules":null;const engC=o.ai_engine==="llm"?V.violet:o.ai_engine?V.teal:V.tt;const rowBg=i%2===0?"transparent":`${V.l2}66`;
                return(
                  <React.Fragment key={o.id}>
                    <motion.tr layout style={{background:rowBg,cursor:o.ai_reasoning?"pointer":"default",borderBottom:isExp?"none":`1px solid ${V.border}15`}}
                      whileHover={{backgroundColor:V.l3}} onClick={()=>{if(o.ai_reasoning)setExpandedOrder(isExp?null:o.id)}}>
                      <td style={{padding:"14px 16px",fontFamily:V.mono,fontSize:12,fontWeight:500,color:V.gold}}>{o.id}</td>
                      <td style={{padding:"14px 16px",fontWeight:500,maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{p?.name||o.product_name||o.product_id}</td>
                      <td style={{padding:"14px 16px",textAlign:"center",fontFamily:V.mono,fontSize:12}}>{o.quantity}</td>
                      <td style={{padding:"14px 16px",fontFamily:V.mono,fontSize:12}}>${o.total_price.toFixed(2)}</td>
                      <td style={{padding:"14px 16px"}}><Badge bg={V.l3} color={V.ts} pill>{o.customer_type}</Badge></td>
                      <td style={{padding:"14px 16px"}}><Badge bg={ss.bg} color={ss.text} pill>{ss.label}</Badge></td>
                      <td style={{padding:"14px 16px"}}>{ps?<Badge bg={ps.bg} color={ps.text} pill>{o.priority}</Badge>:<span style={{color:V.tt}}>—</span>}</td>
                      <td style={{padding:"14px 16px"}}>{rs?<Badge bg={rs.bg} color={rs.text} pill>{o.risk_flag}</Badge>:<span style={{color:V.tt}}>—</span>}</td>
                      <td style={{padding:"14px 8px"}}><RiskGauge score={o.risk_score}/></td>
                      <td style={{padding:"14px 16px"}}>{eng?<div style={{display:"flex",flexDirection:"column",gap:2}}><span style={{fontSize:10,fontWeight:700,color:engC,textTransform:"uppercase",letterSpacing:"0.05em"}}>{eng}</span>{o.ai_latency_ms>0&&<span style={{fontSize:9,color:V.tt,fontFamily:V.mono}}>{o.ai_latency_ms}ms</span>}</div>:<span style={{color:V.tt}}>—</span>}</td>
                      <td style={{padding:"14px 16px"}} onClick={e=>e.stopPropagation()}>
                        {o.status==="pending"?<Btn variant="primary" loading={isP} onClick={()=>processOrder(o.id)} style={{padding:"7px 14px"}}>{IC.play}Process</Btn>:o.ai_reasoning?<motion.div animate={{rotate:isExp?180:0}} transition={{duration:0.2}} style={{display:"flex",alignItems:"center",gap:4,color:V.ts,fontSize:11,cursor:"pointer"}} onClick={()=>setExpandedOrder(isExp?null:o.id)}>{IC.chevDown}</motion.div>:<span style={{color:V.tt}}>—</span>}
                      </td>
                    </motion.tr>
                    <AnimatePresence>
                      {isExp&&o.ai_reasoning&&(
                        <tr><td colSpan="11" style={{padding:0}}><motion.div {...M.expand} style={{overflow:"hidden"}}>
                          <div style={{margin:"0 16px 16px",padding:18,background:V.l2,borderRadius:10,border:`1px solid ${V.borderH}`}}>
                            <div style={{fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:"0.06em",color:V.gold,marginBottom:10,display:"flex",alignItems:"center",gap:6}}>{IC.brain} AI Reasoning</div>
                            <p style={{fontSize:13,lineHeight:1.75,color:V.ts,margin:0}}>{o.ai_reasoning}</p>
                            {o.ai_engine&&<div style={{marginTop:14,display:"flex",gap:8,flexWrap:"wrap"}}><Badge bg={V.l3} color={V.tt}>engine: {o.ai_engine}</Badge>{o.ai_model&&<Badge bg={V.l3} color={V.tt}>model: {o.ai_model}</Badge>}{o.ai_latency_ms>0&&<Badge bg={V.l3} color={V.tt}>{o.ai_latency_ms}ms</Badge>}</div>}
                          </div>
                        </motion.div></td></tr>
                      )}
                    </AnimatePresence>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// INVENTORY
// ═══════════════════════════════════════════════════════════════════════════
function InventoryTab({inventory}){
  const th={padding:"12px 16px",textAlign:"left",fontSize:10.5,fontWeight:600,color:V.tt,textTransform:"uppercase",letterSpacing:"0.06em",whiteSpace:"nowrap",position:"sticky",top:0,background:V.l1,zIndex:2,borderBottom:`1px solid ${V.border}`};
  return(
    <div>
      <h2 style={{fontSize:17,fontWeight:700,letterSpacing:"-0.01em",marginBottom:16}}>Product Inventory</h2>
      <div style={{background:V.l1,border:`1px solid ${V.border}`,borderRadius:16,overflow:"hidden"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr>{["Product","Name","Category","Price","Stock","Threshold","Lead","Status","Supplier"].map(h=><th key={h} style={th}>{h}</th>)}</tr></thead>
            <tbody>
              {inventory.map((p,i)=>{
                const ss=SK[p.stock_status]||SK.normal;const pct=p.reorder_threshold>0?Math.min(100,(p.stock_quantity/(p.reorder_threshold*3))*100):100;const bc=p.stock_status==="normal"?V.teal:p.stock_status==="low"?V.gold:V.rose;const rb=i%2===0?"transparent":`${V.l2}66`;
                return(
                  <motion.tr key={p.id} whileHover={{backgroundColor:V.l3}} style={{background:rb,borderBottom:`1px solid ${V.border}15`}}>
                    <td style={{padding:"14px 16px",fontFamily:V.mono,fontSize:12,fontWeight:500,color:V.gold}}>{p.id}</td>
                    <td style={{padding:"14px 16px",fontWeight:600}}>{p.name}</td>
                    <td style={{padding:"14px 16px"}}><Badge bg={V.l3} color={V.ts} pill>{p.category}</Badge></td>
                    <td style={{padding:"14px 16px",fontFamily:V.mono,fontSize:12}}>${p.price.toFixed(2)}</td>
                    <td style={{padding:"14px 16px"}}>
                      <div style={{display:"flex",alignItems:"center",gap:10}}>
                        <span style={{fontFamily:V.mono,fontSize:14,fontWeight:700,color:bc,minWidth:30}}>{p.stock_quantity}</span>
                        <div style={{flex:1,height:5,background:V.l3,borderRadius:3,overflow:"hidden",maxWidth:70}}>
                          <motion.div initial={{width:0}} animate={{width:`${pct}%`}} transition={{duration:0.7,ease:"easeOut",delay:i*0.04}} style={{height:"100%",background:bc,borderRadius:3}}/>
                        </div>
                      </div>
                    </td>
                    <td style={{padding:"14px 16px",textAlign:"center",color:V.ts,fontFamily:V.mono,fontSize:12}}>{p.reorder_threshold}</td>
                    <td style={{padding:"14px 16px",textAlign:"center",color:V.ts,fontSize:12}}>{p.supplier_lead_time_days?`${p.supplier_lead_time_days}d`:"—"}</td>
                    <td style={{padding:"14px 16px"}}><Badge bg={ss.bg} color={ss.text} pill>{ss.label}</Badge></td>
                    <td style={{padding:"14px 16px",color:V.ts,fontSize:12}}>{p.supplier}</td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ALERTS
// ═══════════════════════════════════════════════════════════════════════════
function AlertsTab({alerts,acknowledgeAlert}){
  if(!alerts.length) return <motion.div initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} style={{textAlign:"center",padding:"64px 24px"}}><div style={{fontSize:40,marginBottom:16,opacity:0.3}}>&#128276;</div><div style={{fontSize:15,fontWeight:600,color:V.ts}}>No alerts yet</div><div style={{fontSize:13,color:V.tt,marginTop:6}}>Process orders to trigger the AI notification agent.</div></motion.div>;
  return(
    <div>
      <h2 style={{fontSize:17,fontWeight:700,letterSpacing:"-0.01em",marginBottom:16}}>System Alerts</h2>
      <motion.div {...M.stagger} style={{display:"flex",flexDirection:"column",gap:10}}>
        {alerts.map(a=>{
          const isCrit=a.severity==="critical";const bc=isCrit?V.rose:a.severity==="warning"?V.gold:V.sky;
          return(
            <motion.div key={a.id} {...M.fadeItem} layout style={{background:V.l1,border:`1px solid ${V.border}`,borderLeft:`3px solid ${bc}`,borderRadius:16,overflow:"hidden",opacity:a.acknowledged?0.4:1}}>
              <div style={{padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16}}>
                <div style={{flex:1}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8,flexWrap:"wrap"}}>
                    <Badge bg={isCrit?V.roseD:a.severity==="warning"?V.goldD:V.skyD} color={bc} pill>{a.severity}</Badge>
                    <Badge bg={V.l3} color={V.tt} pill>{a.alert_type.replace(/_/g," ")}</Badge>
                    <span style={{fontSize:11,color:V.tt,fontFamily:V.mono}}>{new Date(a.created_at).toLocaleTimeString()}</span>
                  </div>
                  <div style={{fontSize:15,fontWeight:600,marginBottom:6}}>{a.title}</div>
                  <div style={{fontSize:13,color:V.ts,lineHeight:1.65}}>{a.message}</div>
                </div>
                {!a.acknowledged&&<Btn variant="secondary" onClick={()=>acknowledgeAlert(a.id)}>Acknowledge</Btn>}
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// AGENTS — Timeline
// ═══════════════════════════════════════════════════════════════════════════
function AgentsTab({logs}){
  const AC=useMemo(()=>({order_processor:{color:V.sky,label:"Order Processor"},inventory_manager:{color:V.teal,label:"Inventory Manager"},notification_agent:{color:V.violet,label:"Notification Agent"}}),[]);
  if(!logs.length) return <motion.div initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} style={{textAlign:"center",padding:"64px 24px"}}><div style={{fontSize:40,marginBottom:16,opacity:0.3}}>&#129302;</div><div style={{fontSize:15,fontWeight:600,color:V.ts}}>No agent decisions recorded yet</div><div style={{fontSize:13,color:V.tt,marginTop:6}}>Process orders to see the multi-agent pipeline in action.</div></motion.div>;
  return(
    <div>
      <h2 style={{fontSize:17,fontWeight:700,letterSpacing:"-0.01em",marginBottom:16}}>AI Agent Decision Log</h2>
      <motion.div {...M.stagger} style={{display:"flex",flexDirection:"column",gap:8,position:"relative",paddingLeft:20}}>
        <div style={{position:"absolute",left:6,top:8,bottom:8,width:2,background:`linear-gradient(to bottom,${V.gold}44,${V.border})`,borderRadius:1}}/>
        {logs.map(l=>{
          const ai=AC[l.agent_name]||{color:V.ts,label:l.agent_name};
          return(
            <motion.div key={l.id} {...M.fadeItem} style={{position:"relative"}}>
              <motion.div initial={{scale:0}} animate={{scale:1}} transition={{type:"spring",stiffness:400,delay:0.1}} style={{position:"absolute",left:-17,top:18,width:10,height:10,borderRadius:"50%",background:V.l1,border:`2.5px solid ${ai.color}`,zIndex:1}}/>
              <div style={{background:V.l1,border:`1px solid ${V.border}`,borderRadius:16,padding:"14px 18px",overflow:"hidden"}}>
                <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:8,flexWrap:"wrap"}}>
                  <Badge bg={`${ai.color}18`} color={ai.color} pill>{ai.label}</Badge>
                  <span style={{fontSize:12,fontWeight:500}}>{l.action.replace(/_/g," ")}</span>
                  <span style={{marginLeft:"auto",fontSize:11,color:V.tt,fontFamily:V.mono}}>{new Date(l.created_at).toLocaleTimeString()}</span>
                </div>
                <div style={{fontSize:12.5,color:V.ts}}><span style={{fontWeight:700,color:V.gold,fontSize:11,letterSpacing:"0.03em",textTransform:"uppercase",marginRight:6}}>Decision</span>{l.decision}</div>
                {l.reasoning&&<div style={{fontSize:12,color:V.tt,marginTop:6,lineHeight:1.6,borderLeft:`2px solid ${V.border}`,paddingLeft:12}}>{l.reasoning}</div>}
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}
