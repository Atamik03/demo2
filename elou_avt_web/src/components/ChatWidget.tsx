import { useCallback, useEffect, useRef, useState } from 'react';
import { api, connectChat } from '../api';
import type { ChatMessage, FieldErrorsResponse } from '../types';

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function ChatWidget({ title = 'Чат операторов' }: { title?: string }) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);

  // Resolve the active practice session (shared between both windows).
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res: FieldErrorsResponse = await api.lmsFieldErrors();
        if (!alive) return;
        const sid = res.active ? res.session_id : null;
        if (sid !== sessionId) {
          setSessionId(sid);
          setSessionTitle(res.title || '');
          if (sid) {
            const history = await api.chatHistory(sid).catch(() => [] as ChatMessage[]);
            if (alive) setMessages(history);
          } else {
            setMessages([]);
          }
        }
      } catch {
        /* server may be unreachable */
      }
    };
    poll();
    const t = window.setInterval(poll, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [sessionId]);

  useEffect(() => {
    return connectChat((m) => {
      setMessages((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m]));
      if (!open) setUnread((u) => u + 1);
    });
  }, [open]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  const send = useCallback(async () => {
    const t = text.trim();
    if (!t || !sessionId) return;
    setText('');
    try {
      const msg = await api.chatSend({ session_id: sessionId, kind: 'text', text: t });
      setMessages((prev) => (prev.some((x) => x.id === msg.id) ? prev : [...prev, msg]));
    } catch {
      /* ignore send errors */
    }
  }, [text, sessionId]);

  const toggle = useCallback(() => {
    setOpen((o) => !o);
    setUnread(0);
  }, []);

  return (
    <div className={`chat-widget${open ? ' open' : ''}`}>
      {open ? (
        <div className="chat-panel">
          <div className="chat-head">
            <div className="chat-head-title">{title}</div>
            <div className="chat-head-sub">
              {sessionId ? `Сессия ${sessionId.slice(0, 8)}${sessionTitle ? ' · ' + sessionTitle : ''}` : 'Нет активной практики'}
            </div>
            <button className="chat-close" onClick={toggle} title="Свернуть">
              –
            </button>
          </div>
          <div className="chat-list" ref={listRef}>
            {messages.length === 0 && (
              <div className="chat-empty">
                {sessionId ? 'Сообщений пока нет. Полевой оператор может отправить сюда ошибку с 3D-схемы.' : 'Запустите практику в окне консольного оператора — чат откроется автоматически.'}
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg${m.kind === 'field_error' || m.kind === 'equipment_check' ? ' field-error' : ''}`}>
                <div className="chat-msg-head">
                  <span className="chat-msg-author">{m.author || 'система'}</span>
                  <span className="chat-msg-time">{fmtTime(m.created_at)}</span>
                </div>
                {(m.kind === 'field_error' || m.kind === 'equipment_check') && m.object_id && (
                  <span className="chat-msg-tag">{m.object_id}</span>
                )}
                <div className="chat-msg-text">{m.text}</div>
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              className="chat-input"
              value={text}
              placeholder={sessionId ? 'Сообщение…' : 'Нет активной сессии'}
              disabled={!sessionId}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') send();
              }}
            />
            <button className="chat-send" onClick={send} disabled={!sessionId || !text.trim()}>
              Отправить
            </button>
          </div>
        </div>
      ) : (
        <button className="chat-toggle" onClick={toggle}>
          Чат{unread > 0 ? <span className="chat-badge">{unread}</span> : null}
        </button>
      )}
    </div>
  );
}
