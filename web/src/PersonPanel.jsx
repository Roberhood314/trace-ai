import React, { useState } from "react";
import { createPerson } from "./api";

export default function PersonPanel({ caseId, person, onCreated }) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    full_name: "",
    year_of_birth: "",
    height_cm: "",
    weight_kg: "",
    appearance: "",
    identifying_features: "",
    permanent_address: "",
    temporary_address: "",
  });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        ...form,
        year_of_birth: form.year_of_birth ? Number(form.year_of_birth) : null,
        height_cm: form.height_cm ? Number(form.height_cm) : null,
        weight_kg: form.weight_kg ? Number(form.weight_kg) : null,
      };
      const created = await createPerson(caseId, payload);
      onCreated(created);
      setEditing(false);
    } catch (err) {
      setError(err.message);
    }
  }

  if (!caseId) {
    return <div className="empty-card">Hồ sơ demo chưa nối backend.</div>;
  }

  if (person && !editing) {
    return (
      <div className="person-card">
        <div className="person-header">
          <div>
            <div className="eyebrow">PERSON PROFILE</div>
            <h4>{person.full_name}</h4>
          </div>
        </div>
        <div className="person-grid">
          <div><span>Năm sinh</span><strong>{person.year_of_birth || "—"}</strong></div>
          <div><span>Chiều cao</span><strong>{person.height_cm ? `${person.height_cm} cm` : "—"}</strong></div>
          <div><span>Cân nặng</span><strong>{person.weight_kg ? `${person.weight_kg} kg` : "—"}</strong></div>
          <div><span>Đặc điểm</span><strong>{person.identifying_features || "—"}</strong></div>
          <div className="wide"><span>Ngoại hình</span><strong>{person.appearance || "—"}</strong></div>
          <div className="wide"><span>Thường trú</span><strong>{person.permanent_address || "—"}</strong></div>
          <div className="wide"><span>Tạm trú</span><strong>{person.temporary_address || "—"}</strong></div>
        </div>
      </div>
    );
  }

  if (!editing) {
    return (
      <div className="empty-card">
        <p>Chưa có hồ sơ người cần tìm cho vụ việc này.</p>
        <button className="primary-button" onClick={() => setEditing(true)}>+ Thêm hồ sơ</button>
      </div>
    );
  }

  return (
    <form className="case-form person-form" onSubmit={submit}>
      <div className="form-grid-2">
        <label>Họ tên<input required value={form.full_name} onChange={(e)=>setForm({...form,full_name:e.target.value})} /></label>
        <label>Năm sinh<input type="number" value={form.year_of_birth} onChange={(e)=>setForm({...form,year_of_birth:e.target.value})} /></label>
        <label>Chiều cao (cm)<input type="number" step="0.1" value={form.height_cm} onChange={(e)=>setForm({...form,height_cm:e.target.value})} /></label>
        <label>Cân nặng (kg)<input type="number" step="0.1" value={form.weight_kg} onChange={(e)=>setForm({...form,weight_kg:e.target.value})} /></label>
      </div>
      <label>Đặc điểm nhận dạng<textarea value={form.identifying_features} onChange={(e)=>setForm({...form,identifying_features:e.target.value})} /></label>
      <label>Ngoại hình / trang phục<textarea value={form.appearance} onChange={(e)=>setForm({...form,appearance:e.target.value})} /></label>
      <label>Địa chỉ thường trú<input value={form.permanent_address} onChange={(e)=>setForm({...form,permanent_address:e.target.value})} /></label>
      <label>Địa chỉ tạm trú<input value={form.temporary_address} onChange={(e)=>setForm({...form,temporary_address:e.target.value})} /></label>
      {error && <div className="form-error">{error}</div>}
      <div className="form-actions">
        <button type="button" className="secondary-button" onClick={()=>setEditing(false)}>Hủy</button>
        <button className="primary-button">Lưu hồ sơ</button>
      </div>
    </form>
  );
}
