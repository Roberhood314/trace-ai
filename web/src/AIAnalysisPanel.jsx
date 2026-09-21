import React,{useEffect,useState} from "react";
import { fetchAiSummary } from "./api";
export default function AIAnalysisPanel({caseId}){
 const [data,setData]=useState(null),[error,setError]=useState("");
 useEffect(()=>{if(!caseId){setData(null);return} fetchAiSummary(caseId).then(setData).catch(e=>setError(e.message))},[caseId]);
 if(!caseId)return <div className="empty-card">Chọn vụ việc thật để tạo bản tổng hợp.</div>;
 if(error)return <div className="form-error">{error}</div>;
 if(!data)return <div className="empty-card">Đang tổng hợp…</div>;
 return <div className="ai-card"><div><h4>AI Search Assistant</h4><p>{data.summary}</p><strong>Kiểm tra đề xuất</strong><ul>{data.recommended_checks.map((x,i)=><li key={i}>{x}</li>)}</ul>{data.zone_order.length>0&&<p>Thứ tự vùng hiện tại: <strong>{data.zone_order.join(" → ")}</strong></p>}<div className="ai-disclaimer">Bản tổng hợp hỗ trợ rà soát dữ liệu, không phải kết luận về một cá nhân hay quyết định nghiệp vụ cuối cùng.</div></div></div>
}
