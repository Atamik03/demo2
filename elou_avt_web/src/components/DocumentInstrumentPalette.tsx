import { useState } from 'react';
import catalog from '../arm/documentInstruments.json';

export default function DocumentInstrumentPalette({placedTags=[]}:{placedTags?:string[]}) {
  const [showAll,setShowAll]=useState(false);
  const normalized=(tag:string)=>tag.toUpperCase().replace(/Р/g,'P').replace(/Т/g,'T').replace(/А/g,'A').replace(/К/g,'K').replace(/В/g,'B').replace(/\s/g,'');
  const placed=new Set(placedTags.map(normalized));
  const [query, setQuery] = useState('');
  const filtered = catalog.filter((item) => `${item.tag} ${item.context}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return (
    <details className="document-instruments">
      <summary>КИП из описания процесса ({catalog.length})</summary>
      <input aria-label="Поиск КИП по документу" placeholder="Позиция или аппарат…" value={query} onChange={(e) => setQuery(e.target.value)} />
      <p className="hint">Перетащите позицию на нужную трубу. Место установки сверяйте с описанием процесса.</p>
      <p className="hint">Размещено: {catalog.filter(item=>placed.has(normalized(item.tag))).length} из {catalog.length}</p>
      {(showAll?filtered:filtered.slice(0, 40)).map((item) => <div className="palette-item" key={item.tag} draggable title={`Стр. ${item.pages}: ${item.context}`}
        onDragStart={(event) => {
          event.dataTransfer.setData('application/elou-type', 'field_instrument');
          event.dataTransfer.setData('application/elou-instrument-tag', item.tag);
          event.dataTransfer.effectAllowed = 'move';
        }}>{placed.has(normalized(item.tag))?'✓ ':''}{item.tag}<small>стр. {item.pages}</small></div>)}
      {filtered.length > 40 && <button className="btn" onClick={()=>setShowAll(!showAll)}>{showAll?'Свернуть':`Показать все ${filtered.length} позиций`}</button>}
      {filtered.length === 0 && <p className="hint">Позиции не найдены.</p>}
    </details>
  );
}
