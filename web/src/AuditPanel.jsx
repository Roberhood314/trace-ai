import React,{useEffect,useState} from "react";
import { fetchAudit } from "./api";
export default function AuditPanel({caseId}){
 const [items,setItems]=useState([]),[error,setError]=useState("");
 useEffect(()=>{if(!caseId)return;fetchAudit(caseId).then(setItems).catch(e=>setError(e.message))},[caseId]);
 if(!caseId)return <div className="empty-card">Chọn vụ việc thật để xem audit log.</div>;
 if(error)return <div className="form-error">{error}</div>;
 return <div className="audit-list">{items.map(x=><div className="audit-row" key={x.id}><div><strong>{x.action}</strong><span>{x.resource_type} #{x.resource_id||"—"}</span></div><div><span>{x.actor}</span><small>{new Date(x.occurred_at).toLocaleString("vi-VN")}</small></div></div>)}{!items.length&&<div className="empty-card">Chưa có nhật ký.</div>}</div>
}
