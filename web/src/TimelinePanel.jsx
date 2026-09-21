import React, { useState } from "react";
import { createTimelineEvent } from "./api";

export default function TimelinePanel({ caseId, items = [], onCreated }) {
  const [form,setForm]=useState({event_time:new Date().toISOString().slice(0,16),event_type:"last_seen",description:"",source_type:"field_report",source_reference:"",latitude:"",longitude:"",confidence:"0.8"});
  const [error,setError]=useState("");
  async function submit(e){e.preventDefault();setError("");try{
    const payload={...form,event_time:new Date(form.event_time).toISOString(),latitude:form.latitude===""?null:Number(form.latitude),longitude:form.longitude===""?null:Number(form.longitude),confidence:form.confidence===""?null:Number(form.confidence)};
    const row=await createTimelineEvent(caseId,payload); onCreated(row); setForm({...form,description:"",source_reference:""});
  }catch(err){setError(err.message)}}
  if(!caseId) return <div className="empty-card">Chọn vụ việc thật để thêm dấu vết.</div>;
  return <div className="split-panel">
    <form className="case-form compact-form" onSubmit={submit}>
      <div className="form-grid-2">
        <label>Thời gian<input type="datetime-local" required value={form.event_time} onChange={e=>setForm({...form,event_time:e.target.value})}/></label>
        <label>Loại dấu vết<select value={form.event_type} onChange={e=>setForm({...form,event_type:e.target.value})}><option value="last_seen">Điểm cuối xác minh</option><option value="camera_sighting">Camera ghi nhận</option><option value="device_signal">Tín hiệu thiết bị được cấp quyền</option><option value="field_clue">Dấu vết hiện trường</option><option value="witness_report">Tin báo nhân chứng</option></select></label>
      </div>
      <label>Mô tả<textarea required value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
      <div className="form-grid-2">
        <label>Nguồn<input value={form.source_type} onChange={e=>setForm({...form,source_type:e.target.value})}/></label>
        <label>Mã nguồn / tham chiếu<input value={form.source_reference} onChange={e=>setForm({...form,source_reference:e.target.value})}/></label>
        <label>Latitude<input type="number" step="any" value={form.latitude} onChange={e=>setForm({...form,latitude:e.target.value})}/></label>
        <label>Longitude<input type="number" step="any" value={form.longitude} onChange={e=>setForm({...form,longitude:e.target.value})}/></label>
        <label>Độ tin cậy 0–1<input type="number" min="0" max="1" step="0.01" value={form.confidence} onChange={e=>setForm({...form,confidence:e.target.value})}/></label>
      </div>
      {error&&<div className="form-error">{error}</div>}
      <button className="primary-button">+ Thêm dấu vết</button>
    </form>
    <div className="timeline">
      {items.map(item=><div className="timeline-item" key={item.id}><div className="time">{new Date(item.event_time).toLocaleString("vi-VN",{hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit"})}</div><div className="timeline-dot"></div><div><strong>{item.event_type}</strong><p>{item.description}</p>{item.latitude!=null&&<small>{item.latitude.toFixed(5)}, {item.longitude.toFixed(5)} • tin cậy {item.confidence??"—"}</small>}</div></div>)}
      {!items.length&&<div className="empty-card">Chưa có sự kiện timeline.</div>}
    </div>
  </div>
}
