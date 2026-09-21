import React,{useEffect,useState} from "react";
import { fetchUsers, updateUser } from "./api";

export default function AdminPanel(){
  const [users,setUsers]=useState([]),[error,setError]=useState("");
  async function load(){try{setUsers(await fetchUsers());setError("")}catch(e){setError(e.message)}}
  useEffect(()=>{load()},[]);
  async function change(user,role){try{const updated=await updateUser(user.id,{role});setUsers(prev=>prev.map(x=>x.id===updated.id?updated:x))}catch(e){setError(e.message)}}
  return <div className="admin-panel">
    <div className="panel-header"><div><div className="eyebrow">ACCESS CONTROL</div><h3>Quản lý quyền</h3></div></div>
    {error&&<div className="form-error">{error}</div>}
    <div className="user-table">
      {users.map(u=><div className="user-row" key={u.id}>
        <div><strong>{u.username||u.pi_uid}</strong><small>{u.pi_uid}</small></div>
        <select value={u.role} onChange={e=>change(u,e.target.value)}>
          <option value="viewer">Viewer</option><option value="analyst">Analyst</option><option value="commander">Commander</option><option value="admin">Admin</option>
        </select>
      </div>)}
      {!users.length&&!error&&<div className="empty-card">Chưa có tài khoản Pi nào đăng nhập.</div>}
    </div>
  </div>
}
