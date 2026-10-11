import { useEffect, useRef, useState } from 'react';

export default function TechnicalReference({ onClose }: { onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const dialog = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (event.key !== 'Tab') return;
      const items = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]');
      if (!items?.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, []);
  const scroll = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  return (
    <section ref={dialog} className="technical-reference" role="dialog" aria-modal="true" aria-label="Исходная технологическая схема">
      <header>
        <div><strong>Исходная технологическая схема</strong><small>01_Схема КТС.pdf · оригинальный чертёж из папки «ЭЛОУ-АВТ»</small></div>
        <button className="btn" onClick={() => setZoom((value) => Math.max(1, value - 0.5))} disabled={zoom <= 1} aria-label="Уменьшить чертёж">−</button>
        <span>{Math.round(zoom * 100)} %</span>
        <button className="btn" onClick={() => setZoom((value) => Math.min(8, value + 0.5))} disabled={zoom >= 8} aria-label="Увеличить чертёж">+</button>
        <button className="btn" onClick={() => setZoom(1)}>Вписать</button>
        <a className="btn" href="/references/avt4-kts.pdf" target="_blank" rel="noreferrer">Открыть PDF</a>
        <a className="btn" href="/references/instruments.csv" download>Перечень КИП</a>
        <button className="btn" autoFocus onClick={onClose}>Вернуться к мнемосхеме</button>
      </header>
      <p>Эталон для сверки оборудования и трубопроводов. Полная расстановка и обозначения КИП на этом листе не приведены.</p>
      <div className="technical-reference-scroll" ref={scroll}
        onPointerDown={(event) => {
          if (event.button !== 0 || !scroll.current) return;
          drag.current = { x: event.clientX, y: event.clientY, left: scroll.current.scrollLeft, top: scroll.current.scrollTop };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drag.current || !scroll.current) return;
          scroll.current.scrollLeft = drag.current.left + drag.current.x - event.clientX;
          scroll.current.scrollTop = drag.current.top + drag.current.y - event.clientY;
        }}
        onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <img src="/references/avt4-kts.svg" alt="Оригинальная технологическая схема АВТ-4" draggable={false}
          style={{ width: `${zoom * 100}%`, maxWidth: 'none' }} />
      </div>
    </section>
  );
}
