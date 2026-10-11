import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AlarmSetpoint } from '../types';
const keys = ['low_low','low','high','high_high'] as const;
const labels = ['LL — авария снизу','L — предупреждение снизу','H — предупреждение сверху','HH — авария сверху'];
export default function InstrumentLimits({nodeId,editable}:{nodeId:string;editable:boolean}) {
  const [point,setPoint]=useState<AlarmSetpoint>();
  const [draft,setDraft]=useState<Record<string,string>>({});
  const [message,setMessage]=useState('');
  useEffect(()=>{
    let current=true;setPoint(undefined);setMessage('');
    api.getAlarmSetpoints().then(response=>{
      if(!current)return;
      const value=response.setpoints.find(item=>item.parameter===`${nodeId}_measurement`);
      setPoint(value);setDraft(Object.fromEntries(keys.map(key=>[key,value?.[key]?.toString()??''])));
    }).catch(()=>{if(current)setMessage('Не удалось загрузить уставки');});
    return()=>{current=false;};
  },[nodeId]);
  const save=async()=>{
    const patch=Object.fromEntries(keys.map(key=>[key,draft[key]?.trim()?Number(draft[key]):null]));
    const values=keys.flatMap(key=>patch[key]===null?[]:[patch[key]]);
    if(values.some((v,i)=>!Number.isFinite(v)||(i>0&&v<values[i-1]))){setMessage('Уставки должны быть числами в порядке LL ≤ L ≤ H ≤ HH');return;}
    try{await api.updateAlarmSetpoint(`${nodeId}_measurement`,patch);setMessage('Уставки сохранены');}
    catch(error){setMessage(String(error));}
  };
  return <section className="instrument-limits"><div className="panel-title">ПРЕДУПРЕДИТЕЛЬНЫЕ И АВАРИЙНЫЕ УСТАВКИ</div>
    {point ? <>
      <p className="hint">Единицы: {point.unit || 'не определены'}. Пустое поле — порог не задан.</p>
      {point.source && <p className="hint">Источник: {point.source}</p>}
      {!keys.some(key=>point[key]!==null)&&<p className="hint">Численные уставки для этой позиции не подтверждены документом. Их можно задать вручную.</p>}
      {keys.map((key,i)=><label key={key}>{labels[i]}<input type="number" step="any" disabled={!editable} value={draft[key]??''} onChange={e=>setDraft(old=>({...old,[key]:e.target.value}))}/></label>)}
      {editable&&<button className="btn" onClick={()=>void save()}>Сохранить уставки</button>}
    </>:<p className="hint">Для загрузки уставок сохраните прибор в схеме.</p>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
