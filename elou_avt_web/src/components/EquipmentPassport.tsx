import { useEffect, useState } from 'react';
import { api } from '../api';
import type { EquipmentSpec } from '../types';

const FIELDS: Record<string,string> = {
  flow_m3_h: 'Производительность, м³/ч', discharge_pressure_kgf_cm2: 'Давление на выкиде, кгс/см²',
  motor_power_kw: 'Мощность двигателя, кВт', speed_rpm: 'Частота вращения, об/мин',
  area_m2: 'Поверхность теплообмена, м²', diameter_mm: 'Диаметр, мм', length_mm: 'Длина, мм',
  design_temperature_c: 'Расчётная температура тр/мтр, °C', design_pressure_kgf_cm2: 'Расчётное давление тр/мтр, кгс/см²',
};
export default function EquipmentPassport({nodeId}:{nodeId:string}) {
  const [passport,setPassport]=useState<EquipmentSpec['passport']>();
  useEffect(()=>{
    let current=true; setPassport(undefined);
    api.getEquipmentSpec(nodeId).then(s=>{if(current)setPassport(s.passport);}).catch(()=>{});
    return ()=>{current=false;};
  },[nodeId]);
  if(!passport?.records.length) return null;
  return <details className="equipment-passport">
    <summary>Паспорт по документам ({passport.records.length})</summary>
    {!passport.complete && <p>Для части обозначений документация не сопоставлена.</p>}
    {passport.records.map(record=><section key={String(record.tag)}>
      <strong>{record.tag}</strong>
      {Object.entries(FIELDS).filter(([key])=>record[key]!=null).map(([key,label])=><div className="param-row" key={key}>
        <span>{label}</span><span>{record[key]}</span>
      </div>)}
      <a href={`/references/${record.type==='pump'?'pumps':'exchangers'}.pdf#page=${record.page}`} target="_blank" rel="noreferrer">{record.source}, стр. {record.page}</a>
    </section>)}
  </details>;
}
