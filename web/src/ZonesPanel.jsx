import React,{useState} from "react";
import { createZone } from "./api";
export default function ZonesPanel({caseId,items=[],onCreated}){
 const [form,setForm]=useState({name:"Zone A",priority:"high",center_latitude:"",center_longitude:"",radius_m:"2000",score:"80",rationale:""});
 const [error,setError]=useState("");
 async function submit(e){e.preventDefault();setError("");try{const p={...form,center_latitude:Number(form.center_latitude),center_longitude:Number(form.center_longitude),radius_m:Number(form.radius_m),score:Number(form.score)};const r=await createZone(caseId,p);onCreated(r)}catch(err){setError(err.message)}}
 if(!caseId)return <div className="empty-card">Chọn vụ việc thật để tạo vùng tìm kiếm.</div>;
 return <div className="split-panel"><form className="case-form compact-form" onSubmit={submit}>
  <div className="form-grid-2"><label>Tên vùng<input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label><label>Ưu tiên<select value={form.priority} onChange={e=>setForm({...form,priority:e.target.value})}><option value="high">Cao</option><option value="medium">Trung bình</option><option value="low">Thấp</option></select></label>
  <label>Tâm latitude<input required type="number" step="any" value={form.center_latitude} onChange={e=>setForm({...form,center_latitude:e.target.value})}/></label><label>Tâm longitude<input required type="number" step="any" value={form.center_longitude} onChange={e=>setForm({...form,center_longitude:e.target.value})}/></label>
  <label>Bán kính (m)<input required type="number" min="50" max="100000" value={form.radius_m} onChange={e=>setForm({...form,radius_m:e.target.value})}/></label><label>Điểm ưu tiên<input required type="number" min="0" max="100" value={form.score} onChange={e=>setForm({...form,score:e.target.value})}/></label></div>
  <label>Căn cứ / giải thích<textarea value={form.rationale} onChange={e=>setForm({...form,rationale:e.target.value})}/></label>{error&&<div className="form-error">{error}</div>}<button className="primary-button">+ Tạo vùng</button>
 </form><div className="zone-list">{items.map(z=><div className="zone-card" key={z.id}><div className="zone-score">{Math.round(z.score)}</div><div className="zone-content"><div className="zone-title-row"><strong>{z.name}</strong><span>{(z.radius_m/1000).toFixed(1)} km</span></div><div className="progress"><div style={{width:`${z.score}%`}}></div></div><p>{z.rationale||"Chưa có giải thích"}</p></div></div>)}{!items.length&&<div className="empty-card">Chưa có vùng tìm kiếm.</div>}</div></div>
}
